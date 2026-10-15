import type { CavityInfo } from "../api";

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
  selected: string;
  onSelect: (name: string) => void;
}

export function CavityMenu({ cavities, selected, onSelect }: Props) {
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
    </div>
  );
}
