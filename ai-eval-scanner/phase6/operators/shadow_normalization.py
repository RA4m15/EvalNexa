"""
phase6/operators/shadow_normalization.py

AI-EVAL PHASE 6.3: PRODUCTION SHADOW NORMALIZATION OPERATOR
============================================================

PURPOSE:
Production implementation of the scale-aware morphological background
normalization operator, adhering strictly to the Phase 6.2 CorrectionOperator
contract.

ARCHITECTURAL PRINCIPLES:
1. EVIDENCE-DRIVEN APPLICABILITY:
   Evaluates regional paper substrate illumination before proposing execution.
   If paper illumination is already uniform, returns (False, "NOT_APPLICABLE").
2. ISOLATION & NON-MUTATION:
   Operates strictly on isolated working copy; never mutates safe state buffers.
3. SCALE-AWARE MORPHOLOGY:
   Dilation and median filter kernels adapt dynamically to document resolution.
4. PROVISIONAL CALIBRATION BASELINES:
   All morphological and trigger thresholds are housed in ShadowNormalizationConfig
   and clearly marked as provisional calibration baselines, NOT immutable truths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
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
class ShadowNormalizationConfig:
    """
    Centralized calibration configuration for ShadowNormalizationOperator.
    
    NOTE: These parameters are empirical calibration baselines derived from
    Phase 4 and Phase 6.1 validation. They are NOT final frozen scientific
    constants and will be refined during Phase 11 field testing.
    """
    # Base morphological structuring element diameter at 1000px scale
    morph_kernel_base: int = 31

    # Ratio of median blur kernel relative to dilation kernel size
    blur_kernel_ratio: float = 0.75

    # Target paper white intensity post-normalization (prevents blinding over-saturation)
    target_white: float = 245.0

    # Regional paper deficit trigger (global paper white - darkest regional paper white)
    # PROVISIONAL: Deficit >= 40.0 intensity levels indicates true cast shadow
    min_spatial_deficit_trigger: float = 40.0

    # Spatial background ratio trigger (min_bg / max_bg < 0.68 indicates illumination gradient)
    max_bg_ratio_trigger: float = 0.68

    # Secondary trigger: high regional standard deviation
    min_spatial_bg_std_trigger: float = 25.0


# ===========================================================================
# 2. SHADOW NORMALIZATION OPERATOR IMPLEMENTATION
# ===========================================================================

class ShadowNormalizationOperator(CorrectionOperator):
    """
    Scale-aware morphological background division operator.
    Remediates regional cast shadows and uneven lighting gradients by estimating
    the spatial background field and normalizing paper substrate to a target white.
    """

    def __init__(self, config: Optional[ShadowNormalizationConfig] = None) -> None:
        self._config = config or ShadowNormalizationConfig()

    @property
    def operator_id(self) -> str:
        return "SHADOW_NORMALIZATION"

    @property
    def supported_condition(self) -> DefectConditionCategory:
        return DefectConditionCategory.ILLUMINATION_SHADOW

    @property
    def recoverability_class(self) -> RecoverabilityClass:
        return RecoverabilityClass.RECOVERABLE

    @property
    def prerequisite_operators(self) -> List[str]:
        # Shadow normalization is an initial photometric operation; no prerequisites
        return []

    @property
    def config(self) -> ShadowNormalizationConfig:
        return self._config

    def estimate_applicability(
        self,
        current_state: SafeImageState,
        quality_profile: Optional[QualityEvidenceProfile] = None
    ) -> Tuple[bool, str]:
        """
        Evaluate whether shadow normalization is warranted based on objective
        evidence of illumination non-uniformity.
        
        Returns (is_applicable, rationale).
        """
        # 1. Use Phase 5 Tier 2 profile evidence if provided
        if quality_profile is not None:
            spatial_bg_ratio = quality_profile.spatial_bg_ratio
            paper_deficit = quality_profile.worst_quadrant_paper_deficit
            spatial_bg_std = quality_profile.spatial_bg_std
        else:
            # Measure directly from working grayscale
            spatial_bg_ratio, paper_deficit, spatial_bg_std = self._measure_regional_background(
                current_state.image_gray
            )

        # 2. Check evidence against provisional calibration triggers
        has_deep_deficit = (
            spatial_bg_ratio < self._config.max_bg_ratio_trigger and
            paper_deficit >= self._config.min_spatial_deficit_trigger
        )
        has_high_variance = (
            spatial_bg_ratio < 0.60 and
            spatial_bg_std >= self._config.min_spatial_bg_std_trigger
        )

        if has_deep_deficit or has_high_variance:
            rationale = (
                f"Applicable: Significant illumination non-uniformity detected "
                f"(bg_ratio={spatial_bg_ratio:.3f} < {self._config.max_bg_ratio_trigger:.2f}, "
                f"paper_deficit={paper_deficit:.1f} >= {self._config.min_spatial_deficit_trigger:.1f})"
            )
            return True, rationale

        rationale = (
            f"Not Applicable: Document illumination is sufficiently uniform "
            f"(bg_ratio={spatial_bg_ratio:.3f}, paper_deficit={paper_deficit:.1f} < threshold)"
        )
        return False, rationale

    def apply(
        self,
        candidate_image: np.ndarray,
        config: Optional[Dict[str, Any]] = None
    ) -> np.ndarray:
        """
        Apply scale-aware morphological background division to an isolated working image.
        
        Guaranteed Invariant:
        Does NOT modify candidate_image in-place; returns a newly allocated np.ndarray.
        """
        if candidate_image.ndim != 2:
            raise ValueError(f"ShadowNormalizationOperator requires 2D grayscale image, got shape {candidate_image.shape}")

        cfg = config or {}
        morph_base = cfg.get("morph_kernel_base", self._config.morph_kernel_base)
        blur_ratio = cfg.get("blur_kernel_ratio", self._config.blur_kernel_ratio)
        target_white = cfg.get("target_white", self._config.target_white)

        h, w = candidate_image.shape[:2]
        scale_factor = min(w, h) / 1000.0

        # 1. Scale-aware morphological kernel
        raw_k = int(round(morph_base * scale_factor))
        k_size = max(11, min(61, raw_k | 1))  # Enforce odd diameter bounded [11, 61]
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))

        # 2. Morphological background estimation via dilation
        # Working on explicit copy to prevent any in-place mutation
        working_gray = candidate_image.copy()
        dilated = cv2.dilate(working_gray, kernel)

        # 3. Median filter to eliminate text ridges from background estimate
        blur_k = max(3, int(round(k_size * blur_ratio)) | 1)
        background = cv2.medianBlur(dilated, blur_k)

        # 4. Background division with zero-division guard
        bg_float = np.maximum(background.astype(np.float32), 1.0)
        normalized = (working_gray.astype(np.float32) / bg_float) * float(target_white)

        # 5. Range clamp to [0, 255]
        output_gray = np.clip(normalized, 0, 255).astype(np.uint8)
        return output_gray

    def _measure_regional_background(self, gray: np.ndarray) -> Tuple[float, float, float]:
        """
        Sample 4x4 regional paper substrate to compute spatial background ratio,
        worst quadrant paper deficit, and regional standard deviation.
        """
        h, w = gray.shape[:2]
        grid_rows, grid_cols = 4, 4
        cell_h = max(1, h // grid_rows)
        cell_w = max(1, w // grid_cols)
        regional_whites: List[float] = []

        # Sobel gradient to identify flat paper regions away from stroke edges
        grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = np.hypot(grad_x, grad_y)
        flat_thresh = max(15.0, float(np.percentile(grad_mag, 50)))

        for r in range(grid_rows):
            for c in range(grid_cols):
                y1, y2 = r * cell_h, min(h, (r + 1) * cell_h)
                x1, x2 = c * cell_w, min(w, (c + 1) * cell_w)
                cell = gray[y1:y2, x1:x2]
                cell_grad = grad_mag[y1:y2, x1:x2]

                flat_paper = cell[cell_grad < flat_thresh]
                if flat_paper.size > 30:
                    regional_whites.append(float(np.percentile(flat_paper, 85)))
                elif cell.size > 50:
                    regional_whites.append(float(np.percentile(cell, 90)))

        if len(regional_whites) >= 8:
            min_bg = min(regional_whites)
            max_bg = max(regional_whites)
            spatial_bg_ratio = float(min_bg / max(1.0, max_bg))
            spatial_bg_std = float(np.std(regional_whites))
            paper_deficit = float(max_bg - min_bg)
            return spatial_bg_ratio, paper_deficit, spatial_bg_std

        return 1.0, 0.0, 0.0
