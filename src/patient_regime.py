"""
patient_regime.py
PatientStateClassifier — 4-state clinical regime classifier.

Maps a patient health score time-series to 4 clinical states:
  STABLE       — improving trend, low volatility (labs stabilizing, good direction)
  RECOVERING   — improving trend, high volatility (good direction, but unstable)
  DETERIORATING — declining trend, low variability (slow steady decline)
  CRITICAL     — declining trend, high volatility (alarm state)

Validation: Critical state episodes should correlate with:
  - More prescriptions in recete.ods around that date
  - Higher TOPLAM_GELIS_SAYISI for those patients
  - Longer ILK_TANI_SON_TANI_GUN_FARKI outcome
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence
import numpy as np
import pandas as pd


class PatientState(str, Enum):
    STABLE = "Stable"
    RECOVERING = "Recovering"
    DETERIORATING = "Deteriorating"
    CRITICAL = "Critical"


# Traffic-light colors for visualization
STATE_COLORS: dict[PatientState, str] = {
    PatientState.STABLE: "#2ECC71",       # green
    PatientState.RECOVERING: "#F39C12",    # amber
    PatientState.DETERIORATING: "#E67E22", # orange
    PatientState.CRITICAL: "#E74C3C",      # red
}

STATE_EMOJI: dict[PatientState, str] = {
    PatientState.STABLE: "🟢",
    PatientState.RECOVERING: "🟡",
    PatientState.DETERIORATING: "🟠",
    PatientState.CRITICAL: "🔴",
}

# Clinical equivalence (for the video narrative)
STATE_CLINICAL_DESC: dict[PatientState, str] = {
    PatientState.STABLE: "Labs stable, trend improving, low variability",
    PatientState.RECOVERING: "Trend improving but labs still volatile — monitor closely",
    PatientState.DETERIORATING: "Gradual decline — intervention may be needed soon",
    PatientState.CRITICAL: "Rapid or high-variability decline — immediate attention required",
}


@dataclass
class RegimeConfig:
    """
    Parameters for regime detection.
    Tuned for lab/vital time-series (1–7 day intervals) rather than daily prices.
    """
    # Trend window: number of observations for moving average
    ma_window: int = 3        # 3 draws ≈ 1 week of outpatient labs
    # Volatility window: observations for rolling std
    vol_window: int = 4       # 4 draws
    # Lookback for vol percentile ranking (all observations for this patient)
    vol_lookback: int = 20    # full available history
    # Percentile threshold above which volatility is "high"
    vol_high_percentile: float = 60.0  # lower than financial (less data)
    # Minimum observations required before classifying
    min_observations: int = 2


@dataclass
class RegimePoint:
    date: pd.Timestamp
    health_score: float
    ma: float | None
    rolling_vol: float | None
    vol_percentile: float | None
    trend_positive: bool | None  # health_score > MA
    vol_high: bool | None
    state: PatientState | None


@dataclass
class PatientRegimeResult:
    patient_id: int
    timeline: list[RegimePoint] = field(default_factory=list)

    @property
    def states(self) -> list[PatientState | None]:
        return [p.state for p in self.timeline]

    @property
    def dates(self) -> list[pd.Timestamp]:
        return [p.date for p in self.timeline]

    @property
    def scores(self) -> list[float]:
        return [p.health_score for p in self.timeline]

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([
            {
                "date": p.date,
                "health_score": p.health_score,
                "ma": p.ma,
                "rolling_vol": p.rolling_vol,
                "vol_percentile": p.vol_percentile,
                "trend_positive": p.trend_positive,
                "vol_high": p.vol_high,
                "state": p.state.value if p.state else None,
                "state_color": STATE_COLORS.get(p.state, "#808080") if p.state else "#808080",
            }
            for p in self.timeline
        ])

    def last_known_state(self) -> PatientState | None:
        for point in reversed(self.timeline):
            if point.state is not None:
                return point.state
        return None

    def state_durations(self) -> dict[str, int]:
        """Count number of observations in each state."""
        counts: dict[str, int] = {s.value: 0 for s in PatientState}
        for point in self.timeline:
            if point.state:
                counts[point.state.value] += 1
        return counts

    def transition_events(self, include_critical_only: bool = False) -> list[dict]:
        """Return events where state changed (useful for correlating with prescriptions)."""
        events = []
        prev = None
        for point in self.timeline:
            if point.state != prev and prev is not None:
                if not include_critical_only or point.state == PatientState.CRITICAL:
                    events.append({
                        "date": point.date,
                        "from_state": prev.value if prev else None,
                        "to_state": point.state.value if point.state else None,
                    })
            prev = point.state
        return events


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------

def _compute_state(trend_positive: bool, vol_high: bool) -> PatientState:
    """
    2×2 grid mapping (trend direction, volatility level) → clinical state.
    This is the core novelty: same as market regime but for patient health.
    """
    if trend_positive and not vol_high:
        return PatientState.STABLE
    elif trend_positive and vol_high:
        return PatientState.RECOVERING
    elif not trend_positive and not vol_high:
        return PatientState.DETERIORATING
    else:  # not trend_positive and vol_high
        return PatientState.CRITICAL


class PatientStateClassifier:
    """
    Classify a patient's health score series into the four-state regime model.

    Compatible with both:
      - List of SeriesPoint objects
      - List of HealthSnapshot objects
      - Direct pandas Series / DataFrame
    """

    def __init__(self, config: RegimeConfig | None = None):
        self.config = config or RegimeConfig()

    def classify_series(
        self,
        patient_id: int,
        scores: Sequence[float],
        dates: Sequence[pd.Timestamp],
    ) -> PatientRegimeResult:
        """
        Classify a health score time-series.

        Args:
            patient_id: patient identifier
            scores: health score values (higher = healthier)
            dates: corresponding timestamps

        Returns:
            PatientRegimeResult with full regime timeline
        """
        cfg = self.config
        scores_arr = np.array(scores, dtype=float)
        dates_list = list(dates)
        n = len(scores_arr)

        result = PatientRegimeResult(patient_id=patient_id)

        # Need at least min_observations to classify
        if n < cfg.min_observations:
            for i in range(n):
                result.timeline.append(RegimePoint(
                    date=dates_list[i],
                    health_score=float(scores_arr[i]),
                    ma=None, rolling_vol=None, vol_percentile=None,
                    trend_positive=None, vol_high=None, state=None,
                ))
            return result

        # Rolling calculations
        ma_series = _rolling_mean(scores_arr, cfg.ma_window)
        vol_series = _rolling_std(scores_arr, cfg.vol_window)

        # Compute vol percentile rank using full available history up to each point
        vol_percentiles = _rolling_percentile_rank(vol_series, cfg.vol_lookback)

        for i in range(n):
            ma = ma_series[i]
            vol = vol_series[i]
            vol_pct = vol_percentiles[i]

            if ma is None or vol is None or vol_pct is None:
                state = None
                trend_positive = None
                vol_high = None
            else:
                trend_positive = float(scores_arr[i]) >= float(ma)
                vol_high = float(vol_pct) >= cfg.vol_high_percentile
                state = _compute_state(trend_positive, vol_high)

            result.timeline.append(RegimePoint(
                date=dates_list[i],
                health_score=float(scores_arr[i]),
                ma=float(ma) if ma is not None else None,
                rolling_vol=float(vol) if vol is not None else None,
                vol_percentile=float(vol_pct) if vol_pct is not None else None,
                trend_positive=trend_positive,
                vol_high=vol_high,
                state=state,
            ))

        return result

    def classify_snapshots(self, patient_id: int, snapshots) -> PatientRegimeResult:
        """Classify from HealthIndexBuilder.build_patient_series() output."""
        if not snapshots:
            return PatientRegimeResult(patient_id=patient_id)
        scores = [s.health_score for s in snapshots]
        dates = [s.date for s in snapshots]
        return self.classify_series(patient_id, scores, dates)

    def classify_dataframe(self, patient_id: int, df: pd.DataFrame) -> PatientRegimeResult:
        """Classify from a DataFrame with 'date' and 'health_score' columns."""
        df = df.sort_values("date")
        return self.classify_series(patient_id, df["health_score"].tolist(), df["date"].tolist())


# ---------------------------------------------------------------------------
# Cohort-level analysis
# ---------------------------------------------------------------------------

def classify_all_patients(
    snapshots_by_patient: dict[int, list],
    config: RegimeConfig | None = None,
) -> dict[int, PatientRegimeResult]:
    """Classify all patients. Input: {patient_id: [HealthSnapshot, ...]}"""
    classifier = PatientStateClassifier(config)
    return {
        pid: classifier.classify_snapshots(pid, snaps)
        for pid, snaps in snapshots_by_patient.items()
    }


def compute_cohort_stats(results: dict[int, PatientRegimeResult]) -> pd.DataFrame:
    """Summary statistics across all patients."""
    rows = []
    for pid, result in results.items():
        durations = result.state_durations()
        last = result.last_known_state()
        rows.append({
            "patient_id": pid,
            "n_observations": len(result.timeline),
            "last_state": last.value if last else None,
            "n_stable": durations.get("Stable", 0),
            "n_recovering": durations.get("Recovering", 0),
            "n_deteriorating": durations.get("Deteriorating", 0),
            "n_critical": durations.get("Critical", 0),
            "pct_critical": durations.get("Critical", 0) / max(len(result.timeline), 1),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Math utilities
# ---------------------------------------------------------------------------

def _rolling_mean(arr: np.ndarray, window: int) -> list[float | None]:
    n = len(arr)
    result: list[float | None] = []
    for i in range(n):
        if i + 1 < window:
            result.append(None)
        else:
            result.append(float(np.mean(arr[max(0, i - window + 1): i + 1])))
    return result


def _rolling_std(arr: np.ndarray, window: int) -> list[float | None]:
    n = len(arr)
    result: list[float | None] = []
    for i in range(n):
        if i + 1 < 3:  # need at least 3 points for meaningful std (was 2)
            result.append(None)
        else:
            slice_ = arr[max(0, i - window + 1): i + 1]
            result.append(float(np.std(slice_, ddof=1)) if len(slice_) >= 3 else None)
    return result


def _rolling_percentile_rank(vols: list[float | None], lookback: int) -> list[float | None]:
    """Compute the percentile rank of each vol value within its lookback window."""
    result: list[float | None] = []
    clean_vols = []
    for v in vols:
        if v is None:
            result.append(None)
            clean_vols.append(None)
            continue
        clean_vols.append(v)
        historical = [x for x in clean_vols[-lookback:] if x is not None]
        if len(historical) < 3:  # was < 2; need ≥3 for non-degenerate ranking
            result.append(50.0)  # default to median — safe neutral
            continue
        rank = float(np.sum(np.array(historical) <= v)) / len(historical) * 100.0
        result.append(rank)
    return result
