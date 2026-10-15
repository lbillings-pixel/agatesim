import { useEffect, useRef, useState } from "react";

import type { Host } from "../api";
import { chaikin, fitToBox, MAX_POINTS, outlineProblem, type Point, strokeToOutline } from "../lib/outline";

// The drawing area is a unit square in screen orientation (y down). Outlines are
// stored with y up, like world coordinates; only their shape matters, since the
// size slider sets the scale.
const VIEW = 1;
const CLOSE_RADIUS = 0.03; // clicking this near the first corner closes the shape
const STROKE_STEP = 0.004; // freehand points closer than this are skipped
const SIMPLIFY = 0.003; // freehand simplification tolerance

type Mode = "corners" | "freehand";

export interface Drawn {
  outline: Point[];
  host: Host;
  smooth: boolean;
}

const toStored = (p: Point[]): Point[] => p.map(([x, y]) => [round(x - 0.5), round(0.5 - y)]);
const fromStored = (p: Point[]): Point[] => fitToBox(p, 0.8).map(([x, y]) => [x + 0.5, 0.5 - y]);
const round = (v: number) => Math.round(v * 1e5) / 1e5;
const svgPoints = (p: Point[]) => p.map(([x, y]) => `${x.toFixed(4)},${y.toFixed(4)}`).join(" ");

interface Props {
  initial: Drawn | null;
  onUse: (drawn: Drawn) => void;
  onCancel: () => void;
}

