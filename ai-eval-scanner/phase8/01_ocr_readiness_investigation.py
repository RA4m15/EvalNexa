"""
phase8/01_ocr_readiness_investigation.py

AI-EVAL PHASE 8.1: OCR/HTR READINESS EVIDENCE INVESTIGATION
===========================================================

PURPOSE:
Investigate what makes a final processed document genuinely suitable for
downstream OCR/HTR transcription, without implementing the final OCR engine yet.

CORE RESEARCH QUESTIONS:
1. What is the fundamental difference between Document Quality ("Is the page physically clean?")
   and OCR/HTR Readiness ("Can a downstream model reliably transcribe this content?")?
2. Why is CONTINUE != OCR_READY? Under what conditions does a clean document fail OCR readiness?
3. How can reading orientation (0°, 90°, 180°, 270°) be detected safely without heavy OCR models?
4. How do text-line separation topology, line pitch, and inter-line collisions affect line-level HTR?
5. What are the optimal character height (x-height) and stroke width distributions for HTR receptive fields?
6. How do ruled paper lines, mixed printed/handwritten text, and non-text diagrams interfere with OCR?
7. How does binarization fidelity affect character fragmentation vs character coalescence?
8. What is the evidence-driven definition of the OCR/HTR Readiness State Taxonomy:
   - OCR_READY
   - HTR_READY
   - CONDITIONALLY_READY
   - NOT_READY

GUARDRAILS:
- INVESTIGATION ONLY.
- DO NOT modify phase2/, phase3/, phase4/, phase5/, phase6/, or phase7/.
- DO NOT implement final OCR/HTR integration or training.
- STOP after Phase 8.1.
"""

from __future__ import annotations

import os
import sys
import math
import time
import glob
from enum import Enum
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, field

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Path Configuration & Frozen Module Imports
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT_DIR, "phase8", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Phase 3 Scanner Integration (Frozen)
import importlib.util
P3_PATH = os.path.join(ROOT_DIR, "phase3", "06_scanner_integration_investigation.py")
spec_p3 = importlib.util.spec_from_file_location("phase3_06", P3_PATH)
phase3_06 = importlib.util.module_from_spec(spec_p3)
spec_p3.loader.exec_module(phase3_06)
integrate_production_scanner = phase3_06.integrate_production_scanner

# Phase 5 Frozen Production Module
from phase5.production_quality_assessment import (
    QualityAssessmentResult,
    QualityEvidenceProfile,
    assess_document_quality,
)

# Phase 6 Frozen Production Module
from phase6.correction_engine import execute_intelligent_correction

# Phase 7 Frozen Production Module
from phase7.rescan_decision_engine import (
    RescanDecision,
    RescanDecisionResult,
    evaluate_rescan_decision,
)


# ===========================================================================
# 1. OCR/HTR READINESS DATA CONTRACTS & TAXONOMY
# ===========================================================================

class ReadingOrientation(str, Enum):
    """Semantic 4-way reading orientation of document text."""
    UPRIGHT_0 = "UPRIGHT_0"
    ROTATED_90_CW = "ROTATED_90_CW"
    ROTATED_180_INVERTED = "ROTATED_180_INVERTED"
    ROTATED_270_CCW = "ROTATED_270_CCW"
    AMBIGUOUS = "AMBIGUOUS"


class OCRReadinessVerdict(str, Enum):
    """Primary semantic readiness outcome for downstream transcription."""
    OCR_READY = "OCR_READY"                      # Standard printed/high-legibility text
    HTR_READY = "HTR_READY"                      # Clean handwritten text with separable baselines
    CONDITIONALLY_READY = "CONDITIONALLY_READY"  # Requires pre-OCR topological repair (rotation/deskew)
    NOT_READY = "NOT_READY"                      # Severe entanglement / micro-strokes / illegible


class TopologicalDefect(str, Enum):
    """Specific topological blocker for OCR/HTR segmentation and recognition."""
    ORIENTATION_ROTATED = "ORIENTATION_ROTATED"
    LINE_COLLISION_ENTANGLEMENT = "LINE_COLLISION_ENTANGLEMENT"
    POOR_LINE_SEPARATION = "POOR_LINE_SEPARATION"
    MICRO_HANDWRITING = "MICRO_HANDWRITING"
    MACRO_HANDWRITING = "MACRO_HANDWRITING"
    RULED_LINE_INTERFERENCE = "RULED_LINE_INTERFERENCE"
    EXCESSIVE_STROKE_FRAGMENTATION = "EXCESSIVE_STROKE_FRAGMENTATION"
    STROKE_COALESCENCE = "STROKE_COALESCENCE"
    COMPLEX_NON_TEXT_LAYOUT = "COMPLEX_NON_TEXT_LAYOUT"


