import { useEffect, useId } from "react";
import type { CSSProperties } from "react";

type RevealVariant = "fade" | "scale";

type RevealOptions = {
  baseDelayMs?: number;
  stepMs?: number;
  threshold?: number;
  rootMargin?: string;
};

type RevealProps = {
  staggerClass: string;
  staggerStyle: CSSProperties;
  staggerAttrs: {
    "data-stagger-group": string;
    "data-stagger-index": number;
    "data-stagger-variant": RevealVariant;
  };
};

export default function useStaggeredReveal(
  count: number,
  {
    baseDelayMs = 0,
    stepMs = 100,
    threshold = 0.2,
    rootMargin = "0px",
  }: RevealOptions = {},
) {
  const id = useId().replace(/:/g, "_");

  useEffect(() => {
    const selector = `[data-stagger-group="${id}"]`;
    const nodes = Array.from(document.querySelectorAll<HTMLElement>(selector)).slice(0, count);

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const el = entry.target as HTMLElement;
          const variant = el.dataset.staggerVariant === "scale" ? "scale" : "fade";
          el.classList.remove(variant === "scale" ? "stagger-scale-hidden" : "stagger-fade-hidden");
          el.classList.add(variant === "scale" ? "stagger-scale-visible" : "stagger-fade-visible");
          observer.unobserve(el);
        });
      },
      { threshold, rootMargin },
    );

    nodes.forEach((node) => observer.observe(node));

    return () => observer.disconnect();
  }, [id, count, threshold, rootMargin]);

  const getRevealProps = (index: number, variant: RevealVariant = "fade"): RevealProps => ({
    staggerClass: `stagger-item ${variant === "scale" ? "stagger-scale-hidden" : "stagger-fade-hidden"}`,
    staggerStyle: { animationDelay: `${baseDelayMs + index * stepMs}ms` },
    staggerAttrs: {
      "data-stagger-group": id,
      "data-stagger-index": index,
      "data-stagger-variant": variant,
    },
  });

  return {
    getRevealProps,
  };
}
