import { describe, expect, it } from "vitest";

import { describeProgress, formatDuration, formatTimeLeft, newTaskId, type Progress } from "./progress";

const progress = (p: Partial<Progress>): Progress => ({
  fraction: null,
  label: "",
  elapsed_s: 0,
  eta_s: null,
  done: false,
  cancelled: false,
  ...p,
});

describe("formatDuration", () => {
  it("reads at a glance", () => {
    expect(formatDuration(0)).toBe("0 s");
    expect(formatDuration(44.6)).toBe("45 s");
    expect(formatDuration(60)).toBe("1 min");
    expect(formatDuration(200)).toBe("3 min 20 s");
    expect(formatDuration(3600)).toBe("1 h");
    expect(formatDuration(3900)).toBe("1 h 5 min");
  });
});

describe("formatTimeLeft", () => {
  it("rounds up, more coarsely for longer waits", () => {
    expect(formatTimeLeft(2)).toBe("a few seconds left");
    expect(formatTimeLeft(41)).toBe("about 45 s left");
    expect(formatTimeLeft(130)).toBe("about 3 min left");
  });
});

describe("describeProgress", () => {
  it("gives the share, the time left and the time so far", () => {
    expect(describeProgress(progress({ fraction: 0.426, eta_s: 68, elapsed_s: 35 }))).toBe(
      "42% · about 1 min 10 s left · 35 s so far",
    );
  });

  it("says when it can't estimate yet, or can't measure at all", () => {
    expect(describeProgress(progress({ fraction: 0.01, elapsed_s: 2 }))).toBe(
      "1% · estimating the time left · 2 s so far",
    );
    expect(describeProgress(progress({ elapsed_s: 12 }))).toBe("12 s so far");
  });

  it("drops the estimate once done", () => {
    expect(describeProgress(progress({ fraction: 1, eta_s: 0, elapsed_s: 90 }))).toBe("100% · 1 min 30 s so far");
  });
});

describe("newTaskId", () => {
  it("makes distinct ids the server accepts", () => {
    const a = newTaskId();
    expect(a).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
    expect(newTaskId()).not.toBe(a);
  });
});
