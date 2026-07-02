"""Relay coil inductive kick seed.

Standalone Class A implementation. Existing bounce / missed pulse / noise seeds
should remain separate and be called by the boundary harness as negative controls.
"""

from .classifier import classify_inductive_kick
from .generator import generate_inductive_case, generate_inductive_cases
from .features import extract_features

__all__ = [
    "classify_inductive_kick",
    "generate_inductive_case",
    "generate_inductive_cases",
    "extract_features",
]
