"""The committed reference photos as regression data (ADR 0006 point 5, ADR 0066)."""

from agatesim.specimen.regression import load_snapshot, record


def test_photo_analysis_of_the_reference_photos_is_unchanged() -> None:
    """A change, better or worse, is looked at and re-recorded on purpose with
    scripts/reference_regression.py --write."""
    before, now = load_snapshot(), record()
    changed = {
        k: (before.get(k), now.get(k))
        for k in set(before) | set(now)
        if before.get(k) != now.get(k)
    }
    assert not changed, changed
