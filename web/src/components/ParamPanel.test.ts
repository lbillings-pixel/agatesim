import { describe, expect, it } from "vitest";

import type { Field } from "../lib/schema";
import { matchingPreset } from "./ParamPanel";

const number = (key: string, defaultValue: number): Field =>
  ({ type: "number", key, label: key, units: "", nature: "effective", description: "", min: 0, max: 1, step: 0.01, defaultValue });

describe("matchingPreset", () => {
  const fields = [number("red", 0), number("blue", 1)];
  const presets = { Red: { red: 1 }, Blue: { blue: 1 } };

  it("names the preset the values match, unlisted weights counting as 0", () => {
    expect(matchingPreset(presets, fields, { red: 1, blue: 0 })).toBe("Red");
    expect(matchingPreset(presets, fields, {})).toBe("Blue"); // defaults: red 0, blue 1
  });

  it("is empty for custom values", () => {
    expect(matchingPreset(presets, fields, { red: 0.5, blue: 0.5 })).toBe("");
  });
});
