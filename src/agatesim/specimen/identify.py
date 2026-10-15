"""Identifying forms in a specimen photo with the archetype criteria.

Every criterion that can read observed fields is reported, but a verdict is only
as good as the photo analysis behind it. The analysis was validated on synthetic
photos (simulated slabs photographed on a cloth, with JPEG quality 95 and 75 and
two noise seeds) of every supported form's verification preset (ADR 0011):

- for every form but eye, a photo *pass* was never wrong (no false positives in
  24 photos of other forms each), so a pass is reliable;
- botryoidal was confirmed in all 4 of its photos; the other forms present were
  not (0 of 4): their strict criteria (closed rings, the flattest band's
  flatness, sharp corners, mirror-image sequences in a thin seam) seldom survive
  the noise in bands traced from a photo, so a *fail* says little;
- eye passed on the 4 botryoidal photos (their lobes read as eyes), and its own
  preset doesn't pass at the validation resolution, so its passes are not
  reliable.

tests/test_specimen.py guards the no-false-positive claim and the botryoidal
detection.
"""

from __future__ import annotations

from dataclasses import dataclass

from agatesim.criteria import evaluate
from agatesim.simulate import SimulationResult

# Forms whose criteria can read observed fields at all. Tube, moss and plume need
# inclusions, which photos don't yet detect; shadow and iris need optics.
SUPPORTED = (
    "fortification",
    "seam",
    "waterline",
    "fortification-waterline",
    "quartz-geode",
    "botryoidal",
    "eye",
)
# Forms whose photo passes were never false positives in validation (kept in step
# by tests/test_specimen.py). Eye is left out: it passed on botryoidal photos.
PASS_RELIABLE = frozenset(SUPPORTED) - {"eye"}
# How often validation photos of the form were confirmed (true positives / photos).
DETECTION_RATE = {
    "fortification": 0.0,
    "seam": 0.0,
    "waterline": 0.0,
    "fortification-waterline": 0.0,
    "quartz-geode": 0.0,
    "botryoidal": 1.0,
    "eye": None,  # its own preset fails at the validation resolution
}
NOT_FROM_PHOTOS = {
    "tube": "needs inclusions (filaments), not yet detected in photos",
    "moss": "needs inclusions (dendrites), not yet detected in photos",
    "plume": "needs inclusions, not yet detected in photos",
    "shadow": "an optical effect: needs the slab under directional light",
    "iris": "an optical effect: needs a backlit thin slice",
}


@dataclass(frozen=True)
class Identification:
    archetype: str
    passed: bool
    pass_reliable: bool
    detection_rate: float | None
    criteria: list[dict[str, object]]

    @property
    def score(self) -> float:
        """Share of criteria passed."""
        return sum(bool(c["passed"]) for c in self.criteria) / max(len(self.criteria), 1)

    @property
    def verdict(self) -> str:
        if self.passed:
            return "confirmed" if self.pass_reliable else "possible (unreliable test)"
        return "not confirmed"

    def to_json(self) -> dict[str, object]:
        return {
            "archetype": self.archetype,
            "passed": self.passed,
            "verdict": self.verdict,
            "pass_reliable": self.pass_reliable,
            "detection_rate": self.detection_rate,
            "score": round(self.score, 3),
            "criteria": self.criteria,
        }


def identify(result: SimulationResult) -> list[Identification]:
    """Each supported form judged on the observed fields: confirmed forms first,
    then by the share of criteria passed."""
    out: list[Identification] = []
    for archetype in SUPPORTED:
        ev = evaluate(archetype, result)
        out.append(
            Identification(
                archetype=archetype,
                passed=ev.passed,
                pass_reliable=archetype in PASS_RELIABLE,
                detection_rate=DETECTION_RATE.get(archetype),
                criteria=[r.__dict__ for r in ev.results],
            )
        )
    out.sort(key=lambda i: (i.passed and i.pass_reliable, i.passed, i.score), reverse=True)
    return out
