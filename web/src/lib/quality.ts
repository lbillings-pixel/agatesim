import type { QualityBadge, QualityLevel } from "../api";

export const USE_LABEL: Record<QualityBadge["use"], string> = {
  classification: "Classify",
  calibration: "Calibrate",
  shape: "Band shape",
};

/** The pill class for a level: fit reads as a pass, borderline as a caution. */
export const levelClass = (level: QualityLevel) =>
  level === "fit" ? "pill pass" : level === "borderline" ? "pill borderline" : "pill fail";

/** One line for a badge's tooltip: the scores that fall short, worst first. */
export function badgeSummary(badge: QualityBadge): string {
  const label = USE_LABEL[badge.use];
  const note = badge.note ? `. This ${badge.note}` : "";
  if (badge.reasons.length === 0) return `${label}: fit${note}`;
  const order: QualityLevel[] = ["not fit", "borderline", "fit"];
  const reasons = [...badge.reasons].sort((a, b) => order.indexOf(a.level) - order.indexOf(b.level));
  return `${label}: ${badge.level} (${reasons.map((r) => r.message).join("; ")})${note}`;
}

/** Each piece of advice once, from the badges' reasons, worst first. */
export function adviceFor(badges: QualityBadge[]): string[] {
  const order: QualityLevel[] = ["not fit", "borderline", "fit"];
  const reasons = badges.flatMap((b) => b.reasons).sort((a, b) => order.indexOf(a.level) - order.indexOf(b.level));
  return [...new Set(reasons.map((r) => r.advice))];
}
