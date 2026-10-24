import { type PointerEvent, useEffect, useState } from "react";

import {
  type FeatureTaps,
  type LibraryIndex,
  type TapPhoto,
  library,
} from "../api";
import {
  ENOUGH,
  type Kind,
  enough,
  featureTaps,
  nextUndone,
  photoDone,
  tap,
} from "../lib/taps";

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Tap points inside and outside each tagged feature on the photos held out
 * for testing the feature maps (ADR 0068). Library photos only. */
export function TapLabeler({ index }: { index: LibraryIndex }) {
  const [photos, setPhotos] = useState<TapPhoto[] | null>(null);
  const [at, setAt] = useState(0);
  // Unsaved taps on the photo on screen.
  const [edit, setEdit] = useState<{
    id: string;
    taps: Record<string, FeatureTaps>;
  } | null>(null);
  const [feature, setFeature] = useState<string | null>(null);
  const [kind, setKind] = useState<Kind>("inside");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    library.taps().then(
      ({ photos }) => {
        setPhotos(photos);
        setAt(nextUndone(photos, -1) ?? 0);
      },
      (e: unknown) => setError(message(e)),
    );
  }, []);

  if (error && !photos) return <p className="error">{error}</p>;
  if (!photos) return <p>Loading the test photos…</p>;
  if (photos.length === 0)
    return (
      <p>
        No photos are held out for testing yet (`agatesim library hold-out`).
      </p>
    );

  const photo = photos[at] ?? photos[0];
  if (!photo) return null;
  const image = index.images.find((i) => i.id === photo.id);
  const taps = edit?.id === photo.id ? edit.taps : photo.taps;
  const dirty = edit?.id === photo.id;
  const active =
    feature && photo.targets.includes(feature)
      ? feature
      : (photo.targets[0] ?? null);
  const done = photos.filter((p) => p.done).length;

  // Save the photo's taps if they changed, then show photo `to`.
  const go = (to: number | null) => {
    if (!dirty) {
      if (to !== null) setAt(to);
      setFeature(null);
      return;
    }
    setBusy(true);
    setError(null);
    library
      .saveTaps(photo.id, taps)
      .then(
        (saved) => {
          const next = photos.map((p) =>
            p.id === photo.id ? { ...p, ...saved } : p,
          );
          setPhotos(next);
          setEdit(null);
          setFeature(null);
          if (to !== null) setAt(to);
        },
        (e: unknown) => setError(message(e)),
      )
      .finally(() => setBusy(false));
  };

  const onTap = (e: PointerEvent<HTMLDivElement>) => {
    if (!active || busy) return;
    const box = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - box.left) / box.width;
    const y = (e.clientY - box.top) / box.height;
    setEdit({
      id: photo.id,
      taps: tap(taps, active, kind, x, y, box.height / box.width),
    });
  };

  const step = (s: number) =>
    (((at + s) % photos.length) + photos.length) % photos.length;
  const current = active ? featureTaps(taps, active) : null;

  return (
    <div className="tapper">
      <p>
        Test taps: {done} of {photos.length} photos done · photo {at + 1}
        {photo.done && !dirty && " · done"}
      </p>
      <p className="muted">
        For each feature below, tap about 5 points inside it and 5 outside it.
        Put the outside points on the stone, not the background. Tap a dot again
        to remove it.
      </p>
      <div className="tap-frame">
        <div className="tap-photo" onPointerUp={onTap}>
          <img
            src={library.imageUrl(photo.id)}
            alt={image?.title ?? photo.id}
            draggable={false}
          />
          {photo.targets.map((f) => {
            const t = featureTaps(taps, f);
            return (["inside", "outside"] as const).map((k) =>
              t[k].map(([x, y], i) => (
                <span
                  key={`${f}-${k}-${i}`}
                  className={`tap-dot ${k}${f === active ? " active" : ""}`}
                  style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
                  title={`${f}: ${k}`}
                />
              )),
            );
          })}
        </div>
      </div>
      {image && (
        <p className="muted tap-credit">
          <a href={image.source} target="_blank" rel="noreferrer">
            {image.title}
          </a>{" "}
          · {image.author} ·{" "}
          <a href={image.licence_url} target="_blank" rel="noreferrer">
            {image.licence}
          </a>
        </p>
      )}
      {photo.targets.length === 0 ? (
        <p>This photo has no tagged features to tap any more. Skip it.</p>
      ) : (
        <>
          <fieldset className="chips">
            <legend>Feature</legend>
            {photo.targets.map((f) => {
              const t = featureTaps(taps, f);
              return (
                <button
                  key={f}
                  type="button"
                  className="chip"
                  aria-pressed={f === active}
                  onClick={() => setFeature(f)}
                >
                  {f}{" "}
                  {enough(t) ? "✓" : `${t.inside.length}·${t.outside.length}`}
                </button>
              );
            })}
          </fieldset>
          <fieldset className="chips">
            <legend>Tapping points</legend>
            <button
              type="button"
              className="chip"
              aria-pressed={kind === "inside"}
              onClick={() => setKind("inside")}
            >
              <span className="tap-key inside" /> inside {active}
            </button>
            <button
              type="button"
              className="chip"
              aria-pressed={kind === "outside"}
              onClick={() => setKind("outside")}
            >
              <span className="tap-key outside" /> outside it
            </button>
          </fieldset>
          {current && (
            <p className="muted">
              {active}: {current.inside.length} inside, {current.outside.length}{" "}
              outside (at least {ENOUGH} of each)
            </p>
          )}
        </>
      )}
      {error && <p className="error">{error}</p>}
      <div className="labeler-actions">
        <button type="button" onClick={() => go(step(-1))} disabled={busy}>
          Back
        </button>
        <button
          type="button"
          disabled={busy || !dirty}
          onClick={() => {
            setEdit(null);
          }}
        >
          Undo changes
        </button>
        <button
          type="button"
          className="primary"
          disabled={busy}
          onClick={() => {
            const next = photos.map((p) =>
              p.id === photo.id ? { ...p, taps, done: photoDone(p, taps) } : p,
            );
            go(nextUndone(next, at) ?? step(1));
          }}
        >
          {dirty ? "Save and next" : "Next"}
        </button>
      </div>
    </div>
  );
}
