import { useEffect, useRef, useState } from "react";

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3;
}

export default function useCountUp(
  targetValue: number,
  duration = 1100,
  decimals = 0,
  startWhen = true,
): number {
  const [value, setValue] = useState(0);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    if (!startWhen) return;

    if (!Number.isFinite(targetValue)) {
      return;
    }

    const start = performance.now();
    const safeDuration = Math.max(1, duration);

    const tick = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(1, elapsed / safeDuration);
      const eased = easeOutCubic(progress);
      const raw = targetValue * eased;
      const factor = 10 ** decimals;
      setValue(Math.round(raw * factor) / factor);

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      }
    };

    frameRef.current = requestAnimationFrame(tick);

    return () => {
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
      }
    };
  }, [targetValue, duration, decimals, startWhen]);

  return startWhen ? value : 0;
}
