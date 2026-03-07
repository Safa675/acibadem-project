"""
visualizer.py
Publication-quality charts for the ACUHIT hackathon video demo.

All charts use matplotlib with a dark clinical theme.
Three main chart types:
  1. Regime Timeline — colored segments per patient state (for video hook)
  2. Monte Carlo Fan Chart — HealthVaR probability cone
  3. NLP Heatmap — keyword scores across visits
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from typing import Sequence

from .patient_regime import PatientRegimeResult, PatientState, STATE_COLORS, STATE_EMOJI
from .health_var import HealthVaRResult
from .health_index import SeriesPoint

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------

DARK_BG = "#0F1117"
PANEL_BG = "#1A1D27"
TEXT_COLOR = "#E8E8E8"
GRID_COLOR = "#2A2D3A"
ACCENT = "#4FC3F7"  # light blue


def _setup_dark_theme():
    plt.rcParams.update(
        {
            "figure.facecolor": DARK_BG,
            "axes.facecolor": PANEL_BG,
            "axes.edgecolor": GRID_COLOR,
            "axes.labelcolor": TEXT_COLOR,
            "xtick.color": TEXT_COLOR,
            "ytick.color": TEXT_COLOR,
            "text.color": TEXT_COLOR,
            "grid.color": GRID_COLOR,
            "grid.alpha": 0.4,
            "font.family": "DejaVu Sans",
            "font.size": 11,
        }
    )


# ---------------------------------------------------------------------------
# 1. Regime Timeline Chart
# ---------------------------------------------------------------------------


def plot_regime_timeline(
    result: PatientRegimeResult,
    patient_label: str = None,
    prescription_dates: list[pd.Timestamp] | None = None,
    ax: plt.Axes | None = None,
    save_path: str | None = None,
) -> plt.Figure:
    """
    Plot health score time-series with regime state background coloring.
    Each segment is shaded in the state color behind the score line.
    """
    _setup_dark_theme()
    fig, axis = (None, ax) if ax else plt.subplots(figsize=(14, 5))
    if fig is None:
        fig = axis.get_figure()

    df = result.to_dataframe()
    if df.empty:
        return fig

    dates = df["date"].tolist()
    scores = df["health_score"].tolist()
    states = df["state"].tolist()
    colors = df["state_color"].tolist()

    axis.set_facecolor(PANEL_BG)
    fig.patch.set_facecolor(DARK_BG)

    # Draw regime background segments
    for i in range(len(dates)):
        x0 = dates[i]
        x1 = dates[i + 1] if i + 1 < len(dates) else dates[i] + pd.Timedelta(days=3)
        c = colors[i] if colors[i] != "#808080" else PANEL_BG
        axis.axvspan(x0, x1, alpha=0.25, color=c, linewidth=0)

    # Health score line
    axis.plot(
        dates, scores, color=ACCENT, linewidth=2.5, zorder=5, label="Health Score"
    )
    axis.scatter(dates, scores, color=ACCENT, s=60, zorder=6)

    # MA line if available
    if "ma" in df.columns and df["ma"].notna().any():
        axis.plot(
            dates,
            df["ma"].tolist(),
            color="#AAAAAA",
            linewidth=1.3,
            linestyle="--",
            zorder=4,
            label="Moving Average",
            alpha=0.7,
        )

    # Mark prescription events
    if prescription_dates:
        for presc_date in prescription_dates:
            axis.axvline(
                presc_date,
                color="#FF6B6B",
                linewidth=1.5,
                linestyle=":",
                alpha=0.8,
                zorder=7,
            )
        axis.axvline(
            prescription_dates[0],
            color="#FF6B6B",
            linewidth=1.5,
            linestyle=":",
            alpha=0.8,
            label="Prescription Event",
        )

    axis.set_ylim(0, 105)
    axis.set_ylabel("Health Score", fontsize=12)
    axis.set_xlabel("Date", fontsize=12)
    label = patient_label or f"Patient {result.patient_id}"
    axis.set_title(f"PatientRegime™ — {label}", fontsize=14, fontweight="bold", pad=12)
    axis.grid(True, axis="y", alpha=0.3)
    line_leg = axis.legend(loc="lower left", fontsize=9)
    axis.add_artist(line_leg)

    # State legend
    legend_patches = [
        mpatches.Patch(
            color=STATE_COLORS[PatientState.STABLE], alpha=0.6, label="🟢 Stable"
        ),
        mpatches.Patch(
            color=STATE_COLORS[PatientState.RECOVERING],
            alpha=0.6,
            label="🟡 Recovering",
        ),
        mpatches.Patch(
            color=STATE_COLORS[PatientState.DETERIORATING],
            alpha=0.6,
            label="🟠 Deteriorating",
        ),
        mpatches.Patch(
            color=STATE_COLORS[PatientState.CRITICAL], alpha=0.6, label="🔴 Critical"
        ),
    ]
    axis.legend(
        handles=legend_patches,
        loc="upper right",
        fontsize=9,
        framealpha=0.3,
        facecolor=PANEL_BG,
    )

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK_BG)

    return fig


# ---------------------------------------------------------------------------
# 2. HealthVaR Fan Chart
# ---------------------------------------------------------------------------


def plot_health_var_fan(
    history_series: list[SeriesPoint],
    var_result: HealthVaRResult,
    patient_label: str = None,
    ax: plt.Axes | None = None,
    save_path: str | None = None,
) -> plt.Figure:
    """
    Plot Monte Carlo fan chart — historical health scores + probability cone.
    """
    _setup_dark_theme()
    fig, axis = (None, ax) if ax else plt.subplots(figsize=(12, 5))
    if fig is None:
        fig = axis.get_figure()

    # Historical
    hist_dates = [pd.Timestamp(sp.date) for sp in history_series]
    hist_scores = [sp.value for sp in history_series]

    last_date = hist_dates[-1]
    td = pd.Timedelta(days=3)  # approximate lab draw interval

    # Future dates to plot
    future_dates = [last_date + td * i for i in range(var_result.horizon_draws + 1)]
    futures = [var_result.current_score, *[var_result.p50] * var_result.horizon_draws]

    p05_vals = [var_result.current_score, *[var_result.p05] * var_result.horizon_draws]
    p25_vals = [var_result.current_score, *[var_result.p25] * var_result.horizon_draws]
    p75_vals = [var_result.current_score, *[var_result.p75] * var_result.horizon_draws]
    p95_vals = [var_result.current_score, *[var_result.p95] * var_result.horizon_draws]

    # History line
    axis.plot(
        hist_dates,
        hist_scores,
        color=ACCENT,
        linewidth=2.5,
        label="Historical Health Score",
        zorder=5,
    )
    axis.scatter(hist_dates, hist_scores, color=ACCENT, s=50, zorder=6)

    # Separator
    axis.axvline(last_date, color="#AAAAAA", linewidth=1, linestyle="--", alpha=0.6)

    # Fan chart
    axis.fill_between(
        future_dates,
        p05_vals,
        p95_vals,
        color="#4FC3F7",
        alpha=0.12,
        label="5th–95th percentile",
    )
    axis.fill_between(
        future_dates,
        p25_vals,
        p75_vals,
        color="#4FC3F7",
        alpha=0.25,
        label="25th–75th percentile",
    )
    axis.plot(
        future_dates,
        futures,
        color="#4FC3F7",
        linewidth=2,
        linestyle="--",
        label="Median forecast",
    )
    axis.plot(
        future_dates,
        p05_vals,
        color=STATE_COLORS[PatientState.CRITICAL],
        linewidth=1.5,
        linestyle=":",
        label=f"Health VaR (95%) = {var_result.p05:.1f}",
    )

    # VaR badge
    tier_colors = {
        "GREEN": "#2ECC71",
        "YELLOW": "#F39C12",
        "ORANGE": "#E67E22",
        "RED": "#E74C3C",
    }
    badge_color = tier_colors.get(var_result.risk_tier, "#AAAAAA")
    axis.text(
        0.98,
        0.97,
        f"Health VaR: {var_result.var_pct:+.1f}%\nTier: {var_result.risk_tier}",
        transform=axis.transAxes,
        ha="right",
        va="top",
        fontsize=10,
        color=badge_color,
        fontweight="bold",
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor=PANEL_BG,
            edgecolor=badge_color,
            alpha=0.8,
        ),
    )

    axis.set_ylim(0, 105)
    axis.set_ylabel("Health Score", fontsize=12)
    axis.set_xlabel("Date", fontsize=12)
    label = patient_label or f"Patient {var_result.patient_id}"
    axis.set_title(
        f"HealthVaR™ — {label} | Next {var_result.horizon_draws} lab draws",
        fontsize=14,
        fontweight="bold",
        pad=12,
    )
    axis.legend(loc="lower left", fontsize=9, framealpha=0.3, facecolor=PANEL_BG)
    axis.grid(True, alpha=0.3)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK_BG)
    return fig


# ---------------------------------------------------------------------------
# 3. NLP Signal Visualization
# ---------------------------------------------------------------------------


def plot_nlp_heatmap(
    nlp_df: pd.DataFrame,
    patient_id: str,
    ax: plt.Axes | None = None,
    save_path: str | None = None,
) -> plt.Figure:
    """
    Heatmap of NLP scores per visit and text column.
    """
    _setup_dark_theme()
    fig, axis = (None, ax) if ax else plt.subplots(figsize=(10, 4))
    if fig is None:
        fig = axis.get_figure()

    # Filter nlp columns
    nlp_cols = [
        c for c in nlp_df.columns if c.startswith("nlp_") and c != "nlp_composite"
    ]
    if not nlp_cols or nlp_df.empty:
        axis.text(
            0.5,
            0.5,
            "No NLP data available",
            ha="center",
            va="center",
            transform=axis.transAxes,
            color=TEXT_COLOR,
        )
        return fig

    data = nlp_df[nlp_cols].fillna(0).values
    labels = [c.replace("nlp_", "").replace("_", " ") for c in nlp_cols]
    date_labels = [
        d.strftime("%d %b") if hasattr(d, "strftime") else str(d)
        for d in nlp_df["visit_date"]
    ]

    im = axis.imshow(data.T, cmap="RdYlGn", vmin=-0.5, vmax=0.5, aspect="auto")
    plt.colorbar(im, ax=axis, label="NLP Score (+ recovery, − deterioration)")

    axis.set_xticks(range(len(date_labels)))
    axis.set_xticklabels(date_labels, rotation=45, ha="right", fontsize=9)
    axis.set_yticks(range(len(labels)))
    axis.set_yticklabels(labels, fontsize=9)
    axis.set_title(
        f"Clinical NLP Signal — Patient {patient_id}", fontsize=13, fontweight="bold"
    )

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK_BG)
    return fig


# ---------------------------------------------------------------------------
# 4. Side-by-Side Hook Chart (for video opening)
# ---------------------------------------------------------------------------


def plot_stock_vs_patient_hook(
    patient_regime: PatientRegimeResult,
    patient_label: str = "Patient #A",
    stock_dates: list | None = None,
    stock_prices: list[float] | None = None,
    save_path: str | None = None,
) -> plt.Figure:
    """
    Side-by-side chart: stock price with regime (left) vs patient health score (right).
    Creates the visual hook for the video opening.
    If no real stock data is provided, uses a synthetic example.
    """
    _setup_dark_theme()
    fig = plt.figure(figsize=(16, 6), facecolor=DARK_BG)
    gs = GridSpec(1, 2, figure=fig, wspace=0.08)
    ax_stock = fig.add_subplot(gs[0])
    ax_patient = fig.add_subplot(gs[1])

    # --- Stock chart (synthetic if no real data) ---
    if stock_dates is None or stock_prices is None:
        rng = np.random.default_rng(42)
        n = max(len(patient_regime.to_dataframe()), 20)
        returns = rng.normal(0.001, 0.02, n)
        prices = 100.0 * np.cumprod(1 + returns)
        stock_dates = pd.date_range("2024-01-01", periods=n, freq="B")
        stock_prices = prices.tolist()

    ax_stock.set_facecolor(PANEL_BG)
    ax_stock.plot(stock_dates, stock_prices, color=ACCENT, linewidth=2)
    ax_stock.fill_between(
        stock_dates, stock_prices, min(stock_prices) * 0.95, alpha=0.1, color=ACCENT
    )
    ax_stock.set_title(
        "📈 Stock Price — Regime Classification", fontsize=13, fontweight="bold"
    )
    ax_stock.set_ylabel("Price (₺)", fontsize=11)
    ax_stock.grid(True, alpha=0.3)

    # Shade stock with simple above/below MA coloring
    arr = np.array(stock_prices)
    ma = np.convolve(arr, np.ones(5) / 5, mode="same")
    for i in range(1, len(stock_dates)):
        c = "#2ECC71" if arr[i] >= ma[i] else "#E74C3C"
        ax_stock.axvspan(stock_dates[i - 1], stock_dates[i], alpha=0.1, color=c)

    # --- Patient chart ---
    plot_regime_timeline(patient_regime, patient_label=patient_label, ax=ax_patient)
    ax_patient.set_title(
        f"🏥 Patient Health Score — PatientRegime™", fontsize=13, fontweight="bold"
    )

    # Shared annotation
    fig.text(
        0.5,
        0.01,
        '"The math is identical. Same regime engine, same risk framework — different data."',
        ha="center",
        fontsize=12,
        style="italic",
        color="#AABBCC",
    )

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK_BG)
    return fig


# ---------------------------------------------------------------------------
# 5. Cohort risk dashboard
# ---------------------------------------------------------------------------


def plot_cohort_risk_dashboard(
    composites_df: pd.DataFrame,
    save_path: str | None = None,
) -> plt.Figure:
    """
    Bar chart of composite risk scores for all patients, color-coded by rating.
    """
    _setup_dark_theme()
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(PANEL_BG)

    df = composites_df.sort_values("composite_score", ascending=True).copy()
    labels = [f"P{pid}" for pid in df["patient_id"]]
    scores = df["composite_score"].tolist()
    ratings = df["rating"].tolist()

    _color_map = {
        "AAA": "#2ECC71",
        "AA": "#27AE60",
        "A": "#F39C12",
        "BBB": "#E67E22",
        "BB": "#C0392B",
        "B/CCC": "#922B21",
    }
    bar_colors = [_color_map.get(r, "#AAAAAA") for r in ratings]
    bars = ax.barh(labels, scores, color=bar_colors, edgecolor=PANEL_BG, height=0.6)

    # Rating labels
    for bar, rating, score in zip(bars, ratings, scores):
        ax.text(
            score + 0.5,
            bar.get_y() + bar.get_height() / 2,
            rating,
            va="center",
            ha="left",
            fontsize=9,
            fontweight="bold",
            color=_color_map.get(rating, "#AAAAAA"),
        )

    ax.set_xlim(0, 115)
    ax.axvline(80, color="#2ECC71", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.axvline(50, color="#E67E22", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.axvline(20, color="#E74C3C", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.set_xlabel("Composite Health Score [0–100]", fontsize=12)
    ax.set_title(
        "HealthQuant™ — Patient Risk Dashboard", fontsize=14, fontweight="bold"
    )
    ax.grid(True, axis="x", alpha=0.3)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=DARK_BG)
    return fig
