"""Did a refactor change any results? Hash every 2D preset's fields, before and after.

    uv run python scripts/regression_hashes.py --write before.json     # on the old code
    uv run python scripts/regression_hashes.py --check before.json     # on the new code

Each preset is simulated at a small resolution (default 160 px, so all of them
take a minute or two) and every field array is hashed (SHA-256 of its bytes,
shape and dtype). --check reports each preset as identical or lists the fields
that changed, and exits non-zero if any did.

Hashes are bit-exact, so compare runs on the same machine and environment:
another platform or library version can change the last bits of floats. That is
why the baseline isn't committed or run in CI. Presets that need the GPU (H2 at
full size) run on the CPU here at the small resolution; skip slow ones with
--skip.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

from agatesim.config import load_preset, preset_names
from agatesim.simulate import simulate


def field_hashes(name: str, resolution: int) -> dict[str, str]:
    config = load_preset(name)
    config = config.model_copy(
        update={"grid": config.grid.model_copy(update={"resolution": resolution})}
    )
    fields = simulate(config).fields
    out: dict[str, str] = {}
    for key, array in sorted(fields.arrays().items()):
        a = np.ascontiguousarray(array)
        h = hashlib.sha256(a.tobytes())
        h.update(f"{a.shape}{a.dtype}".encode())
        out[key] = h.hexdigest()[:16]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", type=Path, help="save hashes to this JSON file")
    mode.add_argument("--check", type=Path, help="compare against hashes in this JSON file")
    parser.add_argument("--resolution", type=int, default=160)
    parser.add_argument("--skip", nargs="*", default=[], help="preset names to leave out")
    args = parser.parse_args()

    names = [n for n in preset_names() if n not in args.skip]
    current: dict[str, dict[str, str]] = {}
    for name in names:
        t0 = time.time()
        current[name] = field_hashes(name, args.resolution)
        print(f"  {name}: {time.time() - t0:.1f} s", file=sys.stderr)

    if args.write:
        payload = {"resolution": args.resolution, "presets": current}
        args.write.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"wrote {len(current)} presets to {args.write}")
        return

    saved = json.loads(args.check.read_text(encoding="utf-8"))
    if saved["resolution"] != args.resolution:
        raise SystemExit(f"baseline is at {saved['resolution']} px; pass --resolution to match")
    changed = 0
    for name, hashes in current.items():
        before = saved["presets"].get(name)
        if before is None:
            print(f"{name}: new (not in the baseline)")
            continue
        diff = [k for k in hashes if before.get(k) != hashes[k]]
        if diff:
            changed += 1
            print(f"{name}: CHANGED ({', '.join(diff)})")
        else:
            print(f"{name}: identical")
    for name in saved["presets"]:
        if name not in current and name not in args.skip:
            print(f"{name}: missing now")
    print(f"{len(current) - changed} of {len(current)} presets identical")
    sys.exit(1 if changed else 0)


if __name__ == "__main__":
    main()
