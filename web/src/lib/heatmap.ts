/** RGBA pixels that dim a photo where a probability grid (rows from the top)
 * is low, as a spotlight: clear above `ceiling`, dimmed by up to `maxDim`
 * at or below `floor`. Dimming reads on any stone's colours. */
export function spotlightPixels(grid: number[][], floor = 0.2, ceiling = 0.8, maxDim = 0.65): Uint8ClampedArray<ArrayBuffer> {
  const rows = grid.length;
  const cols = grid[0]?.length ?? 0;
  const out = new Uint8ClampedArray(rows * cols * 4);
  grid.forEach((row, r) =>
    row.forEach((p, c) => {
      const level = Math.min(1, Math.max(0, (p - floor) / (ceiling - floor)));
      out[(r * cols + c) * 4 + 3] = Math.round((1 - level) * maxDim * 255);
    }),
  );
  return out;
}
