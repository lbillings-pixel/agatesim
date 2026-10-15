import type { CavityInfo } from "../api";
import { chaikin, fitToBox, type Point } from "../lib/outline";

const HOSTS: { host: CavityInfo["host"]; label: string }[] = [
  { host: "volcanic", label: "Volcanic vesicles" },
  { host: "sedimentary", label: "Sedimentary nodules" },
  { host: "seam", label: "Seams" },
];

function outlinePoints(outline: [number, number][]): string {
  // World y points up; SVG y points down.
  return outline.map(([x, y]) => `${x.toFixed(4)},${(-y).toFixed(4)}`).join(" ");
}

interface Props {
  cavities: CavityInfo[];
  /** The selected preset, or null when a drawn shape is in use. */
  selected: string | null;
  drawn: { outline: Point[]; smooth: boolean } | null;
  onSelect: (name: string) => void;
  /** Switch back to the drawn shape. */
  onUseDrawn: () => void;
  /** Open the drawing tool, editing the drawn shape or starting afresh. */
  onDraw: (edit: boolean) => void;
}

export function CavityMenu({ cavities, selected, drawn, onSelect, onUseDrawn, onDraw }: Props) {
  return (
    <div className="cavity-menu">
      {HOSTS.map(({ host, label }) => (
        <div key={host} className="cavity-group">
          <div className="micro-label">{label}</div>
          <div className="cavity-row" role="radiogroup" aria-label={label}>
            {cavities
              .filter((c) => c.host === host)
              .map((c) => (
                <button
                  key={c.name}
                  type="button"
                  role="radio"
                  aria-checked={c.name === selected}
                  className={`cavity-option host-${c.host}`}
                  title={`${c.name}: ${c.description}`}
                  onClick={() => onSelect(c.name)}
                >
                  <svg viewBox="-0.6 -0.6 1.2 1.2" aria-hidden="true">
                    <polygon points={outlinePoints(c.outline)} />
                  </svg>
                  <span>{c.name.split("-")[1]}</span>
                </button>
              ))}
          </div>
        </div>
      ))}
      <div className="cavity-group">
        <div className="micro-label">Your own</div>
        <div className="cavity-row">
          {drawn && (
            <button
              type="button"
              role="radio"
              aria-checked={selected === null}
              className="cavity-option"
              title={selected === null ? "Your drawn shape. Click to edit it." : "Use your drawn shape"}
              onClick={selected === null ? () => onDraw(true) : onUseDrawn}
            >
              <svg viewBox="-0.6 -0.6 1.2 1.2" aria-hidden="true">
                <polygon points={outlinePoints(fitToBox(drawn.smooth ? chaikin(drawn.outline) : drawn.outline, 1))} />
              </svg>
              <span>drawn</span>
            </button>
          )}
          <button type="button" className="cavity-option draw-option" onClick={() => onDraw(false)} title="Draw a cavity outline">
            <svg viewBox="-0.6 -0.6 1.2 1.2" aria-hidden="true">
              <path d="M -0.35 0.3 L 0.25 -0.3 L 0.35 -0.2 L -0.25 0.4 Z M -0.35 0.3 L -0.42 0.47 L -0.25 0.4" />
            </svg>
            <span>{drawn ? "new" : "draw…"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
