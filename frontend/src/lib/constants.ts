export const ACCENT = "#4FC3F7";

export const RATING_COLORS: Record<string, string> = {
  AAA: "#2ECC71",
  AA: "#27AE60",
  A: "#F39C12",
  BBB: "#E67E22",
  BB: "#E74C3C",
  "B/CCC": "#9B59B6",
};

export const RATING_LABELS: Record<string, string> = {
  AAA: "Excellent",
  AA: "Good",
  A: "Moderate",
  BBB: "Below Average",
  BB: "Elevated Risk",
  "B/CCC": "High Risk",
};

export const STATE_COLORS: Record<string, string> = {
  Stable: "#2ECC71",
  Recovering: "#F39C12",
  Deteriorating: "#E67E22",
  Critical: "#E74C3C",
  "Insufficient Data": "#B0BEC5",
};

export const STATE_EMOJI: Record<string, string> = {
  Stable: "\u{1F7E2}",
  Recovering: "\u{1F7E1}",
  Deteriorating: "\u{1F7E0}",
  Critical: "\u{1F534}",
  "Insufficient Data": "\u26AA",
};

export const RISK_TIER_COLORS: Record<string, string> = {
  GREEN: "#2ECC71",
  YELLOW: "#F39C12",
  ORANGE: "#E67E22",
  RED: "#E74C3C",
};

export const RISK_TIER_EMOJI: Record<string, string> = {
  GREEN: "\u{1F7E2}",
  YELLOW: "\u{1F7E1}",
  ORANGE: "\u{1F7E0}",
  RED: "\u{1F534}",
};

export const CSI_TIER_COLORS: Record<string, string> = {
  LOW: "#2ECC71",
  MODERATE: "#F39C12",
  HIGH: "#E67E22",
  CRITICAL: "#E74C3C",
};

export const TAB_BACKGROUNDS = [
  "/images/Gemini_Generated_Image_e7z0jse7z0jse7z0.webp",
  "/images/Gemini_Generated_Image_unlwgkunlwgkunlw.webp",
  "/images/j.webp",
  "/images/Gemini_Generated_Image_o6ulu3o6ulu3o6ul.webp",
];

export const CHART_COLORS = {
  bg: "#111520",
  grid: "rgba(255, 255, 255, 0.07)",
  axis: "rgba(255, 255, 255, 0.12)",
  text: "#B8C5D9",
  accent: ACCENT,
  prescription: "#FF6B6B",
  positive: "#2ECC71",
  negative: "#E74C3C",
  neutral: "#7f8c8d",
  amber: "#F39C12",
  band: "rgba(79, 195, 247, 0.12)",
};

export const BADGE_CLASS: Record<string, string> = {
  AAA: "badge-aaa",
  AA: "badge-aa",
  A: "badge-a",
  BBB: "badge-bbb",
  BB: "badge-bb",
  "B/CCC": "badge-bccc",
};
