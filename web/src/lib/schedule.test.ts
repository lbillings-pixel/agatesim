import { describe, expect, it } from "vitest";

import fixture from "../../../tests/fixtures/schedules.json";
import type { Schedule } from "../api";
import { newEvent, problems, sample } from "./schedule";

interface Case {
  name: string;
  schedule: Schedule;
  t: number[];
  expected: number[];
}

describe("schedule sampling matches the Python implementation", () => {
  for (const c of fixture as Case[]) {
    it(c.name, () => {
      const got = sample(c.schedule, c.t);
      got.forEach((v, i) => expect(v).toBeCloseTo(c.expected[i] ?? NaN, 12));
    });
  }
});

describe("newEvent / problems", () => {
  it("creates valid events", () => {
    for (const type of ["step", "ramp", "pulse"] as const) {
      expect(problems(newEvent(type, 0, 1))).toEqual([]);
    }
  });
  it("flags a backwards ramp", () => {
    expect(problems({ type: "ramp", start: 0.6, end: 0.4, value: 1 })).toHaveLength(1);
  });
});
