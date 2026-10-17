import { describe, expect, it } from "vitest";

import { TOUR_STEPS } from "./Tour";

describe("TOUR_STEPS", () => {
  it("covers each screen and the glossary", () => {
    const text = TOUR_STEPS.map((s) => `${s.title} ${s.body.join(" ")}`).join(" ");
    for (const name of ["Simulator", "Two ways", "3D", "Specimens", "Glossary"]) expect(text).toContain(name);
  });
});
