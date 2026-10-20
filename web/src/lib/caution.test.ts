import { describe, expect, it } from "vitest";

import { cautionText, roughTime } from "./caution";

describe("roughTime", () => {
  it("rounds to what matters for the wait", () => {
    expect(roughTime(2)).toBe("about 5 s");
    expect(roughTime(44)).toBe("about 45 s");
    expect(roughTime(130)).toBe("about 2 min");
    expect(roughTime(4000)).toBe("over an hour");
    expect(roughTime(9 * 3600)).toBe("about 9 hours");
  });
});

describe("cautionText", () => {
  it("names the time, and the memory when it is large", () => {
    const e = { seconds: 100, memory_gb: 3.4, heavy: true, reasons: [] };
    expect(cautionText(e)).toBe("Heavy: about 2 min · about 3.4 GB of memory");
    expect(cautionText({ ...e, memory_gb: 0.5 })).toBe("Heavy: about 2 min");
  });
});