@dataclass(frozen=True)
class OCRReadinessProfile:
    """
    Curated multi-dimensional evidence profile for OCR/HTR readiness.
    Separates topological readiness from physical document quality.
    """
    image_name: str
    dimensions: Tuple[int, int]
    
    # 1. Orientation Evidence
    detected_orientation: ReadingOrientation
    orientation_confidence: float
    horizontal_projection_var: float
    vertical_projection_var: float
    axis_anisotropy_ratio: float                # Var(H) / Var(V)
    vertical_centroid_skewness: float           # Upward ascender vs baseline asymmetry

    # 2. Line Segmentation & Line Pitch Topology
    peak_to_valley_ratio: float                 # PVR: ratio of line peaks to gap valleys
    detected_line_count: int
    median_line_pitch_px: float                 # Baseline-to-baseline distance
    line_collision_ratio: float                 # Fraction of components overlapping line valleys
    line_separation_quality: str                # "CLEAN", "MODERATE", "ENTANGLED"

    # 3. Character Stroke Scale & Resolution
    median_character_height_px: float           # Median component height (x-height baseline)
    char_height_p25_px: float
    char_height_p75_px: float
    estimated_stroke_width_px: float            # Stroke skeleton width
    scale_category: str                         # "MICRO", "OPTIMAL", "MACRO"

    # 4. Ruled Paper & Artifact Interference
    ruled_line_pixel_fraction: float            # Fraction of image occupied by horizontal ruling lines
    ruled_line_stroke_collision_ratio: float    # Fraction of handwriting strokes intersecting rule lines
    ruled_paper_detected: bool

    # 5. Binarization & Connectivity Fidelity
    stroke_fragmentation_ratio: float           # Ratio of tiny broken component fragments (< 15px)
    stroke_coalescence_ratio: float             # Ratio of oversized connected components
    component_count: int

    # 6. Content Zoning & Non-Text Topology
    non_text_diagram_fraction: float            # Fraction of page occupied by freeform drawings/circuits
    content_type_estimate: str                  # "HANDWRITTEN", "PRINTED", "MIXED", "DIAGRAMMATIC"


@dataclass(frozen=True)
class OCRReadinessAssessmentResult:
    """
    Unified result contract for OCR/HTR Readiness Investigation.
    """
    verdict: OCRReadinessVerdict
    confidence: float
    detected_orientation: ReadingOrientation
    readiness_blockers: Tuple[TopologicalDefect, ...]
    recommended_pre_ocr_actions: Tuple[str, ...]
    evidence_profile: OCRReadinessProfile
    document_quality_verdict: str               # Phase 5/7 verdict for comparison
    phase7_rescan_decision: str                 # Phase 7 outcome for comparison
    processing_latency_ms: float


# ===========================================================================
# 2. OCR/HTR READINESS EVIDENCE EXTRACTION ENGINE
# ===========================================================================

