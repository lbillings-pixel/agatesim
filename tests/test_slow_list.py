import subprocess
import sys

from conftest import REPO_ROOT, SLOW


def test_every_slow_entry_names_a_collected_test() -> None:
    files = sorted({entry.split("::")[0] for entry in SLOW})
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *files],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    collected = {line for line in out.splitlines() if "::" in line}
    whole = {nodeid.split("[")[0] for nodeid in collected}
    missing = {entry for entry in SLOW if entry not in collected and entry not in whole}
    assert not missing, f"renamed or removed tests still listed as slow: {sorted(missing)}"
