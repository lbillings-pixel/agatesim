// A small animated-GIF encoder (GIF89a): one palette for the whole animation,
// chosen by median cut over sampled pixels, then LZW-compressed frames.

export interface Rgba {
  width: number;
  height: number;
  data: Uint8ClampedArray; // RGBA, row-major
}

type Box = { pixels: number[][] };

/** Up to `size` colours representing the sampled pixels (median cut). */
export function medianCut(samples: number[][], size = 256): number[][] {
  let boxes: Box[] = [{ pixels: samples }];
  while (boxes.length < size) {
    // Split the box with the widest channel range.
    let best = -1;
    let bestRange = 0;
    let bestChannel = 0;
    boxes.forEach((b, i) => {
      if (b.pixels.length < 2) return;
      for (let c = 0; c < 3; c++) {
        let lo = 255;
        let hi = 0;
        for (const p of b.pixels) {
          const v = p[c] ?? 0;
          if (v < lo) lo = v;
          if (v > hi) hi = v;
        }
        if (hi - lo > bestRange) {
          bestRange = hi - lo;
          best = i;
          bestChannel = c;
        }
      }
    });
    if (best < 0 || bestRange === 0) break;
    const box = boxes[best];
    if (!box) break;
    const sorted = [...box.pixels].sort((a, b) => (a[bestChannel] ?? 0) - (b[bestChannel] ?? 0));
    const mid = sorted.length >> 1;
    boxes = [...boxes.slice(0, best), { pixels: sorted.slice(0, mid) }, { pixels: sorted.slice(mid) }, ...boxes.slice(best + 1)];
  }
  return boxes.map((b) => {
    const sum = [0, 0, 0];
    for (const p of b.pixels) for (let c = 0; c < 3; c++) sum[c] = (sum[c] ?? 0) + (p[c] ?? 0);
    return sum.map((s) => Math.round(s / Math.max(b.pixels.length, 1)));
  });
}

/** Nearest palette entry for every 5-bit-per-channel colour, for fast mapping. */
function lookup(palette: number[][]): Uint8Array {
  const table = new Uint8Array(32 * 32 * 32);
  for (let r = 0; r < 32; r++) {
    for (let g = 0; g < 32; g++) {
      for (let b = 0; b < 32; b++) {
        const pr = r * 8 + 4;
        const pg = g * 8 + 4;
        const pb = b * 8 + 4;
        let best = 0;
        let dist = Infinity;
        palette.forEach((p, i) => {
          const d = ((p[0] ?? 0) - pr) ** 2 + ((p[1] ?? 0) - pg) ** 2 + ((p[2] ?? 0) - pb) ** 2;
          if (d < dist) {
            dist = d;
            best = i;
          }
        });
        table[(r << 10) | (g << 5) | b] = best;
      }
    }
  }
  return table;
}

/** LZW-compress palette indices as GIF image data (with minimum code size 8). */
export function lzw(indices: Uint8Array): Uint8Array {
  const clear = 256;
  const end = 257;
  const out: number[] = [];
  let acc = 0;
  let bits = 0;
  let size = 9;
  const emit = (code: number) => {
    acc |= code << bits;
    bits += size;
    while (bits >= 8) {
      out.push(acc & 0xff);
      acc >>>= 8;
      bits -= 8;
    }
  };
  let dict = new Map<number, number>();
  let next = 258;
  emit(clear);
  let prefix = indices[0] ?? 0;
  for (let i = 1; i < indices.length; i++) {
    const k = indices[i] ?? 0;
    const key = (prefix << 8) | k;
    const found = dict.get(key);
    if (found !== undefined) {
      prefix = found;
      continue;
    }
    emit(prefix);
    if (next < 4096) {
      dict.set(key, next++);
      // Widen codes one entry after the table outgrows them: the decoder's table
      // lags the encoder's by one entry.
      if (next > 1 << size && size < 12) size++;
    } else {
      emit(clear);
      dict = new Map();
      next = 258;
      size = 9;
    }
    prefix = k;
  }
  emit(prefix);
  emit(end);
  if (bits > 0) out.push(acc & 0xff);
  return Uint8Array.from(out);
}

