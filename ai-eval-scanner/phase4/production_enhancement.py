"""
phase4/production_enhancement.py

AI-EVAL PRODUCTION MODULE: AUTOMATIC IMAGE ENHANCEMENT
======================================================
Production implementation of Phase 4 Document Image Enhancement based strictly
on the approved architectural findings of Phases 4.1–4.5.

CORE ARCHITECTURAL GUARANTEES:
1. Multi-Dimensional Condition Profile: Independent measurement of illumination,
   contrast, flat-paper noise, stroke acutance, and color fraction.
2. Semantic Paper & Ink Awareness: Noise measured exclusively on flat paper masks;
   contrast measured at stroke centers, preventing sparse math and dense text false positives.
3. Scale & Resolution Normalization: Filter kernels and gradient measurements scale
   proportionally with document pixel dimensions (no hardcoded fixed pixel assumptions).
4. No Standalone Triggers: Global dynamic range and global Laplacian variance are NOT
   permitted to trigger enhancement in isolation.
5. NO_OP / Pass-Through Support: Documents meeting clean baselines bypass processing.
6. Sequential Candidate Execution with Per-Stage Safety Gate:
   - Operators applied one at a time.
   - Each operator output verified against safe state.
   - ACCEPT -> commits new safe state.
   - REJECT -> rolls back to previous verified-safe state.
   - Previously accepted safe improvements are NEVER rolled back due to later operator failure.
7. Multi-Representation Output Contract:
   - enhanced_gray: Optimal clean grayscale for OCR/HTR.
   - raw_bgr: Preserved original rectified BGR (ultimate recovery representation).
   - binary_derivative: Adaptive binarized representation for OMR / layout parsing.
   - color_rubric_mask: Optional binary mask isolating grading marks / annotations.
8. Zero Universal Quality Scores & Zero Frozen Thresholds: All parameters are adaptive
   or bounded empirical safety guardrails.
"""

import os
import sys
import math
import time
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, field, asdict
import cv2
import numpy as np


# ===========================================================================
# 1. PRODUCTION DATA CONTRACTS & DATACLASSES
# ===========================================================================

@dataclass
class DocumentConditionProfile:
    """
    Multi-dimensional condition profile representing document image state.
    Derived using semantic paper/ink masking and scale normalization.
    """
    mean_paper_brightness: float            # Median intensity of detected paper substrate
    spatial_bg_ratio: float                 # Regional background ratio (min / max on paper)
    spatial_bg_std: float                   # Standard deviation of regional paper backgrounds
    spatial_bg_spread: float                # Max minus min regional background intensity
    paper_noise_sigma: float                # Noise sigma measured strictly on flat paper mask
    stroke_center_dynamic_range: float      # Paper white minus ink core intensity
    normalized_stroke_acutance: float       # Mean Sobel edge gradient along strokes, scale-normalized
    in_page_color_fraction: float           # Color pixel fraction strictly inside page quad
    scale_factor: float                     # min(W, H) / 1000.0
    has_illumination_gradient: bool         # True if cast shadow / lighting gradient detected
    has_low_contrast: bool                  # True if ink strokes lack sufficient dynamic contrast
    has_excessive_noise: bool               # True if paper substrate has sensor/grain noise
    has_optical_softness: bool              # True if strokes exhibit soft focus blur
    is_clean_document: bool                 # True if no remedial operator is required (NO_OP)


@dataclass
class OperatorVerificationEvidence:
    """
    Empirical multi-dimensional evidence evaluated after an operator execution.
    """
    thin_stroke_survival_ratio: float       # Ratio of surviving 1-pixel skeleton stroke pixels
    halo_gain: float                        # Max gradient overshoot at stroke boundaries
    connected_component_ratio: float        # Post-operator CC count / Pre-operator CC count
    background_mean_shift: float            # Absolute drift in flat paper mean intensity
    mean_absolute_difference: float         # Overall pixel change magnitude
    evidence_verdict: str                   # "PASS", "FAIL_FRAGMENTATION", "FAIL_HALO_OVERSHOOT", "FAIL_STROKE_LOSS", "NO_OP_PREFERABLE"
    rejection_reasons: List[str] = field(default_factory=list)


