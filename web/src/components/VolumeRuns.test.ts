import { describe, expect, it } from "vitest";
import { surveyLabel } from "./VolumeRuns";

describe("surveyLabel", () => {
  it("shows the share of random cuts that pass", () => {
    expect(surveyLabel({ cuts: 40, pass_rate: 0.675 })).toBe("68% of 40 cuts");
  });
  it("shows nothing without a survey or a judged cut", () => {
    expect(surveyLabel(null)).toBeNull();
    expect(surveyLabel({ cuts: 5, pass_rate: null })).toBeNull();
  });
});
