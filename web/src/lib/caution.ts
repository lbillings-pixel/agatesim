// Words for the caution badge: an action estimated to take long or use a lot of
// memory (src/agatesim/estimate.py, ADR 0060).

export interface CostEstimate {
  seconds: number;
  memory_gb: number;
  heavy: boolean;
  /** What makes it heavy, e.g. "H2 lattice of 38 million cells, on the GPU". */
  reasons: string[];
}

/** "about 2 min", "about 45 s", "over an hour": rough on purpose. */
export function roughTime(seconds: number): string {
  if (seconds >= 3600) return seconds >= 7200 ? `about ${Math.round(seconds / 3600)} hours` : "over an hour";
  if (seconds >= 90) return `about ${Math.round(seconds / 60)} min`;
  return `about ${Math.max(5, Math.round(seconds / 5) * 5)} s`;
}

/** The badge's text, e.g. "Heavy: about 2 min · about 3 GB"; memory only when it is large. */
export function cautionText(e: CostEstimate, memoryFloorGb = 1): string {
  const parts = [roughTime(e.seconds)];
  if (e.memory_gb >= memoryFloorGb) parts.push(`about ${e.memory_gb >= 10 ? Math.round(e.memory_gb) : e.memory_gb.toFixed(1)} GB of memory`);
  return `Heavy: ${parts.join(" · ")}`;
}