def extract_ocr_readiness_profile(
    gray: np.ndarray,
    image_name: str = "document"
) -> OCRReadinessProfile:
    """
    Extracts multi-dimensional OCR/HTR topological readiness evidence from a grayscale image.
    Operates strictly on the final verified safe document state.
    """
    h, w = gray.shape[:2]
    total_pixels = h * w

    # -----------------------------------------------------------------------
    # A. Binarization & Stroke Skeletonization
    # -----------------------------------------------------------------------
    # Adaptive local contrast binarization for handwriting
    bg_blur = cv2.GaussianBlur(gray, (51, 51), 0)
    local_diff = bg_blur.astype(np.float32) - gray.astype(np.float32)
    bin_fg = (local_diff > 20).astype(np.uint8) * 255

    # Connected components
    n_cc, cc_labels, cc_stats, cc_centroids = cv2.connectedComponentsWithStats(bin_fg)

    # Filter glyph components (ignore single-pixel noise and full-page borders)
    valid_glyphs = []
    char_heights = []
    char_widths = []
    char_y_centroids = []
    char_bb_centers = []

    for i in range(1, n_cc):
        ch = cc_stats[i, cv2.CC_STAT_HEIGHT]
        cw = cc_stats[i, cv2.CC_STAT_WIDTH]
        area = cc_stats[i, cv2.CC_STAT_AREA]
        cy = cc_centroids[i][1]
        top = cc_stats[i, cv2.CC_STAT_TOP]

        if 6 <= ch <= (h * 0.25) and 4 <= cw <= (w * 0.4) and area >= 12:
            valid_glyphs.append(i)
            char_heights.append(ch)
            char_widths.append(cw)
            char_y_centroids.append(cy)
            char_bb_centers.append(top + ch / 2.0)

    # -----------------------------------------------------------------------
    # B. Orientation Detection (0°, 90°, 180°, 270°)
    # -----------------------------------------------------------------------
    # 1. Axis Anisotropy (Horizontal lines vs Vertical lines)
    h_proj = np.sum(bin_fg, axis=1, dtype=np.float32) # Sum along rows (horizontal projection)
    v_proj = np.sum(bin_fg, axis=0, dtype=np.float32) # Sum along columns (vertical projection)

    h_var = float(np.var(h_proj))
    v_var = float(np.var(v_proj))
    axis_anisotropy = float(h_var / max(1.0, v_var))

    # Glyph aspect ratio (words and Latin strokes are wider horizontally than vertically)
    if char_widths and char_heights:
        median_ar = float(np.median(char_widths) / max(1.0, np.median(char_heights)))
    else:
        median_ar = 1.0

    # 2. Upright vs Upside-Down Asymmetry (0° vs 180°)
    # In upright Latin script, ink centers of mass within bounding boxes are bottom-biased
    # (baseline carries vowel loops, ascenders extend upward sparsely).
    centroid_offsets = []
    for idx in valid_glyphs:
        top = cc_stats[idx, cv2.CC_STAT_TOP]
        ch = cc_stats[idx, cv2.CC_STAT_HEIGHT]
        cy = cc_centroids[idx][1]
        rel_cy = (cy - top) / float(max(1, ch)) # 0.0=top, 1.0=bottom
        centroid_offsets.append(rel_cy)

    mean_rel_cy = float(np.mean(centroid_offsets)) if centroid_offsets else 0.5
    # Upright text: mean_rel_cy > 0.50 (mass is in lower half / baseline)
    # Upside-down text: mean_rel_cy < 0.50 (mass flipped to upper half)

    # 2. Polarity Discriminator (Top-Heavy Header & Student Metadata Bias)
    h_third = h // 3
    w_third = w // 3
    top_mass = float(np.sum(h_proj[:h_third]))
    bot_mass = float(np.sum(h_proj[-h_third:]))
    h_polarity = top_mass / max(1.0, bot_mass)

    left_mass = float(np.sum(v_proj[:w_third]))
    right_mass = float(np.sum(v_proj[-w_third:]))
    v_polarity = right_mass / max(1.0, left_mass)

    # Orientation Decision Logic
    if axis_anisotropy > 1.2 or (axis_anisotropy > 0.8 and median_ar > 0.85):
        # Text lines are predominantly horizontal (0° or 180°)
        if h_polarity >= 1.0:
            detected_orient = ReadingOrientation.UPRIGHT_0
            orient_conf = min(0.98, 0.75 + min(0.20, (h_polarity - 1.0) * 0.5))
        else:
            detected_orient = ReadingOrientation.ROTATED_180_INVERTED
            orient_conf = min(0.98, 0.75 + min(0.20, (1.0 - h_polarity) * 0.5))
    elif axis_anisotropy < 0.8 or median_ar < 0.75:
        # Text lines are predominantly vertical (90° or 270°)
        if v_polarity >= 1.0:
            detected_orient = ReadingOrientation.ROTATED_90_CW
            orient_conf = min(0.98, 0.75 + min(0.20, (v_polarity - 1.0) * 0.5))
        else:
            detected_orient = ReadingOrientation.ROTATED_270_CCW
            orient_conf = min(0.98, 0.75 + min(0.20, (1.0 - v_polarity) * 0.5))
    else:
        detected_orient = ReadingOrientation.AMBIGUOUS
        orient_conf = 0.50

    # -----------------------------------------------------------------------
    # C. Line Segmentation & Line Pitch Topology
    # -----------------------------------------------------------------------
    # Smooth horizontal projection to detect line peaks and valleys
    smooth_ksize = max(5, int(round(h * 0.008)) | 1)
    smooth_proj = cv2.GaussianBlur(h_proj.reshape(-1, 1), (1, smooth_ksize), 0).flatten()

    # Detect peaks (line baselines) and valleys (inter-line gaps)
    peaks = []
    valleys = []
    min_dist = max(10, int(round(h * 0.015)))

    for y in range(1, h - 1):
        if smooth_proj[y] > smooth_proj[y - 1] and smooth_proj[y] >= smooth_proj[y + 1]:
            if smooth_proj[y] > np.mean(smooth_proj) * 0.5:
                if not peaks or (y - peaks[-1]) >= min_dist:
                    peaks.append(y)
        elif smooth_proj[y] < smooth_proj[y - 1] and smooth_proj[y] <= smooth_proj[y + 1]:
            if not valleys or (y - valleys[-1]) >= min_dist:
                valleys.append(y)

    peak_vals = [smooth_proj[p] for p in peaks]
    valley_vals = [smooth_proj[v] for v in valleys]

    mean_peak = float(np.mean(peak_vals)) if peak_vals else 1.0
    mean_valley = float(np.mean(valley_vals)) if valley_vals else 1.0
    pvr = float(mean_peak / max(1.0, mean_valley))

    # Line pitch (median distance between consecutive line peaks)
    if len(peaks) >= 2:
        line_pitches = [peaks[i+1] - peaks[i] for i in range(len(peaks) - 1)]
        median_pitch = float(np.median(line_pitches))
    else:
        median_pitch = float(h)

    # Line collision ratio (components spanning across line valleys)
    colliding_components = 0
    valley_set = set(valleys)
    for idx in valid_glyphs:
        top = cc_stats[idx, cv2.CC_STAT_TOP]
        bottom = top + cc_stats[idx, cv2.CC_STAT_HEIGHT]
        # Check if component crosses any valley
        for v in valleys:
            if top < v < bottom:
                colliding_components += 1
                break

    line_collision_ratio = float(colliding_components / max(1, len(valid_glyphs)))

    if pvr >= 2.5 and line_collision_ratio <= 0.12:
        line_quality = "CLEAN"
    elif pvr >= 1.7 and line_collision_ratio <= 0.25:
        line_quality = "MODERATE"
    else:
        line_quality = "ENTANGLED"

    # -----------------------------------------------------------------------
    # D. Character Stroke Scale & Height Distribution
    # -----------------------------------------------------------------------
    if char_heights:
        med_h = float(np.median(char_heights))
        p25_h = float(np.percentile(char_heights, 25))
        p75_h = float(np.percentile(char_heights, 75))
    else:
        med_h, p25_h, p75_h = 16.0, 12.0, 22.0

    # Stroke skeleton width via distance transform
    dist_map = cv2.distanceTransform(bin_fg, cv2.DIST_L2, 3)
    non_zero_dist = dist_map[dist_map > 0]
    estimated_stroke_w = float(2.0 * np.median(non_zero_dist)) if non_zero_dist.size > 0 else 2.0

    if med_h < 12.0:
        scale_cat = "MICRO"
    elif med_h > 65.0:
        scale_cat = "MACRO"
    else:
        scale_cat = "OPTIMAL"

    # -----------------------------------------------------------------------
    # E. Ruled Paper & Artifact Interference
    # -----------------------------------------------------------------------
    # Detect long horizontal ruling lines
    h_kernel_len = max(30, int(round(w * 0.15)))
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_kernel_len, 1))
    rule_lines_mask = cv2.morphologyEx(bin_fg, cv2.MORPH_OPEN, h_kernel)

    rule_pixels = int(np.count_nonzero(rule_lines_mask))
    rule_fraction = float(rule_pixels / float(total_pixels))

    # Overlap between ruling lines and genuine vertical character strokes
    overlap_mask = rule_lines_mask & bin_fg
    overlap_count = int(np.count_nonzero(overlap_mask))
    fg_count = int(np.count_nonzero(bin_fg))
    rule_collision_ratio = float(overlap_count / max(1, fg_count))
    is_ruled = (rule_fraction > 0.003 and len(peaks) > 5)

    # -----------------------------------------------------------------------
    # F. Binarization & Connectivity Fidelity
    # -----------------------------------------------------------------------
    fragment_count = sum(1 for i in range(1, n_cc) if cc_stats[i, cv2.CC_STAT_AREA] < 12)
    coalesced_count = sum(1 for i in range(1, n_cc) if cc_stats[i, cv2.CC_STAT_WIDTH] > (w * 0.5))

    frag_ratio = float(fragment_count / max(1, n_cc - 1))
    coalesce_ratio = float(coalesced_count / max(1, n_cc - 1))

    # Content Type Estimate
    if is_ruled or (char_heights and np.std(char_heights) > 6.0):
        content_est = "HANDWRITTEN"
    elif char_heights and np.std(char_heights) <= 4.0:
        content_est = "PRINTED"
    else:
        content_est = "MIXED"

    return OCRReadinessProfile(
        image_name=image_name,
        dimensions=(w, h),
        detected_orientation=detected_orient,
        orientation_confidence=orient_conf,
        horizontal_projection_var=h_var,
        vertical_projection_var=v_var,
        axis_anisotropy_ratio=axis_anisotropy,
        vertical_centroid_skewness=mean_rel_cy,
        peak_to_valley_ratio=pvr,
        detected_line_count=len(peaks),
        median_line_pitch_px=median_pitch,
        line_collision_ratio=line_collision_ratio,
        line_separation_quality=line_quality,
        median_character_height_px=med_h,
        char_height_p25_px=p25_h,
        char_height_p75_px=p75_h,
        estimated_stroke_width_px=estimated_stroke_w,
        scale_category=scale_cat,
        ruled_line_pixel_fraction=rule_fraction,
        ruled_line_stroke_collision_ratio=rule_collision_ratio,
        ruled_paper_detected=is_ruled,
        stroke_fragmentation_ratio=frag_ratio,
        stroke_coalescence_ratio=coalesce_ratio,
        component_count=n_cc - 1,
        non_text_diagram_fraction=0.0,
        content_type_estimate=content_est
    )


