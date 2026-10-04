"""
phase8/ocr_readiness_engine.py

AI-EVAL PHASE 8.2: PRODUCTION OCR/HTR PREPROCESSING & READINESS ENGINE
======================================================================

PURPOSE:
Production implementation of the controlled preparation layer between
Phase 7 CONTINUE decisions and downstream OCR/HTR transcription models.

CORE CAPABILITIES:
1. Input Contract Adaptability: Consumes RescanDecisionResult, SafeImageState,
   or raw image arrays safely, respecting Phase 7 decisions.
2. Safe 4-Way Reading Orientation Normalization:
   - Analyzes axis anisotropy and polarity.
   - If confident and rotated (90°, 180°, 270°), losslessly de-rotates.
   - If ambiguous, NEVER forces a speculative rotation; preserves original orientation
     and flags ORIENTATION_AMBIGUOUS.
3. Fine Baseline Deskew:
   - Detects sub-orthogonal line tilt (|theta| <= 5.0°) via Radon projection variance.
   - Safely deskews canvas if skew exceeds configurable deadband.
4. Non-Destructive Multi-Representation Bundle:
   - Generates ready_gray, ready_bin, ready_bgr, and auxiliary rule_lines_mask.
   - Keeps raw_rectified_bgr completely unmodified and immutable.
   - Does NOT destructively delete handwriting strokes.
5. Geometry & Model Agnostic:
   - No A4 aspect ratio assumptions; supports arbitrary canvas sizes and landscape layouts.
   - No assumptions of specific OCR vendors (TrOCR, CRNN, Tesseract).
6. Provisional Telemetry:
   - Computes line pitch, PVR, collision ratio, and character scale metrics
     annotated as provisional calibration baselines.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Path Configuration & Frozen Module Imports
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Phase 6 Frozen Production Module
from phase6.correction_contracts import SafeImageState

# Phase 7 Frozen Production Module
from phase7.rescan_decision_engine import (
    RescanDecision,
    RescanDecisionResult,
)

# Phase 8.2 Production Contracts
from phase8.ocr_readiness_contracts import (
    ReadingOrientation,
    OCRReadinessVerdict,
    ProvisionalReadinessObservation,
    ReadinessTopologicalDefect,
    ReadinessNormalizationAction,
    PreprocessedImageBundle,
    TextTopologyMetrics,
    ReadinessPreparationConfig,
    OCRReadinessPreparationResult,
)


# ===========================================================================
# 1. CORE SIGNAL ANALYSIS UTILITIES
# ===========================================================================

def analyze_canvas_orientation(
    gray: np.ndarray,
    config: ReadinessPreparationConfig
) -> Tuple[ReadingOrientation, float, float, float, float, float]:
    """
    Evaluates 4-way reading orientation using axis anisotropy and directional polarity.
    Returns: (detected_orientation, confidence, axis_ratio, polarity_ratio, h_var, v_var)
    """
    h, w = gray.shape[:2]
    
    # 1. High-frequency foreground binarization
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    bin_fg = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 10
    )

    # 2. Projection profiles
    h_proj = np.asarray(np.sum(bin_fg, axis=1, dtype=np.float64) / 255.0)
    v_proj = np.asarray(np.sum(bin_fg, axis=0, dtype=np.float64) / 255.0)

    h_var = float(np.var(h_proj))
    v_var = float(np.var(v_proj))

    # Guard against sparse or blank canvases
    if h_var < config.min_content_variance and v_var < config.min_content_variance:
        return (ReadingOrientation.AMBIGUOUS, 0.0, 1.0, 1.0, h_var, v_var)

    axis_ratio = float(h_var / max(1.0, v_var))

    # 3. Axis determination
    if axis_ratio > config.min_axis_anisotropy_for_h:
        # Horizontal text lines -> 0° or 180°
        top_band = int(round(h * 0.30))
        bot_band = int(round(h * 0.70))
        top_mass = float(np.sum(h_proj[:top_band]))
        bot_mass = float(np.sum(h_proj[bot_band:]))
        
        polarity_ratio = float(top_mass / max(1.0, bot_mass))
        conf_margin = abs(polarity_ratio - 1.0)

        if conf_margin < config.min_polarity_confidence_margin:
            # Symmetric layout or missing header -> Ambiguous
            return (ReadingOrientation.AMBIGUOUS, 0.50, axis_ratio, polarity_ratio, h_var, v_var)

        confidence = float(np.clip(0.70 + (conf_margin * 0.25), 0.70, 0.95))
        if polarity_ratio > 1.0:
            return (ReadingOrientation.UPRIGHT_0, confidence, axis_ratio, polarity_ratio, h_var, v_var)
        else:
            return (ReadingOrientation.ROTATED_180_INVERTED, confidence, axis_ratio, polarity_ratio, h_var, v_var)

    elif axis_ratio < config.max_axis_anisotropy_for_v:
        # Vertical text lines -> 90° CW or 270° CCW
        left_band = int(round(w * 0.30))
        right_band = int(round(w * 0.70))
        left_mass = float(np.sum(v_proj[:left_band]))
        right_mass = float(np.sum(v_proj[right_band:]))
        
        polarity_ratio = float(right_mass / max(1.0, left_mass))
        conf_margin = abs(polarity_ratio - 1.0)

        if conf_margin < config.min_polarity_confidence_margin:
            return (ReadingOrientation.AMBIGUOUS, 0.50, axis_ratio, polarity_ratio, h_var, v_var)

        confidence = float(np.clip(0.70 + (conf_margin * 0.25), 0.70, 0.95))
        if polarity_ratio > 1.0:
            # Right-side concentration in vertical projection implies top header rotated 90° CW
            return (ReadingOrientation.ROTATED_90_CW, confidence, axis_ratio, polarity_ratio, h_var, v_var)
        else:
            return (ReadingOrientation.ROTATED_270_CCW, confidence, axis_ratio, polarity_ratio, h_var, v_var)

    else:
        # Near isotropic projection variance -> layout is ambiguous (e.g. square grid or square diagram)
        return (ReadingOrientation.AMBIGUOUS, 0.40, axis_ratio, 1.0, h_var, v_var)


def estimate_residual_skew(
    bin_fg: np.ndarray,
    config: ReadinessPreparationConfig
) -> float:
    """
    Estimates residual page/baseline skew angle theta in [-deskew_max_angle_deg, +deskew_max_angle_deg]
    using Radon projection variance maximization.
    """
    h, w = bin_fg.shape[:2]
    # Use downsampled canvas or center crop for fast, robust Radon sweep
    if max(h, w) > 1000:
        scale = 800.0 / float(max(h, w))
        sweep_bin = cv2.resize(bin_fg, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_NEAREST)
    else:
        sweep_bin = bin_fg

    sh, sw = sweep_bin.shape[:2]
    center = (sw // 2, sh // 2)

    best_angle = 0.0
    max_var = -1.0

    angles = np.arange(
        -config.deskew_max_angle_deg,
        config.deskew_max_angle_deg + (config.deskew_angle_step_deg / 2.0),
        config.deskew_angle_step_deg
    )

    for angle in angles:
        M = cv2.getRotationMatrix2D(center, float(angle), 1.0)
        rotated_mask = cv2.warpAffine(
            sweep_bin, M, (sw, sh), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0
        )
        h_proj = np.sum(rotated_mask, axis=1, dtype=np.float64)
        v = float(np.var(h_proj))
        if v > max_var:
            max_var = v
            best_angle = float(angle)

    # best_angle is the rotation angle required to align with horizontal;
    # therefore, text skew relative to horizontal is -best_angle.
    return -best_angle


def perform_fine_deskew(
    gray: np.ndarray,
    bgr: Optional[np.ndarray],
    skew_angle_deg: float
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Applies fine rotational deskew to compensate for detected line tilt.
    Uses BORDER_REPLICATE to avoid introducing artificial black border artifacts.
    """
    h, w = gray.shape[:2]
    center = (w // 2, h // 2)
    # Rotating by -skew_angle_deg aligns lines horizontally
    M = cv2.getRotationMatrix2D(center, -skew_angle_deg, 1.0)

    deskewed_gray = cv2.warpAffine(
        gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )
    deskewed_bgr = None
    if bgr is not None:
        deskewed_bgr = cv2.warpAffine(
            bgr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )

    return deskewed_gray, deskewed_bgr


def extract_topology_metrics(
    gray: np.ndarray,
    bin_fg: np.ndarray,
    axis_ratio: float,
    polarity_ratio: float,
    orient_conf: float,
    detected_skew: float
) -> Tuple[TextTopologyMetrics, Optional[np.ndarray]]:
    """
    Extracts line pitch, peak-to-valley ratio, glyph scales, and candidate rule lines.
    """
    h, w = gray.shape[:2]
    total_pixels = max(1, h * w)

    # 1. Horizontal profile for line pitch and valleys
    h_proj = np.sum(bin_fg, axis=1, dtype=np.float64) / 255.0
    kernel_len = max(3, int(round(h * 0.01)))
    smoothed_h = cv2.GaussianBlur(h_proj.reshape(-1, 1), (1, kernel_len if kernel_len % 2 == 1 else kernel_len + 1), 0).flatten()

    # Peak detection (text baselines)
    peaks = []
    valleys = []
    mean_h = np.mean(smoothed_h)

    for y in range(1, h - 1):
        if smoothed_h[y] > smoothed_h[y - 1] and smoothed_h[y] > smoothed_h[y + 1] and smoothed_h[y] > mean_h:
            peaks.append(y)
        elif smoothed_h[y] < smoothed_h[y - 1] and smoothed_h[y] < smoothed_h[y + 1]:
            valleys.append(y)

    # Pitch calculation
    if len(peaks) >= 2:
        pitches = np.diff(peaks)
        med_pitch = float(np.median(pitches))
    else:
        med_pitch = 0.0

    # Peak-to-valley ratio (PVR)
    peak_vals = [smoothed_h[p] for p in peaks] if peaks else [mean_h]
    valley_vals = [smoothed_h[v] for v in valleys] if valleys else [1.0]
    pvr = float(np.mean(peak_vals) / max(1.0, np.mean(valley_vals)))

    # 2. Connected Component analysis (Glyph scales and collisions)
    n_cc, cc_labels, cc_stats, cc_centroids = cv2.connectedComponentsWithStats(bin_fg, connectivity=8)

    char_heights = []
    colliding_components = 0
    valid_glyphs = 0

    valley_set = set(valleys)

    for i in range(1, n_cc):
        ch_w = cc_stats[i, cv2.CC_STAT_WIDTH]
        ch_h = cc_stats[i, cv2.CC_STAT_HEIGHT]
        ch_y = cc_stats[i, cv2.CC_STAT_TOP]
        ch_area = cc_stats[i, cv2.CC_STAT_AREA]

        # Ignore tiny speckles and full-canvas margins
        if ch_area < 8 or ch_h > (h * 0.5) or ch_w > (w * 0.7):
            continue

        valid_glyphs += 1
        char_heights.append(ch_h)

        # Check valley collision
        for vy in valleys:
            if ch_y < vy < (ch_y + ch_h):
                colliding_components += 1
                break

    if char_heights:
        med_char_h = float(np.median(char_heights))
        p25_char_h = float(np.percentile(char_heights, 25))
        p75_char_h = float(np.percentile(char_heights, 75))
    else:
        med_char_h = 0.0
        p25_char_h = 0.0
        p75_char_h = 0.0

    collision_ratio = float(colliding_components / max(1, valid_glyphs))

    # Skeleton stroke width estimation
    dist_map = cv2.distanceTransform(bin_fg, cv2.DIST_L2, 3)
    fg_dists = dist_map[bin_fg > 0]
    estimated_stroke_w = float(np.median(fg_dists) * 2.0) if len(fg_dists) > 0 else 1.0

    # 3. Ruled line candidate detection (Non-destructive auxiliary mask)
    rule_kernel_len = max(30, int(round(w * 0.15)))
    rule_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (rule_kernel_len, 1))
    rule_lines_mask = cv2.morphologyEx(bin_fg, cv2.MORPH_OPEN, rule_kernel)

    rule_pixels = int(np.count_nonzero(rule_lines_mask))
    rule_fraction = float(rule_pixels / float(total_pixels))

    overlap_mask = rule_lines_mask & bin_fg
    overlap_count = int(np.count_nonzero(overlap_mask))
    rule_collision_ratio = float(overlap_count / max(1, np.count_nonzero(bin_fg)))

    has_rule_lines = (rule_fraction > 0.003 and len(peaks) > 5)

    # 4. Stroke fragmentation & coalescence
    frag_count = sum(1 for i in range(1, n_cc) if cc_stats[i, cv2.CC_STAT_AREA] < 10)
    coalesce_count = sum(1 for i in range(1, n_cc) if cc_stats[i, cv2.CC_STAT_WIDTH] > (w * 0.4))
    frag_ratio = float(frag_count / max(1, n_cc - 1))
    coalesce_ratio = float(coalesce_count / max(1, n_cc - 1))

    metrics = TextTopologyMetrics(
        axis_anisotropy_ratio=axis_ratio,
        header_polarity_ratio=polarity_ratio,
        orientation_confidence=orient_conf,
        detected_line_count=len(peaks),
        peak_to_valley_ratio=pvr,
        median_line_pitch_px=med_pitch,
        line_collision_ratio=collision_ratio,
        detected_skew_angle_deg=detected_skew,
        median_char_height_px=med_char_h,
        char_height_p25_px=p25_char_h,
        char_height_p75_px=p75_char_h,
        estimated_stroke_width_px=estimated_stroke_w,
        ruled_line_pixel_fraction=rule_fraction,
        ruled_line_stroke_collision_ratio=rule_collision_ratio,
        stroke_fragmentation_ratio=frag_ratio,
        stroke_coalescence_ratio=coalesce_ratio,
        component_count=valid_glyphs,
    )

    return metrics, (rule_lines_mask if has_rule_lines else None)


