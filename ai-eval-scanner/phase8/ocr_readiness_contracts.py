"""
phase8/ocr_readiness_contracts.py

AI-EVAL PHASE 8.2: OCR/HTR PREPROCESSING & READINESS CONTRACTS
==============================================================

PURPOSE:
Defines immutable data contracts, semantic enums, and configuration structures
for the Phase 8.2 Preprocessing and Readiness Preparation Layer.

ARCHITECTURAL PRINCIPLES (AUDITED):
1. Representation Preparation over Decision Making:
   Phase 8.2 prepares normalized, ready representations and telemetry evidence.
   It does NOT make a final production OCR/HTR readiness decision (Classifier = NOT FROZEN).
2. Non-Destructive Multi-Representation: Preserves original safe buffers and provides
   auxiliary normalized grayscale, color, and binarized representations.
3. Ambiguity Preservation: If reading orientation or baseline skew cannot be confidently
   determined, the engine NEVER forces a speculative rotation. It flags AMBIGUOUS.
4. Scale-Agnostic & Geometry-Free: No A4 aspect ratio assumptions, no portrait-only
   constraints; handles landscape, square crops, and arbitrary resolution inputs.
5. Strict Immutability: Stored buffers in output bundles are isolated and protected.
6. Provisional Baselines: All numerical configuration values are explicitly annotated
   as CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from dataclasses import dataclass, field

import numpy as np


# ===========================================================================
# 1. SEMANTIC ENUMS & TAXONOMY
# ===========================================================================

class ReadingOrientation(str, Enum):
    """
    Semantic 4-way reading orientation of document text relative to canvas top.
    """
    UPRIGHT_0 = "UPRIGHT_0"                    # Standard upright reading orientation (0°)
    ROTATED_90_CW = "ROTATED_90_CW"            # Page is rotated 90° clockwise (text reads downwards)
    ROTATED_180_INVERTED = "ROTATED_180_INVERTED"  # Page is upside down (180°)
    ROTATED_270_CCW = "ROTATED_270_CCW"        # Page is rotated 270° clockwise / 90° counter-clockwise
    AMBIGUOUS = "AMBIGUOUS"                    # Insufficient or conflicting evidence; rotation unsafe


class ProvisionalReadinessObservation(str, Enum):
    """
    INVESTIGATION_ONLY / PROVISIONAL / NOT A FINAL DECISION.
    Provisional semantic classification of extracted readiness evidence.
    This is an exploratory indicator for downstream intake experimentation,
    NOT a final production gating decision.
    """
    PROVISIONAL_OCR_CANDIDATE = "PROVISIONAL_OCR_CANDIDATE"      # High-contrast printed text observation
    PROVISIONAL_HTR_CANDIDATE = "PROVISIONAL_HTR_CANDIDATE"      # Clean handwritten script observation
    NORMALIZATION_RECOMMENDED = "NORMALIZATION_RECOMMENDED"      # Pre-OCR digital adjustments indicated
    COMPLEX_LAYOUT_OBSERVED = "COMPLEX_LAYOUT_OBSERVED"          # Inter-line collision / ruled lines / micro-scale noted
    ORIENTATION_AMBIGUOUS = "ORIENTATION_AMBIGUOUS"              # Unresolved orientation; safe to keep unrotated
    UPSTREAM_RESCAN_REQUIRED = "UPSTREAM_RESCAN_REQUIRED"        # Document received RESCAN_REQUIRED from Phase 7 intake


class OCRReadinessVerdict(str, Enum):
    """
    INVESTIGATION_ONLY / PROVISIONAL / NOT A FINAL DECISION.
    Retained for backward compatibility with exploratory test suites.
    NOTE: Production Readiness Classifier = NOT YET FROZEN.
    """
    OCR_READY = "OCR_READY"                      # Provisional observation: printed / high-contrast text
    HTR_READY = "HTR_READY"                      # Provisional observation: handwritten script
    CONDITIONALLY_READY = "CONDITIONALLY_READY"  # Provisional observation: normalization recommended
    NOT_READY = "NOT_READY"                      # Provisional observation: complex layout / collisions noted
    ORIENTATION_AMBIGUOUS = "ORIENTATION_AMBIGUOUS"  # Provisional observation: orientation uncertain


class ReadinessTopologicalDefect(str, Enum):
    """
    Specific topological blockers or layout warnings detected on the document canvas.
    """
    ORIENTATION_ROTATED = "ORIENTATION_ROTATED"
    ORIENTATION_AMBIGUOUS = "ORIENTATION_AMBIGUOUS"
    LINE_COLLISION_ENTANGLEMENT = "LINE_COLLISION_ENTANGLEMENT"
    POOR_LINE_SEPARATION = "POOR_LINE_SEPARATION"
    MICRO_SCALE_TEXT = "MICRO_SCALE_TEXT"
    MACRO_SCALE_TEXT = "MACRO_SCALE_TEXT"
    RULED_LINE_INTERFERENCE = "RULED_LINE_INTERFERENCE"
    EXCESSIVE_STROKE_FRAGMENTATION = "EXCESSIVE_STROKE_FRAGMENTATION"
    STROKE_COALESCENCE = "STROKE_COALESCENCE"
    SPARSE_OR_BLANK_CONTENT = "SPARSE_OR_BLANK_CONTENT"


class ReadinessNormalizationAction(str, Enum):
    """
    Candidate pre-OCR normalization operations applied or recommended.
    """
    NO_OP = "NO_OP"
    DE_ROTATE_90_CCW = "DE_ROTATE_90_CCW"        # Corrects 90° CW rotation
    DE_ROTATE_180 = "DE_ROTATE_180"              # Inverts upside-down page
    DE_ROTATE_90_CW = "DE_ROTATE_90_CW"          # Corrects 270° CCW rotation
    DESKEW_FINE = "DESKEW_FINE"                  # Corrects fine residual baseline skew (< 5°)
    RULED_LINE_MASK_GENERATED = "RULED_LINE_MASK_GENERATED"  # Non-destructive auxiliary mask
    SCALE_NORMALIZATION_CANDIDATE = "SCALE_NORMALIZATION_CANDIDATE"  # Flagged for line patch resizing


# ===========================================================================
# 2. OUTPUT DATA CONTRACTS
# ===========================================================================

@dataclass(frozen=True)
class PreprocessedImageBundle:
    """
    Multi-representation image bundle prepared for downstream OCR/HTR engines.
    Maintains complete isolation from the upstream raw rectified buffer.
    """
    ready_gray: np.ndarray                       # Normalized, de-rotated, deskewed grayscale image
    ready_bin: np.ndarray                        # Clean adaptive binarization for line segmentation
    ready_bgr: Optional[np.ndarray]              # Normalized 3-channel color image (for vision transformers)
    raw_rectified_bgr: np.ndarray                # Upstream frozen master buffer (read-only)
    rule_lines_mask: Optional[np.ndarray] = None # Detected ruling lines (if present; non-destructive)

    def __post_init__(self) -> None:
        """Enforce strict buffer immutability across all stored representations."""
        if isinstance(self.ready_gray, np.ndarray):
            self.ready_gray.flags.writeable = False
        if isinstance(self.ready_bin, np.ndarray):
            self.ready_bin.flags.writeable = False
        if isinstance(self.ready_bgr, np.ndarray):
            self.ready_bgr.flags.writeable = False
        if isinstance(self.raw_rectified_bgr, np.ndarray):
            self.raw_rectified_bgr.flags.writeable = False
        if isinstance(self.rule_lines_mask, np.ndarray):
            self.rule_lines_mask.flags.writeable = False


@dataclass(frozen=True)
class TextTopologyMetrics:
    """
    Quantitative measurements describing canvas line structure and stroke scale.
    All values are provisional calibration metrics; none are frozen production boundaries.
    """
    # Orientation signals (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    axis_anisotropy_ratio: float                 # Var(H_proj) / max(1.0, Var(V_proj))
    header_polarity_ratio: float                 # TopMass / BottomMass (or Right / Left)
    orientation_confidence: float                # Confidence score [0.0, 1.0]

    # Baseline & Line pitch signals (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    detected_line_count: int
    peak_to_valley_ratio: float                  # PVR: Mean(peaks) / Mean(valleys)
    median_line_pitch_px: float                  # Baseline-to-baseline vertical distance
    line_collision_ratio: float                  # Fraction of components crossing inter-line valleys
    detected_skew_angle_deg: float               # Estimated residual skew angle in [-5.0, +5.0]

    # Character scale signals (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    median_char_height_px: float                 # Median connected component height
    char_height_p25_px: float
    char_height_p75_px: float
    estimated_stroke_width_px: float             # Skeleton stroke width estimate

    # Artifact & Rule signals (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    ruled_line_pixel_fraction: float
    ruled_line_stroke_collision_ratio: float
    stroke_fragmentation_ratio: float
    stroke_coalescence_ratio: float
    component_count: int


@dataclass(frozen=True)
class ReadinessPreparationConfig:
    """
    Centralized configuration for Phase 8.2 preparation and normalization.
    ALL PARAMETERS ARE CALIBRATION BASELINES — NOT SCIENTIFICALLY FROZEN.
    """
    # Orientation discrimination parameters (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    min_axis_anisotropy_for_h: float = 1.30      # Ratio > 1.30 implies horizontal text lines
    max_axis_anisotropy_for_v: float = 0.75      # Ratio < 0.75 implies vertical text lines
    min_polarity_confidence_margin: float = 0.18 # |ratio - 1.0| must exceed this to distinguish polarities
    min_content_variance: float = 5.0            # Below this variance, canvas is considered blank/sparse
    allow_auto_rotation: bool = True             # If True, losslessly de-rotates confident orientations

    # Fine baseline deskew parameters (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    deskew_max_angle_deg: float = 5.0            # Max tilt searched (degrees)
    deskew_angle_step_deg: float = 0.25          # Search step resolution (degrees)
    deskew_deadband_deg: float = 0.40            # Skew below this threshold is not altered
    allow_auto_deskew: bool = True               # If True, deskews canvas if skew exceeds deadband

    # Line topology calibration values (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    pvr_clean_baseline: float = 2.20             # PVR above this indicates easily separable lines
    pvr_entangled_baseline: float = 1.65         # PVR below this indicates baseline entanglement
    line_collision_threshold: float = 0.15       # Collision fraction above this flags line overlap

    # Scale calibration values (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    micro_char_height_px: float = 12.0           # Median height below this flags micro-scale text
    macro_char_height_px: float = 65.0           # Median height above this flags macro-scale text

    # Ruled paper candidate parameters (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    ruled_line_collision_threshold: float = 0.15 # Collision fraction above this flags rule interference


@dataclass(frozen=True)
class OCRReadinessPreparationResult:
    """
    Definitive output contract of the Phase 8.2 Preprocessing & Readiness Preparation Layer.
    Carries prepared image representations and extracted telemetry evidence.
    Does NOT assert an unvalidated final OCR/HTR readiness probability.
    """
    document_id: str
    verdict: OCRReadinessVerdict                 # INVESTIGATION_ONLY / PROVISIONAL / NOT A FINAL DECISION
    provisional_observation: ProvisionalReadinessObservation # Exploratory telemetry categorization
    detected_orientation: ReadingOrientation
    applied_rotation_deg: int                    # 0, 90, 180, 270 (degrees clockwise applied)
    detected_skew_angle_deg: float
    applied_deskew_angle_deg: float
    is_orientation_ambiguous: bool
    applied_actions: List[ReadinessNormalizationAction]
    blockers: List[ReadinessTopologicalDefect]
    warnings: List[str]
    unresolved_ambiguities: List[str]
    recommended_downstream_actions: List[str]
    image_bundle: PreprocessedImageBundle
    metrics: TextTopologyMetrics
    latency_ms: float
    provenance_notes: List[str]