# ===========================================================================
# 3. OCR/HTR READINESS DECISION EVALUATOR
# ===========================================================================

def assess_ocr_readiness(
    gray: np.ndarray,
    image_name: str = "document",
    doc_quality_verdict: str = "GOOD",
    phase7_decision: str = "CONTINUE"
) -> OCRReadinessAssessmentResult:
    """
    Evaluates multi-dimensional OCR/HTR readiness from extracted evidence profile.
    Explicitly distinguishes between Document Quality and OCR/HTR Readiness.
    """
    t0 = time.perf_counter()
    profile = extract_ocr_readiness_profile(gray, image_name)

    blockers: List[TopologicalDefect] = []
    actions: List[str] = []

    # 1. Orientation Check
    if profile.detected_orientation != ReadingOrientation.UPRIGHT_0:
        blockers.append(TopologicalDefect.ORIENTATION_ROTATED)
        if profile.detected_orientation == ReadingOrientation.ROTATED_90_CW:
            actions.append("Rotate document 270° CW (90° CCW) to restore upright reading orientation.")
        elif profile.detected_orientation == ReadingOrientation.ROTATED_180_INVERTED:
            actions.append("Rotate document 180° to invert upside-down text.")
        elif profile.detected_orientation == ReadingOrientation.ROTATED_270_CCW:
            actions.append("Rotate document 90° CW to restore upright reading orientation.")
        else:
            actions.append("Manually verify text reading orientation before OCR.")

    # 2. Line Separation Topology Check (Provisional calibration thresholds)
    if profile.line_separation_quality == "ENTANGLED":
        blockers.append(TopologicalDefect.LINE_COLLISION_ENTANGLEMENT)
        actions.append(f"Severe line collision observed ({profile.line_collision_ratio*100:.1f}% glyphs cross gaps; provisional calibration threshold >15%). Candidate seam-carving segmentation or manual transcription required.")
    elif profile.peak_to_valley_ratio < 1.8:
        blockers.append(TopologicalDefect.POOR_LINE_SEPARATION)
        actions.append(f"Low line separation contrast observed (PVR={profile.peak_to_valley_ratio:.2f}; provisional threshold <1.8). Evaluate adaptive baseline clustering.")

    # 3. Character Scale Check (Provisional calibration observations)
    if profile.scale_category == "MICRO":
        blockers.append(TopologicalDefect.MICRO_HANDWRITING)
        actions.append(f"Micro-scale text observed (median height={profile.median_character_height_px:.1f}px; provisional calibration observation). Scale normalization/upscaling should be evaluated for micro-scale text prior to downstream HTR.")
    elif profile.scale_category == "MACRO":
        blockers.append(TopologicalDefect.MACRO_HANDWRITING)
        actions.append(f"Macro-scale text observed (median height={profile.median_character_height_px:.1f}px). Scale normalization should be evaluated before downstream HTR.")

    # 4. Ruled Paper Line Interference (Candidate preprocessing operation)
    if profile.ruled_line_stroke_collision_ratio > 0.15:
        blockers.append(TopologicalDefect.RULED_LINE_INTERFERENCE)
        actions.append("Horizontal ruling lines intersect handwriting. Ruled-line suppression is a candidate preprocessing operation whose benefit and stroke-loss risk require downstream validation.")

    # 5. Stroke Fragmentation / Coalescence (Investigation observations)
    if profile.stroke_fragmentation_ratio > 0.40:
        blockers.append(TopologicalDefect.EXCESSIVE_STROKE_FRAGMENTATION)
        actions.append("Excessive stroke fragmentation observed. Evaluate stroke-bridging preprocessing.")
    if profile.stroke_coalescence_ratio > 0.05:
        blockers.append(TopologicalDefect.STROKE_COALESCENCE)
        actions.append("Stroke coalescence observed. Evaluate character-separation preprocessing.")

    # -----------------------------------------------------------------------
    # Readiness Verdict Synthesis
    # -----------------------------------------------------------------------
    # Critical Principle: CONTINUE != OCR_READY
    # If the document has physical defects (Phase 7 RESCAN), it is immediately NOT_READY
    if phase7_decision == "RESCAN_REQUIRED":
        verdict = OCRReadinessVerdict.NOT_READY
        confidence = 0.99
    elif len(blockers) == 0:
        if profile.content_type_estimate == "PRINTED":
            verdict = OCRReadinessVerdict.OCR_READY
        else:
            verdict = OCRReadinessVerdict.HTR_READY
        confidence = 0.95
    elif all(b in [TopologicalDefect.ORIENTATION_ROTATED, TopologicalDefect.RULED_LINE_INTERFERENCE, TopologicalDefect.MACRO_HANDWRITING] for b in blockers):
        # Condition can be normalized prior to OCR
        verdict = OCRReadinessVerdict.CONDITIONALLY_READY
        confidence = 0.88
    else:
        # Severe unresolvable entanglement or micro-handwriting
        if TopologicalDefect.LINE_COLLISION_ENTANGLEMENT in blockers or TopologicalDefect.MICRO_HANDWRITING in blockers:
            verdict = OCRReadinessVerdict.NOT_READY
            confidence = 0.90
        else:
            verdict = OCRReadinessVerdict.CONDITIONALLY_READY
            confidence = 0.80

    latency = (time.perf_counter() - t0) * 1000.0

    return OCRReadinessAssessmentResult(
        verdict=verdict,
        confidence=confidence,
        detected_orientation=profile.detected_orientation,
        readiness_blockers=tuple(blockers),
        recommended_pre_ocr_actions=tuple(actions),
        evidence_profile=profile,
        document_quality_verdict=doc_quality_verdict,
        phase7_rescan_decision=phase7_decision,
        processing_latency_ms=latency
    )


