import { describe, expect, it } from "vitest";

import { formatBytes } from "./bytes";

describe("formatBytes", () => {
  it("reads at a glance", () => {
    expect(formatBytes(0)).toBe("0 bytes");
    expect(formatBytes(850_000)).toBe("850 KB");
    expect(formatBytes(1_400_000_000)).toBe("1.4 GB");
    expect(formatBytes(58_000_000)).toBe("58 MB");
  });
});
