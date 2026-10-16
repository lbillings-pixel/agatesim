// Exporting the growth animation as an animated GIF or a video file.

import { encodeGif } from "./gif";

export interface Stage {
  start: number;
  end: number;
  label: string;
}

/** What is forming at growth t (the last stage started by then). */
export function stageAt(stages: Stage[] | undefined, t: number): string | null {
  if (!stages?.length) return null;
  const s = stages.find((st) => t >= st.start && t < st.end) ?? stages.at(-1);
  return s?.label ?? null;
}

/** Draws the scene at growth t (0..1) into a canvas of the given size. */
export interface FrameSource {
  width: number;
  height: number;
  draw: (ctx: CanvasRenderingContext2D, t: number) => void;
}

export interface ExportOptions {
  seconds: number; // length of the growth part of the animation
  fps: number;
  holdSeconds?: number; // the finished agate is held this long at the end
  onProgress?: (share: number) => void;
}

const MAX_GIF_WIDTH = 640;
const CAPTION_PX = 26;

/** A caption strip under a frame: growth and the stage forming. */
export function captioned(source: FrameSource, stages: Stage[] | undefined): FrameSource {
  return {
    width: source.width,
    height: source.height + CAPTION_PX,
    draw: (ctx, t) => {
      source.draw(ctx, t);
      ctx.fillStyle = "#14181b";
      ctx.fillRect(0, source.height, source.width, CAPTION_PX);
      ctx.fillStyle = "#e8ecef";
      ctx.font = "14px system-ui, sans-serif";
      ctx.textBaseline = "middle";
      const stage = stageAt(stages, t);
      ctx.fillText(`Growth ${Math.round(t * 100)}%${stage ? ` · ${stage}` : ""}`, 10, source.height + CAPTION_PX / 2);
    },
  };
}

function frameTimes(opts: ExportOptions): number[] {
  const n = Math.max(2, Math.round(opts.seconds * opts.fps));
  const hold = Math.round((opts.holdSeconds ?? 1) * opts.fps);
  return [...Array.from({ length: n }, (_, i) => i / (n - 1)), ...Array.from({ length: hold }, () => 1)];
}

function canvasFor(source: FrameSource, maxWidth: number): { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D; scale: number } {
  const scale = Math.min(1, maxWidth / source.width);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(source.width * scale);
  canvas.height = Math.round(source.height * scale);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("canvas unavailable");
  return { canvas, ctx, scale };
}

const nextTask = () => new Promise((r) => setTimeout(r, 0));

export async function exportGif(source: FrameSource, opts: ExportOptions): Promise<Blob> {
  const { canvas, ctx, scale } = canvasFor(source, MAX_GIF_WIDTH);
  const frames = [];
  const times = frameTimes(opts);
  for (const [i, t] of times.entries()) {
    ctx.save();
    ctx.scale(scale, scale);
    source.draw(ctx, t);
    ctx.restore();
    frames.push(ctx.getImageData(0, 0, canvas.width, canvas.height));
    opts.onProgress?.((0.6 * (i + 1)) / times.length);
    if (i % 8 === 0) await nextTask(); // keep the page responsive
  }
  const gif = encodeGif(frames, Math.round(100 / opts.fps));
  opts.onProgress?.(1);
  return new Blob([gif.slice().buffer], { type: "image/gif" });
}

/** The best video format this browser can record. */
export function videoFormat(): { mime: string; ext: string } | null {
  if (typeof MediaRecorder === "undefined") return null;
  const options = [
    { mime: "video/mp4;codecs=avc1", ext: "mp4" },
    { mime: "video/mp4", ext: "mp4" },
    { mime: "video/webm;codecs=vp9", ext: "webm" },
    { mime: "video/webm", ext: "webm" },
  ];
  return options.find((o) => MediaRecorder.isTypeSupported(o.mime)) ?? null;
}

/** Record the animation in real time from a canvas stream. */
export async function exportVideo(source: FrameSource, opts: ExportOptions): Promise<{ blob: Blob; ext: string }> {
  const format = videoFormat();
  if (!format) throw new Error("This browser can't record video.");
  const { canvas, ctx, scale } = canvasFor(source, 1280);
  // Even dimensions, which video encoders need.
  canvas.width -= canvas.width % 2;
  canvas.height -= canvas.height % 2;
  const stream = canvas.captureStream(opts.fps);
  const recorder = new MediaRecorder(stream, { mimeType: format.mime, videoBitsPerSecond: 6_000_000 });
  const chunks: Blob[] = [];
  recorder.ondataavailable = (e) => {
    if (e.data.size) chunks.push(e.data);
  };
  const stopped = new Promise<void>((resolve) => {
    recorder.onstop = () => resolve();
  });
  const times = frameTimes(opts);
  const draw = (t: number) => {
    ctx.save();
    ctx.scale(scale, scale);
    source.draw(ctx, t);
    ctx.restore();
  };
  draw(0);
  recorder.start();
  const start = performance.now();
  for (const [i, t] of times.entries()) {
    draw(t);
    opts.onProgress?.((i + 1) / times.length);
    const due = start + ((i + 1) * 1000) / opts.fps;
    await new Promise((r) => setTimeout(r, Math.max(0, due - performance.now())));
  }
  recorder.stop();
  await stopped;
  return { blob: new Blob(chunks, { type: format.mime.split(";")[0] }), ext: format.ext };
}

/** Save a file the user asked for. */
export function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
