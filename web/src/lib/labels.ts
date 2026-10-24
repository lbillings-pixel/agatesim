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
