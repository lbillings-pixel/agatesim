import { describe, expect, it } from "vitest";

import type { LibraryImage, LibraryLabel } from "../api";
import {
  applyAnswers,
  checkQueue,
  checkTags,
  draftFor,
  draftFromAnswer,
  nextIndex,
  toggle,
} from "./labels";

const image = (id: string, over: Partial<LibraryImage> = {}): LibraryImage => ({
  id,
  title: id,
  source: "",
  author: "a",
  licence: "CC BY 4.0",
  licence_url: "",
  guesses: [],
  guessed_features: [],
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
    expect(draftFor(image("a", { guessed_features: ["host rock"] }))).toMatchObject({
      label: { forms: [], features: ["host rock"] },
      guessed: true,
    });
    const saved = {
      verdict: "cant-tell" as const,
      forms: [],
      sure: false,
      features: [],
      unsure: [],
      reviewed: false,
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
      unsure: [],
      reviewed: false,
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

describe("the owner's photos", () => {
  it("open with the classifier's likely forms as guesses, or the saved label", () => {
    const fresh = draftFromAnswer(null, ["moss", "fortification"]);
    expect(fresh.guessed).toBe(true);
    expect(fresh.label.forms).toEqual(["moss", "fortification"]);
    expect(draftFromAnswer(null, []).guessed).toBe(false);
    const saved = { verdict: "cant-tell" as const, forms: [], sure: false, features: [], unsure: [], reviewed: false, note: "" };
    const kept = draftFromAnswer(saved, ["moss"]);
    expect(kept).toEqual({ label: saved, guessed: false });
    expect(kept.label).not.toBe(saved);
  });
});
const label = (over: Partial<LibraryLabel> = {}): LibraryLabel => ({
  verdict: "forms",
  forms: ["fortification"],
  sure: true,
  features: [],
  unsure: [],
  reviewed: false,
  note: "",
  ...over,
});

const MAP_TAGS = ["quartz core", "open cavity", "host rock", "moss", "tube", "plume"];

describe("checking tags", () => {
  it("lists a photo's map tags, listed or unsure", () => {
    const l = label({ forms: ["fortification", "tube"], features: ["inclusions"], unsure: ["moss"] });
    expect(checkTags(l, MAP_TAGS)).toEqual(["moss", "tube"]);
    expect(checkTags(label({ verdict: "unusable", forms: [] }), MAP_TAGS)).toEqual([]);
    expect(checkTags(null, MAP_TAGS)).toEqual([]);
  });

  it("queues unchecked photos with map tags, tube first", () => {
    const images = [
      image("qc", { label: label({ features: ["quartz core"] }) }),
      image("plain", { label: label() }),
      image("tube", { label: label({ forms: ["tube"] }) }),
      image("done", { label: label({ forms: ["tube"], reviewed: true }) }),
      image("away", { fetched: false, label: label({ forms: ["tube"] }) }),
    ];
    expect(checkQueue(images, MAP_TAGS)).toEqual([2, 0]);
  });

  it("keeps yes, removes no and sets aside not sure", () => {
    const forms = new Set(["fortification", "tube", "moss"]);
    const l = label({ forms: ["fortification", "tube", "moss"], features: ["quartz core"], unsure: ["plume"] });
    const out = applyAnswers(l, { tube: "no", moss: "unsure", "quartz core": "yes", plume: "yes" }, forms);
    expect(out.forms).toEqual(["fortification"]);
    expect(out.features).toEqual(["quartz core", "plume"]);
    expect(out.unsure).toEqual(["moss"]);
    expect(out.reviewed).toBe(true);
    expect(out.verdict).toBe("forms");
  });

  it("marks a photo left with no forms as can't tell", () => {
    const out = applyAnswers(label({ forms: ["moss"] }), { moss: "no" }, new Set(["moss"]));
    expect(out.verdict).toBe("cant-tell");
    expect(out.forms).toEqual([]);
  });
});
