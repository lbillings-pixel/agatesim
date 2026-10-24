import type { LibraryImage, LibraryLabel } from "../api";

/** The labels a photo opens with: its saved labels, or else its guesses
 * pre-selected (marked as guesses until saved). */
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
      features: [],
      note: "",
    },
    guessed: image.guesses.length > 0,
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
    label: { verdict: "forms", forms: [...likely], sure: true, features: [], note: "" },
    guessed: likely.length > 0,
  };
}
