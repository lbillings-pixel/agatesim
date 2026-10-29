import type { LibraryImage, LibraryLabel } from "../api";

/** The labels a photo opens with: its saved labels, or else its guessed
 * forms and features pre-selected (marked as guesses until saved). */
export function draftFor(image: LibraryImage): {
  label: LibraryLabel;
  guessed: boolean;
} {
  if (image.label) return { label: { ...image.label }, guessed: false };
  return {
    label: {
      verdict: "forms",
      forms: [...image.guesses],
      sure: true,
      features: [...image.guessed_features],
      unsure: [],
      reviewed: false,
      note: "",
    },
    guessed: image.guesses.length > 0 || image.guessed_features.length > 0,
  };
}

export function toggle(list: string[], item: string): string[] {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
}

export type Filter = "unlabelled" | "labelled" | "all";

export function matches(image: LibraryImage, filter: Filter): boolean {
  return filter === "all" || (filter === "labelled") === (image.label !== null);
}

/** The next photo after `from` (wrapping round) that the filter shows and has
 * been fetched; null if there is none. */
export function nextIndex(images: LibraryImage[], from: number, filter: Filter, step = 1): number | null {
  const n = images.length;
  for (let k = 1; k <= n; k++) {
    const i = (((from + step * k) % n) + n) % n;
    const image = images[i];
    if (image?.fetched && matches(image, filter)) return i;
  }
  return null;
}

/** The label one of the owner's photos opens with: their saved label, or else
 * the classifier's likely forms pre-selected (marked as guesses until saved). */
export function draftFromAnswer(
  saved: LibraryLabel | null,
  likely: string[],
): {
  label: LibraryLabel;
  guessed: boolean;
} {
  if (saved) return { label: { ...saved }, guessed: false };
  return {
    label: {
      verdict: "forms",
      forms: [...likely],
      sure: true,
      features: [],
      unsure: [],
      reviewed: false,
      note: "",
    },
    guessed: likely.length > 0,
  };
}

/** A tag check's answer for one tag (ADR 0071). */
export type Answer = "yes" | "no" | "unsure";

/** Map tags checked first: the rarest and most often mistaken. */
const CHECK_FIRST = ["tube", "plume", "moss", "host rock", "open cavity", "quartz core"];

/** A photo's map tags to check, listed or unsure, in `mapTags` order. */
export function checkTags(label: LibraryLabel | null, mapTags: string[]): string[] {
  if (!label || label.verdict !== "forms") return [];
  const tags = new Set([...label.forms, ...label.features, ...label.unsure]);
  return mapTags.filter((t) => tags.has(t));
}

/** The photos still to check, fetched ones with map tags, tube, plume and
 * moss photos first; as indexes into `images`. */
export function checkQueue(images: LibraryImage[], mapTags: string[]): number[] {
  const rank = (tags: string[]) =>
    Math.min(...tags.map((t) => (CHECK_FIRST.includes(t) ? CHECK_FIRST.indexOf(t) : CHECK_FIRST.length)));
  return images
    .map((image, i) => ({ i, tags: image.fetched && !image.label?.reviewed ? checkTags(image.label, mapTags) : [] }))
    .filter((x) => x.tags.length > 0)
    .sort((a, b) => rank(a.tags) - rank(b.tags) || a.i - b.i)
    .map((x) => x.i);
}

/** The label after a check: yes keeps a tag listed, no removes it, unsure
 * moves it to `unsure`; `forms` tells forms from features. A photo left
 * with no forms can't be told. */
export function applyAnswers(label: LibraryLabel, answers: Record<string, Answer>, forms: Set<string>): LibraryLabel {
  const asked = Object.keys(answers);
  const keep = (list: string[]) => list.filter((t) => !asked.includes(t));
  const yes = asked.filter((t) => answers[t] === "yes");
  const out: LibraryLabel = {
    ...label,
    forms: [...keep(label.forms), ...yes.filter((t) => forms.has(t))],
    features: [...keep(label.features), ...yes.filter((t) => !forms.has(t))],
    unsure: [...keep(label.unsure), ...asked.filter((t) => answers[t] === "unsure")],
    reviewed: true,
  };
  return out.forms.length > 0 ? out : { ...out, verdict: "cant-tell" };
}
