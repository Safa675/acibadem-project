"use client";

import { useMemo, useState } from "react";
import { getGlossaryEntry } from "@/lib/metricGlossary";

interface Props {
  metricId: string;
  iconOnly?: boolean;
}

export default function InfoTooltip({ metricId, iconOnly = true }: Props) {
  const [open, setOpen] = useState(false);
  const entry = useMemo(() => getGlossaryEntry(metricId), [metricId]);

  if (!entry) return null;

  return (
    <span
      className="info-tooltip"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="info-trigger"
        aria-label={`Metric definition: ${entry.title}`}
        aria-expanded={open}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            setOpen(false);
            (e.currentTarget as HTMLButtonElement).blur();
          }
        }}
      >
        i
      </button>

      {!iconOnly && <span className="info-inline-title">{entry.title}</span>}

      {open && (
        <span className="info-popover" role="tooltip">
          <span className="info-popover-title">{entry.title}</span>
          <span className="info-popover-item">
            <strong>Definition:</strong> {entry.definition}
          </span>
          <span className="info-popover-item">
            <strong>Formula:</strong> {entry.formula}
          </span>
          <span className="info-popover-item">
            <strong>Interpretation:</strong> {entry.interpretation}
          </span>
          {entry.range && (
            <span className="info-popover-item">
              <strong>Range:</strong> {entry.range}
            </span>
          )}
          {entry.source && (
            <span className="info-popover-item">
              <strong>Source:</strong> {entry.source}
            </span>
          )}
        </span>
      )}
    </span>
  );
}
