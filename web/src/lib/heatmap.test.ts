import { describe, expect, it } from "vitest";

import { spotlightPixels } from "./heatmap";

describe("spotlight pixels", () => {
  it("dims most where unlikely and leaves likely areas clear", () => {
    const px = spotlightPixels(
      [
        [0.1, 0.9],
        [0.5, 0.2],
      ],
      0.2,
      0.8,
      0.6,
    );
    expect(px.length).toBe(16);
    expect([...px.slice(0, 4)]).toEqual([0, 0, 0, 153]);
    expect(px[7]).toBe(0);
    expect(px[11]).toBe(77);
    expect(px[15]).toBe(153);
  });
});
