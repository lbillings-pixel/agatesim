import { describe, expect, it } from "vitest";

import type { ArchetypeInfo, Meta } from "../api";
import { formPresets, otherPresets, tierOf } from "./forms";

const archetype = (id: string, implemented = true) => ({ id, name: id, implemented }) as unknown as ArchetypeInfo;
const preset = (name: string) => ({ name, config: { name } }) as unknown as Meta["presets"][number];

describe("forms", () => {
  const meta = {
    archetypes: [archetype("seam"), archetype("stick"), archetype("future", false)],
    presets: [preset("seam"), preset("seam-mechanistic"), preset("stick"), preset("liesegang-seam")],
  };

  it("pairs each implemented form with its presets", () => {
    const forms = formPresets(meta);
    expect(forms.map((f) => f.id)).toEqual(["seam", "stick"]);
    expect(forms[0]?.mechanistic?.name).toBe("seam-mechanistic");
    expect(forms[1]?.mechanistic).toBeNull();
  });

  it("keeps the other presets apart", () => {
    expect(otherPresets(meta).map((p) => p.name)).toEqual(["liesegang-seam"]);
  });

  it("reads a model's tier from its kind", () => {
    expect(tierOf("mechanistic-staged")).toBe("mechanistic");
    expect(tierOf("procedural-growth")).toBe("procedural");
  });
});
