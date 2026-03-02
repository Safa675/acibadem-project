import InfoTooltip from "@/components/ui/InfoTooltip";

interface Props {
  text: string;
  metricId: string;
  className?: string;
}

export default function MetricLabel({ text, metricId, className }: Props) {
  return (
    <span className={`metric-label-with-info ${className ?? ""}`.trim()}>
      <span>{text}</span>
      <InfoTooltip metricId={metricId} />
    </span>
  );
}
