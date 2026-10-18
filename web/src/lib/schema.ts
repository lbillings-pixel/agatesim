// Turn a model's JSON schema (pydantic, with our units/nature extras) into slider controls.

import type { JsonSchemaProperty, ModelSchema, Nature } from "../api";

export interface Control {
  key: string;
  label: string;
  units: string;
  nature: Nature;
  description: string;
  min: number;
  max: number;
  step: number;
  defaultValue: number;
}

const UNIT_SUFFIXES = ["_mm", "_um", "_deg"];

export function labelFor(key: string): string {
  let base = key;
  for (const suffix of UNIT_SUFFIXES) {
    if (base.endsWith(suffix)) base = base.slice(0, -suffix.length);
  }
  const words = base.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** A step of about 1/200 of the range, rounded to 1, 2 or 5 × a power of ten. */
export function niceStep(range: number): number {
  if (!(range > 0)) return 0.01;
  const raw = range / 200;
  const power = 10 ** Math.floor(Math.log10(raw));
  const scaled = raw / power;
  const nice = scaled < 1.5 ? 1 : scaled < 3.5 ? 2 : scaled < 7.5 ? 5 : 10;
  return nice * power;
}

export function controlFor(key: string, p: JsonSchemaProperty): Control | null {
  if (p.type !== "number" && p.type !== "integer") return null;
  const defaultValue = typeof p.default === "number" ? p.default : 0;
  const units = p.units ?? "";
  let min = p.minimum ?? p.exclusiveMinimum ?? 0;
  let max = p.maximum ?? p.exclusiveMaximum;
  if (units === "deg") {
    min = 0;
    max = 359;
  }
  if (max === undefined) {
    // Unbounded above: offer a generous range around the default.
    max = Math.max(defaultValue * 4, min + 1);
  }
  const step = units === "deg" ? 1 : niceStep(max - min);
  if (p.exclusiveMinimum !== undefined && min === p.exclusiveMinimum) min += step;
  return {
    key,
    label: labelFor(key),
    units,
    nature: p.nature ?? "effective",
    description: p.description ?? "",
    min,
    max,
    step,
    defaultValue,
  };
}

export function controlsFor(properties: Record<string, JsonSchemaProperty>): Control[] {
  return Object.entries(properties)
    .map(([key, p]) => controlFor(key, p))
    .filter((c): c is Control => c !== null);
}

export function defaultsFor(properties: Record<string, JsonSchemaProperty>): Record<string, number> {
  return Object.fromEntries(controlsFor(properties).map((c) => [c.key, c.defaultValue]));
}

/** Format a value for display with precision matched to the control's step. */
export function formatValue(value: number, step: number): string {
  const decimals = Math.max(0, Math.min(4, -Math.floor(Math.log10(step))));
  return value.toFixed(decimals);
}

/** A choice among named options (a pydantic Literal), shown as a menu. */
export interface Choice {
  key: string;
  label: string;
  description: string;
  options: string[];
  defaultValue: string;
}

/** An on/off setting (a pydantic bool), shown as a checkbox. */
export interface Toggle {
  key: string;
  label: string;
  description: string;
  defaultValue: boolean;
}

/** A nested model's settings (for example one stage of a staged model), with any
 * ready-made values for them (`presets`, a palette's say). */
export interface Group {
  key: string;
  label: string;
  description: string;
  fields: Field[];
  presets?: Record<string, Record<string, number>>;
}

/** `primary` marks one of the model's key settings, shown first (a group is
 * primary when any of its settings is). */
export type Field = (
  | ({ type: "number" } & Control)
  | ({ type: "choice" } & Choice)
  | ({ type: "toggle" } & Toggle)
  | ({ type: "group" } & Group)
) & { usedWhen?: Record<string, string[]>[]; primary?: boolean };

function choiceFor(key: string, p: JsonSchemaProperty): Choice | null {
  const options = (p.enum ?? []).filter((o): o is string => typeof o === "string");
  if (options.length < 2) return null;
  return {
    key,
    label: labelFor(key),
    description: p.description ?? "",
    options,
    defaultValue: typeof p.default === "string" ? p.default : (options[0] ?? ""),
  };
}

/** Every setting of a model: numbers, choices, and nested models as groups. A nested
 * model's field that its parent also has is left out, since the parent's governs
 * (a staged model's gravity, for example). */
export function fieldsFor(schema: ModelSchema, properties = schema.properties): Field[] {
  return Object.entries(properties).flatMap(([key, p]): Field[] => {
    const ref = p.$ref?.match(/^#\/\$defs\/(.+)$/)?.[1];
    const nested = ref ? schema.$defs?.[ref] : undefined;
    if (nested) {
      const inner = Object.fromEntries(
        Object.entries(nested.properties).filter(([k]) => !(k in properties)),
      );
      const fields = fieldsFor(schema, inner);
      const group: Field = {
        type: "group",
        key,
        label: labelFor(key),
        description: p.description ?? "",
        fields,
        ...(nested.presets ? { presets: nested.presets } : {}),
        ...(fields.some(isPrimary) ? { primary: true } : {}),
      };
      return fields.length ? [withUse(group, p)] : [];
    }
    const choice = choiceFor(key, p);
    if (choice) return [withUse({ type: "choice", ...choice }, p)];
    if (p.type === "boolean") {
      const toggle: Field = {
        type: "toggle",
        key,
        label: labelFor(key),
        description: p.description ?? "",
        defaultValue: p.default === true,
      };
      return [withUse(toggle, p)];
    }
    const control = controlFor(key, p);
    return control ? [withUse({ type: "number", ...control }, p)] : [];
  });
}

function withUse(field: Field, p: JsonSchemaProperty): Field {
  const used = p.used_when ? { ...field, usedWhen: p.used_when } : field;
  return p.key ? { ...used, primary: true } : used;
}

/** Whether a field is one of the key settings shown first. */
export function isPrimary(field: Field): boolean {
  return field.primary === true;
}

/** Whether a field matters given its siblings' values (their defaults where unset):
 * for one of its `usedWhen` alternatives, each named sibling's value is one of the
 * listed values (on/off settings as "true" or "false"), or a stage order
 * ("wall-floor") with one of them as a stage. */
export function isUsed(field: Field, values: Record<string, unknown>, siblings: Field[]): boolean {
  if (!field.usedWhen) return true;
  const valueOf = (key: string): string => {
    const v = values[key];
    if (typeof v === "string" || typeof v === "boolean") return String(v);
    const sibling = siblings.find((f) => f.key === key);
    if (sibling?.type === "choice") return sibling.defaultValue;
    if (sibling?.type === "toggle") return String(sibling.defaultValue);
    return "";
  };
  return field.usedWhen.some((alt) =>
    Object.entries(alt).every(([key, wanted]) => {
      const v = valueOf(key);
      return wanted.includes(v) || v.split("-").some((part) => wanted.includes(part));
    }),
  );
}

/** A copy of `values` with the setting at `path` (keys into nested settings) replaced. */
export function withSetting(
  values: Record<string, unknown>,
  path: string[],
  value: unknown,
): Record<string, unknown> {
  const [key, ...rest] = path;
  if (key === undefined) return values;
  if (rest.length === 0) return { ...values, [key]: value };
  const inner = values[key];
  const nested = typeof inner === "object" && inner !== null ? (inner as Record<string, unknown>) : {};
  return { ...values, [key]: withSetting(nested, rest, value) };
}

/** The settings a model uses that are `imposed` (they set a property of the result
 * directly), with the values in `values` (defaults where unset), nested groups
 * included and labelled "Group › Setting". Settings that don't apply are left out. */
export function imposedSettings(
  fields: Field[],
  values: Record<string, unknown>,
): { label: string; value: number; units: string }[] {
  return fields
    .filter((f) => isUsed(f, values, fields))
    .flatMap((f) => {
      if (f.type === "group") {
        const inner = values[f.key];
        const nested = typeof inner === "object" && inner !== null ? (inner as Record<string, unknown>) : {};
        return imposedSettings(f.fields, nested).map((s) => ({ ...s, label: `${f.label} › ${s.label}` }));
      }
      if (f.type !== "number" || f.nature !== "imposed") return [];
      const v = values[f.key];
      return [{ label: f.label, value: typeof v === "number" ? v : f.defaultValue, units: f.units }];
    });
}