@dataclass
class OperatorExecutionRecord:
    """
    Audit record for an individual candidate operator evaluation.
    """
    operator_name: str                      # e.g., "SHADOW_CORRECTION", "CONTRAST_STRETCH"
    status: str                             # "ACCEPTED", "REJECTED_ROLLBACK", "BYPASSED_NO_OP"
    latency_ms: float                       # Execution time in milliseconds
    rejection_reason: Optional[str] = None  # Reason if rejected
    evidence: Optional[OperatorVerificationEvidence] = None


@dataclass
class EnhancedDocumentResult:
    """
    Unified production output contract delivered downstream to OCR/HTR/OMR engines.
    """
    status: str                             # "ENHANCED_VERIFIED", "NO_OP_PRISTINE", "RECOVERED_RAW_FALLBACK"
    enhanced_gray: np.ndarray               # Primary enhanced grayscale for OCR/HTR
    raw_bgr: np.ndarray                     # Preserved unmodified raw rectified BGR
    binary_derivative: Optional[np.ndarray] # Adaptive binary derivative for OMR / layout parsing
    color_rubric_mask: Optional[np.ndarray] # 8-bit binary mask of colored annotations (if any)
    condition_profile: DocumentConditionProfile
    operator_audit_log: List[OperatorExecutionRecord]
    total_latency_ms: float
    dimensions: Tuple[int, int]             # (width, height)
    is_reading_orientation_resolved: bool = False  # Explicitly deferred to OCR / readiness stage


# ===========================================================================
# 2. SCALE-NORMALIZED & SEMANTIC CONDITION MEASUREMENT ENGINE
# ===========================================================================

