import { describe, expect, it } from "vitest";

import type { QualityBadge } from "../api";
import { adviceFor, badgeSummary, levelClass } from "./quality";

const calibration: QualityBadge = {
  use: "calibration",
  level: "not fit",
  reasons: [
    {
      score: "band spacing",
      level: "borderline",
      message: "bands are 6.0 px apart",
      advice: "move closer",
    },
    {
      score: "scale",
      level: "not fit",
      message: "no scale is set",
      advice: "click the ruler",
    },
  ],
};
const classification: QualityBadge = {
  use: "classification",
  level: "borderline",
  reasons: [
    {
      score: "band spacing",
      level: "borderline",
      message: "bands are 4.0 px apart",
      advice: "move closer",
    },
  ],
};

describe("quality badges", () => {
  it("summarise the scores that fall short, worst first", () => {
    expect(badgeSummary(calibration)).toBe("Calibrate: not fit (no scale is set; bands are 6.0 px apart)");
    expect(badgeSummary({ use: "classification", level: "fit", reasons: [] })).toBe("Classify: fit");
    expect(badgeSummary({ use: "shape", level: "fit", note: "judges band shape only", reasons: [] })).toBe(
      "Band shape: fit. This judges band shape only",
    );
  });

  it("give each piece of advice once", () => {
    expect(adviceFor([classification, calibration])).toEqual(["click the ruler", "move closer"]);
  });

  it("map levels onto pills", () => {
    expect(levelClass("fit")).toBe("pill pass");
    expect(levelClass("borderline")).toBe("pill borderline");
    expect(levelClass("not fit")).toBe("pill fail");
  });
});
