import { describe, expect, it } from "vitest";

import type { CriterionResult, Evaluation } from "../api";
import { overallVerdict } from "./CriteriaPanel";

function result(value: number | null, passed: boolean): CriterionResult {
  return { id: "c", value, min: null, max: null, passed, detail: "" };
}

function evaluation(...criteria: CriterionResult[]): Evaluation {
  return { archetype: "fortification", passed: criteria.every((c) => c.passed), criteria };
}

describe("overallVerdict", () => {
  it("passes when every test passes", () => {
    expect(overallVerdict(evaluation(result(1, true))).tone).toBe("pass");
  });
  it("fails when a measured test fails", () => {
    expect(overallVerdict(evaluation(result(1, true), result(2, false))).tone).toBe("fail");
  });
  it("is only partly judged when the sole problem is an unmeasurable test", () => {
    expect(overallVerdict(evaluation(result(1, true), result(null, false)))).toEqual({
      label: "partly judged",
      tone: "na",
    });
  });
});
