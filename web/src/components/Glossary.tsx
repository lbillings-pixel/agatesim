import { useRef, useState } from "react";
import { api } from "../api";
import { type Inline, parseMarkdown } from "../lib/markdown";

function renderInline(parts: Inline[]) {
  return parts.map((p, i) =>
    p.kind === "bold" ? (
      <strong key={i}>{p.text}</strong>
    ) : p.kind === "link" ? (
      // Links point into the repository's docs, which the app doesn't serve: show their text.
      <span key={i} className="glossary-ref">
        {p.text}
      </span>
    ) : (
      <span key={i}>{p.text}</span>
    ),
  );
}

/** The plain-language glossary (docs/glossary.md) in a dialog. */
export function Glossary() {
  const dialog = useRef<HTMLDialogElement>(null);
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const open = () => {
    dialog.current?.showModal();
    if (markdown === null) {
      api.glossary().then(
        (r) => setMarkdown(r.markdown),
        (e: unknown) => setError(e instanceof Error ? e.message : String(e)),
      );
    }
  };

  return (
    <>
      <button type="button" className="glossary-button" onClick={open}>
        Glossary
      </button>
      <dialog ref={dialog} className="glossary" aria-labelledby="glossary-title">
        <div className="glossary-head">
          <h2 id="glossary-title">Glossary</h2>
          <button type="button" onClick={() => dialog.current?.close()}>
            Close
          </button>
        </div>
        {error && <p className="error">Can’t load the glossary: {error}</p>}
        {markdown === null && !error && <p className="muted">Loading…</p>}
        {markdown !== null &&
          parseMarkdown(markdown)
            .filter((b) => !(b.kind === "heading" && b.level === 1))
            .map((b, i) =>
              b.kind === "heading" ? (
                <h3 key={i}>{renderInline(b.inline)}</h3>
              ) : b.kind === "list" ? (
                <ul key={i}>
                  {b.items.map((item, j) => (
                    <li key={j}>{renderInline(item)}</li>
                  ))}
                </ul>
              ) : (
                <p key={i}>{renderInline(b.inline)}</p>
              ),
            )}
      </dialog>
    </>
  );
}
