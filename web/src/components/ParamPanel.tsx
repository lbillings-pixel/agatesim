import type { Nature } from "../api";
import { type Control, formatValue } from "../lib/schema";

const NATURE_HELP: Record<Nature, string> = {
  physical: "A measurable environmental condition.",
  effective: "A model coefficient with no direct measurement.",
  imposed: "Sets a property of the result directly (procedural models only).",
};

interface SliderProps {
  id: string;
  control: Control;
  value: number;
  onChange: (value: number) => void;
}

export function Slider({ id, control, value, onChange }: SliderProps) {
  return (
    <div className="param">
      <div className="param-head">
        <label htmlFor={id} title={control.description}>
          {control.label}
        </label>
        <span className={`nature nature-${control.nature}`} title={NATURE_HELP[control.nature]}>
          {control.nature}
        </span>
        <output htmlFor={id} className="param-value">
          {formatValue(value, control.step)}
          {control.units && <span className="units"> {control.units}</span>}
        </output>
      </div>
      <input
        id={id}
        type="range"
        min={control.min}
        max={control.max}
        step={control.step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      {control.description && <p className="param-help">{control.description}</p>}
    </div>
  );
}

interface Props {
  controls: Control[];
  values: Record<string, unknown>;
  onChange: (key: string, value: number) => void;
}

export function ParamPanel({ controls, values, onChange }: Props) {
  return (
    <div className="params">
      {controls.map((c) => (
        <Slider
          key={c.key}
          id={`param-${c.key}`}
          control={c}
          value={typeof values[c.key] === "number" ? (values[c.key] as number) : c.defaultValue}
          onChange={(v) => onChange(c.key, v)}
        />
      ))}
    </div>
  );
}
