import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(dateStr: string): string {
  if (!dateStr || dateStr === "—") return "—";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

export function nlpColor(score: number): string {
  if (score > 0.05) return "#2ECC71";
  if (score < -0.05) return "#E74C3C";
  return "#7f8c8d";
}

export function eciColor(value: number): string {
  if (value >= 66) return "#E74C3C";
  if (value >= 33) return "#F39C12";
  return "#2ECC71";
}
