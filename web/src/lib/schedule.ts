// Evaluate a schedule over formation time, for plotting in the editor.
// Mirrors src/agatesim/schedules.py; tests/fixtures/schedules.json pins both
// implementations to the same numbers (see schedule.test.ts).

import type { Schedule, ScheduleEvent } from "../api";

const EPS = 1e-9;

type Background = Exclude<ScheduleEvent, { type: "pulse" }>;

function startOf(e: Background): number {
  return e.type === "step" ? e.at : e.start;
}

function background(base: number, events: Background[], t: number): number {
  let value = base;
  events.forEach((e, i) => {
    if (e.type === "step") {
      if (t >= e.at) value = e.value;
    } else {
      const v0 = background(base, events.slice(0, i), e.start);
      if (t >= e.end) value = e.value;
      else if (t >= e.start) value = v0 + ((e.value - v0) * (t - e.start)) / (e.end - e.start);
    }
  });
  return value;
}

export function sampleAt(schedule: Schedule, t: number): number {
  const steady = schedule.events
    .filter((e): e is Background => e.type !== "pulse")
    .sort((a, b) => startOf(a) - startOf(b));
  let value = background(schedule.base, steady, t);
  for (const e of schedule.events) {
    if (e.type === "pulse" && t >= e.at && t < e.at + e.width - EPS) value = e.value;
  }
  return value;
}

export function sample(schedule: Schedule, ts: number[]): number[] {
  return ts.map((t) => sampleAt(schedule, t));
}

/** A sensible new event of each type, given the variable's range. */
export function newEvent(type: ScheduleEvent["type"], min: number, max: number): ScheduleEvent {
  const mid = Math.round(((min + max) / 2) * 100) / 100;
  switch (type) {
    case "step":
      return { type, at: 0.5, value: mid };
    case "ramp":
      return { type, start: 0.4, end: 0.6, value: max };
    case "pulse":
      return { type, at: 0.5, width: 0.1, value: max };
  }
}

/** Problems the server would reject, in words, so the editor can show them inline. */
export function problems(event: ScheduleEvent): string[] {
  const out: string[] = [];
  if (event.type === "ramp" && event.end <= event.start) out.push("A ramp must end after it starts.");
  if (event.type === "pulse" && event.width <= 0) out.push("A pulse needs a width above 0.");
  const times = event.type === "ramp" ? [event.start, event.end] : [event.at];
  if (times.some((t) => t < 0 || t > 1)) out.push("Times run from 0 to 1.");
  return out;
}
