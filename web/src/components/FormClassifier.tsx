import { useEffect, useState } from "react";

import {
  type ClassifierAnswer,
  type ClassifierStatus,
  type LibraryLabel,
  classifier,
  library,
  specimens,
} from "../api";
import { draftFromAnswer, toggle } from "../lib/labels";
import { newTaskId } from "../lib/progress";
import { CautionBadge } from "./CautionBadge";
import { TaskProgress } from "./TaskProgress";

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));
const percent = (p: number) => `${Math.round(p * 100)}%`;
const SHOWN = 5;

/** The learned classifier's answer on one of the owner's photos, and their
 * confirmation or correction (ADR 0067). Corrections are kept beside the photo,
 * never in the reference library, and train the classifier on this PC only.
 * Mount it with `key={name}`, so another photo starts afresh. */
export function FormClassifier({ name }: { name: string }) {
  const [answer, setAnswer] = useState<ClassifierAnswer | null>(null);
  const [saved, setSaved] = useState<LibraryLabel | null>(null);
  const [edit, setEdit] = useState<{ label: LibraryLabel; guessed: boolean } | null>(null);
  const [vocab, setVocab] = useState<{ forms: { id: string; name: string }[]; features: string[] } | null>(null);
  const [status, setStatus] = useState<ClassifierStatus | null>(null);
  const [task, setTask] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshStatus = () => classifier.status().then(setStatus, () => setStatus(null));
  const ask = (n: string) => specimens.classify(n).then(setAnswer, (e: unknown) => setError(message(e)));

  useEffect(() => {
    library.list().then(
      (i) => setVocab({ forms: i.forms, features: i.features }),
      (e: unknown) => setError(message(e)),
    );
    void refreshStatus();
  }, []);

  useEffect(() => {
    void ask(name);
    specimens.label(name).then(setSaved, () => setSaved(null));
  }, [name]);

  const likely = (answer?.likely ?? []).map((l) => l.form);
  const current = edit ?? draftFromAnswer(saved, likely);
  const draft = current.label;
  const names = Object.fromEntries((vocab?.forms ?? []).map((f) => [f.id, f.name]));
  const set = (patch: Partial<LibraryLabel>) => setEdit({ label: { ...draft, ...patch }, guessed: false });

  const save = (label: LibraryLabel | null) => {
    setBusy(true);
    setError(null);
    const done = label ? specimens.saveLabel(name, label) : specimens.clearLabel(name).then(() => null);
    done
      .then(
        (l) => {
          setSaved(l);
          setEdit(null);
          setNote(l ? "Saved. Retrain to teach the classifier." : "Label cleared.");
          void refreshStatus();
        },
        (e: unknown) => setError(message(e)),
      )
      .finally(() => setBusy(false));
  };

  const retrain = () => {
    const id = newTaskId();
    setTask(id);
    setError(null);
    setNote(null);
    classifier
      .train(id)
      .then(
        (r) => {
          setNote(
            `Retrained on ${r.photos} labelled photos (${r.own_photos} of yours) and ${r.simulated} simulated slabs.`,
          );
          void ask(name);
        },
        (e: unknown) => setError(message(e)),
      )
      .finally(() => {
        setTask(null);
        void refreshStatus();
      });
  };

  const ranked = answer?.ranked ?? [];
  return (
    <section className="form-classifier" aria-label="Form classifier">
      <div className="criteria-head">
        <h3>Form classifier</h3>
        <span className="muted small">
          A guess from appearance, learned from labelled photos: never evidence of how an agate formed.
        </span>
      </div>
      {!answer && !error && <p className="muted small">Asking the classifier…</p>}
      {answer && !answer.ready && <p className="small">{answer.why}</p>}
      {answer?.ready && (
        <>
          <p className="classifier-likely">
            {likely.length === 0 ? (
              <span className="pill na">undetermined</span>
            ) : (
              (answer.likely ?? []).map((l) => (
                <span key={l.form} className="pill pass" title={names[l.form] ?? l.form}>
                  {l.form} {percent(l.p)}
                </span>
              ))
            )}
          </p>
          <ul className="classifier-ranked small">
            {ranked.slice(0, SHOWN).map((r) => (
              <li key={r.form}>
                <span className="classifier-form">{r.form}</span>
                <span className="classifier-bar" aria-hidden="true">
                  <span style={{ width: percent(r.p) }} />
                </span>
                <span className="num">{percent(r.p)}</span>
                <span className="muted">from {answer.trained_on?.[r.form] ?? 0} labelled photos</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {vocab && (
        <div className="classifier-label">
          <fieldset className="chips">
            <legend>
              {saved ? "Your label" : "What it shows"}
              {current.guessed && <span className="muted"> (the classifier&apos;s guess: confirm or correct)</span>}
            </legend>
            {vocab.forms.map((f) => (
              <button
                key={f.id}
                type="button"
                className={`chip${current.guessed && draft.forms.includes(f.id) ? " guess" : ""}`}
                aria-pressed={draft.forms.includes(f.id)}
                onClick={() => set({ forms: toggle(draft.forms, f.id), verdict: "forms" })}
                title={f.name}
              >
                {f.id}
              </button>
            ))}
          </fieldset>
          <fieldset className="chips">
            <legend>Features</legend>
            {vocab.features.map((f) => (
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
            <button type="button" className="chip" aria-pressed={!draft.sure} onClick={() => set({ sure: !draft.sure })}>
              not sure
            </button>
          </fieldset>
          {saved && (
            <p className="muted small">
              Saved: {saved.verdict === "forms" ? saved.forms.map((f) => names[f] ?? f).join(" · ") : saved.verdict}
            </p>
          )}
          <div className="labeler-actions">
            <button
              type="button"
              className="primary"
              disabled={busy || draft.forms.length === 0}
              onClick={() => save({ ...draft, verdict: "forms" })}
            >
              {current.guessed ? "Confirm" : "Save"}
            </button>
            <button type="button" disabled={busy} onClick={() => save({ ...draft, verdict: "cant-tell", forms: [] })}>
              Can&apos;t tell
            </button>
            <button type="button" disabled={busy} onClick={() => save({ ...draft, verdict: "unusable", forms: [] })}>
              Not usable
            </button>
            {saved && (
              <button type="button" disabled={busy} onClick={() => save(null)}>
                Clear label
              </button>
            )}
          </div>
        </div>
      )}

      <div className="classifier-train small">
        <span className="muted">
          {status ? `${status.own_labels} of your photos labelled. ` : ""}
          Labels stay on this PC.
        </span>
        <button type="button" disabled={task !== null || !status?.model || status.training} onClick={retrain}>
          Retrain
        </button>
        <CautionBadge estimate={status?.estimate} />
      </div>
      <TaskProgress task={task} title="Retraining" fallback={task ? <p className="muted small">Retraining…</p> : null} />
      {note && <p className="small">{note}</p>}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
