import { describe, expect, it } from "vitest";

import { applyGrowth, NEVER } from "./growth";

const VOID = [1, 2, 3] as const;

function pixels(...rgba: number[][]): Uint8ClampedArray {
  return new Uint8ClampedArray(rgba.flat());
}

describe("applyGrowth", () => {
  const slab = pixels([100, 100, 100, 255], [150, 150, 150, 255], [200, 200, 200, 255]);
  // early deposit, late deposit, never deposited (host rock)
  const tdep = pixels([10, 10, 10, 255], [250, 250, 250, 255], [NEVER, NEVER, NEVER, 255]);

  it("shows everything at t = 1", () => {
    expect(Array.from(applyGrowth(slab, tdep, 1, VOID))).toEqual(Array.from(slab));
  });

  it("hides material deposited after t", () => {
    const out = Array.from(applyGrowth(slab, tdep, 0.5, VOID));
    expect(out.slice(0, 4)).toEqual([100, 100, 100, 255]);
    expect(out.slice(4, 8)).toEqual([1, 2, 3, 255]);
    expect(out.slice(8, 12)).toEqual([200, 200, 200, 255]);
  });

  it("never hides host rock or open space", () => {
    const out = Array.from(applyGrowth(slab, tdep, 0, VOID));
    expect(out.slice(8, 12)).toEqual([200, 200, 200, 255]);
  });
});
