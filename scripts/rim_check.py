# pyright: basic
"""The rim-finder on the library (ADR 0073 section 3, ADR 0074).

uv run --no-sync python scripts/rim_check.py split
    fix the seeded split once: 80 tuning, 150 held out (nodule's 30
    owner-checked photos among them), the tier-2 photos as a hard set;
    written to references/rim-split.toml
uv run --no-sync python scripts/rim_check.py run tune|held|friend [--tau T] [--b]
    find the rim on one set (with the segmentation model where fetched; --b
    keeps to method B); outlines drawn on each photo (no metadata), results.json
    (with the model's scores) and masks.npz written to runs/rim-check/<set>[-<tag>]/
uv run --no-sync python scripts/rim_check.py score tune [--tag T]
    score a run against the helpers' judgments (runs/rim-check/judge-*.json):
    an outline matching a judged one (IoU >= 0.95) inherits its answer; the
    owner's answers (runs/rim-check/owner-*.json) override the helpers'
uv run --no-sync python scripts/rim_check.py check held|friend [--port P]
    the owner's check page on this PC only (127.0.0.1): every helper "no" and
    20 drawn "yes" outlines, blind and shuffled; answers to owner-<set>.json
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import tomllib
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import numpy as np
from PIL import Image, ImageDraw

from agatesim.library import load_labels, load_library
from agatesim.maps import OnnxPatchEmbedder, PatchCache, library_patches
from agatesim.specimen import rim as rim_module
from agatesim.specimen.photo import load_photo
from agatesim.specimen.rim import TAU, find_rim
from agatesim.specimen.sam import Sam

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "references" / "rim-split.toml"
OUT = ROOT / "runs" / "rim-check"
NODULE_LABELS = ROOT.parent / "nodule" / "references" / "library-view-labels.toml"
SEED = 73
TUNE = 80
VIEW_PX = 768  # long side of the drawn outlines


def split(force: bool) -> None:
    if SPLIT.exists() and not force:
        sys.exit(f"{SPLIT} exists: the split is fixed before tuning (--force to redo)")
    library, labels = load_library(), load_labels()
    usable = sorted(
        i.id
        for i in library.images
        if i.tier == 1 and i.id in labels and labels[i.id].verdict != "unusable"
    )
    checked = set(tomllib.loads(NODULE_LABELS.read_text("utf-8"))["meta"]["check_sample"])
    assert checked <= set(usable), sorted(checked - set(usable))
    # Photos of one stone stay together (only tier 2 records stones so far).
    stones = {i.id: i.stone or i.id for i in library.images}
    groups = sorted({stones[i] for i in usable if i not in checked})
    rng = np.random.default_rng(SEED)
    order = [groups[k] for k in rng.permutation(len(groups))]
    tune: list[str] = []
    for g in order:
        members = [i for i in usable if stones[i] == g]
        if len(tune) + len(members) <= TUNE:
            tune += members
    held = sorted(set(usable) - set(tune))
    friend = sorted(i.id for i in library.images if i.tier == 2)
    lines = [
        "# The rim-finder's split (ADR 0073 section 3), drawn once with seed "
        f"{SEED} by scripts/rim_check.py.",
        "# Settings are tuned on `tune` only; `held` includes nodule's 30 owner-checked",
        "# photos; `friend` (tier 2) is a hard test set, never used for tuning.",
        f"seed = {SEED}",
    ]
    for name, ids in (("tune", sorted(tune)), ("held", held), ("friend", friend)):
        lines.append(f"{name} = [")
        lines += [f'    "{i}",' for i in ids]
        lines.append("]")
    SPLIT.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"tune {len(tune)}, held {len(held)}, friend {len(friend)} -> {SPLIT}")


def draw(rgb: np.ndarray, outline: np.ndarray, caption: str) -> Image.Image:
    im = Image.fromarray(rgb).convert("RGB")
    scale = VIEW_PX / max(im.size)
    im = im.resize((round(im.width * scale), round(im.height * scale)))
    d = ImageDraw.Draw(im)
    if len(outline):
        pts = [
            (float(x) * scale, float(y) * scale)
            for x, y in outline[:: max(1, len(outline) // 2000)]
        ]
        d.line([*pts, pts[0]], fill=(255, 0, 255), width=3)
    d.rectangle((0, 0, 8 * len(caption) + 8, 18), fill=(0, 0, 0))
    d.text((4, 3), caption, fill=(255, 255, 255))
    return im


MASK_PX = 256  # long side of the saved masks
SAME = 0.95  # IoU at which two outlines of a photo count as the same


def run(name: str, tau: float, tag: str, method_b: bool) -> None:
    ids = tomllib.loads(SPLIT.read_text("utf-8"))[name]
    library = load_library()
    cache = PatchCache(OnnxPatchEmbedder())
    model = None if method_b else Sam()
    out = OUT / (f"{name}-{tag}" if tag else name)
    out.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, object]] = {}
    masks: dict[str, np.ndarray] = {}
    start = time.perf_counter()
    for k, image_id in enumerate(ids, 1):
        image = library.get(image_id)
        rgb = load_photo(image.path.read_bytes(), 1024).rgb
        rim = find_rim(rgb, patches=library_patches(cache, image), tau=tau, sam=model)
        results[image_id] = {
            "reason": rim.reason,
            "area": float(rim.mask.mean()),
            "scores": rim.scores,
        }
        small = Image.fromarray(rim.mask)
        small.thumbnail((MASK_PX, MASK_PX), Image.Resampling.NEAREST)
        masks[image_id] = np.asarray(small, dtype=bool)
        caption = "outline" if rim.found else f"no outline: {rim.reason}"
        draw(rgb, rim.outline, caption).save(out / f"{image_id}.png")
        if k % 20 == 0:
            print(f"{k}/{len(ids)}", flush=True)
    settings = {"tau": tau, "method": "B" if method_b else "C"}
    (out / "results.json").write_text(json.dumps({**settings, "results": results}, indent=1))
    np.savez_compressed(out / "masks.npz", **masks)  # pyright: ignore[reportArgumentType]
    found = sum(r["reason"] is None for r in results.values())
    took = time.perf_counter() - start
    print(f"{name}: outline on {found}/{len(ids)}, {took:.0f} s -> {out}")


def score(name: str, tag: str) -> None:
    """Counts against ADR 0073's bar, from the judgments so far. A judgment
    belongs to the run it was made on (its `run` key, the run folder name)."""
    out = OUT / (f"{name}-{tag}" if tag else name)
    results = json.loads((out / "results.json").read_text())["results"]
    masks = np.load(out / "masks.npz")
    in_frame: dict[str, bool] = {}
    # (run, id) -> (mask, follows); the owner's answers, read last, override the helpers'.
    verdicts: dict[tuple[str, str], tuple[np.ndarray, bool]] = {}
    helpers: dict[str, bool] = {}
    owner: dict[str, bool] = {}
    for path in [*sorted(OUT.glob("judge-*.json")), *sorted(OUT.glob("owner-*.json"))]:
        data = json.loads(path.read_text())
        run_name = data.pop("_run", name)
        run_dir = OUT / run_name
        old = np.load(run_dir / "masks.npz") if (run_dir / "masks.npz").exists() else None
        for image_id, j in data.items():
            in_frame[image_id] = j["rim_in_frame"] == "yes"
            if j["outline_follows"] != "na" and old is not None and image_id in old:
                yes = j["outline_follows"] == "yes"
                verdicts[run_name, image_id] = (old[image_id], yes)
                if run_name == out.name:
                    (owner if path.name.startswith("owner-") else helpers)[image_id] = yes
    judged = [(i, m, f) for (_, i), (m, f) in verdicts.items()]
    follows, unknown = 0, []
    for image_id, r in results.items():
        if r["reason"] is not None:
            continue
        m = masks[image_id]
        # The closest judged outline, so a judgment of this very outline wins.
        overlaps = [
            ((m & o).sum() / max((m | o).sum(), 1), f) for i, o, f in judged if i == image_id
        ]
        best = max(overlaps, default=(0.0, None), key=lambda t: t[0])
        verdict = best[1] if best[0] >= SAME else None
        if verdict is None:
            unknown.append(image_id)
        else:
            follows += verdict
    found = [i for i, r in results.items() if r["reason"] is None]
    rim_in = [i for i in results if in_frame.get(i)]
    rim_out = [i for i in results if i in in_frame and not in_frame[i]]
    known = len(found) - len(unknown)
    print(
        f"{out.name}: {len(found)} outlines; follow the rim {follows}/{known} judged"
        f" ({len(unknown)} not yet judged)"
    )
    print(
        f"  outline on {sum(i in found for i in rim_in)}/{len(rim_in)} rim-in-frame photos;"
        f" declined {sum(i not in found for i in rim_out)}/{len(rim_out)} cut-off photos"
    )
    if owner:
        agree = sum(owner[i] == helpers.get(i) for i in owner)
        print(f"  owner checked {len(owner)} outlines; agreed with the helpers on {agree}")
    if unknown:
        (out / "unjudged.txt").write_text("".join(f"{i}.png\n" for i in unknown))
        print(f"  list of unjudged outlines -> {out / 'unjudged.txt'}")


OWNER_YES = 20  # helper "yes" outlines drawn for the owner's check, with every "no"
JUDGE_KEYS = ("rim_in_frame", "outline_follows", "note")
PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Rim check</title>
<style>body{font:16px system-ui;margin:16px;max-width:820px}img{max-width:100%;display:block;
margin:8px 0}button{font-size:16px;padding:6px 14px;margin:2px}.on{background:#6a6;color:#fff}
fieldset{border:0;padding:0;margin:8px 0}input[type=text]{width:100%;font-size:16px}</style>
<p id="head"></p><img id="pic"><fieldset id="q1">Is the stone's whole rim inside the photo?
<br></fieldset><fieldset id="q2">Does the purple outline follow the rim?<br></fieldset>
<p>Note (optional): <input type="text" id="note"></p>
<button id="prev">Back</button> <button id="next">Save and next</button> <span id="msg"></span>
<script>
const ROWS = /*DATA*/null;
let k = ROWS.findIndex((r) => !r.answer); if (k < 0) k = 0;
const pick = {};
function choice(box, key) {
  for (const v of ["yes", "no"]) {
    const b = document.createElement("button"); b.textContent = v; b.dataset.v = v;
    b.onclick = () => { pick[key] = v; show(false); }; box.appendChild(b);
  }
}
choice(document.getElementById("q1"), "rim_in_frame");
choice(document.getElementById("q2"), "outline_follows");
function show(fresh) {
  const r = ROWS[k];
  if (fresh) {
    const a = r.answer || {};
    pick.rim_in_frame = a.rim_in_frame;
    pick.outline_follows = a.outline_follows;
    document.getElementById("note").value = a.note || "";
  }
  const done = ROWS.filter((x) => x.answer).length;
  document.getElementById("head").textContent = `Photo ${k + 1} of ${ROWS.length} (${done} saved)`;
  document.getElementById("pic").src = "/img/" + encodeURIComponent(r.id) + ".png";
  for (const [id, key] of [["q1", "rim_in_frame"], ["q2", "outline_follows"]])
    for (const b of document.getElementById(id).querySelectorAll("button"))
      b.className = pick[key] === b.dataset.v ? "on" : "";
}
document.getElementById("prev").onclick = () => { if (k > 0) { k--; show(true); } };
document.getElementById("next").onclick = async () => {
  const msg = document.getElementById("msg");
  if (!pick.rim_in_frame || !pick.outline_follows) {
    msg.textContent = "Answer both questions.";
    return;
  }
  const answer = { rim_in_frame: pick.rim_in_frame, outline_follows: pick.outline_follows,
    note: document.getElementById("note").value };
  const body = JSON.stringify({ id: ROWS[k].id, answer });
  const res = await fetch("/save", { method: "POST", body });
  if (!res.ok) { msg.textContent = "Not saved: " + (await res.text()); return; }
  ROWS[k].answer = answer;
  msg.textContent = ROWS.every((x) => x.answer) ? "All saved. You can close this page." : "Saved.";
  if (k < ROWS.length - 1) k++;
  show(true);
};
show(true);
</script>"""


