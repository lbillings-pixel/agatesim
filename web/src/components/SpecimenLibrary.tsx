import { useEffect, useRef, useState } from "react";

import { type QualityBadge, type SpecimenFile, specimens } from "../api";
import { formatBytes } from "../lib/bytes";
import { USE_LABEL, adviceFor, badgeSummary, levelClass } from "../lib/quality";

interface Props {
  files: SpecimenFile[];
  selected: string | null;
  onOpen: (name: string) => void;
  onRenamed: (from: string, to: string) => void;
  onDeleted: (name: string) => void;
  onUploaded: (name: string) => void;
  refresh: () => void;
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Every photo with its quality badges: what it is fit for, and why not (ADR 0064). */
export function SpecimenLibrary({ files, selected, onOpen, onRenamed, onDeleted, onUploaded, refresh }: Props) {
  const [scored, setScored] = useState<Record<string, QualityBadge[]>>({});
  const [scoring, setScoring] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const failed = useRef(new Set<string>());

  // Score the photos that have no cached scores yet, one at a time.
  useEffect(() => {
    if (scoring) return;
    const next = files.find((f) => !f.badges && !scored[f.name] && !failed.current.has(f.name));
    if (!next) return;
    setScoring(next.name);
    specimens
      .settings(next.name)
      .then((s) => specimens.quality(next.name, s))
      .then(
        (r) => setScored((all) => ({ ...all, [next.name]: r.badges })),
        () => failed.current.add(next.name),
      )
      .finally(() => setScoring(null));
  }, [files, scored, scoring]);

  const badgesOf = (f: SpecimenFile) => scored[f.name] ?? f.badges;

  const rename = (from: string) => {
    const to = newName.trim();
    if (!to || to === from) {
      setRenaming(null);
      return;
    }
    setBusy(`Renaming ${from}`);
    setError(null);
    specimens
      .rename(from, to)
      .then(
        (r) => {
          setScored(({ [from]: moved, ...rest }) => (moved ? { ...rest, [r.name]: moved } : rest));
          setRenaming(null);
          onRenamed(from, r.name);
          refresh();
        },
        (e: unknown) => setError(message(e)),
      )
      .finally(() => setBusy(null));
  };

  const remove = (name: string) => {
    if (confirmDelete !== name) {
      setConfirmDelete(name); // a second click deletes
      return;
    }
    setBusy(`Deleting ${name}`);
    setError(null);
    specimens
      .remove(name)
      .then(
        () => {
          setConfirmDelete(null);
          onDeleted(name);
          refresh();
        },
        (e: unknown) => setError(message(e)),
      )
      .finally(() => setBusy(null));
  };

  const upload = (file: File | undefined) => {
    if (!file) return;
    setBusy("Uploading");
    setError(null);
    specimens
      .upload(file)
      .then(
        (r) => {
          refresh();
          onUploaded(r.name);
        },
        (e: unknown) => setError(message(e)),
      )
      .finally(() => setBusy(null));
  };

  return (
    <main className="specimen-library">
      <div className="library-head">
        <p className="muted small">
          Photos in your <code>specimens/</code> folder. They stay on this machine; new photos are stored without their
          location or other metadata. Each photo is scored for what it can be used for.
        </p>
        <label className="upload">
          <span className="micro-label">Add a photo</span>
          <input type="file" accept="image/jpeg,image/png" onChange={(e) => upload(e.target.files?.[0])} />
        </label>
        {(busy ?? scoring) && <span className="muted small">{busy ?? `Scoring ${scoring}`}…</span>}
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {files.length === 0 && <p className="muted">No photos yet. Add one above.</p>}
      <ul className="library-grid">
        {files.map((f) => {
          const badges = badgesOf(f);
          return (
            <li key={f.name} className={f.name === selected ? "library-card selected" : "library-card"}>
              <button type="button" className="library-thumb" onClick={() => onOpen(f.name)} title="Open in Classify">
                <img src={`${specimens.thumbUrl(f.name)}?v=${f.bytes}`} alt="" loading="lazy" />
              </button>
              {renaming === f.name ? (
                <form
                  className="library-rename"
                  onSubmit={(e) => {
                    e.preventDefault();
                    rename(f.name);
                  }}
                >
                  <input
                    aria-label="New name"
                    value={newName}
                    autoFocus
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => e.key === "Escape" && setRenaming(null)}
                  />
                  <button type="submit" disabled={busy !== null}>
                    Save
                  </button>
                </form>
              ) : (
                <div className="library-name" title={f.name}>
                  {f.name}
                  <span className="muted small">
                    {" "}
                    · {formatBytes(f.bytes)}
                    {f.has_settings && " · scaled"}
                  </span>
                </div>
              )}
              <div className="library-badges">
                {badges ? (
                  badges.map((b) => (
                    <span key={b.use} className={levelClass(b.level)} title={badgeSummary(b)}>
                      {USE_LABEL[b.use]}: {b.level}
                    </span>
                  ))
                ) : (
                  <span className="muted small">
                    {failed.current.has(f.name) ? "couldn't score" : scoring === f.name ? "scoring…" : "waiting…"}
                  </span>
                )}
              </div>
              {badges && open === f.name && (
                <ul className="library-reasons small">
                  {badges.flatMap((b) =>
                    b.reasons.map((r) => (
                      <li key={`${b.use}-${r.score}`}>
                        <span className={levelClass(r.level)}>{USE_LABEL[b.use]}</span> {r.message}
                      </li>
                    )),
                  )}
                  {adviceFor(badges).map((a) => (
                    <li key={a} className="muted">
                      Tip: {a}
                    </li>
                  ))}
                </ul>
              )}
              <div className="library-actions">
                <button type="button" onClick={() => onOpen(f.name)}>
                  Classify
                </button>
                {badges && badges.some((b) => b.reasons.length > 0) && (
                  <button
                    type="button"
                    aria-expanded={open === f.name}
                    onClick={() => setOpen(open === f.name ? null : f.name)}
                  >
                    Why
                  </button>
                )}
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => {
                    setRenaming(f.name);
                    setNewName(f.name);
                  }}
                >
                  Rename
                </button>
                <button
                  type="button"
                  disabled={busy !== null}
                  className={confirmDelete === f.name ? "danger" : undefined}
                  onClick={() => remove(f.name)}
                  onBlur={() => setConfirmDelete(null)}
                >
                  {confirmDelete === f.name ? "Click again to delete" : "Delete"}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="muted small">
        Deleted photos are moved to <code>specimens/.agatesim/deleted/</code>, so they can be put back by hand.
      </p>
    </main>
  );
}
