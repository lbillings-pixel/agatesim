import { useCallback, useEffect, useRef, useState } from "react";

import { applyGrowth } from "../lib/growth";

const VOID_COLOUR = [18, 18, 22] as const; // matches render.VOID
const SCALE_BAR_MM = [1, 2, 5, 10, 20, 50];

async function loadPixels(src: string): Promise<ImageData> {
  const image = new Image();
  image.src = src;
  await image.decode();
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("canvas unavailable");
  ctx.drawImage(image, 0, 0);
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}

/** Clicking the slab to place things (tubes), in world mm. */
export interface Picking {
  grid: { x0: number; y1: number; dx: number };
  markers: { x: number; y: number; r: number }[];
  onPick: (x: number, y: number) => void;
}

const CLICK_SLOP_PX = 4;

interface Props {
  picking?: Picking;
  imageSrc: string;
  tdepSrc: string;
  dxMm: number;
  caption: string;
  /** Changes whenever the slab is replaced, to reset zoom. */
  identity: string;
}

export function SlabView({ imageSrc, tdepSrc, dxMm, caption, identity, picking }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [pixels, setPixels] = useState<{ slab: ImageData; tdep: ImageData } | null>(null);
  const [growth, setGrowth] = useState(1);
  const [view, setView] = useState({ zoom: 1, x: 0, y: 0 });
  const [fit, setFit] = useState(1);
  const [origin, setOrigin] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; startX: number; startY: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([loadPixels(imageSrc), loadPixels(tdepSrc)])
      .then(([slab, tdep]) => {
        if (!cancelled) setPixels({ slab, tdep });
      })
      .catch(() => {
        if (!cancelled) setPixels(null);
      });
    return () => {
      cancelled = true;
    };
  }, [imageSrc, tdepSrc]);

  // Reset zoom when a different slab is shown (adjusting state during render,
  // as React recommends, rather than in an effect).
  const [shown, setShown] = useState(identity);
  if (shown !== identity) {
    setShown(identity);
    setView({ zoom: 1, x: 0, y: 0 });
  }

  // Draw the slab at the chosen point in its growth.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !pixels) return;
    const { slab, tdep } = pixels;
    canvas.width = slab.width;
    canvas.height = slab.height;
    const out = new ImageData(slab.width, slab.height);
    applyGrowth(slab.data, tdep.data, growth, VOID_COLOUR, out.data);
    canvas.getContext("2d")?.putImageData(out, 0, 0);
  }, [pixels, growth]);

  // Fit the slab to its frame, centred.
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame || !pixels) return;
    const update = () => {
      const f = Math.min(frame.clientWidth / pixels.slab.width, frame.clientHeight / pixels.slab.height);
      setFit(f);
      setOrigin({
        x: (frame.clientWidth - pixels.slab.width * f) / 2,
        y: (frame.clientHeight - pixels.slab.height * f) / 2,
      });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(frame);
    return () => observer.disconnect();
  }, [pixels]);

  // Zoom about the cursor. Registered natively: React's wheel listeners are passive,
  // so they can't stop the page from scrolling.
  const onWheel = useCallback(
    (e: WheelEvent) => {
      const frame = frameRef.current;
      if (!frame) return;
      e.preventDefault();
      const rect = frame.getBoundingClientRect();
      const px = e.clientX - rect.left - origin.x;
      const py = e.clientY - rect.top - origin.y;
      setView((v) => {
        const zoom = Math.min(16, Math.max(1, v.zoom * (e.deltaY < 0 ? 1.2 : 1 / 1.2)));
        const k = zoom / v.zoom;
        return zoom === 1 ? { zoom, x: 0, y: 0 } : { zoom, x: px - (px - v.x) * k, y: py - (py - v.y) * k };
      });
    },
    [origin],
  );

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    frame.addEventListener("wheel", onWheel, { passive: false });
    return () => frame.removeEventListener("wheel", onWheel);
  }, [onWheel]);

  const scale = fit * view.zoom; // screen px per slab px
  const barMm = SCALE_BAR_MM.find((mm) => (mm / dxMm) * scale >= 60) ?? SCALE_BAR_MM.at(-1) ?? 10;
  const barPx = (barMm / dxMm) * scale;
  const width = pixels ? pixels.slab.width * fit : 0;
  const height = pixels ? pixels.slab.height * fit : 0;

  return (
    <figure className="slab-view">
      <div
        ref={frameRef}
        className={`slab-frame${picking ? " picking" : ""}`}
        onPointerDown={(e) => {
          drag.current = { x: e.clientX - view.x, y: e.clientY - view.y, startX: e.clientX, startY: e.clientY };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (drag.current && view.zoom > 1) {
            const start = drag.current;
            setView((v) => ({ ...v, x: e.clientX - start.x, y: e.clientY - start.y }));
          }
        }}
        onPointerUp={(e) => {
          const start = drag.current;
          drag.current = null;
          if (!picking || !start || !frameRef.current) return;
          if (Math.hypot(e.clientX - start.startX, e.clientY - start.startY) > CLICK_SLOP_PX) return;
          const rect = frameRef.current.getBoundingClientRect();
          const col = (e.clientX - rect.left - origin.x - view.x) / scale;
          const row = (e.clientY - rect.top - origin.y - view.y) / scale;
          if (!pixels || col < 0 || row < 0 || col > pixels.slab.width || row > pixels.slab.height) return;
          const { x0, y1, dx } = picking.grid;
          picking.onPick(x0 + col * dx, y1 - row * dx);
        }}
        onDoubleClick={() => setView({ zoom: 1, x: 0, y: 0 })}
      >
        <canvas
          ref={canvasRef}
          className={view.zoom >= 4 ? "pixelated" : undefined}
          style={{
            width,
            height,
            transform: `translate(${origin.x + view.x}px, ${origin.y + view.y}px) scale(${view.zoom})`,
          }}
        />
        {pixels && picking && (
          <svg
            className="slab-markers"
            viewBox={`0 0 ${pixels.slab.width} ${pixels.slab.height}`}
            style={{
              width,
              height,
              transform: `translate(${origin.x + view.x}px, ${origin.y + view.y}px) scale(${view.zoom})`,
            }}
            aria-hidden="true"
          >
            {picking.markers.map((m, i) => (
              <circle
                key={i}
                cx={(m.x - picking.grid.x0) / picking.grid.dx}
                cy={(picking.grid.y1 - m.y) / picking.grid.dx}
                r={m.r / picking.grid.dx + 6 / scale}
              />
            ))}
          </svg>
        )}
        {pixels && (
          <div className="scale-bar" aria-label={`Scale bar: ${barMm} mm`}>
            <div style={{ width: barPx }} />
            <span>{barMm} mm</span>
          </div>
        )}
        {view.zoom > 1 && <div className="zoom-badge">{view.zoom.toFixed(1)}×</div>}
      </div>
      <div className="growth">
        <label htmlFor={`growth-${identity}`}>Growth</label>
        <input
          id={`growth-${identity}`}
          type="range"
          min={0}
          max={1}
          step={0.005}
          value={growth}
          onChange={(e) => setGrowth(Number(e.target.value))}
        />
        <output htmlFor={`growth-${identity}`}>{Math.round(growth * 100)}%</output>
      </div>
      <figcaption>
        {caption}
        <span className="hint">
          {picking ? " · click to add a tube or remove one" : ""} · scroll to zoom, drag to pan, double-click to reset
        </span>
      </figcaption>
    </figure>
  );
}
