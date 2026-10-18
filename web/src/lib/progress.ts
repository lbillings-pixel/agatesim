// Words for a progress bar: how far a long action has got, and roughly how
// long it has left (src/agatesim/progress.py estimates both).

export interface Progress {
  /** Share done, 0..1, or null when the work can't say (the bar then just moves). */
  fraction: number | null;
  /** What the work is doing now, e.g. "Branched inclusions". */
  label: string;
  elapsed_s: number;
  /** Seconds left at the recent rate, or null until there is enough to go by. */
  eta_s: number | null;
  done: boolean;
  cancelled: boolean;
}

/** Wait this long before showing a bar, so quick actions don't flicker one. */
export const SHOW_AFTER_S = 1;

/** "45 s", "3 min 20 s", "1 h 5 min": a duration to read at a glance. */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  if (s < 3600) {
    const m = Math.floor(s / 60);
    const rest = s % 60;
    return rest ? `${m} min ${rest} s` : `${m} min`;
  }
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return m ? `${h} h ${m} min` : `${h} h`;
}

/** The time left, rounded so the estimate doesn't flicker: to 5 s under two
 * minutes, to the minute beyond. */
export function formatTimeLeft(seconds: number): string {
  if (seconds < 5) return "a few seconds left";
  const rounded = seconds < 120 ? Math.ceil(seconds / 5) * 5 : Math.ceil(seconds / 60) * 60;
  return `about ${formatDuration(rounded)} left`;
}

/** One line under the bar: "42% · about 1 min 10 s left · 35 s so far". Work
 * that can't measure itself (a search that stops at the first good draw) shows
 * only the time so far. */
export function describeProgress(p: Progress): string {
  const parts: string[] = [];
  if (p.fraction !== null) {
    parts.push(`${Math.floor(p.fraction * 100)}%`);
    if (p.fraction < 1) parts.push(p.eta_s === null ? "estimating the time left" : formatTimeLeft(p.eta_s));
  }
  parts.push(`${formatDuration(p.elapsed_s)} so far`);
  return parts.join(" · ");
}

/** A fresh id for one long action, sent with its requests (X-Progress). */
export function newTaskId(): string {
  return `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}
