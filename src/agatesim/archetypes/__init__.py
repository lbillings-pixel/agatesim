"""The archetype ladder: agate forms the simulator aims to reproduce.

See docs/adr/0004-archetype-ladder.md for how archetypes are verified.
"""

from agatesim.archetypes.registry import (
    Archetype,
    Criterion,
    Host,
    Registry,
    Status,
    Subsystem,
    Tier,
    TierStatus,
    load_registry,
    to_markdown,
)

__all__ = [
    "Archetype",
    "Criterion",
    "Host",
    "Registry",
    "Status",
    "Subsystem",
    "Tier",
    "TierStatus",
    "load_registry",
    "to_markdown",
]
