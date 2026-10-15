// Turn a model's JSON schema (pydantic, with our units/nature extras) into slider controls.

import type { JsonSchemaProperty, Nature } from "../api";

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

const UNIT_SUFFIXES = ["_mm", "_deg"];

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
