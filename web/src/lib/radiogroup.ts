// Arrow keys for the app's button-based radio groups (role="radiogroup" with
// role="radio" buttons), as for native radio buttons: the arrows move to the
// previous or next option and select it, wrapping at the ends; Home and End go
// to the first and last.

const KEYS: Record<string, "prev" | "next" | "first" | "last"> = {
  ArrowLeft: "prev",
  ArrowUp: "prev",
  ArrowRight: "next",
  ArrowDown: "next",
  Home: "first",
  End: "last",
};

/** The option to move to from `current` of `count` on `key`, or null if the key
 * doesn't move. */
export function radioTarget(key: string, current: number, count: number): number | null {
  const move = KEYS[key];
  if (!move || count === 0) return null;
  switch (move) {
    case "prev":
      return (current - 1 + count) % count;
    case "next":
      return (current + 1) % count;
    case "first":
      return 0;
    case "last":
      return count - 1;
  }
}

/** Handle the keys for every radio group under `root`; returns a function that
 * stops. */
export function installRadioKeys(root: Document | HTMLElement = document): () => void {
  const onKey = (event: Event) => {
    const e = event as KeyboardEvent;
    const radio = (e.target as HTMLElement | null)?.closest<HTMLElement>('[role="radio"]');
    const group = radio?.closest<HTMLElement>('[role="radiogroup"]');
    if (!radio || !group || e.altKey || e.ctrlKey || e.metaKey) return;
    const options = [...group.querySelectorAll<HTMLElement>('[role="radio"]')].filter(
      (o) => o.closest('[role="radiogroup"]') === group && !(o as HTMLButtonElement).disabled,
    );
    const target = radioTarget(e.key, options.indexOf(radio), options.length);
    if (target === null) return;
    e.preventDefault();
    const next = options[target];
    next?.focus();
    next?.click();
  };
  root.addEventListener("keydown", onKey);
  return () => root.removeEventListener("keydown", onKey);
}
