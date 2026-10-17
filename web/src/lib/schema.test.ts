import { describe, expect, it } from "vitest";

import type { ModelSchema } from "../api";

import {
  controlFor, controlsFor, defaultsFor, fieldsFor, formatValue, isUsed, labelFor, niceStep, withSetting,
} from "./schema";

describe("labelFor", () => {
  it("drops unit suffixes and humanizes", () => {
    expect(labelFor("mean_band_thickness_mm")).toBe("Mean band thickness");
    expect(labelFor("gravity_deg")).toBe("Gravity");
    expect(labelFor("iron")).toBe("Iron");
  });
});

describe("niceStep", () => {
  it("rounds to 1, 2 or 5 times a power of ten", () => {
    expect(niceStep(1)).toBeCloseTo(0.005);
    expect(niceStep(2)).toBeCloseTo(0.01);
    expect(niceStep(0.6)).toBeCloseTo(0.002);
  });
});

describe("controlFor", () => {
  it("uses schema bounds and our extras", () => {
    const c = controlFor("iron", {
      type: "number", default: 0.25, minimum: 0, maximum: 1, units: "", nature: "imposed",
    });
    expect(c).toMatchObject({ min: 0, max: 1, nature: "imposed", defaultValue: 0.25 });
  });

  it("gives unbounded parameters a range around the default", () => {
    const c = controlFor("wobble_mm", { type: "number", default: 0.15, minimum: 0, units: "mm" });
    expect(c?.max).toBeCloseTo(1);
  });

  it("keeps exclusive minimums out of reach", () => {
    const c = controlFor("mean_band_thickness_mm", {
      type: "number", default: 0.5, exclusiveMinimum: 0, units: "mm",
    });
    expect(c?.min).toBeGreaterThan(0);
  });

  it("treats angles as 0-359 in whole degrees", () => {
    const c = controlFor("gravity_deg", {
      type: "number", default: 270, minimum: 0, exclusiveMaximum: 360, units: "deg",
    });
    expect(c).toMatchObject({ min: 0, max: 359, step: 1 });
  });

  it("ignores non-numeric fields such as the model kind", () => {
    expect(controlFor("kind", { type: "string", const: "procedural-fortification" })).toBeNull();
  });
});

describe("controlsFor / defaultsFor", () => {
  const properties = {
    kind: { type: "string", const: "procedural-waterline" },
    gravity_deg: { type: "number", default: 270, units: "deg", nature: "physical" as const },
    iron: { type: "number", default: 0.15, minimum: 0, maximum: 1 },
  };
  it("builds controls for numeric fields only", () => {
    expect(controlsFor(properties).map((c) => c.key)).toEqual(["gravity_deg", "iron"]);
  });
  it("collects defaults", () => {
    expect(defaultsFor(properties)).toEqual({ gravity_deg: 270, iron: 0.15 });
  });
});

describe("formatValue", () => {
  it("matches precision to the step", () => {
    expect(formatValue(0.123456, 0.005)).toBe("0.123");
    expect(formatValue(270, 1)).toBe("270");
  });
});

describe("fieldsFor", () => {
  // The shape of a staged model's pydantic schema, cut down.
  const schema: ModelSchema = {
    properties: {
      kind: { type: "string", const: "mechanistic-staged" },
      order: { type: "string", default: "wall-floor", enum: ["wall-floor", "floor-wall"], description: "Stages." },
      gravity_deg: { type: "number", default: 270, units: "deg" },
      wall: { $ref: "#/$defs/FrontFeedback", description: "The H1 wall stages." },
      floor: { $ref: "#/$defs/Settling" },
    },
    $defs: {
      FrontFeedback: {
        properties: {
          kind: { type: "string", const: "mechanistic-front-feedback" },
          growth_form: { type: "string", default: "lining", enum: ["lining", "spherulitic"] },
          catalysis: { type: "number", default: 17.4, minimum: 0 },
        },
      },
      Settling: {
        properties: {
          kind: { type: "string", const: "mechanistic-settling" },
          gravity_deg: { type: "number", default: 270, units: "deg" },
        },
      },
    },
  };

  it("turns enums into choices and nested models into groups", () => {
    const fields = fieldsFor(schema);
    expect(fields.map((f) => [f.type, f.key])).toEqual([
      ["choice", "order"], ["number", "gravity_deg"], ["group", "wall"],
    ]);
    const order = fields[0];
    expect(order?.type === "choice" && order.options).toEqual(["wall-floor", "floor-wall"]);
    const wall = fields[2];
    expect(wall?.type === "group" && wall.fields.map((f) => [f.type, f.key])).toEqual([
      ["choice", "growth_form"], ["number", "catalysis"],
    ]);
  });

  it("leaves out a nested field the parent governs, and groups left empty", () => {
    // The floor's only setting is gravity, which the staged model sets itself.
    expect(fieldsFor(schema).some((f) => f.key === "floor")).toBe(false);
  });
});

