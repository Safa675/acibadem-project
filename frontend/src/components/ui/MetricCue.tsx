import type { MetricCue as MetricCueType } from "@/lib/interpretation";

interface Props {
  cue: MetricCueType;
  showDetail?: boolean;
}

export default function MetricCue({ cue, showDetail = true }: Props) {
  const tonePrefix =
    cue.tone === "good"
      ? "OK"
      : cue.tone === "warn"
        ? "WARN"
        : cue.tone === "bad"
          ? "ALERT"
          : "INFO";

  return (
    <div className="metric-cue-wrap">
      <span className={`metric-cue metric-cue-${cue.tone}`}>
        <span className={`metric-cue-marker metric-cue-marker-${cue.tone}`} aria-hidden="true" />
        <span className="metric-cue-prefix">{tonePrefix}</span>
        <span>{cue.label}</span>
      </span>
      {showDetail && cue.detail && <span className="metric-cue-detail">{cue.detail}</span>}
    </div>
  );
}
