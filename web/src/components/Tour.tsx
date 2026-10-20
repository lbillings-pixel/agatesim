import { useEffect, useRef, useState } from "react";

import { CautionBadge } from "./CautionBadge";

/** The tour's steps: what each screen is for, in plain language. */
export const TOUR_STEPS = [
  {
    title: "Welcome to agatesim",
    body: [
      "agatesim simulates how agate forms inside a cavity in its host rock, and judges each result the way a collector judges a cut stone: against measurable tests for each classic form.",
      "This short tour shows where things are. You can reopen it any time from the Tour button.",
    ],
  },
  {
    title: "Simulator",
    body: [
      "Pick a form on the left, procedural or mechanistic, to start from its verified settings, or choose a model and a cavity yourself. The slab in the middle updates as you change settings, and the tests below it say whether it still shows the form.",
      "Key settings come first; the rest wait under “More settings”. “Randomize” moves the key settings to random values within safe ranges, to explore what a model can make; “Undo” takes you back.",
      "“Run full resolution” saves a run to the list on the right. Pin a run to compare it with another side by side: their tests, what differs, and one growth slider for both.",
    ],
  },
  {
    title: "Two ways",
    body: [
      "Each form made two ways: by a rule-based model that builds the form in by design, and by a model of a proposed formation process, where the form emerges.",
      "Passing with a mechanism shows the mechanism can make the form, not that nature does.",
    ],
  },
  {
    title: "3D and Specimens",
    body: [
      "3D treats the cavity as a solid: you choose a cut through it and judge that cut, or survey many random cuts to see how often a form shows. Long builds show how far they have got and roughly how long is left; Cancel stops them.",
      "Specimens analyses photos of real agates. Your photos stay on this computer.",
    ],
  },
  {
    title: "Heavy work",
    body: [
      "Some actions take minutes or a lot of memory: Liesegang precipitation (H2) without a GPU, fine 3D dendrites, full runs at the largest sizes, long surveys, or front feedback (H1) at extreme settings. Before you start one, an amber badge beside it says roughly how long it will take and, if it is large, how much memory it needs; hover over the badge to see why.",
      "Once something long is running, a progress bar shows how far it has got, with Cancel.",
    ],
    visual: "caution",
  },
  {
    title: "Words and tags",
    body: [
      "Settings carry a tag: physical (a measurable condition), effective (a model coefficient) or imposed (it sets a property of the result directly, rule-based models only).",
      "The Glossary explains the other terms used here.",
    ],
  },
] as const;

const SEEN_KEY = "agatesim.tour.seen";

function seen(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return true; // storage blocked: don't keep showing the tour
  }
}

function markSeen(): void {
  try {
    localStorage.setItem(SEEN_KEY, "1");
  } catch {
    // Storage blocked; the tour may show again next time.
  }
}

/** A short tour of the screens, opened on a first visit and from its button. */
export function Tour() {
  const dialog = useRef<HTMLDialogElement>(null);
  const [step, setStep] = useState(0);

  const show = () => {
    // Effects run twice in development (StrictMode): open only once.
    if (dialog.current && !dialog.current.open) dialog.current.showModal();
  };
  const open = () => {
    setStep(0);
    show();
  };

  // On a first visit the tour opens at its first step.
  useEffect(() => {
    if (!seen()) show();
  }, []);

  const current = TOUR_STEPS[step] ?? TOUR_STEPS[0];
  const last = step === TOUR_STEPS.length - 1;
  return (
    <>
      <button type="button" className="glossary-button" onClick={open}>
        Tour
      </button>
      <dialog ref={dialog} className="glossary tour" aria-labelledby="tour-title" onClose={markSeen}>
        <div className="glossary-head">
          <h2 id="tour-title">{current.title}</h2>
          <span className="muted small">
            {step + 1} of {TOUR_STEPS.length}
          </span>
        </div>
        {current.body.map((p) => (
          <p key={p}>{p}</p>
        ))}
        {"visual" in current && current.visual === "caution" && (
          <figure className="tour-visual">
            <button type="button" className="primary" tabIndex={-1} aria-hidden="true">
              Save a full 3D run
            </button>
            <CautionBadge
              estimate={{
                seconds: 130,
                memory_gb: 3.4,
                heavy: true,
                reasons: ["H2 lattice of 38 million cells, on the GPU", "384³ voxels"],
              }}
            />
            <figcaption className="muted small">Example: what the badge looks like beside an action.</figcaption>
          </figure>
        )}
        <div className="tour-actions">
          <button type="button" onClick={() => dialog.current?.close()}>
            {last ? "Close" : "Skip the tour"}
          </button>
          <span className="tour-steps">
            <button type="button" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
              Back
            </button>
            {!last && (
              <button type="button" className="primary" onClick={() => setStep((s) => s + 1)}>
                Next
              </button>
            )}
          </span>
        </div>
      </dialog>
    </>
  );
}
