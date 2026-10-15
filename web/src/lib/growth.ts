// Show a slab partway through its growth, using the deposition-time image.
// tdep codes (red channel): 0..254 = deposition time 0..1; 255 = never deposited.

export const NEVER = 255;

export function applyGrowth(
  slab: Uint8ClampedArray,
  tdep: Uint8ClampedArray,
  t: number,
  voidColour: readonly [number, number, number],
  out: Uint8ClampedArray = new Uint8ClampedArray(slab.length),
): Uint8ClampedArray {
  const cutoff = Math.round(Math.min(Math.max(t, 0), 1) * 254);
  for (let i = 0; i < slab.length; i += 4) {
    const code = tdep[i] ?? NEVER;
    const notYet = code !== NEVER && code > cutoff;
    out[i] = notYet ? voidColour[0] : (slab[i] ?? 0);
    out[i + 1] = notYet ? voidColour[1] : (slab[i + 1] ?? 0);
    out[i + 2] = notYet ? voidColour[2] : (slab[i + 2] ?? 0);
    out[i + 3] = slab[i + 3] ?? 255;
  }
  return out;
}
