import { useState } from "react";

import { type LibraryIndex, library } from "../api";
import { type Answer, applyAnswers, checkQueue, checkTags } from "../lib/labels";

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

const ANSWERS: { answer: Answer; text: string }[] = [
  { answer: "yes", text: "yes" },
  { answer: "no", text: "no" },
  { answer: "unsure", text: "not sure" },
];

/** Check each photo's map tags one at a time: yes, no or not sure (ADR 0071).
 * Unsure tags sit out of training; library photos only. */
export function TagChecker({
  index,
  onSaved,
}: {
  index: LibraryIndex;
  onSaved: (index: LibraryIndex) => void;
}) {
  // The queue is fixed when the screen opens, so saved photos keep their place.
  const [queue] = useState(() => checkQueue(index.images, index.map_tags));
  const [at, setAt] = useState(0);
  const [answers, setAnswers] = useState<{
    id: string;
    answers: Record<string, Answer>;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const left = index.images.filter(
    (i) =>
      i.fetched &&
      !i.label?.reviewed &&
      checkTags(i.label, index.map_tags).length > 0,
  ).length;
  const position = queue[at];
  const image = position === undefined ? undefined : index.images[position];
  if (!image?.label)
    return (
      <p>
        {queue.length === 0
          ? "Every photo's tags are checked."
          : "That was the last photo to check."}
      </p>
    );

  const label = image.label;
  const tags = checkTags(label, index.map_tags);
  const mine: Record<string, Answer> =
    answers?.id === image.id
      ? answers.answers
      : Object.fromEntries(
          tags.map((t) => [t, label.unsure.includes(t) ? "unsure" : "yes"]),
        );
  const forms = new Set(index.forms.map((f) => f.id));
  const after = applyAnswers(label, mine, forms);

  const save = () => {
    setBusy(true);
    setError(null);
    library
      .label(image.id, after)
      .then(
        (saved) => {
          const images = index.images.map((i) =>
            i.id === image.id ? { ...i, label: saved } : i,
          );
          onSaved({ ...index, images });
          setAnswers(null);
          setAt(at + 1);
        },
        (e: unknown) => setError(message(e)),
      )
      .finally(() => setBusy(false));
  };

  return (
    <div className="tapper">
      <p>
        Tag check: {left} photos left · photo {at + 1} of {queue.length}
      </p>
      <p className="muted">
        Is each tag below really in this photo? Answer “not sure” when you
        can't tell: those tags are left out of training rather than guessed.
      </p>
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
        </figcaption>
      </figure>
      {tags.map((t) => (
        <fieldset key={t} className="chips">
          <legend>{t}</legend>
          {ANSWERS.map(({ answer, text }) => (
            <button
              key={answer}
              type="button"
              className="chip"
              aria-pressed={mine[t] === answer}
              onClick={() =>
                setAnswers({ id: image.id, answers: { ...mine, [t]: answer } })
              }
            >
              {text}
            </button>
          ))}
        </fieldset>
      ))}
      {after.verdict !== label.verdict && (
        <p className="muted">
          No forms would be left, so the photo will be marked “can't tell”.
        </p>
      )}
      {error && <p className="error">{error}</p>}
      <div className="labeler-actions">
        <button
          type="button"
          onClick={() => {
            setAnswers(null);
            setAt(Math.max(0, at - 1));
          }}
          disabled={busy || at === 0}
        >
          Back
        </button>
        <button type="button" className="primary" disabled={busy} onClick={save}>
          Save and next
        </button>
        <button
          type="button"
          onClick={() => {
            setAnswers(null);
            setAt(at + 1);
          }}
          disabled={busy}
        >
          Skip
        </button>
      </div>
    </div>
  );
}