export function CavityDrawer({ initial, onUse, onCancel }: Props) {
  const [mode, setMode] = useState<Mode>("corners");
  const [points, setPoints] = useState<Point[]>(() => (initial ? fromStored(initial.outline) : []));
  const [closed, setClosed] = useState(initial !== null);
  const [stroke, setStroke] = useState<Point[] | null>(null);
  const [host, setHost] = useState<Host>(initial?.host ?? "sedimentary");
  const [smooth, setSmooth] = useState(initial?.smooth ?? false);
  const [hover, setHover] = useState<Point | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const firstButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    firstButton.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const at = (e: React.PointerEvent): Point => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return [0, 0];
    const clamp = (v: number) => Math.min(VIEW, Math.max(0, v));
    return [clamp((e.clientX - rect.left) / rect.width), clamp((e.clientY - rect.top) / rect.height)];
  };

  const problem = points.length === 0 ? "draw a shape" : outlineProblem(points);
  const ready = closed && problem === null;
  const shown = smooth && ready ? chaikin(points) : points;

  const onPointerDown = (e: React.PointerEvent) => {
    const p = at(e);
    if (mode === "freehand") {
      e.currentTarget.setPointerCapture(e.pointerId);
      setStroke([p]);
      setPoints([]);
      setClosed(false);
      return;
    }
    if (closed) {
      setPoints([p]);
      setClosed(false);
      return;
    }
    const first = points[0];
    if (first && points.length >= 3 && Math.hypot(p[0] - first[0], p[1] - first[1]) < CLOSE_RADIUS) {
      setClosed(true);
    } else if (points.length < MAX_POINTS) {
      setPoints([...points, p]);
    }
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const p = at(e);
    setHover(p);
    if (mode !== "freehand" || !stroke) return;
    const last = stroke[stroke.length - 1];
    if (!last || Math.hypot(p[0] - last[0], p[1] - last[1]) >= STROKE_STEP) setStroke([...stroke, p]);
  };

  const onPointerUp = () => {
    if (mode !== "freehand" || !stroke) return;
    const outline = strokeToOutline(stroke, SIMPLIFY).slice(0, MAX_POINTS);
    setStroke(null);
    setPoints(outline);
    setClosed(outline.length >= 3);
  };

  const undo = () => {
    if (mode === "freehand") {
      setPoints([]);
      setClosed(false);
    } else if (closed) {
      setClosed(false);
    } else {
      setPoints(points.slice(0, -1));
    }
  };

  const hint =
    mode === "corners"
      ? closed
        ? "Shape closed. Click anywhere to start again."
        : points.length >= 3
          ? "Click to add corners; click the first corner to close the shape."
          : "Click to place the corners of the cavity wall."
      : "Press and drag to sketch the outline in one stroke; release to close it.";

  const first = points[0];
  const last = points[points.length - 1];

  return (
    <div className="dialog-backdrop" onPointerDown={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="dialog drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <header className="dialog-head">
          <h3 id="drawer-title">Draw a cavity</h3>
          <p className="muted small">
            Only the shape matters: the size and rotation sliders set its scale and orientation.
          </p>
        </header>

        <div className="drawer-tools">
          <div className="toggle" role="radiogroup" aria-label="Drawing tool">
            {(
              [
                ["corners", "Click corners"],
                ["freehand", "Freehand"],
              ] as const
            ).map(([m, label], i) => (
              <button
                key={m}
                ref={i === 0 ? firstButton : undefined}
                type="button"
                role="radio"
                aria-checked={mode === m}
                onClick={() => {
                  setMode(m);
                  setPoints([]);
                  setClosed(false);
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="toggle" role="radiogroup" aria-label="Wall">
            {(
              [
                [false, "Angular"],
                [true, "Smooth"],
              ] as const
            ).map(([s, label]) => (
              <button key={label} type="button" role="radio" aria-checked={smooth === s} onClick={() => setSmooth(s)}>
                {label}
              </button>
            ))}
          </div>
          <label className="inline">
            <span className="micro-label">Host</span>
            <select id="drawer-host" value={host} onChange={(e) => setHost(e.target.value as Host)}>
              <option value="volcanic">Volcanic</option>
              <option value="sedimentary">Sedimentary</option>
              <option value="seam">Seam</option>
            </select>
          </label>
        </div>

        <svg
          ref={svgRef}
          className={`drawer-canvas mode-${mode}`}
          viewBox={`0 0 ${VIEW} ${VIEW}`}
          role="img"
          aria-label="Drawing area"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={() => setHover(null)}
        >
          <defs>
            <pattern id="drawer-grid" width="0.1" height="0.1" patternUnits="userSpaceOnUse">
              <path d="M 0.1 0 L 0 0 0 0.1" className="grid-line" />
            </pattern>
          </defs>
          <rect width={VIEW} height={VIEW} fill="url(#drawer-grid)" />
          {closed ? (
            <polygon points={svgPoints(shown)} className={`shape${problem ? " bad" : ""}`} />
          ) : (
            <polyline points={svgPoints(stroke ?? points)} className="shape open" />
          )}
          {!closed && mode === "corners" && last && hover && (
            <line x1={last[0]} y1={last[1]} x2={hover[0]} y2={hover[1]} className="rubber" />
          )}
          {mode === "corners" &&
            points.map(([x, y], i) => (
              <circle key={i} cx={x} cy={y} r={i === 0 && !closed ? 0.012 : 0.007} className={i === 0 ? "corner first" : "corner"} />
            ))}
          {!closed && mode === "corners" && first && points.length >= 3 && (
            <circle cx={first[0]} cy={first[1]} r={CLOSE_RADIUS} className="close-target" />
          )}
        </svg>

        <p className={`small${closed && problem ? " drawer-problem" : " muted"}`} aria-live="polite">
          {closed && problem ? `This outline ${problem}.` : hint}
        </p>

        <footer className="dialog-foot">
          <button type="button" onClick={undo} disabled={points.length === 0}>
            Undo
          </button>
          <button
            type="button"
            onClick={() => {
              setPoints([]);
              setClosed(false);
            }}
            disabled={points.length === 0}
          >
            Clear
          </button>
          <span className="spacer" />
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className="primary"
            disabled={!ready}
            onClick={() => onUse({ outline: toStored(points), host, smooth })}
          >
            Use this shape
          </button>
        </footer>
      </div>
    </div>
  );
}
