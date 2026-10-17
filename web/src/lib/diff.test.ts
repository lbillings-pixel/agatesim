import { describe, expect, it } from "vitest";

import { flatten, settingDiffs } from "./diff";

describe("flatten", () => {
  it("joins nested keys and keeps lists whole", () => {
    expect(flatten({ seed: 1, model: { kind: "x", wall: { catalysis: 17.4 } }, tubes: [{ x: 1 }] })).toEqual({
      seed: "1",
      "model/kind": "x",
      "model/wall/catalysis": "17.4",
      tubes: '[{"x":1}]',
    });
  });
});

describe("settingDiffs", () => {
  it("lists only the settings that differ, ignoring the run name", () => {
    const a = { name: "a", seed: 1, model: { kind: "staged", rim_share: 0.3, wall: { catalysis: 17.4 } } };
    const b = { name: "b", seed: 1, model: { kind: "staged", rim_share: 0.1, wall: { catalysis: 17.4 } } };
    expect(settingDiffs(a, b)).toEqual([{ path: "model/rim_share", label: "Model › Rim share", a: "0.3", b: "0.1" }]);
  });

  it("shows a setting only one side has as missing on the other", () => {
    const diffs = settingDiffs({ model: { kind: "a", band_period: 0.02 } }, { model: { kind: "a" } });
    expect(diffs).toEqual([{ path: "model/band_period", label: "Model › Band period", a: "0.02", b: null }]);
  });

  it("compares runs of different models by their kind alone", () => {
    const diffs = settingDiffs(
      { seed: 1, model: { kind: "procedural-growth", band_period: 0.02 } },
      { seed: 2, model: { kind: "mechanistic-staged", rim_share: 0.3 } },
    );
    expect(diffs.map((d) => d.path)).toEqual(["model/kind", "seed"]);
  });
});
