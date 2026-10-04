"""
phase6/operators/contrast_normalization.py

AI-EVAL PHASE 6.5: PRODUCTION CONTRAST NORMALIZATION OPERATOR
==============================================================

PURPOSE:
Production implementation of the controlled percentile contrast normalization
operator, adhering strictly to the Phase 6.2 CorrectionOperator contract.

ARCHITECTURAL PRINCIPLES:
1. EVIDENCE-DRIVEN APPLICABILITY:
   Evaluates local stroke-to-paper contrast and faint-stroke fraction rather than
   global dynamic range alone. Avoids false positives on clean documents or headers.
2. ISOLATION & NON-MUTATION:
   Operates strictly on an isolated working copy; never mutates safe state buffers
   or raw_rectified_bgr. Returns newly allocated ndarray.
3. CONDITIONALLY RECOVERABLE:
   Contrast expansion inherently amplifies substrate noise; execution is gated
   by post-correction multi-dimensional verification.
4. PROVISIONAL CALIBRATION BASELINES:
   All percentiles and trigger thresholds reside in ContrastNormalizationConfig
   and are clearly labeled as provisional calibration baselines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from phase6.correction_contracts import (
    CorrectionOperator,
    DefectConditionCategory,
    RecoverabilityClass,
    SafeImageState,
)
from phase5.production_quality_assessment import QualityEvidenceProfile


# ===========================================================================
# 1. CENTRALIZED CONFIGURATION (PROVISIONAL CALIBRATION BASELINES)
# ===========================================================================

@dataclass(frozen=True)
class ContrastNormalizationConfig:
    """
    Centralized calibration configuration for ContrastNormalizationOperator.
    
    CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN.
    Subject to real-world validation in Phase 11.
    """
    # Lower and upper percentiles for dynamic range stretching
    p_low: float = 1.0
    p_high: float = 99.0

    # Minimum dynamic range between p_high and p_low required to attempt stretching
    min_range_guard: float = 15.0

    # Primary applicability trigger: local stroke contrast median floor
    # Documents with local_stroke_contrast < 55.0 have deficient stroke contrast
    local_stroke_contrast_trigger: float = 55.0

    # Secondary applicability trigger: fraction of stroke pixels in faint contrast band [10, 35]
    # Documents with faint fraction >= 0.20 contain substantial washed-out writing
    faint_stroke_fraction_trigger: float = 0.20

    # Local background dilation base diameter at 1000px resolution
    local_bg_kernel_base: int = 25

    # Target minimum stroke contrast delta gain to consider enhancement successful
    min_stroke_contrast_gain: float = 15.0


# ===========================================================================
# 2. CONTRAST NORMALIZATION OPERATOR IMPLEMENTATION
# ===========================================================================

class ContrastNormalizationOperator(CorrectionOperator):
    """
    Linear percentile dynamic range expansion operator.
    Remediates low stroke contrast and washed-out handwriting by stretching
    the effective intensity distribution of stroke ink against paper substrate.
    """

    def __init__(self, config: Optional[ContrastNormalizationConfig] = None) -> None:
        self._config = config or ContrastNormalizationConfig()

    @property
    def operator_id(self) -> str:
        return "CONTRAST_NORMALIZATION"

    @property
    def supported_condition(self) -> DefectConditionCategory:
        return DefectConditionCategory.LOW_STROKE_CONTRAST

    @property
    def recoverability_class(self) -> RecoverabilityClass:
        return RecoverabilityClass.CONDITIONALLY_RECOVERABLE

    @property
    def prerequisite_operators(self) -> List[str]:
        # Soft preference handled dynamically by planner ordering.
        # Contrast does not enforce a rigid universal dependency when shadows are absent.
        return []

    @property
    def config(self) -> ContrastNormalizationConfig:
        return self._config

    def estimate_applicability(
        self,
        current_state: SafeImageState,
        quality_profile: Optional[QualityEvidenceProfile] = None
    ) -> Tuple[bool, str]:
        """
        Evaluate whether contrast normalization is warranted based on objective
        evidence of stroke contrast deficiency.
        
        Returns (is_applicable, rationale).
        """
        gray = current_state.image_gray
        h, w = gray.shape[:2]
        scale_factor = min(w, h) / 1000.0

        local_med_contrast, stroke_delta, faint_fraction = self._measure_stroke_contrast(gray, scale_factor)

        # 1. Clean document pass-through (NO_OP)
        # Pristine documents with high ink separation and low faint stroke fraction
        if local_med_contrast >= 70.0 and faint_fraction < 0.10:
            rationale = (
                f"Not Applicable: Document handwriting has strong contrast "
                f"(local_contrast={local_med_contrast:.1f} >= 70.0, faint_fraction={faint_fraction*100:.1f}% < 10.0%)"
            )
            return False, rationale

        # 2. Check applicability triggers
        has_low_contrast = local_med_contrast < self._config.local_stroke_contrast_trigger
        has_high_faint = faint_fraction >= self._config.faint_stroke_fraction_trigger

        if has_low_contrast or has_high_faint:
            rationale = (
                f"Applicable: Low stroke contrast detected "
                f"(local_contrast={local_med_contrast:.1f} < {self._config.local_stroke_contrast_trigger:.1f} "
                f"or faint_fraction={faint_fraction*100:.1f}% >= {self._config.faint_stroke_fraction_trigger*100:.1f}%)"
            )
            return True, rationale

        rationale = (
            f"Not Applicable: Contrast is within acceptable operational range "
            f"(local_contrast={local_med_contrast:.1f}, faint_fraction={faint_fraction*100:.1f}%)"
        )
        return False, rationale

    def apply(
        self,
        candidate_image: np.ndarray,
        config: Optional[Dict[str, Any]] = None
    ) -> np.ndarray:
        """
        Apply linear percentile contrast stretching to an isolated working image.
        
        Guaranteed Invariants:
        - Does NOT modify candidate_image in-place.
        - Returns a newly allocated np.ndarray.
        """
        if candidate_image.ndim != 2:
            raise ValueError(f"ContrastNormalizationOperator requires 2D grayscale image, got shape {candidate_image.shape}")

        cfg = config or {}
        p_low = cfg.get("p_low", self._config.p_low)
        p_high = cfg.get("p_high", self._config.p_high)
        guard = cfg.get("min_range_guard", self._config.min_range_guard)

        # Working on explicit copy to prevent any in-place mutation
        working_gray = candidate_image.copy()

        v_min = float(np.percentile(working_gray, p_low))
        v_max = float(np.percentile(working_gray, p_high))

        # Dynamic range guard to prevent division by zero on flat/uniform images
        if (v_max - v_min) < guard:
            return working_gray

        stretched = (working_gray.astype(np.float32) - v_min) * (255.0 / (v_max - v_min))
        output_gray = np.clip(stretched, 0, 255).astype(np.uint8)
        return output_gray

    def _measure_stroke_contrast(self, gray: np.ndarray, scale_factor: float) -> Tuple[float, float, float]:
        """
        Measures local stroke contrast median, global stroke intensity separation, and faint stroke fraction.
        Returns: (local_med_contrast, stroke_intensity_delta, faint_fraction)
        """
        h, w = gray.shape[:2]
        bg_k = max(11, int(round(self._config.local_bg_kernel_base * scale_factor)) | 1)
        local_bg = cv2.dilate(gray, cv2.getStructuringElement(cv2.MORPH_RECT, (bg_k, bg_k)))
        local_contrast = np.maximum(0, local_bg.astype(np.float32) - gray.astype(np.float32))

        adapt_k = max(15, int(round(min(w, h) * 0.03)) | 1)
        ref_bin = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, adapt_k, 10)

        stroke_mask = ref_bin > 0
        n_stroke = int(np.count_nonzero(stroke_mask))

        if n_stroke > 50:
            stroke_contrasts = local_contrast[stroke_mask]
            local_med_contrast = float(np.median(stroke_contrasts))
            faint_pixels = np.count_nonzero((stroke_contrasts >= 10.0) & (stroke_contrasts <= 35.0))
            faint_fraction = float(faint_pixels / n_stroke)

            paper_white = float(np.percentile(gray[~stroke_mask], 85)) if np.count_nonzero(~stroke_mask) > 100 else 240.0
            ink_core = float(np.percentile(gray[stroke_mask], 15))
            stroke_intensity_delta = float(paper_white - ink_core)
            return local_med_contrast, stroke_intensity_delta, faint_fraction

        return 100.0, 100.0, 0.0
