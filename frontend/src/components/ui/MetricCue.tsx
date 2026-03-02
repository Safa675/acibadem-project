import type { MetricCue as MetricCueType } from "@/lib/interpretation";

interface Props {
  cue: MetricCueType;
  showDetail?: boolean;
}

export default function MetricCue({ cue, showDetail = true }: Props) {
  return (
    <div className="metric-cue-wrap">
      <span className={`metric-cue metric-cue-${cue.tone}`}>{cue.label}</span>
      {showDetail && cue.detail && <span className="metric-cue-detail">{cue.detail}</span>}
    </div>
  );
}
