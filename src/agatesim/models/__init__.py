"""Formation models. Each takes a prepared domain and returns material Fields."""

from agatesim.models.base import Domain
from agatesim.models.fortification import ProceduralFortification, run_fortification
from agatesim.models.waterline import ProceduralWaterline, run_waterline

__all__ = [
    "Domain",
    "ProceduralFortification",
    "ProceduralWaterline",
    "run_fortification",
    "run_waterline",
]
