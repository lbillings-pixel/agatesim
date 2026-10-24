import { describe, expect, it } from "vitest";

import type { LibraryImage } from "../api";
import { draftFor, nextIndex, toggle } from "./labels";

const image = (id: string, over: Partial<LibraryImage> = {}): LibraryImage => ({
  id,
  title: id,
  source: "",
  author: "a",
  licence: "CC BY 4.0",
  licence_url: "",
  guesses: [],
  fetched: true,
  label: null,
  ...over,
});

describe("labelling", () => {
  it("pre-selects guesses only until a label is saved", () => {
    expect(draftFor(image("a", { guesses: ["moss"] }))).toMatchObject({
      label: { forms: ["moss"] },
      guessed: true,
    });
    const saved = {
      verdict: "cant-tell" as const,
      forms: [],
      sure: false,
      features: [],
      note: "",
    };
    expect(draftFor(image("a", { guesses: ["moss"], label: saved }))).toEqual({
      label: saved,
      guessed: false,
    });
  });

  it("toggles chips", () => {
    expect(toggle(["eye"], "moss")).toEqual(["eye", "moss"]);
    expect(toggle(["eye", "moss"], "eye")).toEqual(["moss"]);
  });

  it("steps to the next fetched photo the filter shows, wrapping round", () => {
    const done = {
      verdict: "unusable" as const,
      forms: [],
      sure: true,
      features: [],
      note: "",
    };
    const images = [image("a"), image("b", { label: done }), image("c", { fetched: false }), image("d")];
    expect(nextIndex(images, 0, "unlabelled")).toBe(3);
    expect(nextIndex(images, 3, "unlabelled")).toBe(0);
    expect(nextIndex(images, 0, "unlabelled", -1)).toBe(3);
    expect(nextIndex(images, 0, "labelled")).toBe(1);
    expect(nextIndex([image("a", { label: done })], 0, "unlabelled")).toBeNull();
  });
});
