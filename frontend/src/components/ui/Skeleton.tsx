import type { HTMLAttributes } from "react";

type SkeletonVariant = "line" | "block" | "card";

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  variant?: SkeletonVariant;
}

export default function Skeleton({
  variant = "block",
  className = "",
  ...rest
}: SkeletonProps) {
  return <div className={`skeleton skeleton-${variant} ${className}`.trim()} {...rest} />;
}
