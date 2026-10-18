import { type ReactNode, useEffect, useState } from "react";

import { progress as progressApi } from "../api";
import { describeProgress, type Progress, SHOW_AFTER_S } from "../lib/progress";

const POLL_MS = 500;

/** Follow a task's progress on the server while `task` is set. */
export function useProgress(task: string | null): Progress | null {
  const [state, setState] = useState<{ task: string; progress: Progress | null } | null>(null);
  useEffect(() => {
    if (!task) return;
    let stopped = false;
    const poll = () => {
      progressApi.get(task).then(
        (p) => {
          if (!stopped) setState({ task, progress: p });
        },
        () => undefined,
      );
    };
    poll();
    const timer = window.setInterval(poll, POLL_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [task]);
  return task && state?.task === task ? state.progress : null;
}

interface Props {
  /** The task to follow; nothing shows while it is null. */
  task: string | null;
  /** Shown before the work names its current step. */
  title: string;
  onCancel?: () => void;
  /** Light text, for the dark 3D view. */
  onDark?: boolean;
  /** Shown until the bar appears (and if the work reports nothing). */
  fallback?: ReactNode;
}

/** A progress bar for a long action, shown once it has run for a second: what it
 * is doing, how far it has got, and roughly how long it has left. */
export function TaskProgress({ task, title, onCancel, onDark, fallback = null }: Props) {
  const p = useProgress(task);
  if (!task || !p || p.elapsed_s < SHOW_AFTER_S || p.cancelled) return <>{fallback}</>;
  const label = p.label ? `${title}: ${p.label}` : title;
  const percent = p.fraction === null ? undefined : Math.round(p.fraction * 100);
  return (
    <div className={`task-progress${onDark ? " on-dark" : ""}`} aria-live="polite">
      <div className="task-progress-head small">
        <span>{label}</span>
        {onCancel && (
          <button type="button" className="link-button" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
      <div
        className={`task-progress-track${percent === undefined ? " indeterminate" : ""}`}
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <div className="task-progress-fill" style={percent === undefined ? undefined : { width: `${percent}%` }} />
      </div>
      <div className="task-progress-detail small">{describeProgress(p)}</div>
    </div>
  );
}
