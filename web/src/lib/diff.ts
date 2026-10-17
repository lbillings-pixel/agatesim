// What differs between two run configurations, setting by setting.

import { labelFor } from "./schema";

/** Each leaf setting as "path → value", nested objects joined by "/". Lists (an
 * outline, tubes, schedule events) count as one setting each. */
export function flatten(value: unknown, prefix = ""): Record<string, string> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return { [prefix]: typeof value === "string" ? value : JSON.stringify(value) };
  }
  return Object.entries(value as Record<string, unknown>).reduce<Record<string, string>>(
    (out, [k, v]) => ({ ...out, ...flatten(v, prefix ? `${prefix}/${k}` : k) }),
    {},
  );
}

export interface SettingDiff {
  path: string;
  label: string;
  a: string | null;
  b: string | null;
}

/** Settings whose values differ between two configurations (the run name aside),
 * in a stable order; a setting only one of them has shows null for the other.
 * Runs of different models differ in their model kind alone: their models'
 * settings aren't comparable one by one. */
export function settingDiffs(a: object, b: object, ignore: string[] = ["name"]): SettingDiff[] {
  const fa = flatten(a);
  const fb = flatten(b);
  const sameModel = fa["model/kind"] === fb["model/kind"];
  const paths = [...new Set([...Object.keys(fa), ...Object.keys(fb)])].filter(
    (p) =>
      !ignore.includes(p.split("/")[0] ?? "") && (sameModel || !p.startsWith("model/") || p === "model/kind"),
  );
  return paths
    .filter((p) => fa[p] !== fb[p])
    .sort()
    .map((p) => ({
      path: p,
      label: p.split("/").map(labelFor).join(" › "),
      a: fa[p] ?? null,
      b: fb[p] ?? null,
    }));
}
