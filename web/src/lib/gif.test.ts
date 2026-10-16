import { describe, expect, it } from "vitest";

import { encodeGif, lzw, medianCut } from "./gif";

/** A GIF LZW decoder (minimum code size 8), to check the encoder against. */
function unlzw(data: Uint8Array, count: number): number[] {
  const out: number[] = [];
  let dict: number[][] = [];
  const reset = () => {
    dict = Array.from({ length: 258 }, (_, i) => [i]);
  };
  reset();
  let size = 9;
  let pos = 0;
  let prev: number[] | null = null;
  const read = () => {
    let code = 0;
    for (let i = 0; i < size; i++, pos++) {
      const bit = ((data[pos >> 3] ?? 0) >> (pos & 7)) & 1;
      code |= bit << i;
    }
    return code;
  };
  while (out.length < count) {
    const code = read();
    if (code === 256) {
      reset();
      size = 9;
      prev = null;
      continue;
    }
    if (code === 257) break;
    let entry = dict[code];
    if (!entry && prev) entry = [...prev, prev[0] ?? 0];
    if (!entry) throw new Error(`bad code ${code}`);
    out.push(...entry);
    if (prev) dict.push([...prev, entry[0] ?? 0]);
    prev = entry;
    if (dict.length === 1 << size && size < 12) size++;
  }
  return out;
}

describe("gif", () => {
  it("compresses indices losslessly, including past a full code table", () => {
    const rng = (() => {
      let s = 1;
      return () => ((s = (s * 48271) % 2147483647) / 2147483647);
    })();
    for (const n of [1, 10, 1000, 60000]) {
      const indices = Uint8Array.from({ length: n }, () => Math.floor(rng() * (n > 1000 ? 7 : 256)));
      expect(unlzw(lzw(indices), n)).toEqual(Array.from(indices));
    }
  });

  it("picks distinct colours for distinct pixels", () => {
    const palette = medianCut([[0, 0, 0], [255, 0, 0], [0, 255, 0], [0, 0, 255]], 4);
    expect(palette).toHaveLength(4);
    expect(new Set(palette.map((p) => p.join(","))).size).toBe(4);
  });

  it("writes a looping GIF89a with one image per frame", () => {
    const frame = (v: number) => ({ width: 2, height: 2, data: new Uint8ClampedArray(16).fill(v) });
    const gif = encodeGif([frame(0), frame(200)], 10);
    expect(String.fromCharCode(...gif.slice(0, 6))).toBe("GIF89a");
    expect(gif.at(-1)).toBe(0x3b);
    expect(gif.filter((b) => b === 0x2c).length).toBeGreaterThanOrEqual(2);
  });
});
