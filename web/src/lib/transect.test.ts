import { describe, expect, it } from "vitest";

import { addMark, distanceTo, markNear, project, removeMark, tick, type Transect } from "./transect";

const line: Transect = { start: [0, 0], end: [100, 0], boundaries: [] };

describe("transects", () => {
  it("projects clicks onto the line and clamps to its ends", () => {
    expect(project(line, [25, 7])).toBeCloseTo(0.25);
    expect(project(line, [-10, 3])).toBe(0);
    expect(project(line, [130, -3])).toBe(1);
    expect(distanceTo(line, [25, 7])).toBeCloseTo(7);
  });

  it("adds marks in order, however close, and removes the nearest on request", () => {
    let l = addMark(line, 0.5, 0.5);
    l = addMark(l, 0.2, 0.5);
    l = addMark(l, 0.51, 0.5); // 1 px from a mark: a separate boundary
    l = addMark(l, 0.512, 0.5); // 0.2 px: the same click again
    expect(l.boundaries).toEqual([0.2, 0.5, 0.51]);
    l = removeMark(l, 0.508, 4);
    expect(l.boundaries).toEqual([0.2, 0.5]);
    expect(removeMark(l, 0.3, 4)).toBe(l);
    expect(markNear(l, 0.3, 4)).toBe(-1);
  });

  it("draws ticks across the line", () => {
    const [a, b] = tick(line, 0.5, 5);
    expect(a[0]).toBeCloseTo(50);
    expect(b[0]).toBeCloseTo(50);
    expect(Math.abs(a[1] - b[1])).toBeCloseTo(10);
  });
});