describe("withSetting", () => {
  it("replaces a nested setting without touching its neighbours", () => {
    const model = { kind: "mechanistic-staged", rim_share: 0.3, wall: { catalysis: 17.4, partition: 0.2 } };
    const next = withSetting(model, ["wall", "catalysis"], 30);
    expect(next).toEqual({ kind: "mechanistic-staged", rim_share: 0.3, wall: { catalysis: 30, partition: 0.2 } });
    expect(model.wall.catalysis).toBe(17.4);
  });

  it("creates a group missing from the values", () => {
    expect(withSetting({ kind: "x" }, ["dendrite", "tint"], 0)).toEqual({ kind: "x", dendrite: { tint: 0 } });
  });
});

describe("isUsed", () => {
  // A staged model's stage groups, with the hints its schema carries.
  const schema: ModelSchema = {
    properties: {
      order: { type: "string", default: "wall-floor-wall", enum: ["wall-floor-wall", "spherulite-wall", "dendrite-wall"] },
      wall_mechanism: {
        type: "string", default: "front-feedback", enum: ["front-feedback", "liesegang"],
        used_when: [{ order: ["wall"] }],
      },
      wall: {
        $ref: "#/$defs/Stage",
        used_when: [{ order: ["spherulite"] }, { order: ["wall"], wall_mechanism: ["front-feedback"] }],
      },
      liesegang: { $ref: "#/$defs/Stage", used_when: [{ order: ["wall"], wall_mechanism: ["liesegang"] }] },
      floor: { $ref: "#/$defs/Stage", used_when: [{ order: ["floor"] }] },
      dendrite: { $ref: "#/$defs/Stage", used_when: [{ order: ["dendrite"] }] },
    },
    $defs: { Stage: { properties: { rate: { type: "number", default: 1, minimum: 0 } } } },
  };
  const fields = fieldsFor(schema);
  const shown = (values: Record<string, unknown>) =>
    fields.filter((f) => isUsed(f, values, fields)).map((f) => f.key);

  it("uses the defaults when nothing is set", () => {
    expect(shown({})).toEqual(["order", "wall_mechanism", "wall", "floor"]);
  });

  it("shows only the stages the order has", () => {
    expect(shown({ order: "dendrite-wall" })).toEqual(["order", "wall_mechanism", "wall", "dendrite"]);
  });

  it("follows the wall mechanism, but the spherulite stage always uses H1", () => {
    expect(shown({ wall_mechanism: "liesegang" })).toEqual(["order", "wall_mechanism", "liesegang", "floor"]);
    expect(shown({ order: "spherulite-wall", wall_mechanism: "liesegang" })).toEqual([
      "order", "wall_mechanism", "wall", "liesegang",
    ]);
  });
});

describe("fieldsFor toggles", () => {
  it("shows booleans as on/off settings with their default", () => {
    const fields = fieldsFor({
      properties: { micro_rhythm: { type: "boolean", default: false, description: "A fast rhythm." } },
    });
    expect(fields).toEqual([
      { type: "toggle", key: "micro_rhythm", label: "Micro rhythm", description: "A fast rhythm.", defaultValue: false },
    ]);
  });
});

describe("isUsed with an on/off setting", () => {
  const fields = fieldsFor({
    properties: {
      micro_rhythm: { type: "boolean", default: false },
      micro_boundary_layer_um: { type: "number", default: 0.1, maximum: 1, used_when: [{ micro_rhythm: ["true"] }] },
    },
  });
  const layer = fields.find((f) => f.key === "micro_boundary_layer_um");
  if (!layer) throw new Error("missing field");
  it("hides a setting until the switch it depends on is on", () => {
    expect(isUsed(layer, {}, fields)).toBe(false);
    expect(isUsed(layer, { micro_rhythm: true }, fields)).toBe(true);
  });
});
