import { useEffect, useRef, useState } from "react";

import { type FeatureMapAnswer, specimens } from "../api";
import { spotlightPixels } from "../lib/heatmap";

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Rough locations of features on one of the owner's photos (ADR 0068): maps
 * learnt from photo-level tags, shown only where they passed the tap test.
 * Mount it with `key={name}`, so another photo starts afresh. */
export function RoughLocation({ name }: { name: string }) {
  const [answer, setAnswer] = useState<FeatureMapAnswer | null>(null);
  const [feature, setFeature] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    specimens.maps(name).then(
      (a) => {
        setAnswer(a);
        setFeature(a.maps?.[0]?.feature ?? null);
      },
      (e: unknown) => setError(message(e)),
    );
  }, [name]);

  const shown = answer?.maps?.find((m) => m.feature === feature) ?? null;

  useEffect(() => {
    const c = canvas.current;
    if (!c || !shown) return;
    const rows = shown.grid.length;
    const cols = shown.grid[0]?.length ?? 0;
    c.width = cols;
    c.height = rows;
    const ctx = c.getContext("2d");
    if (!ctx || rows === 0 || cols === 0) return;
    ctx.putImageData(new ImageData(spotlightPixels(shown.grid), cols, rows), 0, 0);
  }, [shown]);

  if (error) return <p className="error">{error}</p>;
  if (!answer) return null;

  return (
    <section className="rough-location" aria-label="Rough location">
      <h3>Rough location</h3>
      {!answer.ready ? (
        <p className="muted small">{answer.why}</p>
      ) : (
        <>
          <p className="muted small">
            Where the image model sees each feature, learnt from photo-level
            labels alone. Coarse: each square is 1/37 of the photo's long side.
            A feature is shown only if its map beat both chance and a
            middle-of-the-photo guess on your test taps. Appearance only, never
            how a feature formed.
          </p>
          {(answer.maps ?? []).length > 0 && (
            <fieldset className="chips">
              <legend>Feature</legend>
              {(answer.maps ?? []).map((m) => (
                <button
                  key={m.feature}
                  type="button"
                  className="chip"
                  aria-pressed={m.feature === feature}
                  onClick={() =>
                    setFeature(m.feature === feature ? null : m.feature)
                  }
                >
                  {m.feature}
                </button>
              ))}
            </fieldset>
          )}
          <div className="rough-frame">
            <div className="rough-photo">
              <img
                src={specimens.photoUrl(name)}
                alt={`Specimen photo ${name}`}
              />
              {shown && <canvas ref={canvas} aria-hidden="true" />}
            </div>
          </div>
          {shown && (
            <p className="small">
              Clear: more likely{" "}
              {shown.feature}; dimmed: less likely. Tested on your taps: {shown.score.toFixed(2)}{" "}
              (middle guess {shown.centre.toFixed(2)}; 0.5 is chance).
            </p>
          )}
          {(answer.not_shown ?? []).length > 0 && (
            <p className="muted small">
              Not shown (failed the tap test or too few test photos):{" "}
              {(answer.not_shown ?? []).map((n) => n.feature).join(", ")}.
            </p>
          )}
        </>
      )}
    </section>
  );
}
