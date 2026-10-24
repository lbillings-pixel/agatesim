"""Record or check what photo analysis makes of the committed reference photos
(ADR 0006 point 5, ADR 0066).

    uv run python scripts/reference_regression.py            # show the differences
    uv run python scripts/reference_regression.py --write    # re-record on purpose

tests/test_reference_regression.py fails when the results change; look at what
changed, and re-record only if the change is intended (about a minute).
"""

from __future__ import annotations

import argparse
import json
import sys

from agatesim.specimen.regression import SNAPSHOT, load_snapshot, record, write_snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    now = record()
    if args.write:
        write_snapshot(now)
        hits = sum(len(v.get("recognised", [])) for v in now.values())  # pyright: ignore[reportArgumentType]
        forms = sum(len(v["forms"]) for v in now.values())  # pyright: ignore[reportArgumentType]
        print(f"wrote {SNAPSHOT}: {hits} of {forms} catalogued forms recognised")
        return 0
    before = load_snapshot()
    changed = [k for k in sorted(set(now) | set(before)) if now.get(k) != before.get(k)]
    for k in changed:
        print(f"{k}:\n  was {json.dumps(before.get(k))}\n  now {json.dumps(now.get(k))}")
    print(f"{len(changed)} of {len(now)} photos changed")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
