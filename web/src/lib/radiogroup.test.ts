import { describe, expect, it } from "vitest";

import { radioTarget } from "./radiogroup";

describe("radioTarget", () => {
  it("moves with the arrows and wraps at the ends", () => {
    expect(radioTarget("ArrowRight", 0, 3)).toBe(1);
    expect(radioTarget("ArrowDown", 2, 3)).toBe(0);
    expect(radioTarget("ArrowLeft", 0, 3)).toBe(2);
    expect(radioTarget("ArrowUp", 1, 3)).toBe(0);
  });

  it("jumps to the ends with Home and End", () => {
    expect(radioTarget("Home", 2, 3)).toBe(0);
    expect(radioTarget("End", 0, 3)).toBe(2);
  });

  it("ignores other keys", () => {
    expect(radioTarget("Enter", 1, 3)).toBeNull();
    expect(radioTarget("a", 1, 3)).toBeNull();
  });
});
