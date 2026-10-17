import { describe, expect, it } from "vitest";

import type { ArchetypeInfo, RunConfig } from "../api";
import { fieldsFor, imposedSettings } from "../lib/schema";
import { formPairs } from "./TwoWays";

const archetype = (id: string, implemented = true): ArchetypeInfo => ({
  id, name: id, rung: 1, status: { procedural: "verified", mechanistic: "pending" }, implemented, criteria: [],
});
const preset = (name: string) => ({ name, config: { name } as unknown as RunConfig, description: "" });

describe("formPairs", () => {
  it("pairs each form's procedural and mechanistic presets by name", () => {
    const pairs = formPairs({
      archetypes: [archetype("moss"), archetype("plume"), archetype("future", false)],
      presets: [preset("moss"), preset("moss-mechanistic"), preset("plume")],
    });
    expect(pairs.map((p) => [p.archetype.id, p.procedural?.name, p.mechanistic?.name ?? null])).toEqual([
      ["moss", "moss", "moss-mechanistic"],
      ["plume", "plume", null],
    ]);
  });
});

describe("imposedSettings", () => {
  const schema = {
    properties: {
      band_period: { type: "number", default: 0.012, maximum: 0.5, nature: "imposed" as const },
      growth_mm: { type: "number", default: 30, nature: "effective" as const, units: "mm" },
      stage: { $ref: "#/$defs/Stage" },
    },
    $defs: {
      Stage: { properties: { alternation: { type: "number", default: 0.7, maximum: 1, nature: "imposed" as const } } },
    },
  };

  it("lists imposed settings, nested ones included, with the given values", () => {
    expect(imposedSettings(fieldsFor(schema), { band_period: 0.03 })).toEqual([
      { label: "Band period", value: 0.03, units: "" },
      { label: "Stage › Alternation", value: 0.7, units: "" },
    ]);
  });

  it("is empty for a model with nothing imposed", () => {
    const rest = { growth_mm: schema.properties.growth_mm };
    expect(imposedSettings(fieldsFor({ properties: rest }), {})).toEqual([]);
  });
});

