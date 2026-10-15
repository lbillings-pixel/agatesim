import { describe, expect, it } from "vitest";

import { controlFor, controlsFor, defaultsFor, formatValue, labelFor, niceStep } from "./schema";

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
