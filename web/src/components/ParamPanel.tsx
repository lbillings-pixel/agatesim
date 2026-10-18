import type { Nature } from "../api";
import { type Choice, type Control, type Field, formatValue, isPrimary, isUsed } from "../lib/schema";

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
  onChange: (path: string[], value: number | string | boolean) => void;
  idPrefix?: string;
}

/** The preset whose values a group's settings match, or "" for custom values. */
export function matchingPreset(
  presets: Record<string, Record<string, number>>,
  fields: Field[],
  values: Record<string, unknown>,
): string {
  const numbers = fields.filter((f) => f.type === "number");
  const valueOf = (f: (typeof numbers)[number]) => {
    const v = values[f.key];
    return typeof v === "number" ? v : f.type === "number" ? f.defaultValue : 0;
  };
  for (const [name, preset] of Object.entries(presets)) {
    if (numbers.every((f) => Math.abs(valueOf(f) - (preset[f.key] ?? 0)) < 1e-9)) return name;
  }
  return "";
}

/** A model's settings: sliders for numbers, menus for choices, and a collapsible
 * section for each nested model (such as one stage of a staged model). Key
 * settings come first; the rest wait under "More settings". Settings that don't
 * matter for the current choices (a stage the order leaves out) are hidden. */
export function ParamPanel({ fields, values, onChange, idPrefix = "param" }: Props) {
  const visible = fields.filter((f) => isUsed(f, values, fields));
  const primary = visible.filter(isPrimary);
  const rest = visible.filter((f) => !isPrimary(f));
  const render = (f: Field) => {
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
      case "toggle":
        return (
          <div key={f.key} className="param">
            <label className="inline" title={f.description}>
              <input
                id={id}
                type="checkbox"
                checked={typeof value === "boolean" ? value : f.defaultValue}
                onChange={(e) => onChange([f.key], e.target.checked)}
              />
              {f.label}
            </label>
            {f.description && <p className="param-help">{f.description}</p>}
          </div>
        );
      case "group": {
        const inner = typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
        const presets = f.presets;
        return (
          <details key={f.key} className="param-group">
            <summary title={f.description}>{f.label}</summary>
            {f.description && <p className="param-help">{f.description}</p>}
            {presets && (
              <div className="param">
                <div className="param-head">
                  <label htmlFor={`${id}-preset`}>Ready-made</label>
                </div>
                <select
                  id={`${id}-preset`}
                  value={matchingPreset(presets, f.fields, inner)}
                  onChange={(e) => {
                    const chosen = presets[e.target.value];
                    if (!chosen) return;
                    for (const g of f.fields) {
                      if (g.type === "number") onChange([f.key, g.key], chosen[g.key] ?? 0);
                    }
                  }}
                >
                  <option value="" disabled>
                    Custom
                  </option>
                  {Object.keys(presets).map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <ParamPanel
              fields={f.fields}
              values={inner}
              onChange={(path, v) => onChange([f.key, ...path], v)}
              idPrefix={id}
            />
          </details>
        );
      }
    }
  };
  if (primary.length === 0 || rest.length === 0) return <div className="params">{visible.map(render)}</div>;
  return (
    <div className="params">
      {primary.map(render)}
      <details className="more-settings">
        <summary>More settings ({rest.length})</summary>
        {rest.map(render)}
      </details>
    </div>
  );
}
