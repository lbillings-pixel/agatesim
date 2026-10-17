import { describe, expect, it } from "vitest";

import type { ArchetypeInfo, RunConfig } from "../api";
import { buildReport, escapeHtml } from "./report";

const config = {
  name: "eye-<test>",
  seed: 8,
  archetype: "eye",
  grid: { resolution: 768, margin_fraction: 0.05 },
  cavity: { preset: "vesicle-round", size_mm: 50 },
  model: { kind: "mechanistic-staged", order: "spherulite-wall", wall: { spherulite_spacing_mm: 20 } },
} as unknown as RunConfig;
const eye: ArchetypeInfo = {
  id: "eye", name: "Eye agate", rung: 7, status: { procedural: "verified", mechanistic: "verified" },
  implemented: true, criteria: [{ id: "discrete-eyes", description: "", pass: "value ≥ 3" }],
};

describe("buildReport", () => {
  const html = buildReport({
    config,
    image: "data:image/png;base64,AAAA",
    evaluation: {
      archetype: "eye", passed: true,
      criteria: [{ id: "discrete-eyes", value: 7, min: 3, max: null, passed: true, detail: "" }],
    },
    stats: null,
    archetypes: [eye],
    models: [],
    description: "Eyes & lining",
    source: "saved run 768×768 px",
    created: new Date("2026-10-17T15:00:00Z"),
  });

  it("holds the slab, the verdict, each test and every setting", () => {
    expect(html).toContain('src="data:image/png;base64,AAAA"');
    expect(html).toContain("all tests pass");
    expect(html).toContain("<code>discrete-eyes</code>");
    expect(html).toContain("value ≥ 3");
    expect(html).toContain("Model › Wall › Spherulite spacing");
    expect(html).toContain("<code>spherulite-wall</code>");
  });

  it("escapes text from the configuration", () => {
    expect(html).toContain("eye-&lt;test&gt;");
    expect(html).not.toContain("eye-<test>");
    expect(html).toContain("Eyes &amp; lining");
  });
});

describe("escapeHtml", () => {
  it("escapes the five special characters", () => {
    expect(escapeHtml(`<a href="x">'&'</a>`)).toBe("&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;");
  });
});