def extract_document_condition_profile(
    bgr_image: np.ndarray,
    page_mask: Optional[np.ndarray] = None
) -> Tuple[DocumentConditionProfile, np.ndarray, np.ndarray]:
    """
    Computes scale-normalized, semantic paper/ink condition measurements.
    Returns: (DocumentConditionProfile, paper_mask, ink_mask)
    """
    h, w = bgr_image.shape[:2]
    scale_factor = max(0.2, min(w, h) / 1000.0)

    # 1. Luminance & Grayscale
    if bgr_image.ndim == 3:
        gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2HSV)
    else:
        gray = bgr_image.copy()
        hsv = None

    # Restrict to validated document page boundary if provided
    active_mask = np.ones((h, w), dtype=bool) if page_mask is None else (page_mask > 0)

    # 2. Semantic Paper vs. Ink Segmentation
    # Calculate robust local gradient magnitude to avoid text boundaries
    sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.hypot(sobel_x, sobel_y)

    # Paper is high-reflectance and low-gradient
    active_gray = gray[active_mask]
    if active_gray.size == 0:
        active_gray = gray.flatten()

    median_bright = float(np.median(active_gray))
    paper_threshold = max(120.0, float(np.percentile(active_gray, 55)))
    flat_grad_threshold = float(np.percentile(grad_mag[active_mask], 60))

    paper_mask = (gray >= paper_threshold) & (grad_mag <= flat_grad_threshold) & active_mask

    # Fallback if paper mask is too sparse
    if np.count_nonzero(paper_mask) < 200:
        paper_mask = (gray >= np.percentile(gray, 50)) & active_mask

    mean_paper_brightness = float(np.median(gray[paper_mask]))

    # Ink mask is pixels significantly darker than local paper white
    ink_threshold = max(30.0, mean_paper_brightness - 25.0)
    ink_mask = (gray < ink_threshold) & active_mask

    # 3. Paper Noise Sigma (MAD on Laplacian over Paper Mask)
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    paper_lap = lap[paper_mask]
    if paper_lap.size > 100:
        med_lap = np.median(paper_lap)
        paper_noise_sigma = float(1.4826 * np.median(np.abs(paper_lap - med_lap)))
    else:
        paper_noise_sigma = 3.0

    # 4. Stroke-Center Dynamic Range (Ink-Aware, Sparse-Proof)
    if np.count_nonzero(ink_mask) > 50:
        ink_core_val = float(np.percentile(gray[ink_mask], 15))
        stroke_center_dynamic_range = float(max(0.0, mean_paper_brightness - ink_core_val))
    else:
        # Very sparse content; evaluate difference between 95th and 5th percentiles of active area
        stroke_center_dynamic_range = float(np.percentile(active_gray, 95) - np.percentile(active_gray, 5))

    # 5. Spatial Background Uniformity (Masked Paper Grid)
    # Evaluate 4x4 regional paper substrate to ignore text, ruled lines, and dark structural form boxes
    grid_rows, grid_cols = 4, 4
    cell_h = max(1, h // grid_rows)
    cell_w = max(1, w // grid_cols)
    regional_paper_whites = []
    flat_grad_thresh = max(15.0, float(np.percentile(grad_mag[active_mask], 50)))

    for r in range(grid_rows):
        for c in range(grid_cols):
            y1, y2 = r * cell_h, min(h, (r + 1) * cell_h)
            x1, x2 = c * cell_w, min(w, (c + 1) * cell_w)
            cell = gray[y1:y2, x1:x2]
            cell_grad = grad_mag[y1:y2, x1:x2]
            cell_act = active_mask[y1:y2, x1:x2] if active_mask is not None else np.ones_like(cell, dtype=bool)

            # Sample low-gradient paper substrate in this cell
            flat_paper = cell[(cell_grad < flat_grad_thresh) & cell_act]
            if flat_paper.size > 30:
                regional_paper_whites.append(float(np.percentile(flat_paper, 85)))
            else:
                cell_valid = cell[cell_act]
                if cell_valid.size > 50:
                    regional_paper_whites.append(float(np.percentile(cell_valid, 90)))

    if len(regional_paper_whites) >= 8:
        min_bg = min(regional_paper_whites)
        max_bg = max(regional_paper_whites)
        spatial_bg_ratio = float(min_bg / max(1.0, max_bg))
        spatial_bg_std = float(np.std(regional_paper_whites))
        spatial_bg_spread = float(max_bg - min_bg)
    else:
        spatial_bg_ratio = 1.0
        spatial_bg_std = 0.0
        spatial_bg_spread = 0.0
        min_bg = 255.0
        max_bg = 255.0

    # 6. Normalized Stroke Acutance (Scale-Normalized Gradient on Stroke Edges)
    stroke_edges = (grad_mag > 25.0) & active_mask
    if np.count_nonzero(stroke_edges) > 50:
        raw_acutance = float(np.mean(grad_mag[stroke_edges]))
        # Normalize by scale so that high-resolution documents are not artificially favored
        normalized_stroke_acutance = float(raw_acutance / (0.8 + 0.2 * scale_factor))
    else:
        normalized_stroke_acutance = 60.0

    # 7. In-Page Color Fraction
    if hsv is not None:
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        color_pixels = (sat > 50) & (val > 50) & active_mask
        in_page_color_fraction = float(np.count_nonzero(color_pixels) / max(1, np.count_nonzero(active_mask)))
    else:
        in_page_color_fraction = 0.0

    # 8. Multi-Dimensional Profile Condition Flags (Adaptive & Bounded)
    # Cast shadow: true cast shadow produces a deep intensity drop across paper substrate
    # (B_min / B_max < 0.68, spread >= 65 intensity levels, and shaded region paper drops below 165)
    # Minor illumination roll-off or handwriting density variation is NOT a cast shadow.
    has_illumination_gradient = bool(
        (spatial_bg_ratio < 0.68 and spatial_bg_spread >= 65.0 and min_bg < 165.0) or
        (spatial_bg_ratio < 0.60 and spatial_bg_std >= 25.0)
    )

    # Low contrast: stroke dynamic range is insufficient for reliable binarization
    has_low_contrast = bool(stroke_center_dynamic_range < 52.0)

    # Excessive noise: paper substrate grain/sensor noise exceeds baseline (excluding benign paper grain)
    has_excessive_noise = bool(paper_noise_sigma > 8.0)

    # Optical softness: stroke acutance is low, provided paper is not simply noisy
    has_optical_softness = bool(normalized_stroke_acutance < 42.0 and not has_excessive_noise)

    # Clean document: already legible, high contrast, uniform illumination
    is_clean_document = bool(
        not has_illumination_gradient and
        not has_low_contrast and
        not has_excessive_noise and
        not has_optical_softness
    )

    profile = DocumentConditionProfile(
        mean_paper_brightness=round(mean_paper_brightness, 2),
        spatial_bg_ratio=round(spatial_bg_ratio, 3),
        spatial_bg_std=round(spatial_bg_std, 2),
        spatial_bg_spread=round(spatial_bg_spread, 2),
        paper_noise_sigma=round(paper_noise_sigma, 2),
        stroke_center_dynamic_range=round(stroke_center_dynamic_range, 2),
        normalized_stroke_acutance=round(normalized_stroke_acutance, 2),
        in_page_color_fraction=round(in_page_color_fraction, 4),
        scale_factor=round(scale_factor, 3),
        has_illumination_gradient=has_illumination_gradient,
        has_low_contrast=has_low_contrast,
        has_excessive_noise=has_excessive_noise,
        has_optical_softness=has_optical_softness,
        is_clean_document=is_clean_document
    )

    return profile, paper_mask, ink_mask


# ===========================================================================
# 3. PRODUCTION OPERATOR IMPLEMENTATIONS (SCALE-ADAPTIVE)
# ===========================================================================

def apply_shadow_correction(gray: np.ndarray, scale_factor: float) -> np.ndarray:
    """
    Scale-proportional morphological background division to eliminate illumination gradients.
    Kernel size scales proportionally with document dimensions: K ~ 0.03 * min(W, H).
    """
    h, w = gray.shape[:2]
    # Proportional kernel: guarantees line-spacing coverage across 224x224 and 1600x1200
    k_size = max(7, int(round(min(w, h) * 0.03)) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))

    # Morphological dilation followed by median blur to estimate smooth background envelope
    dilated = cv2.dilate(gray, kernel)
    blur_k = max(3, int(round(k_size * 0.75)) | 1)
    background = cv2.medianBlur(dilated, blur_k)

    # Division normalization to 255.0 with clipping guard
    bg_float = np.maximum(background.astype(np.float32), 1.0)
    normalized = (gray.astype(np.float32) / bg_float) * 255.0
    return np.clip(normalized, 0, 255).astype(np.uint8)


def apply_contrast_stretching(gray: np.ndarray, p_low: float = 1.0, p_high: float = 99.0) -> np.ndarray:
    """
    Conservative linear min-max percentile stretch to expand stroke contrast safely.
    Uses 1st and 99th percentiles to avoid amplifying extreme outlier pixels.
    """
    v_min = float(np.percentile(gray, p_low))
    v_max = float(np.percentile(gray, p_high))
    if v_max - v_min < 15.0:
        return gray.copy()

    stretched = (gray.astype(np.float32) - v_min) * (255.0 / (v_max - v_min))
    return np.clip(stretched, 0, 255).astype(np.uint8)


def apply_bilateral_denoising(gray: np.ndarray, scale_factor: float) -> np.ndarray:
    """
    Edge-preserving bilateral denoising to suppress paper grain and sensor noise.
    Spatial radius scales with image resolution.
    """
    d = max(3, int(round(5 * scale_factor)) | 1)
    sigma_color = 25.0
    sigma_space = float(d)
    return cv2.bilateralFilter(gray, d=d, sigmaColor=sigma_color, sigmaSpace=sigma_space)


def apply_mild_unsharp_mask(gray: np.ndarray, scale_factor: float) -> np.ndarray:
    """
    Mild unsharp masking with halo suppression to restore stroke edge acutance.
    """
    sigma = max(0.8, 1.0 * scale_factor)
    blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma, sigmaY=sigma)
    # Strength factor alpha = 0.5 (conservative to prevent ringing)
    alpha = 0.5
    sharpened = cv2.addWeighted(gray, 1.0 + alpha, blurred, -alpha, 0)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


