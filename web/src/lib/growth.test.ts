import { describe, expect, it } from "vitest";

import { advanceGrowth, applyGrowth, NEVER, PLAY_SECONDS } from "./growth";

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

describe("advanceGrowth", () => {
  it("plays the whole growth in PLAY_SECONDS at 1x, faster or slower with speed", () => {
    expect(advanceGrowth(0, PLAY_SECONDS / 2, 1, false).t).toBeCloseTo(0.5);
    expect(advanceGrowth(0, PLAY_SECONDS / 2, 0.5, false).t).toBeCloseTo(0.25);
    expect(advanceGrowth(0, PLAY_SECONDS / 8, 4, false).t).toBeCloseTo(0.5);
  });

  it("stops at the end, or wraps when looping", () => {
    expect(advanceGrowth(0.9, PLAY_SECONDS, 1, false)).toEqual({ t: 1, playing: false });
    const looped = advanceGrowth(0.9, PLAY_SECONDS * 0.2, 1, true);
    expect(looped.playing).toBe(true);
    expect(looped.t).toBeCloseTo(0.1);
  });
});