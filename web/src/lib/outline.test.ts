import { describe, expect, it } from "vitest";

import fixture from "../../../tests/fixtures/outlines.json";
import { chaikin, fitToBox, outlineProblem, type Point, simplify, strokeToOutline } from "./outline";

interface ProblemCase {
  name: string;
  outline: Point[];
  problem: string | null;
}
interface SmoothCase {
  name: string;
  outline: Point[];
  iterations: number;
  expected: Point[];
}

describe("outline checks match the Python implementation", () => {
  for (const c of fixture.problems as ProblemCase[]) {
    it(c.name, () => expect(outlineProblem(c.outline)).toBe(c.problem));
  }
  for (const c of fixture.chaikin as SmoothCase[]) {
    it(`smooths ${c.name}`, () => {
      const got = chaikin(c.outline, c.iterations);
      expect(got).toHaveLength(c.expected.length);
      got.forEach(([x, y], i) => {
        const [ex, ey] = c.expected[i] ?? [NaN, NaN];
        expect(x).toBeCloseTo(ex, 10);
        expect(y).toBeCloseTo(ey, 10);
      });
    });
  }
});

describe("freehand strokes", () => {
  it("keep sharp corners and drop wobble", () => {
    const stroke: Point[] = [];
    for (let i = 0; i <= 20; i++) stroke.push([i, 0.001 * (i % 2)]);
    for (let i = 1; i <= 20; i++) stroke.push([20, i]);
    for (let i = 19; i >= 0; i--) stroke.push([i, 20]);
    const outline = strokeToOutline(stroke, 0.1);
    expect(outline).toEqual([
      [0, 0],
      [20, 0],
      [20, 20],
      [0, 20],
    ]);
  });
  it("simplify keeps the end points", () => {
    expect(simplify([[0, 0], [1, 0.01], [2, 0]], 0.1)).toEqual([[0, 0], [2, 0]]);
  });
  it("fitToBox centres and scales", () => {
    expect(fitToBox([[0, 0], [4, 0], [4, 2]], 1)).toEqual([[-0.5, -0.25], [0.5, -0.25], [0.5, 0.25]]);
  });
});