def check(name: str, port: int, open_page: bool) -> None:
    """The owner's check (ADR 0073 section 3): every outline the helpers judged
    "no" and a seeded draw of their "yes" ones, shown blind and in random order;
    answers go to owner-<set>.json, which `score` reads over the helpers'."""
    sample_path = OUT / f"check-sample-{name}.json"
    answers_path = OUT / f"owner-{name}.json"
    if not sample_path.exists():
        helper = json.loads((OUT / f"judge-{name}.json").read_text())
        helper.pop("_run")
        no = sorted(i for i, j in helper.items() if j["outline_follows"] == "no")
        yes = sorted(i for i, j in helper.items() if j["outline_follows"] == "yes")
        rng = np.random.default_rng(SEED)
        drawn = [yes[k] for k in rng.choice(len(yes), min(OWNER_YES, len(yes)), replace=False)]
        both = no + sorted(drawn)
        sample = [both[k] for k in rng.permutation(len(both))]
        sample_path.write_text(json.dumps(sample, indent=1))
    sample: list[str] = json.loads(sample_path.read_text())
    answers: dict[str, object] = (
        json.loads(answers_path.read_text()) if answers_path.exists() else {"_run": name}
    )
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/":
                rows = [{"id": i, "answer": answers.get(i)} for i in sample]
                page = PAGE.replace("/*DATA*/null", json.dumps(rows).replace("</", "<\\/"))
                self.send(200, page.encode("utf-8"), "text/html; charset=utf-8")
                return
            image_id = unquote(self.path.removeprefix("/img/").removesuffix(".png"))
            picture = OUT / name / f"{image_id}.png"
            if self.path.startswith("/img/") and image_id in sample and picture.exists():
                self.send(200, picture.read_bytes(), "image/png")
            else:
                self.send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                image_id, answer = str(body["id"]), dict(body["answer"])
                ok = image_id in sample and all(
                    answer.get(k) in ("yes", "no") for k in ("rim_in_frame", "outline_follows")
                )
            except (ValueError, KeyError, TypeError):
                ok = False
            if self.path != "/save" or not ok:
                self.send(400, b"bad save", "text/plain")
                return
            with lock:
                answers[image_id] = {k: str(answer.get(k, "")) for k in JUDGE_KEYS}
                answers_path.write_text(json.dumps(answers, indent=1))
            self.send(200, b"ok", "text/plain")

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    done = sum(i in answers for i in sample)
    print(f"rim check at {url} ({len(sample)} outlines, {done} saved); Ctrl+C to stop")
    if open_page:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split")
    s.add_argument("--force", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("set", choices=("tune", "held", "friend"))
    r.add_argument("--tau", type=float, default=TAU)
    r.add_argument("--tag", default="")
    r.add_argument("--b", action="store_true", help="method B only, without the model")
    r.add_argument("--param", action="append", default=[], help="NAME=VALUE, a rim setting")
    c = sub.add_parser("score")
    c.add_argument("set", choices=("tune", "held", "friend"))
    c.add_argument("--tag", default="")
    k = sub.add_parser("check")
    k.add_argument("set", choices=("held", "friend"))
    k.add_argument("--port", type=int, default=8766)
    k.add_argument("--no-open", action="store_true", help="do not open the browser")
    a = p.parse_args()
    if a.cmd == "split":
        split(a.force)
    elif a.cmd == "run":
        for item in a.param:
            key, value = item.split("=")
            setattr(rim_module, key, type(getattr(rim_module, key))(value))
        run(a.set, a.tau, a.tag, a.b)
    elif a.cmd == "check":
        check(a.set, a.port, not a.no_open)
    else:
        score(a.set, a.tag)


if __name__ == "__main__":
    main()
