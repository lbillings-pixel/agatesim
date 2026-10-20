import { type CostEstimate, cautionText } from "../lib/caution";

/** An amber badge beside an action estimated to be heavy (over 30 s or 2 GB);
 * nothing otherwise. Hovering or focusing it lists the reasons. */
export function CautionBadge({ estimate }: { estimate: CostEstimate | null | undefined }) {
  if (!estimate?.heavy) return null;
  const why = estimate.reasons.length ? estimate.reasons.join("; ") : "a large or slow computation";
  return (
    <span className="caution" role="note" tabIndex={0} title={`Estimated before it runs, roughly. Why: ${why}.`}>
      <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
        <path d="M8 1.5 15 14H1z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        <path d="M8 6v3.6M8 11.4v.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      {cautionText(estimate)}
    </span>
  );
}