/** Builds a looping animated GIF without holding its frames: the palette comes
 * from pixels sampled from every frame (`sample`), then each frame is encoded as
 * it is added (`add`), so the caller draws the animation twice and keeps one
 * frame at a time, not hundreds of megabytes of them. */
export class GifEncoder {
  private readonly samples: number[][] = [];
  private readonly stride: number;
  private table: Uint8Array | null = null;
  private readonly parts: Uint8Array[] = [];

  constructor(
    private readonly width: number,
    private readonly height: number,
    frameCount: number,
    private readonly delayCs: number,
  ) {
    this.stride = Math.max(1, Math.floor((frameCount * width * height) / 60000));
  }

  /** First pass: sample a frame's pixels for the shared palette. */
  sample(f: Rgba): void {
    for (let i = 0; i < this.width * this.height; i += this.stride) {
      this.samples.push([f.data[4 * i] ?? 0, f.data[4 * i + 1] ?? 0, f.data[4 * i + 2] ?? 0]);
    }
  }

  /** Second pass: encode a frame (the palette is fixed by the first). */
  add(f: Rgba): void {
    this.table ??= this.header();
    const table = this.table;
    const indices = new Uint8Array(this.width * this.height);
    for (let i = 0; i < indices.length; i++) {
      const r = (f.data[4 * i] ?? 0) >> 3;
      const g = (f.data[4 * i + 1] ?? 0) >> 3;
      const b = (f.data[4 * i + 2] ?? 0) >> 3;
      indices[i] = table[(r << 10) | (g << 5) | b] ?? 0;
    }
    const data = lzw(indices);
    // Graphic control, image descriptor, then the data in blocks of 255 bytes.
    const head = [0x21, 0xf9, 0x04, 0x00, ...word(this.delayCs), 0, 0, 0x2c, ...word(0), ...word(0)];
    head.push(...word(this.width), ...word(this.height), 0, 8);
    const blocks = Math.ceil(data.length / 255);
    const body = new Uint8Array(data.length + blocks + 1);
    let at = 0;
    for (let i = 0; i < data.length; i += 255) {
      const block = data.subarray(i, i + 255);
      body[at++] = block.length;
      body.set(block, at);
      at += block.length;
    }
    body[at] = 0;
    this.parts.push(Uint8Array.from(head), body);
  }

  /** The finished file, in parts (for a Blob, without copying them together). */
  finish(): Uint8Array[] {
    this.table ??= this.header();
    return [...this.parts, Uint8Array.of(0x3b)];
  }

  private header(): Uint8Array {
    const palette = medianCut(this.samples, 256);
    while (palette.length < 256) palette.push([0, 0, 0]);
    const head = [..."GIF89a"].map((ch) => ch.charCodeAt(0));
    head.push(...word(this.width), ...word(this.height), 0xf7, 0, 0); // global palette of 256 colours
    for (const p of palette) head.push(p[0] ?? 0, p[1] ?? 0, p[2] ?? 0);
    // Loop forever (NETSCAPE2.0 application extension).
    head.push(0x21, 0xff, 0x0b, ...[..."NETSCAPE2.0"].map((ch) => ch.charCodeAt(0)), 0x03, 0x01, 0, 0, 0);
    this.parts.push(Uint8Array.from(head));
    return lookup(palette);
  }
}

const word = (v: number) => [v & 0xff, (v >> 8) & 0xff];

/** Encode frames (all the same size) as a looping animated GIF. */
export function encodeGif(frames: Rgba[], delayCs: number): Uint8Array {
  const first = frames[0];
  if (!first) throw new Error("no frames");
  const encoder = new GifEncoder(first.width, first.height, frames.length, delayCs);
  for (const f of frames) encoder.sample(f);
  for (const f of frames) encoder.add(f);
  const parts = encoder.finish();
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of parts) {
    out.set(p, at);
    at += p.length;
  }
  return out;
}
