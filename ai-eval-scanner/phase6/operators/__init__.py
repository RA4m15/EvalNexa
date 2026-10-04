"""
phase6/operators/__init__.py
Pluggable correction operators for AI-EVAL Phase 6.
"""

from phase6.operators.shadow_normalization import ShadowNormalizationOperator
from phase6.operators.contrast_normalization import (
    ContrastNormalizationConfig,
    ContrastNormalizationOperator,
)

__all__ = [
    "ShadowNormalizationOperator",
    "ContrastNormalizationConfig",
    "ContrastNormalizationOperator",
]
