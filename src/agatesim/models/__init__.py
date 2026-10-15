"""Formation models. Each takes a prepared domain and returns material Fields."""

from agatesim.models.base import Domain
from agatesim.models.fortification import ProceduralFortification, run_fortification
from agatesim.models.front_feedback import FrontFeedback, run_front_feedback
from agatesim.models.growth import ProceduralGrowth, run_growth
from agatesim.models.waterline import ProceduralWaterline, run_waterline

__all__ = [
    "Domain",
    "FrontFeedback",
    "ProceduralFortification",
    "ProceduralGrowth",
    "ProceduralWaterline",
    "run_fortification",
    "run_front_feedback",
    "run_growth",
    "run_waterline",
]