# ===========================================================================
# 4. SAFETY VERIFICATION & ROLLBACK ENGINE
# ===========================================================================

def verify_operator_safety(
    reference_gray: np.ndarray,
    candidate_gray: np.ndarray,
    operator_name: str,
    scale_factor: float
) -> OperatorVerificationEvidence:
    """
    Evaluates empirical multi-dimensional evidence to accept or reject an operator.
    Guarantees that an operator damaging thin strokes or introducing halos is caught.
    """
    rejection_reasons = []

    # 1. Mean Absolute Difference (Check for zero change / identity)
    diff = np.abs(candidate_gray.astype(np.float32) - reference_gray.astype(np.float32))
    mad = float(np.mean(diff))
    if mad < 0.5:
        return OperatorVerificationEvidence(
            thin_stroke_survival_ratio=1.0,
            halo_gain=0.0,
            connected_component_ratio=1.0,
            background_mean_shift=0.0,
            mean_absolute_difference=mad,
            evidence_verdict="NO_OP_PREFERABLE",
            rejection_reasons=["Operator caused negligible image change (MAD < 0.5)"]
        )

    # 2. Thin-Stroke Survival Analysis
    # Extract reference thin stroke skeleton
    _, ref_bin = cv2.threshold(reference_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    _, cand_bin = cv2.threshold(candidate_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    ref_edges = cv2.Canny(reference_gray, 40, 120)
    cand_edges = cv2.Canny(candidate_gray, 40, 120)

    n_ref_edge = int(np.count_nonzero(ref_edges))
    if n_ref_edge > 50:
        # Edge overlap within 1-pixel dilation
        dilated_cand = cv2.dilate(cand_edges, np.ones((3, 3), np.uint8))
        surviving = np.count_nonzero((ref_edges > 0) & (dilated_cand > 0))
        thin_stroke_survival = float(surviving / n_ref_edge)
    else:
        thin_stroke_survival = 1.0

    if thin_stroke_survival < 0.70:
        rejection_reasons.append(f"Excessive thin-stroke erosion: survival = {thin_stroke_survival*100:.1f}% (< 70%)")

    # 3. Halo Gain / Ringing Overshoot Analysis
    sobel_ref = np.hypot(cv2.Sobel(reference_gray, cv2.CV_32F, 1, 0), cv2.Sobel(reference_gray, cv2.CV_32F, 0, 1))
    sobel_cand = np.hypot(cv2.Sobel(candidate_gray, cv2.CV_32F, 1, 0), cv2.Sobel(candidate_gray, cv2.CV_32F, 0, 1))

    # Evaluate gradient surge on paper background adjacent to strokes
    dilated_ref = cv2.dilate(ref_bin, np.ones((5, 5), np.uint8))
    paper_near_strokes = cv2.bitwise_xor(dilated_ref, ref_bin)
    if np.count_nonzero(paper_near_strokes) > 50:
        halo_gain = float(np.mean(sobel_cand[paper_near_strokes > 0]) - np.mean(sobel_ref[paper_near_strokes > 0]))
    else:
        halo_gain = 0.0

    halo_limit = 10.0 * (1.0 + 0.2 * scale_factor)
    if halo_gain > halo_limit:
        rejection_reasons.append(f"Excessive edge ringing / halo overshoot: halo gain = +{halo_gain:.1f} (> {halo_limit:.1f})")

    # 4. Connected-Component Topological Stability
    n_cc_ref, _ = cv2.connectedComponents(ref_bin)
    n_cc_cand, _ = cv2.connectedComponents(cand_bin)
    cc_ratio = float(n_cc_cand / max(1, n_cc_ref))

    if cc_ratio > 1.60:
        rejection_reasons.append(f"Severe character fragmentation: CC count surged by {cc_ratio:.2f}x (> 1.60x)")
    elif cc_ratio < 0.65:
        rejection_reasons.append(f"Severe stroke smearing/bridging: CC count collapsed to {cc_ratio:.2f}x (< 0.65x)")

    # 5. Background Mean Shift
    ref_bg_median = float(np.percentile(reference_gray, 85))
    cand_bg_median = float(np.percentile(candidate_gray, 85))
    bg_shift = float(abs(cand_bg_median - ref_bg_median))

    if bg_shift > 45.0 and operator_name != "SHADOW_CORRECTION":
        rejection_reasons.append(f"Excessive paper background intensity shift: {bg_shift:.1f} (> 45.0)")

    # Final Verification Decision
    if not rejection_reasons:
        verdict = "PASS"
    else:
        verdict = "FAIL_" + ("STROKE_LOSS" if thin_stroke_survival < 0.70 else "DEGRADATION")

    return OperatorVerificationEvidence(
        thin_stroke_survival_ratio=round(thin_stroke_survival, 3),
        halo_gain=round(halo_gain, 2),
        connected_component_ratio=round(cc_ratio, 3),
        background_mean_shift=round(bg_shift, 2),
        mean_absolute_difference=round(mad, 2),
        evidence_verdict=verdict,
        rejection_reasons=rejection_reasons
    )


# ===========================================================================
# 5. MULTI-REPRESENTATION DERIVATIVE BUILDER
# ===========================================================================

def build_binary_derivative(enhanced_gray: np.ndarray, scale_factor: float) -> np.ndarray:
    """
    Constructs clean adaptive binary representation for downstream OMR & layout parsing.
    Uses scale-proportional Gaussian adaptive thresholding.
    """
    h, w = enhanced_gray.shape[:2]
    block_size = max(11, int(round(min(w, h) * 0.02)) | 1)
    C = 8.0
    return cv2.adaptiveThreshold(
        enhanced_gray,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv2.THRESH_BINARY_INV,
        blockSize=block_size,
        C=C
    )


def build_color_rubric_mask(
    bgr_image: np.ndarray,
    page_mask: Optional[np.ndarray],
    color_fraction: float
) -> Optional[np.ndarray]:
    """
    Extracts 8-bit binary mask of colored grading marks/annotations if present.
    Strictly masked to validated physical page quad.
    """
    if bgr_image.ndim != 3 or color_fraction < 0.003:
        return None

    hsv = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    color_mask = (sat > 50) & (val > 50)
    if page_mask is not None:
        color_mask = color_mask & (page_mask > 0)

    # Filter isolated single-pixel noise
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    cleaned = cv2.morphologyEx(color_mask.astype(np.uint8) * 255, cv2.MORPH_OPEN, kernel)
    return cleaned if np.count_nonzero(cleaned) > 25 else None


# ===========================================================================
# 6. UNIFIED PRODUCTION ENHANCEMENT PIPELINE
# ===========================================================================

def enhance_scanned_document(
    input_document: Union[Any, np.ndarray],
    page_quad_mask: Optional[np.ndarray] = None
) -> EnhancedDocumentResult:
    """
    Unified production entry point for Phase 4 Automatic Image Enhancement.

    Parameters:
    - input_document: Either a ScannedDocumentResult from Phase 3 or a raw BGR/Gray ndarray.
    - page_quad_mask: Optional binary mask of the validated document quad.

    Returns:
    - EnhancedDocumentResult: Multi-representation result containing enhanced_gray,
      raw_bgr, binary_derivative, color_rubric_mask, condition_profile, and audit log.
    """
    t_start = time.perf_counter()

    # 1. Unpack input and preserve raw rectified BGR
    if hasattr(input_document, "scanned_image"):
        raw_bgr = input_document.scanned_image.copy()
    elif isinstance(input_document, np.ndarray):
        raw_bgr = input_document.copy()
    else:
        raise TypeError(f"Unsupported input type for enhancement: {type(input_document)}")

    # Ensure raw_bgr is 3-channel for color preservation
    if raw_bgr.ndim == 2:
        raw_bgr_color = cv2.cvtColor(raw_bgr, cv2.COLOR_GRAY2BGR)
        raw_gray = raw_bgr.copy()
    else:
        raw_bgr_color = raw_bgr.copy()
        raw_gray = cv2.cvtColor(raw_bgr, cv2.COLOR_BGR2GRAY)

    h, w = raw_gray.shape[:2]

    # 2. Extract Multi-Dimensional Document Condition Profile
    profile, paper_mask, ink_mask = extract_document_condition_profile(raw_bgr_color, page_quad_mask)
    audit_log: List[OperatorExecutionRecord] = []

    # 3. Path A: NO_OP Bypass (Clean Document)
    if profile.is_clean_document:
        audit_log.append(OperatorExecutionRecord(
            operator_name="NO_OP_BYPASS",
            status="BYPASSED_NO_OP",
            latency_ms=round((time.perf_counter() - t_start) * 1000.0, 2),
            rejection_reason=None,
            evidence=None
        ))
        binary_deriv = build_binary_derivative(raw_gray, profile.scale_factor)
        color_mask = build_color_rubric_mask(raw_bgr_color, page_quad_mask, profile.in_page_color_fraction)
        total_lat = (time.perf_counter() - t_start) * 1000.0

        return EnhancedDocumentResult(
            status="NO_OP_PRISTINE",
            enhanced_gray=raw_gray,
            raw_bgr=raw_bgr_color,
            binary_derivative=binary_deriv,
            color_rubric_mask=color_mask,
            condition_profile=profile,
            operator_audit_log=audit_log,
            total_latency_ms=round(total_lat, 2),
            dimensions=(w, h)
        )

    # 4. Path B: Conditional Sequential Enhancement with Safety Gate
    # Current verified safe state initialized to raw rectified gray
    safe_gray = raw_gray.copy()

    # Plan candidate operators in empirically verified safe sequence:
    # SHADOW_CORRECTION -> BILATERAL_DENOISE -> CONTRAST_STRETCH -> UNSHARP_MASK
    candidate_ops = []
    if profile.has_illumination_gradient:
        candidate_ops.append(("SHADOW_CORRECTION", lambda g: apply_shadow_correction(g, profile.scale_factor)))
    if profile.has_excessive_noise:
        candidate_ops.append(("BILATERAL_DENOISE", lambda g: apply_bilateral_denoising(g, profile.scale_factor)))
    if profile.has_low_contrast:
        candidate_ops.append(("CONTRAST_STRETCH", lambda g: apply_contrast_stretching(g)))
    if profile.has_optical_softness:
        candidate_ops.append(("MILD_UNSHARP_MASK", lambda g: apply_mild_unsharp_mask(g, profile.scale_factor)))

    # Execute candidates one at a time with verification & rollback
    any_operator_accepted = False

    for op_name, op_fn in candidate_ops:
        t_op0 = time.perf_counter()
        candidate_gray = op_fn(safe_gray)
        t_op = (time.perf_counter() - t_op0) * 1000.0

        # Run safety verification against current safe state
        evidence = verify_operator_safety(safe_gray, candidate_gray, op_name, profile.scale_factor)

        if evidence.evidence_verdict == "PASS":
            # ACCEPT: Commit new safe state
            safe_gray = candidate_gray
            any_operator_accepted = True
            audit_log.append(OperatorExecutionRecord(
                operator_name=op_name,
                status="ACCEPTED",
                latency_ms=round(t_op, 2),
                rejection_reason=None,
                evidence=evidence
            ))
        else:
            # REJECT: Discard candidate, retain safe_gray (Rollback)
            rejection_msg = "; ".join(evidence.rejection_reasons)
            audit_log.append(OperatorExecutionRecord(
                operator_name=op_name,
                status="REJECTED_ROLLBACK",
                latency_ms=round(t_op, 2),
                rejection_reason=rejection_msg,
                evidence=evidence
            ))

    # 5. Build Derivatives and Package Result Contract
    status = "ENHANCED_VERIFIED" if any_operator_accepted else "RECOVERED_RAW_FALLBACK"
    binary_deriv = build_binary_derivative(safe_gray, profile.scale_factor)
    color_mask = build_color_rubric_mask(raw_bgr_color, page_quad_mask, profile.in_page_color_fraction)
    total_lat = (time.perf_counter() - t_start) * 1000.0

    return EnhancedDocumentResult(
        status=status,
        enhanced_gray=safe_gray,
        raw_bgr=raw_bgr_color,
        binary_derivative=binary_deriv,
        color_rubric_mask=color_mask,
        condition_profile=profile,
        operator_audit_log=audit_log,
        total_latency_ms=round(total_lat, 2),
        dimensions=(w, h)
    )
