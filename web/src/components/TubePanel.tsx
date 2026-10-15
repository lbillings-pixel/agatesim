import type { Tube } from "../api";
import { Slider } from "./ParamPanel";
import type { Control } from "../lib/schema";

const RADIUS_CONTROL: Control = {
  key: "radius_mm",
  label: "New tube radius",
  units: "mm",
  nature: "physical",
  description: "Radius of the filament at the centre of each tube.",
  min: 0.1,
  max: 3,
  step: 0.05,
  defaultValue: 0.3,
};

interface Props {
  tubes: Tube[];
  placing: boolean;
  radius: number;
  onPlacing: (on: boolean) => void;
  onRadius: (r: number) => void;
  onClear: () => void;
}

/** Tubes: filaments crossing the slab, placed by clicking the live preview. */
export function TubePanel({ tubes, placing, radius, onPlacing, onRadius, onClear }: Props) {
  return (
    <div className="tubes">
      <div className="tubes-head">
        <button type="button" aria-pressed={placing} className={placing ? "primary" : undefined} onClick={() => onPlacing(!placing)}>
          {placing ? "Done placing tubes" : "Place tubes"}
        </button>
        <span className="muted small">
          {tubes.length === 0 ? "none" : `${tubes.length} tube${tubes.length === 1 ? "" : "s"}`}
        </span>
        {tubes.length > 0 && (
          <button type="button" className="link" onClick={onClear}>
            Clear
          </button>
        )}
      </div>
      {placing && (
        <>
          <p className="param-help">
            Click the live preview to add a tube where a filament crosses the slab; click a tube to remove it. The
            growth-history model grows banding around them.
          </p>
          <Slider id="tube-radius" control={RADIUS_CONTROL} value={radius} onChange={onRadius} />
        </>
      )}
    </div>
  );
}
