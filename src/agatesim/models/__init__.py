"""Formation models. Each takes a prepared domain and returns material Fields."""

from agatesim.models.base import Domain
from agatesim.models.fortification import ProceduralFortification, run_fortification
from agatesim.models.front_feedback import FrontFeedback, run_front_feedback
from agatesim.models.growth import ProceduralGrowth, run_growth
from agatesim.models.liesegang import Liesegang, run_liesegang
from agatesim.models.settling import Settling, run_settling
from agatesim.models.waterline import ProceduralWaterline, run_waterline

__all__ = [
    "Domain",
    "FrontFeedback",
    "Liesegang",
    "ProceduralFortification",
    "ProceduralGrowth",
    "ProceduralWaterline",
    "Settling",
    "run_fortification",
    "run_front_feedback",
    "run_growth",
    "run_liesegang",
    "run_settling",
    "run_waterline",
]
