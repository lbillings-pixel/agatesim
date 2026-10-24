import { useEffect, useState } from "react";

import { type LibraryIndex, type LibraryLabel, library } from "../api";
import {
  type Filter,
  draftFor,
  matches,
  nextIndex,
  toggle,
} from "../lib/labels";
import { TapLabeler } from "./TapLabeler";

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Label the reference library one photo at a time, by tapping chips (ADR 0066).
 * Only openly licensed library photos appear here, never the owner's own. */
export function ReferenceLabeler() {
  const [index, setIndex] = useState<LibraryIndex | null>(null);
  const [at, setAt] = useState<number | null>(null);
  const [filter, setFilter] = useState<Filter>("unlabelled");
  // Labelling tags, or tapping test points for the feature maps (ADR 0068).
  const [mode, setMode] = useState<"label" | "tap">("label");
  // Edits to the photo on screen; another photo opens with its own draft.
  const [edit, setEdit] = useState<{
    id: string;
    label: LibraryLabel;
    guessed: boolean;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    library.list().then(
      (i) => {
        setIndex(i);
        setAt(
          nextIndex(i.images, -1, "unlabelled") ??
            nextIndex(i.images, -1, "all"),
        );
      },
      (e: unknown) => setError(message(e)),
    );
  }, []);

  const image = index && at !== null ? (index.images[at] ?? null) : null;
  const current = image
    ? edit?.id === image.id
      ? edit
      : draftFor(image)
    : null;
  const draft = current?.label ?? null;
  const guessed = current?.guessed ?? false;

  if (error && !index) return <p className="error specimen-library">{error}</p>;
  if (!index) return <p className="specimen-library">Loading the library…</p>;

  const fetched = index.images.filter((i) => i.fetched).length;
  const labelled = index.images.filter((i) => i.label).length;
  const names = Object.fromEntries(index.forms.map((f) => [f.id, f.name]));

  const go = (step: number, f: Filter = filter) => {
    if (at === null) return;
    setAt(nextIndex(index.images, at, f, step));
    setError(null);
  };

  const save = (label: LibraryLabel) => {
    if (!image) return;
    setBusy(true);
    setError(null);
    library
      .label(image.id, label)
      .then(
        (saved) => {
          const images = index.images.map((i) =>
            i.id === image.id ? { ...i, label: saved } : i,
          );
          setIndex({ ...index, images });
          setAt(nextIndex(images, at ?? -1, filter) ?? at);
        },
        (e: unknown) => setError(message(e)),
      )
      .finally(() => setBusy(false));
  };

  const head = (
    <div className="library-head">
      <div className="tabs" role="tablist" aria-label="Mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "label"}
          onClick={() => setMode("label")}
        >
          Label
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "tap"}
          onClick={() => setMode("tap")}
        >
          Test taps
        </button>
      </div>
      {mode === "label" && (
        <p>
          {labelled} of {index.images.length} labelled
          {fetched < index.images.length &&
            ` · ${index.images.length - fetched} not fetched yet`}
        </p>
      )}
      {mode === "label" && (
        <label>
          Show{" "}
          <select
            value={filter}
            onChange={(e) => {
              const f = e.target.value as Filter;
              setFilter(f);
              if (image && !matches(image, f)) go(1, f);
            }}
          >
            <option value="unlabelled">unlabelled</option>
            <option value="labelled">labelled</option>
            <option value="all">all</option>
          </select>
        </label>
      )}
    </div>
  );

  if (mode === "tap")
    return (
      <div className="specimen-library labeler">
        {head}
        <TapLabeler index={index} />
      </div>
    );

  if (!image || !draft)
    return (
      <div className="specimen-library">
        {head}
        <p>
          {index.images.length === 0
            ? "The library list hasn't been built yet."
            : fetched === 0
              ? "No library photos have been fetched yet."
              : "Nothing left to show here. Try another filter."}
        </p>
      </div>
    );

  const set = (patch: Partial<LibraryLabel>) =>
    setEdit({ id: image.id, label: { ...draft, ...patch }, guessed: false });

  return (
    <div className="specimen-library labeler">
      {head}
      <figure className="labeler-photo">
        <img src={library.imageUrl(image.id)} alt={image.title} />
        <figcaption className="muted">
          <a href={image.source} target="_blank" rel="noreferrer">
            {image.title}
          </a>{" "}
          · {image.author} ·{" "}
          <a href={image.licence_url} target="_blank" rel="noreferrer">
            {image.licence}
          </a>
          {image.label &&
            ` · labelled ${image.label.verdict === "forms" ? "" : image.label.verdict}`}
        </figcaption>
      </figure>
      <fieldset className="chips">
        <legend>
          Forms it shows
          {guessed && (
            <span className="muted"> (guessed from its title: check them)</span>
          )}
        </legend>
        {index.forms.map((f) => (
          <button
            key={f.id}
            type="button"
            className={`chip${guessed && draft.forms.includes(f.id) ? " guess" : ""}`}
            aria-pressed={draft.forms.includes(f.id)}
            onClick={() =>
              set({ forms: toggle(draft.forms, f.id), verdict: "forms" })
            }
            title={f.name}
          >
            {f.id}
          </button>
        ))}
      </fieldset>
      <fieldset className="chips">
        <legend>Features</legend>
        {index.features.map((f) => (
          <button
            key={f}
            type="button"
            className="chip"
            aria-pressed={draft.features.includes(f)}
            onClick={() => set({ features: toggle(draft.features, f) })}
          >
            {f}
          </button>
        ))}
        <button
          type="button"
          className="chip"
          aria-pressed={!draft.sure}
          onClick={() => set({ sure: !draft.sure })}
        >
          not sure
        </button>
      </fieldset>
      {draft.forms.length > 0 && (
        <p className="muted">
          {draft.forms.map((f) => names[f] ?? f).join(" · ")}
        </p>
      )}
      {error && <p className="error">{error}</p>}
      <div className="labeler-actions">
        <button type="button" onClick={() => go(-1)} disabled={busy}>
          Back
        </button>
        <button
          type="button"
          className="primary"
          disabled={busy || draft.forms.length === 0}
          onClick={() => save({ ...draft, verdict: "forms" })}
        >
          Save
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => save({ ...draft, verdict: "cant-tell", forms: [] })}
        >
          Can't tell
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => save({ ...draft, verdict: "unusable", forms: [] })}
        >
          Not usable
        </button>
        <button type="button" onClick={() => go(1)} disabled={busy}>
          Skip
        </button>
      </div>
    </div>
  );
}