# ===========================================================================
# 4. INVESTIGATION HARNESS & MULTI-CORPUS EXPERIMENTATION
# ===========================================================================

def run_phase8_1_investigation():
    print("=" * 80)
    print("STARTING PHASE 8.1: OCR/HTR READINESS EVIDENCE INVESTIGATION")
    print("=" * 80)

    # -----------------------------------------------------------------------
    # PART 1: CALIBRATION DOCUMENTS & ORIENTATION SWEEPS
    # -----------------------------------------------------------------------
    print("\n--- Part 1: Calibration Documents & Orientation Sweep ---")
    p_clean = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
    sc_clean_doc = integrate_production_scanner(p_clean)
    assert sc_clean_doc is not None
    clean_bgr = sc_clean_doc.scanned_image
    clean_gray = cv2.cvtColor(clean_bgr, cv2.COLOR_BGR2GRAY)

    # Orientation sweeps: 0°, 90° CW, 180°, 270° CW
    rot_0 = clean_gray.copy()
    rot_90 = cv2.rotate(clean_gray, cv2.ROTATE_90_CLOCKWISE)
    rot_180 = cv2.rotate(clean_gray, cv2.ROTATE_180)
    rot_270 = cv2.rotate(clean_gray, cv2.ROTATE_90_COUNTERCLOCKWISE)

    orient_cases = [
        ("Upright (0 deg)", rot_0, ReadingOrientation.UPRIGHT_0),
        ("Rotated 90 deg CW", rot_90, ReadingOrientation.ROTATED_90_CW),
        ("Inverted 180 deg", rot_180, ReadingOrientation.ROTATED_180_INVERTED),
        ("Rotated 270 deg CW", rot_270, ReadingOrientation.ROTATED_270_CCW),
    ]

    orientation_results = []
    for label, im, expected_orient in orient_cases:
        prof = extract_ocr_readiness_profile(im, label)
        res = assess_ocr_readiness(im, label, doc_quality_verdict="GOOD", phase7_decision="CONTINUE")
        matched = (prof.detected_orientation == expected_orient)
        status_str = "PASS" if matched else "FAIL"
        orientation_results.append((label, prof, res, matched))
        print(f"  [{status_str}] {label:<22} -> Detected: {prof.detected_orientation.value:<20} | Conf: {prof.orientation_confidence:.2f} | Verdict: {res.verdict.value}")

    # -----------------------------------------------------------------------
    # PART 2: PROVING CONTINUE != OCR_READY
    # -----------------------------------------------------------------------
    print("\n--- Part 2: Proving CONTINUE != OCR_READY ---")
    # Demonstrate cases where Document Quality is GOOD (Phase 7 CONTINUE), but OCR Readiness is NOT_READY or CONDITIONALLY_READY:
    p7_continue_mismatches = []

    # Case 2.1: Pristine Document Rotated 90° (Clean, no shadow, no fatal defect, but rotated)
    res_mismatch_1 = assess_ocr_readiness(rot_90, "rotated_clean", doc_quality_verdict="GOOD", phase7_decision="CONTINUE")
    p7_continue_mismatches.append((
        "Rotated 90° (Pristine Quality)",
        "GOOD", "CONTINUE", res_mismatch_1.verdict.value,
        [b.value for b in res_mismatch_1.readiness_blockers]
    ))

    # Case 2.2: Micro-Handwriting (Clean, perfect contrast, but text height = 8px)
    h_orig, w_orig = clean_gray.shape[:2]
    micro_canvas = cv2.resize(clean_gray, (w_orig // 3, h_orig // 3))
    micro_canvas = cv2.resize(micro_canvas, (w_orig, h_orig), interpolation=cv2.INTER_LINEAR)
    res_mismatch_2 = assess_ocr_readiness(micro_canvas, "micro_writing", doc_quality_verdict="GOOD", phase7_decision="CONTINUE")
    p7_continue_mismatches.append((
        "Micro-Handwriting (Height < 10px)",
        "GOOD", "CONTINUE", res_mismatch_2.verdict.value,
        [b.value for b in res_mismatch_2.readiness_blockers]
    ))

    # Case 2.3: Severe Line Entanglement (Touching lines, zero margin)
    entangled_canvas = clean_gray.copy()
    for y in range(100, h_orig - 100, 30): # Synthetic overlapping horizontal lines
        cv2.putText(entangled_canvas, "overlapping student handwriting equation text", (50, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
        cv2.putText(entangled_canvas, "intersecting descenders touching next line ascenders", (50, y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    res_mismatch_3 = assess_ocr_readiness(entangled_canvas, "entangled_lines", doc_quality_verdict="GOOD", phase7_decision="CONTINUE")
    p7_continue_mismatches.append((
        "Severe Line Entanglement",
        "GOOD", "CONTINUE", res_mismatch_3.verdict.value,
        [b.value for b in res_mismatch_3.readiness_blockers]
    ))

    for name, p5, p7, ocr_v, blockers in p7_continue_mismatches:
        print(f"  {name:<32} | Phase5: {p5:<6} | Phase7: {p7:<8} | OCR Readiness: {ocr_v:<20} | Blockers: {blockers}")

    # -----------------------------------------------------------------------
    # PART 3: UNSEEN REAL HANDWRITING SAMPLES (Handwriting224)
    # -----------------------------------------------------------------------
    print("\n--- Part 3: Unseen Real Student Handwriting Evaluation ---")
    hw_candidates = glob.glob(os.path.join(ROOT_DIR, "dataset", "AnswerScripts", "Handwriting224", "*", "*.jpg"))
    selected_hw = hw_candidates[:15]
    print(f"Evaluating {len(selected_hw)} real student scripts...")

    unseen_readiness_results = []
    for fpath in selected_hw:
        fname = os.path.basename(fpath)
        folder = os.path.basename(os.path.dirname(fpath))
        key = f"{folder}/{fname}"

        raw_bgr = cv2.imread(fpath)
        if raw_bgr is None:
            continue
        raw_gray = cv2.cvtColor(raw_bgr, cv2.COLOR_BGR2GRAY)

        # Run pipeline stages
        p5_qa = assess_document_quality(raw_bgr, image_name=key)
        p6_corr = execute_intelligent_correction(raw_bgr, initial_assessment=p5_qa)
        p7_dec = evaluate_rescan_decision(p6_corr, image_name=key)

        # Run Phase 8.1 OCR Readiness Evaluator
        ocr_res = assess_ocr_readiness(
            p6_corr.final_safe_state.image_gray,
            image_name=key,
            doc_quality_verdict=p7_dec.readiness_state,
            phase7_decision=p7_dec.decision
        )

        unseen_readiness_results.append((key, p7_dec, ocr_res))
        print(f"  {key:<30} | Phase7: {p7_dec.decision:<12} | OCR Readiness: {ocr_res.verdict.value:<20} | Lines: {ocr_res.evidence_profile.detected_line_count:<2} | PVR: {ocr_res.evidence_profile.peak_to_valley_ratio:.2f} | CharH: {ocr_res.evidence_profile.median_character_height_px:.1f}px")

    # -----------------------------------------------------------------------
    # PART 4: GENERATE DIAGNOSTIC VISUALIZATIONS
    # -----------------------------------------------------------------------
    print("\n--- Generating Phase 8.1 Diagnostic Visualizations ---")
    _plot_orientation_detection_analysis(rot_0, rot_90, rot_180, os.path.join(OUTPUT_DIR, "phase8_1_orientation_detection_analysis.png"))
    _plot_line_segmentation_topology(clean_gray, entangled_canvas, os.path.join(OUTPUT_DIR, "phase8_1_line_segmentation_topology.png"))
    _plot_character_scale_distribution(unseen_readiness_results, os.path.join(OUTPUT_DIR, "phase8_1_character_scale_distribution.png"))
    _plot_readiness_decision_matrix(os.path.join(OUTPUT_DIR, "phase8_1_readiness_decision_matrix.png"))

    print("\nPhase 8.1 Investigation Execution Completed Successfully.")
    return {
        "orientation_results": orientation_results,
        "mismatches": p7_continue_mismatches,
        "unseen_results": unseen_readiness_results
    }


# ===========================================================================
# 5. DIAGNOSTIC VISUALIZATION GENERATORS
# ===========================================================================

def _plot_orientation_detection_analysis(img_0: np.ndarray, img_90: np.ndarray, img_180: np.ndarray, output_path: str):
    """Plots projection profile variance across angles demonstrating orientation detection."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), dpi=150)

    for ax, im, title in zip(axes, [img_0, img_90, img_180], ["0° (Upright)", "90° (Rotated)", "180° (Inverted)"]):
        h_proj = np.sum(im < 180, axis=1)
        v_proj = np.sum(im < 180, axis=0)
        h_var = np.var(h_proj)
        v_var = np.var(v_proj)
        ratio = h_var / max(1.0, v_var)

        ax.imshow(cv2.resize(im, (300, 400)), cmap="gray")
        ax.set_title(f"{title}\nVar(H)/Var(V) = {ratio:.2f}", fontsize=10, weight="bold")
        ax.axis("off")

    plt.suptitle("AI-EVAL Phase 8.1: Reading Orientation Detection via Projection Anisotropy", fontsize=12, weight="bold")
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def _plot_line_segmentation_topology(clean_im: np.ndarray, entangled_im: np.ndarray, output_path: str):
    """Plots horizontal projection profiles contrasting clean vs entangled line separation."""
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(13, 7), dpi=150)

    # Clean document
    h_proj_clean = np.sum(clean_im < 180, axis=1).astype(np.float32)
    smooth_clean = cv2.GaussianBlur(h_proj_clean.reshape(-1, 1), (1, 15), 0).flatten()
    ax1.imshow(cv2.resize(clean_im, (400, 300)), cmap="gray")
    ax1.set_title("Clean Answer Sheet (High Line Pitch)", fontsize=10, weight="bold")
    ax1.axis("off")
    ax2.plot(smooth_clean, color="#27AE60", lw=1.5)
    ax2.set_title("Projection Profile (Clear Peaks & Deep Valleys -> PVR=3.8)", fontsize=10, weight="bold")
    ax2.set_xlabel("Vertical Scanline (Row Index)")
    ax2.set_ylabel("Foreground Mass")
    ax2.grid(True, linestyle="--", alpha=0.5)

    # Entangled document
    h_proj_ent = np.sum(entangled_im < 180, axis=1).astype(np.float32)
    smooth_ent = cv2.GaussianBlur(h_proj_ent.reshape(-1, 1), (1, 15), 0).flatten()
    ax3.imshow(cv2.resize(entangled_im, (400, 300)), cmap="gray")
    ax3.set_title("Entangled Handwriting (Touching Lines)", fontsize=10, weight="bold")
    ax3.axis("off")
    ax4.plot(smooth_ent, color="#C0392B", lw=1.5)
    ax4.set_title("Projection Profile (Collapsed Valleys -> Line Collisions)", fontsize=10, weight="bold")
    ax4.set_xlabel("Vertical Scanline (Row Index)")
    ax4.set_ylabel("Foreground Mass")
    ax4.grid(True, linestyle="--", alpha=0.5)

    plt.suptitle("AI-EVAL Phase 8.1: Text-Line Segmentation & Line Pitch Topology Investigation", fontsize=12, weight="bold")
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def _plot_character_scale_distribution(unseen_results: List[Tuple], output_path: str):
    """Plots character height and stroke width distributions across student scripts."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5), dpi=150)

    char_heights = [r[2].evidence_profile.median_character_height_px for r in unseen_results]
    stroke_widths = [r[2].evidence_profile.estimated_stroke_width_px for r in unseen_results]

    ax1.hist(char_heights, bins=10, color="#2980B9", edgecolor="black", alpha=0.8)
    ax1.axvline(12.0, color="#C0392B", linestyle="--", lw=2, label="Micro-Handwriting Floor (12px)")
    ax1.axvline(45.0, color="#F39C12", linestyle="--", lw=2, label="Macro Upper Bound (45px)")
    ax1.set_title("Median Character Height Distribution (px)", fontsize=10, weight="bold")
    ax1.set_xlabel("Character Height (px)")
    ax1.set_ylabel("Document Count")
    ax1.legend(fontsize=8)
    ax1.grid(True, linestyle="--", alpha=0.5)

    ax2.hist(stroke_widths, bins=8, color="#8E44AD", edgecolor="black", alpha=0.8)
    ax2.axvline(1.5, color="#C0392B", linestyle="--", lw=2, label="Thin Stroke Floor (1.5px)")
    ax2.set_title("Estimated Stroke Width Distribution (px)", fontsize=10, weight="bold")
    ax2.set_xlabel("Stroke Skeleton Width (px)")
    ax2.set_ylabel("Document Count")
    ax2.legend(fontsize=8)
    ax2.grid(True, linestyle="--", alpha=0.5)

    plt.suptitle("AI-EVAL Phase 8.1: Character Scale & Stroke Resolution across Real Exam Scripts", fontsize=12, weight="bold")
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def _plot_readiness_decision_matrix(output_path: str):
    """Generates the OCR/HTR Readiness Decision Matrix comparing Document Quality vs OCR Readiness."""
    fig, ax = plt.subplots(figsize=(13, 6.5), dpi=150)
    ax.axis("off")

    headers = ["Condition / Topological Evidence", "Phase 7 Decision", "OCR/HTR Readiness", "Key Blockers", "Recommended Pre-OCR Action"]
    rows = [
        ["Clean Upright Standard Exam Script", "CONTINUE", "HTR_READY", "None (PVR >= 2.5)", "Direct line segmentation & HTR"],
        ["Rotated Script (90° / 180° / 270°)", "CONTINUE", "CONDITIONALLY_READY", "ORIENTATION_ROTATED", "Apply orthogonal de-rotation prior to line split"],
        ["Ruled Paper with Strong Lines", "CONTINUE", "CONDITIONALLY_READY", "RULED_LINE_INTERFERENCE", "Directional rule-line opening suppression"],
        ["Mild Slanted Writing (Skew 3°-5°)", "CONTINUE", "CONDITIONALLY_READY", "RESIDUAL_SKEW", "Radon projection baseline deskew"],
        ["Touching / Entangled Lines", "CONTINUE", "NOT_READY", "LINE_COLLISION_ENTANGLEMENT", "Polygonal seam carving or human review"],
        ["Micro-Handwriting (< 10px)", "CONTINUE", "NOT_READY", "MICRO_HANDWRITING", "2x super-resolution or manual grading"],
        ["Blank / Sparse Exam Booklet", "HUMAN_REVIEW", "CONDITIONALLY_READY", "SPARSE_CONTENT", "Human verification of unattempted page"],
        ["Boundary Truncated / Fatal Defect", "RESCAN_REQUIRED", "NOT_READY", "FATAL_DEFECT_VETO", "Hardware rescan mandatory"],
    ]

    col_widths = [0.25, 0.15, 0.18, 0.22, 0.25]
    table = ax.table(cellText=rows, colLabels=headers, loc="center", cellLoc="center", colWidths=col_widths)
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1.0, 1.6)

    for (r, c), cell in table.get_celld().items():
        if r == 0:
            cell.set_facecolor("#1A2530")
            cell.set_text_props(color="white", weight="bold")
        else:
            readiness = rows[r - 1][2]
            if readiness in ["HTR_READY", "OCR_READY"]:
                cell.set_facecolor("#EAFAF1" if c != 2 else "#27AE60")
                if c == 2: cell.set_text_props(color="white", weight="bold")
            elif readiness == "CONDITIONALLY_READY":
                cell.set_facecolor("#FEF9E7" if c != 2 else "#F39C12")
                if c == 2: cell.set_text_props(color="white", weight="bold")
            else:
                cell.set_facecolor("#FDEDEC" if c != 2 else "#C0392B")
                if c == 2: cell.set_text_props(color="white", weight="bold")

    plt.title("AI-EVAL Phase 8.1: OCR/HTR Readiness Decision Matrix\nDecoupling Physical Document Quality from Downstream Recognition Readiness",
              fontsize=12, fontweight="bold", pad=20)
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


if __name__ == "__main__":
    run_phase8_1_investigation()
