import type { Nature } from "../api";
import { type Choice, type Control, type Field, formatValue } from "../lib/schema";

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

interface ChoiceMenuProps {
  id: string;
  choice: Choice;
  value: string;
  onChange: (value: string) => void;
}

export function ChoiceMenu({ id, choice, value, onChange }: ChoiceMenuProps) {
  return (
    <div className="param">
      <div className="param-head">
        <label htmlFor={id} title={choice.description}>
          {choice.label}
        </label>
      </div>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {choice.options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      {choice.description && <p className="param-help">{choice.description}</p>}
    </div>
  );
}

interface Props {
  fields: Field[];
  values: Record<string, unknown>;
  /** A setting changed; `path` holds the keys from the model down to it. */
  onChange: (path: string[], value: number | string) => void;
  idPrefix?: string;
}

/** A model's settings: sliders for numbers, menus for choices, and a collapsible
 * section for each nested model (such as one stage of a staged model). */
export function ParamPanel({ fields, values, onChange, idPrefix = "param" }: Props) {
  return (
    <div className="params">
      {fields.map((f) => {
        const id = `${idPrefix}-${f.key}`;
        const value = values[f.key];
        switch (f.type) {
          case "number":
            return (
              <Slider
                key={f.key}
                id={id}
                control={f}
                value={typeof value === "number" ? value : f.defaultValue}
                onChange={(v) => onChange([f.key], v)}
              />
            );
          case "choice":
            return (
              <ChoiceMenu
                key={f.key}
                id={id}
                choice={f}
                value={typeof value === "string" ? value : f.defaultValue}
                onChange={(v) => onChange([f.key], v)}
              />
            );
          case "group":
            return (
              <details key={f.key} className="param-group">
                <summary title={f.description}>{f.label}</summary>
                {f.description && <p className="param-help">{f.description}</p>}
                <ParamPanel
                  fields={f.fields}
                  values={typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {}}
                  onChange={(path, v) => onChange([f.key, ...path], v)}
                  idPrefix={id}
                />
              </details>
            );
        }
      })}
    </div>
  );
}
