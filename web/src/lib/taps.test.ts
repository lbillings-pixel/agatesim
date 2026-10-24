import { describe, expect, it } from "vitest";

import type { TapPhoto } from "../api";
import { ENOUGH, nextUndone, photoDone, tap } from "./taps";

const photo = (id: string, over: Partial<TapPhoto> = {}): TapPhoto => ({
  id,
  targets: ["moss"],
  taps: {},
  done: false,
  ...over,
});

describe("test taps", () => {
  it("adds points of the chosen kind and removes one tapped again", () => {
    let t = tap({}, "moss", "inside", 0.5, 0.5);
    t = tap(t, "moss", "outside", 0.1, 0.1);
    expect(t.moss).toEqual({ inside: [[0.5, 0.5]], outside: [[0.1, 0.1]] });
    t = tap(t, "moss", "outside", 0.505, 0.5);
    expect(t.moss).toEqual({ inside: [], outside: [[0.1, 0.1]] });
  });

  it("keeps points on the photo and leaves other features alone", () => {
    const t = tap(
      { tube: { inside: [[0.5, 0.5]], outside: [] } },
      "moss",
      "inside",
      1.2,
      -0.1,
    );
    expect(t.moss?.inside).toEqual([[1, 0]]);
    expect(t.tube?.inside).toEqual([[0.5, 0.5]]);
  });

  it("counts a photo done only with enough points of both kinds", () => {
    const pts = Array.from({ length: ENOUGH }, (): [number, number] => [
      0.2, 0.2,
    ]);
    expect(photoDone(photo("a"), { moss: { inside: pts, outside: pts } })).toBe(
      true,
    );
    expect(photoDone(photo("a"), { moss: { inside: pts, outside: [] } })).toBe(
      false,
    );
    expect(photoDone(photo("a", { targets: [] }), {})).toBe(false);
  });

  it("finds the next photo still to tap, wrapping round", () => {
    const photos = [
      photo("a"),
      photo("b", { done: true }),
      photo("c", { targets: [] }),
      photo("d"),
    ];
    expect(nextUndone(photos, 0)).toBe(3);
    expect(nextUndone(photos, 3)).toBe(0);
    expect(nextUndone(photos, 0, -1)).toBe(3);
    expect(nextUndone([photo("a", { done: true })], 0)).toBe(null);
  });
});
