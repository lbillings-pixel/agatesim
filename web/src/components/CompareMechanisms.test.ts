import { describe, expect, it } from "vitest";
import type { ModelInfo, RunConfig } from "../api";
import { comparisonConfigs } from "./CompareMechanisms";

const model = (kind: string): ModelInfo => ({
  kind,
  title: kind,
  schema: { properties: { band_mm: { type: "number", default: 1.5 } } },
  schedules: [],
});

const base: RunConfig = {
  name: "my-run",
  seed: 3,
  archetype: "waterline",
  grid: { resolution: 768, margin_fraction: 0.05 },
  cavity: { preset: "nodule-angular", size_mm: 50 } as RunConfig["cavity"],
  model: { kind: "procedural-waterline" },
};

describe("comparisonConfigs", () => {
  it("keeps the cavity and seed, swaps the model, and judges fortification", () => {
    const configs = comparisonConfigs(base, [
      model("procedural-fortification"),
      model("mechanistic-front-feedback"),
      model("mechanistic-liesegang"),
    ]);
    expect(configs.map((c) => c.model.kind)).toEqual([
      "procedural-fortification",
      "mechanistic-front-feedback",
      "mechanistic-liesegang",
    ]);
    for (const c of configs) {
      expect(c.cavity).toBe(base.cavity);
      expect(c.seed).toBe(3);
      expect(c.archetype).toBe("fortification");
      expect(c.name).toMatch(/^[a-z0-9][a-z0-9-]*$/);
      expect(c.model).toMatchObject({ band_mm: 1.5 });
    }
  });

  it("leaves out mechanisms the server doesn't offer", () => {
    expect(comparisonConfigs(base, [model("mechanistic-front-feedback")])).toHaveLength(1);
  });

  it("leaves out H2 when the server has no GPU", () => {
    const kinds = comparisonConfigs(
      base,
      [model("procedural-fortification"), model("mechanistic-liesegang")],
      false,
    ).map((c) => c.model.kind);
    expect(kinds).toEqual(["procedural-fortification"]);
  });
});
