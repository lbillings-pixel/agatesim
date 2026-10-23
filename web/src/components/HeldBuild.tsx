import { type CostEstimate, cautionText } from "../lib/caution";

/** A heavy preview the app didn't start by itself: its estimate and a button to
 * start it anyway. Light previews still update on their own (ADR 0062). */
export function HeldBuild({ what, estimate, onBuild }: { what: string; estimate: CostEstimate; onBuild: () => void }) {
  const why = estimate.reasons.length ? ` (${estimate.reasons.join("; ")})` : "";
  return (
    <div className="held-build" role="status">
      <p>
        <strong>Paused before building {what}.</strong> {cautionText(estimate)}
        {why}, estimated roughly.
      </p>
      <button type="button" className="primary" onClick={onBuild}>
        Build it
      </button>
    </div>
  );
}
