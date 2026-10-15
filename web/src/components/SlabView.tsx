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

interface Props {
  imageSrc: string;
  tdepSrc: string;
  dxMm: number;
  caption: string;
  /** Changes whenever the slab is replaced, to reset zoom. */
  identity: string;
}

export function SlabView({ imageSrc, tdepSrc, dxMm, caption, identity }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [pixels, setPixels] = useState<{ slab: ImageData; tdep: ImageData } | null>(null);
  const [growth, setGrowth] = useState(1);
  const [view, setView] = useState({ zoom: 1, x: 0, y: 0 });
  const [fit, setFit] = useState(1);
  const [origin, setOrigin] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);

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
        className="slab-frame"
        onPointerDown={(e) => {
          drag.current = { x: e.clientX - view.x, y: e.clientY - view.y };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (drag.current && view.zoom > 1) {
            const start = drag.current;
            setView((v) => ({ ...v, x: e.clientX - start.x, y: e.clientY - start.y }));
          }
        }}
        onPointerUp={() => {
          drag.current = null;
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
        <span className="hint"> · scroll to zoom, drag to pan, double-click to reset</span>
      </figcaption>
    </figure>
  );
}