# ===========================================================================
# 2. PRODUCTION PREPARATION & READINESS ENGINE
# ===========================================================================

def prepare_ocr_readiness(
    source: Union[SafeImageState, np.ndarray, Tuple[Any, Any]],
    document_id: str = "document",
    rescan_decision: Optional[Union[RescanDecisionResult, str]] = None,
    config: Optional[ReadinessPreparationConfig] = None
) -> OCRReadinessPreparationResult:
    """
    Executes the Phase 8.2 Preprocessing and Readiness Preparation Layer.
    Consumes verified safe states and produces a normalized, ready image bundle.
    """
    t0 = time.perf_counter()
    if config is None:
        config = ReadinessPreparationConfig()

    blockers: List[ReadinessTopologicalDefect] = []
    actions: List[ReadinessNormalizationAction] = []
    recommendations: List[str] = []
    warnings: List[str] = []
    unresolved_ambiguities: List[str] = []
    provenance: List[str] = []

    # -----------------------------------------------------------------------
    # Step 1: Input Precondition Handling & Buffer Extraction
    # -----------------------------------------------------------------------
    if isinstance(source, tuple) and len(source) == 2:
        source_item, decision_item = source
        source = source_item
        if rescan_decision is None:
            rescan_decision = decision_item

    # Extract decision value if provided
    decision_val = None
    if isinstance(rescan_decision, RescanDecisionResult):
        decision_val = rescan_decision.decision
        provenance.append(f"Ingested from Phase 7 RescanDecisionResult (Decision: {rescan_decision.decision})")
    elif isinstance(rescan_decision, str):
        decision_val = rescan_decision
        provenance.append(f"Ingested Phase 7 routing verdict string: {rescan_decision}")

    if decision_val == "RESCAN_REQUIRED":
        # Fatal document failure veto from Phase 5/7
        provenance.append("Phase 7 RESCAN_REQUIRED: Document failed physical quality veto. Halting.")
        blockers.append(ReadinessTopologicalDefect.LINE_COLLISION_ENTANGLEMENT)
        warnings.append("Document received fatal RESCAN_REQUIRED from Phase 7 intake gate.")
        if isinstance(source, SafeImageState):
            raw_bgr = source.raw_rectified_bgr.copy()
            gray = source.image_gray.copy()
        elif isinstance(source, np.ndarray):
            gray = source.copy() if source.ndim == 2 else cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
            raw_bgr = source.copy() if source.ndim == 3 else cv2.cvtColor(source, cv2.COLOR_GRAY2BGR)
        else:
            gray = np.zeros((100, 100), dtype=np.uint8)
            raw_bgr = np.zeros((100, 100, 3), dtype=np.uint8)

        bundle = PreprocessedImageBundle(
            ready_gray=gray,
            ready_bin=np.zeros_like(gray),
            ready_bgr=raw_bgr,
            raw_rectified_bgr=raw_bgr,
            rule_lines_mask=None,
        )
        dummy_metrics = TextTopologyMetrics(
            axis_anisotropy_ratio=1.0,
            header_polarity_ratio=1.0,
            orientation_confidence=0.0,
            detected_line_count=0,
            peak_to_valley_ratio=1.0,
            median_line_pitch_px=0.0,
            line_collision_ratio=1.0,
            detected_skew_angle_deg=0.0,
            median_char_height_px=0.0,
            char_height_p25_px=0.0,
            char_height_p75_px=0.0,
            estimated_stroke_width_px=0.0,
            ruled_line_pixel_fraction=0.0,
            ruled_line_stroke_collision_ratio=0.0,
            stroke_fragmentation_ratio=0.0,
            stroke_coalescence_ratio=0.0,
            component_count=0,
        )
        return OCRReadinessPreparationResult(
            document_id=document_id,
            verdict=OCRReadinessVerdict.NOT_READY,
            provisional_observation=ProvisionalReadinessObservation.UPSTREAM_RESCAN_REQUIRED,
            detected_orientation=ReadingOrientation.AMBIGUOUS,
            applied_rotation_deg=0,
            detected_skew_angle_deg=0.0,
            applied_deskew_angle_deg=0.0,
            is_orientation_ambiguous=True,
            applied_actions=[ReadinessNormalizationAction.NO_OP],
            blockers=blockers,
            warnings=warnings,
            unresolved_ambiguities=["Upstream document rejected by Phase 7 rescan veto."],
            recommended_downstream_actions=["Physical page rescan required by Phase 7 intake gate."],
            image_bundle=bundle,
            metrics=dummy_metrics,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            provenance_notes=provenance,
        )

    if isinstance(source, SafeImageState):
        working_gray = source.image_gray.copy()
        raw_master_bgr = source.raw_rectified_bgr.copy()
        working_bgr = raw_master_bgr.copy()
        provenance.append("Ingested directly from Phase 6 SafeImageState")

    elif isinstance(source, np.ndarray):
        if source.ndim == 2:
            working_gray = source.copy()
            raw_master_bgr = cv2.cvtColor(source, cv2.COLOR_GRAY2BGR)
            working_bgr = raw_master_bgr.copy()
        else:
            working_bgr = source.copy()
            raw_master_bgr = source.copy()
            working_gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
        provenance.append("Ingested raw image buffer")
    else:
        raise TypeError(f"Unsupported source type for Phase 8.2: {type(source)}")

    # -----------------------------------------------------------------------
    # Step 2: Reading Orientation Detection & Safe Orthogonal De-Rotation
    # -----------------------------------------------------------------------
    (
        detected_orient,
        orient_conf,
        axis_ratio,
        polarity_ratio,
        h_var,
        v_var
    ) = analyze_canvas_orientation(working_gray, config)

    applied_rotation = 0
    is_ambiguous = (detected_orient == ReadingOrientation.AMBIGUOUS)

    if is_ambiguous:
        blockers.append(ReadinessTopologicalDefect.ORIENTATION_AMBIGUOUS)
        unresolved_ambiguities.append(f"Reading orientation is ambiguous (AxisRatio: {axis_ratio:.2f}, Polarity: {polarity_ratio:.2f}). Safe state left unrotated.")
        recommendations.append("Reading orientation is ambiguous. Canvas left unrotated to avoid speculative error.")
        provenance.append(f"Orientation ambiguous (AxisRatio: {axis_ratio:.2f}, Polarity: {polarity_ratio:.2f})")
    elif detected_orient != ReadingOrientation.UPRIGHT_0:
        blockers.append(ReadinessTopologicalDefect.ORIENTATION_ROTATED)
        if config.allow_auto_rotation:
            if detected_orient == ReadingOrientation.ROTATED_90_CW:
                working_gray = cv2.rotate(working_gray, cv2.ROTATE_90_COUNTERCLOCKWISE)
                if working_bgr is not None:
                    working_bgr = cv2.rotate(working_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
                applied_rotation = 270
                actions.append(ReadinessNormalizationAction.DE_ROTATE_90_CCW)
                provenance.append("Applied lossless orthogonal de-rotation: 90° CW -> UPRIGHT (270° CCW warp)")

            elif detected_orient == ReadingOrientation.ROTATED_180_INVERTED:
                working_gray = cv2.rotate(working_gray, cv2.ROTATE_180)
                if working_bgr is not None:
                    working_bgr = cv2.rotate(working_bgr, cv2.ROTATE_180)
                applied_rotation = 180
                actions.append(ReadinessNormalizationAction.DE_ROTATE_180)
                provenance.append("Applied lossless orthogonal de-rotation: 180° Inversion -> UPRIGHT")

            elif detected_orient == ReadingOrientation.ROTATED_270_CCW:
                working_gray = cv2.rotate(working_gray, cv2.ROTATE_90_CLOCKWISE)
                if working_bgr is not None:
                    working_bgr = cv2.rotate(working_bgr, cv2.ROTATE_90_CLOCKWISE)
                applied_rotation = 90
                actions.append(ReadinessNormalizationAction.DE_ROTATE_90_CW)
                provenance.append("Applied lossless orthogonal de-rotation: 270° CCW -> UPRIGHT (90° CW warp)")
        else:
            recommendations.append(f"Document is rotated ({detected_orient.value}); auto-rotation disabled in config.")
    else:
        provenance.append(f"Orientation verified upright (0°) with confidence {orient_conf:.2f}")

    # -----------------------------------------------------------------------
    # Step 3: High-Quality Binary Mask & Fine Baseline Deskew
    # -----------------------------------------------------------------------
    blur = cv2.GaussianBlur(working_gray, (5, 5), 0)
    bin_fg = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 10
    )

    detected_skew = estimate_residual_skew(bin_fg, config)
    applied_deskew = 0.0

    if config.allow_auto_deskew and abs(detected_skew) > config.deskew_deadband_deg:
        working_gray, working_bgr = perform_fine_deskew(working_gray, working_bgr, detected_skew)
        # Recalculate binary mask on deskewed canvas
        blur = cv2.GaussianBlur(working_gray, (5, 5), 0)
        bin_fg = cv2.adaptiveThreshold(
            blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 10
        )
        applied_deskew = -detected_skew
        actions.append(ReadinessNormalizationAction.DESKEW_FINE)
        provenance.append(f"Applied fine baseline deskew: {detected_skew:+.2f}° corrected")
    else:
        provenance.append(f"Residual skew {detected_skew:+.2f}° within deadband ({config.deskew_deadband_deg}°); no deskew required")

    # -----------------------------------------------------------------------
    # Step 4: Text-Line & Scale Telemetry Extraction
    # -----------------------------------------------------------------------
    metrics, rule_mask = extract_topology_metrics(
        working_gray, bin_fg, axis_ratio, polarity_ratio, orient_conf, detected_skew
    )

    if rule_mask is not None:
        actions.append(ReadinessNormalizationAction.RULED_LINE_MASK_GENERATED)
        provenance.append(f"Auxiliary ruled-line mask generated ({metrics.ruled_line_pixel_fraction*100:.2f}% canvas coverage)")
        if metrics.ruled_line_stroke_collision_ratio > config.ruled_line_collision_threshold:
            blockers.append(ReadinessTopologicalDefect.RULED_LINE_INTERFERENCE)
            warnings.append(f"Ruled lines intersect handwriting ({metrics.ruled_line_stroke_collision_ratio*100:.1f}% stroke collision).")
            recommendations.append("Ruled paper lines intersect handwriting strokes; evaluate candidate line suppression.")

    # Check line separation
    if metrics.line_collision_ratio > config.line_collision_threshold:
        blockers.append(ReadinessTopologicalDefect.LINE_COLLISION_ENTANGLEMENT)
        warnings.append(f"Inter-line collision observed ({metrics.line_collision_ratio*100:.1f}%). Advanced polygonal line extraction recommended.")
        recommendations.append(f"Inter-line collision high ({metrics.line_collision_ratio*100:.1f}%); use polygonal seam carving.")
    elif metrics.peak_to_valley_ratio < config.pvr_entangled_baseline:
        blockers.append(ReadinessTopologicalDefect.POOR_LINE_SEPARATION)
        warnings.append(f"Low line separation contrast (PVR={metrics.peak_to_valley_ratio:.2f}).")
        recommendations.append(f"Low line contrast (PVR={metrics.peak_to_valley_ratio:.2f}); evaluate adaptive baseline clustering.")

    # Check character scale
    if metrics.component_count > 0:
        if metrics.median_char_height_px < config.micro_char_height_px:
            blockers.append(ReadinessTopologicalDefect.MICRO_SCALE_TEXT)
            actions.append(ReadinessNormalizationAction.SCALE_NORMALIZATION_CANDIDATE)
            warnings.append(f"Micro-scale text observed (median {metrics.median_char_height_px:.1f}px).")
            recommendations.append(f"Micro-scale text (median {metrics.median_char_height_px:.1f}px); scale normalization recommended.")
        elif metrics.median_char_height_px > config.macro_char_height_px:
            blockers.append(ReadinessTopologicalDefect.MACRO_SCALE_TEXT)
            warnings.append(f"Macro-scale text observed (median {metrics.median_char_height_px:.1f}px).")
            recommendations.append(f"Macro-scale text (median {metrics.median_char_height_px:.1f}px); line patch downscaling recommended.")
    else:
        blockers.append(ReadinessTopologicalDefect.SPARSE_OR_BLANK_CONTENT)
        warnings.append("Insufficient glyph components found on canvas.")
        recommendations.append("Insufficient glyph components found on canvas.")

    # -----------------------------------------------------------------------
    # Step 5: Provisional Observation Synthesis (INVESTIGATION-LEVEL ONLY)
    # -----------------------------------------------------------------------
    # NOTE: Phase 8.2 NEVER performs final production OCR/HTR gating.
    # The observations below are exploratory telemetry categories for downstream systems.
    if is_ambiguous:
        provisional_obs = ProvisionalReadinessObservation.ORIENTATION_AMBIGUOUS
        verdict = OCRReadinessVerdict.ORIENTATION_AMBIGUOUS
        warnings.append("Orientation could not be unambiguously resolved; downstream review recommended.")
    elif ReadinessTopologicalDefect.LINE_COLLISION_ENTANGLEMENT in blockers:
        provisional_obs = ProvisionalReadinessObservation.COMPLEX_LAYOUT_OBSERVED
        verdict = OCRReadinessVerdict.NOT_READY
    elif ReadinessTopologicalDefect.ORIENTATION_ROTATED in blockers and not config.allow_auto_rotation:
        provisional_obs = ProvisionalReadinessObservation.NORMALIZATION_RECOMMENDED
        verdict = OCRReadinessVerdict.CONDITIONALLY_READY
        warnings.append("Document text is rotated, but auto-rotation is disabled in config.")
    elif any(b in [ReadinessTopologicalDefect.MICRO_SCALE_TEXT, ReadinessTopologicalDefect.RULED_LINE_INTERFERENCE] for b in blockers):
        provisional_obs = ProvisionalReadinessObservation.COMPLEX_LAYOUT_OBSERVED
        verdict = OCRReadinessVerdict.CONDITIONALLY_READY
    else:
        # Baselines are clean and orientation is upright
        if metrics.peak_to_valley_ratio >= config.pvr_clean_baseline and metrics.line_collision_ratio < 0.08:
            provisional_obs = ProvisionalReadinessObservation.PROVISIONAL_HTR_CANDIDATE
            verdict = OCRReadinessVerdict.HTR_READY
        else:
            provisional_obs = ProvisionalReadinessObservation.NORMALIZATION_RECOMMENDED
            verdict = OCRReadinessVerdict.CONDITIONALLY_READY

    # -----------------------------------------------------------------------
    # Step 6: Immutable Bundle Packaging & Result Construction
    # -----------------------------------------------------------------------
    bundle = PreprocessedImageBundle(
        ready_gray=working_gray,
        ready_bin=bin_fg,
        ready_bgr=working_bgr,
        raw_rectified_bgr=raw_master_bgr,
        rule_lines_mask=rule_mask,
    )

    if not actions:
        actions.append(ReadinessNormalizationAction.NO_OP)

    latency_ms = (time.perf_counter() - t0) * 1000.0

    return OCRReadinessPreparationResult(
        document_id=document_id,
        verdict=verdict,
        provisional_observation=provisional_obs,
        detected_orientation=detected_orient,
        applied_rotation_deg=applied_rotation,
        detected_skew_angle_deg=detected_skew,
        applied_deskew_angle_deg=applied_deskew,
        is_orientation_ambiguous=is_ambiguous,
        applied_actions=actions,
        blockers=blockers,
        warnings=warnings,
        unresolved_ambiguities=unresolved_ambiguities,
        recommended_downstream_actions=recommendations,
        image_bundle=bundle,
        metrics=metrics,
        latency_ms=latency_ms,
        provenance_notes=provenance,
    )
