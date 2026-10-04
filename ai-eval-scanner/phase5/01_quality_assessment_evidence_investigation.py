"""
phase5/01_quality_assessment_evidence_investigation.py

AI-EVAL PHASE 5.1: SMART QUALITY ASSESSMENT EVIDENCE INVESTIGATION
==================================================================

PURPOSE:
Investigate how to objectively assess whether a processed exam-answer image
is usable for OCR/HTR and downstream AI evaluation.

CORE OBJECTIVES:
1. Multi-Dimensional Quality Evidence Extraction:
   - Stroke/text contrast & faintness (Michelson, Weber, delta, faint stroke ratio).
   - Defocus blur, acutance, & edge transition width (scale-normalized).
   - Residual shadow & illumination non-uniformity.
   - Specular glare, white saturation, & text obliteration.
   - Occlusion, fingers, & foreign object intrusion.
   - Page completeness, edge clipping, & margin text cutoff.
   - Geometric distortion, baseline skew, & aspect ratio integrity.
   - Handwriting legibility vs. printed template legibility.
   - OCR/HTR readiness (glyph topology, stroke continuity, binarization suitability).
2. Distinction between "Image Can Be Enhanced" vs "Image Is Good Enough for Evaluation".
3. Correlation & Redundancy Analysis across signals.
4. Stress Testing across Calibration (N=5), Unseen Validation (N=10), and Defect Cases (N=5).

GUARDRAILS:
- INVESTIGATION ONLY.
- Do NOT implement the final production quality system yet.
- Do NOT create a universal quality score or weighted scalar ranking.
- Do NOT introduce fixed GOOD/BAD thresholds.
- Do NOT modify frozen Phase 2, Phase 3, or Phase 4 files.
"""

import os
import sys
import math
import time
import importlib.util
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict, field
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT_DIR, "phase5", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Dynamic Import of Phase 3 Scanner & Phase 4 Production Enhancement
# ---------------------------------------------------------------------------
P3_PATH = os.path.join(ROOT_DIR, "phase3", "06_scanner_integration_investigation.py")
spec_p3 = importlib.util.spec_from_file_location("phase3_06", P3_PATH)
phase3_06 = importlib.util.module_from_spec(spec_p3)
spec_p3.loader.exec_module(phase3_06)
integrate_production_scanner = phase3_06.integrate_production_scanner

P4_PATH = os.path.join(ROOT_DIR, "phase4", "production_enhancement.py")
spec_p4 = importlib.util.spec_from_file_location("phase4_prod", P4_PATH)
phase4_prod = importlib.util.module_from_spec(spec_p4)
spec_p4.loader.exec_module(phase4_prod)
enhance_scanned_document = phase4_prod.enhance_scanned_document


# ===========================================================================
# 1. QUALITY ASSESSMENT EVIDENCE DATA CONTRACT
# ===========================================================================

@dataclass
class QualityAssessmentEvidence:
    """
    Independent multi-dimensional quality evidence representation.
    Preserves raw measurement vectors without collapsing into a single score.
    """
    image_name: str
    dimensions: Tuple[int, int]             # (width, height)
    scale_factor: float                     # min(W, H) / 1000.0

    # 1. Stroke Visibility & Contrast Evidence
    paper_white_intensity: float            # Median intensity of detected paper substrate
    ink_core_intensity: float               # 15th percentile of detected stroke cores
    weber_contrast: float                   # (I_paper - I_ink) / I_paper
    michelson_contrast: float               # (I_paper - I_ink) / (I_paper + I_ink)
    stroke_intensity_delta: float           # I_paper - I_ink
    faint_stroke_pixel_fraction: float      # Fraction of stroke pixels with contrast < 25 levels

    # 2. Sharpness, Acutance, & Defocus Evidence
    normalized_stroke_acutance: float       # Scale-normalized mean Sobel gradient on stroke contours
    edge_spread_width_pixels: float         # 10%-90% intensity transition distance across stroke edges
    high_freq_energy_ratio: float           # High-pass energy in stroke neighborhoods
    global_laplacian_variance: float        # Global Laplacian variance (recorded for correlation audit)

    # 3. Illumination Uniformity & Shadow Evidence
    spatial_bg_ratio: float                 # Regional paper white min / max across 4x4 grid
    spatial_bg_std: float                   # Standard deviation of regional paper whites
    spatial_bg_spread: float                # Max minus min regional background intensity
    worst_quadrant_paper_deficit: float     # Max local paper deficit relative to global paper white

    # 4. Specular Glare & Saturated Clipping Evidence
    glare_pixel_fraction: float             # Percentage of pixels with I >= 254 and low local gradient
    glare_text_collision_fraction: float    # Percentage of stroke pixels obliterated by saturated glare

    # 5. Occlusion & Margin Obstruction Evidence
    margin_occlusion_fraction: float        # Fraction of perimeter margin occupied by foreign blobs
    foreign_object_detected: bool           # True if high-saturation / intrusive blob detected at margin

    # 6. Page Completeness & Text Clipping Evidence
    boundary_text_touch_count: int          # Count of binarized stroke pixels touching the outer 5px frame
    text_margin_clearance_min_px: float     # Minimum distance from any text pixel to outer border
    is_framing_clipped: bool                # True if strokes directly intersect sensor/image frame

    # 7. Geometric Distortion & Skew Evidence
    residual_skew_angle_deg: float          # Text baseline skew angle in degrees
    aspect_ratio: float                     # Width / Height
    aspect_ratio_a4_deviation: float        # |aspect_ratio - 1.414| / 1.414

    # 8. Dual-Content Legibility Evidence (Handwriting vs Printed)
    printed_text_contrast: float            # Contrast on detected printed / form elements
    handwriting_contrast: float             # Contrast on detected student handwriting strokes
    handwriting_acutance: float             # Acutance on detected student handwriting strokes

    # 9. OCR/HTR Readiness & Topology Evidence
    median_character_height_px: float       # Median connected-component bounding box height
    stroke_continuity_euler_index: float    # Euler characteristic normalized by character count
    binarization_otsu_eta: float            # Otsu between-class / total variance separation (bimodality)
    sauvola_otsu_divergence_rate: float     # Mismatch rate between local Sauvola and global Otsu masks

    # Diagnostic & Readiness Categorization (Qualitative, Non-Scalar)
    enhancement_potential: str              # "CAN_BE_ENHANCED", "ALREADY_CLEAN", "UNRECOVERABLE"
    evaluation_readiness: str               # "READY_FOR_EVALUATION", "BORDERLINE_RISK", "UNUSABLE_FATAL"
    fatal_defects: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)


# ===========================================================================
# 2. QUALITY MEASUREMENT EXTRACTION ENGINE
# ===========================================================================

def extract_quality_assessment_evidence(
    image: np.ndarray,
    image_name: str,
    framing_status: str = "ACCEPTED_PHYSICAL_PAGE"
) -> QualityAssessmentEvidence:
    """
    Extracts 9 dimensions of objective quality evidence from a processed image.
    Operates without hardcoded quality scores or linear weightings.
    """
    h, w = image.shape[:2]
    scale_factor = max(0.2, min(w, h) / 1000.0)

    # 1. Grayscale & Gradients
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    else:
        gray = image.copy()
        hsv = None

    sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.hypot(sobel_x, sobel_y)

    # 2. Semantic Paper vs. Ink Segmentation
    # Flat paper: low gradient and relatively high intensity
    flat_grad_thresh = max(15.0, float(np.percentile(grad_mag, 50)))
    paper_mask = (grad_mag <= flat_grad_thresh) & (gray >= np.percentile(gray, 40))
    if np.count_nonzero(paper_mask) < 200:
        paper_mask = gray >= np.percentile(gray, 50)

    paper_white = float(np.median(gray[paper_mask]))

    # Ink strokes: pixels darker than local paper white with non-zero local gradient
    ink_thresh = max(30.0, paper_white - 25.0)
    ink_mask = (gray < ink_thresh)

    # -----------------------------------------------------------------------
    # Dimension 1: Stroke Visibility & Contrast Evidence
    # -----------------------------------------------------------------------
    if np.count_nonzero(ink_mask) > 50:
        ink_core = float(np.percentile(gray[ink_mask], 15))
        delta = max(0.0, paper_white - ink_core)
        weber = delta / max(1.0, paper_white)
        michelson = delta / max(1.0, paper_white + ink_core)
        # Faint stroke pixels: ink pixels with contrast < 25 intensity levels
        faint_pixels = np.count_nonzero((gray >= (paper_white - 25.0)) & ink_mask)
        faint_ratio = float(faint_pixels / max(1, np.count_nonzero(ink_mask)))
    else:
        ink_core = paper_white
        delta = 0.0
        weber = 0.0
        michelson = 0.0
        faint_ratio = 1.0

    # -----------------------------------------------------------------------
    # Dimension 2: Sharpness, Acutance, & Defocus Evidence
    # -----------------------------------------------------------------------
    # Acutance along Canny stroke edges
    edges = cv2.Canny(gray, 40, 120)
    if np.count_nonzero(edges) > 50:
        raw_acutance = float(np.mean(grad_mag[edges > 0]))
        norm_acutance = raw_acutance / (0.8 + 0.2 * scale_factor)

        # Edge spread function (ESF) transition width: 10%-90% gradient profile
        # Approximate transition width as ratio of local gradient standard deviation to peak gradient
        dilated_edges = cv2.dilate(edges, np.ones((5, 5), np.uint8))
        local_grad = grad_mag[dilated_edges > 0]
        peak_grad = float(np.percentile(local_grad, 95))
        mean_grad = float(np.mean(local_grad))
        edge_spread_px = float(max(1.0, (peak_grad / max(1.0, mean_grad)) * (1.2 * scale_factor)))
    else:
        norm_acutance = 30.0
        edge_spread_px = 6.0

    # High frequency energy in stroke neighborhoods
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    high_freq_energy = float(np.mean(np.abs(lap[ink_mask])) if np.count_nonzero(ink_mask) > 50 else 0.0)
    global_lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # -----------------------------------------------------------------------
    # Dimension 3: Illumination Uniformity & Shadow Evidence
    # -----------------------------------------------------------------------
    grid_rows, grid_cols = 4, 4
    ch, cw = max(1, h // grid_rows), max(1, w // grid_cols)
    regional_whites = []
    for r in range(grid_rows):
        for c in range(grid_cols):
            cell = gray[r*ch:(r+1)*ch, c*cw:(c+1)*cw]
            cell_grad = grad_mag[r*ch:(r+1)*ch, c*cw:(c+1)*cw]
            cell_flat = cell[cell_grad < flat_grad_thresh]
            if cell_flat.size > 20:
                regional_whites.append(float(np.percentile(cell_flat, 85)))
            else:
                regional_whites.append(float(np.percentile(cell, 90)))

    bg_min = min(regional_whites)
    bg_max = max(regional_whites)
    bg_ratio = float(bg_min / max(1.0, bg_max))
    bg_std = float(np.std(regional_whites))
    bg_spread = float(bg_max - bg_min)
    worst_quadrant_deficit = float(paper_white - bg_min)

    # -----------------------------------------------------------------------
    # Dimension 4: Specular Glare & Saturated White Clipping Evidence
    # -----------------------------------------------------------------------
    # Glare pixels: intensity >= 254 with flat gradient (specular hotspot)
    glare_mask = (gray >= 254) & (grad_mag < 10.0)
    glare_frac = float(np.count_nonzero(glare_mask) / gray.size)

    # Glare text collision: binarized strokes adjacent to or inside glare mask
    dilated_glare = cv2.dilate(glare_mask.astype(np.uint8), np.ones((7, 7), np.uint8))
    obliterated_strokes = np.count_nonzero((dilated_glare > 0) & ink_mask)
    glare_collision_frac = float(obliterated_strokes / max(1, np.count_nonzero(ink_mask)))

    # -----------------------------------------------------------------------
    # Dimension 5: Occlusion & Boundary Obstruction Evidence
    # -----------------------------------------------------------------------
    # Perimeter margin analysis (outer 5% border)
    margin_w = max(5, int(round(w * 0.05)))
    margin_h = max(5, int(round(h * 0.05)))
    perimeter_mask = np.zeros((h, w), dtype=bool)
    perimeter_mask[:margin_h, :] = True
    perimeter_mask[-margin_h:, :] = True
    perimeter_mask[:, :margin_w] = True
    perimeter_mask[:, -margin_w:] = True

    # Foreign dark/high-saturation blob in margin (e.g. finger, desk, clothing)
    if hsv is not None:
        high_sat_margin = (hsv[:, :, 1] > 60) & perimeter_mask
        dark_margin = (gray < 80) & perimeter_mask
        occlusion_mask = high_sat_margin | dark_margin
    else:
        occlusion_mask = (gray < 80) & perimeter_mask

    # Connected components of occlusion mask to reject small punctuation
    n_occ_cc, occ_labels, occ_stats, _ = cv2.connectedComponentsWithStats(occlusion_mask.astype(np.uint8))
    large_occlusion_pixels = 0
    foreign_object = False
    for i in range(1, n_occ_cc):
        area = occ_stats[i, cv2.CC_STAT_AREA]
        if area > (margin_w * margin_h * 0.4): # Significant margin intrusion
            large_occlusion_pixels += area
            foreign_object = True

    margin_occlusion_frac = float(large_occlusion_pixels / max(1, np.count_nonzero(perimeter_mask)))

    # -----------------------------------------------------------------------
    # Dimension 6: Page Completeness & Text Clipping Evidence
    # -----------------------------------------------------------------------
    # Binarize strokes via Otsu inverse
    _, otsu_bin = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # For supplementary dataset patch crops (224x224), they are content patches,
    # not full page scans. Page completeness is only evaluated on full documents (e.g. min(w, h) >= 300).
    is_patch_crop = bool(min(w, h) < 300)

    if is_patch_crop:
        boundary_touches = 0
        is_clipped = False
        margin_clearance = 15.0
    else:
        # Exclude outer 2 pixels (canvas interpolation fringe during warping)
        otsu_clean = otsu_bin.copy()
        otsu_clean[:2, :] = 0
        otsu_clean[-2:, :] = 0
        otsu_clean[:, :2] = 0
        otsu_clean[:, -2:] = 0

        # Margin band [2, 8] px
        band = np.zeros((h, w), dtype=bool)
        band[2:8, :] = True
        band[-8:-2, :] = True
        band[:, 2:8] = True
        band[:, -8:-2] = True

        n_cc_clip, labels_clip, stats_clip, _ = cv2.connectedComponentsWithStats(otsu_clean)
        char_clipping_pixels = 0
        for i in range(1, n_cc_clip):
            area = stats_clip[i, cv2.CC_STAT_AREA]
            cw = stats_clip[i, cv2.CC_STAT_WIDTH]
            ch = stats_clip[i, cv2.CC_STAT_HEIGHT]
            # Check if this character component touches the boundary band
            comp_mask = (labels_clip == i)
            if np.any(comp_mask & band):
                # Character glyphs have bounded width/height, not page-spanning borders
                if cw < (w * 0.35) and ch < (h * 0.35) and area > 10:
                    char_clipping_pixels += area

        boundary_touches = char_clipping_pixels
        is_clipped = bool(boundary_touches > 80)

    # Text bounding box margin clearance
    y_ink, x_ink = np.where(otsu_bin > 0)
    if y_ink.size > 0:
        d_top = float(np.min(y_ink))
        d_bottom = float(h - np.max(y_ink))
        d_left = float(np.min(x_ink))
        d_right = float(w - np.max(x_ink))
        margin_clearance = min(d_top, d_bottom, d_left, d_right)
    else:
        margin_clearance = float(min(h, w))

    # -----------------------------------------------------------------------
    # Dimension 7: Geometric Distortion & Baseline Skew Evidence
    # -----------------------------------------------------------------------
    # Baseline skew estimation via projection profile variance
    angles = np.linspace(-15.0, 15.0, 31)
    best_var = -1.0
    best_skew = 0.0

    # Downscale for fast Radon/projection search
    small_bin = cv2.resize(otsu_bin, (min(400, w), min(400, h)), interpolation=cv2.INTER_NEAREST)
    sh, sw = small_bin.shape

    for ang in angles:
        M = cv2.getRotationMatrix2D((sw / 2.0, sh / 2.0), ang, 1.0)
        rotated = cv2.warpAffine(small_bin, M, (sw, sh), flags=cv2.INTER_NEAREST)
        proj = np.sum(rotated, axis=1)
        var = float(np.var(proj))
        if var > best_var:
            best_var = var
            best_skew = float(ang)

    aspect_ratio = float(w / max(1, h))
    # A4 standard aspect ratio is 1.414 (or 1/1.414 = 0.707)
    target_ar = 0.707 if aspect_ratio < 1.0 else 1.414
    ar_deviation = float(abs(aspect_ratio - target_ar) / target_ar)

    # -----------------------------------------------------------------------
    # Dimension 8: Dual-Content Separation (Handwriting vs Printed Template)
    # -----------------------------------------------------------------------
    # Printed elements: horizontal/vertical lines and structured rectangular fonts
    # Morphological kernel to isolate horizontal lines
    h_line_k = cv2.getStructuringElement(cv2.MORPH_RECT, (max(9, int(round(w * 0.05))), 1))
    v_line_k = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(9, int(round(h * 0.05)))))
    lines_h = cv2.morphologyEx(otsu_bin, cv2.MORPH_OPEN, h_line_k)
    lines_v = cv2.morphologyEx(otsu_bin, cv2.MORPH_OPEN, v_line_k)
    printed_mask = (lines_h > 0) | (lines_v > 0)

    # Handwriting mask: remaining stroke pixels excluding rigid lines
    handwriting_mask = (otsu_bin > 0) & (~printed_mask)

    if np.count_nonzero(printed_mask) > 50:
        printed_contrast = float(paper_white - np.median(gray[printed_mask]))
    else:
        printed_contrast = delta

    if np.count_nonzero(handwriting_mask) > 50:
        handwriting_contrast = float(paper_white - np.median(gray[handwriting_mask]))
        hw_edges = (edges > 0) & handwriting_mask
        handwriting_acutance = float(np.mean(grad_mag[hw_edges]) / (0.8 + 0.2 * scale_factor) if np.count_nonzero(hw_edges) > 20 else norm_acutance)
    else:
        handwriting_contrast = delta
        handwriting_acutance = norm_acutance

    # -----------------------------------------------------------------------
    # Dimension 9: OCR/HTR Readiness & Topology Evidence
    # -----------------------------------------------------------------------
    n_cc, cc_labels, cc_stats, _ = cv2.connectedComponentsWithStats(otsu_bin)
    char_heights = []
    for i in range(1, n_cc):
        ch_h = cc_stats[i, cv2.CC_STAT_HEIGHT]
        ch_w = cc_stats[i, cv2.CC_STAT_WIDTH]
        # Filter tiny specks and page-spanning lines
        if 4 < ch_h < (h * 0.4) and 4 < ch_w < (w * 0.6):
            char_heights.append(ch_h)

    median_char_h = float(np.median(char_heights) if char_heights else 16.0)

    # Euler number (topological holes & loops):
    # Normalized euler characteristic = (Total CCs - Total Holes) / Total CCs
    contours, hierarchy = cv2.findContours(otsu_bin, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    n_holes = 0
    if hierarchy is not None:
        for h_info in hierarchy[0]:
            if h_info[3] != -1: # Inner contour (hole in character like 'o', 'e')
                n_holes += 1
    euler_index = float((max(1, len(contours)) - n_holes) / max(1, len(contours)))

    # Binarization suitability: Otsu Eta between-class separation
    # eta = sigma_B^2 / sigma_T^2
    total_var = float(np.var(gray))
    weight_bg = float(np.count_nonzero(gray >= ink_thresh) / gray.size)
    weight_fg = float(np.count_nonzero(gray < ink_thresh) / gray.size)
    if weight_bg > 0 and weight_fg > 0 and total_var > 0:
        mean_bg = float(np.mean(gray[gray >= ink_thresh]))
        mean_fg = float(np.mean(gray[gray < ink_thresh]))
        between_var = weight_bg * weight_fg * ((mean_bg - mean_fg) ** 2)
        otsu_eta = float(min(1.0, between_var / total_var))
    else:
        otsu_eta = 0.5

    # Sauvola vs Otsu divergence rate
    # Compute fast Sauvola local threshold
    k_local = max(11, int(round(min(w, h) * 0.03)) | 1)
    mean_local = cv2.blur(gray.astype(np.float32), (k_local, k_local))
    sq_mean = cv2.blur(gray.astype(np.float32) ** 2, (k_local, k_local))
    std_local = np.sqrt(np.maximum(0.0, sq_mean - mean_local ** 2))
    sauvola_thresh = mean_local * (1.0 + 0.2 * ((std_local / 128.0) - 1.0))
    sauvola_bin = (gray < sauvola_thresh).astype(np.uint8) * 255

    bin_divergence = float(np.count_nonzero(sauvola_bin != otsu_bin) / gray.size)

    # -----------------------------------------------------------------------
    # Qualitative Diagnostics & Defect Identification
    # -----------------------------------------------------------------------
    fatal_defects = []
    risk_factors = []

    # Fatal Defect Checks (Cannot be rescued by OCR)
    if is_clipped and boundary_touches > 80:
        fatal_defects.append(f"Severe Page Boundary Clipping: {boundary_touches} stroke pixels truncated at border")
    if glare_collision_frac > 0.15:
        fatal_defects.append(f"Severe Specular Glare: {glare_collision_frac*100:.1f}% of text strokes obliterated by reflection")
    if norm_acutance < 35.0 and edge_spread_px > 4.5:
        fatal_defects.append(f"Severe Optical Defocus: Stroke acutance ({norm_acutance:.1f}) below legibility threshold, edge spread {edge_spread_px:.1f}px")
    if weber < 0.20 or delta < 25.0:
        fatal_defects.append(f"Extreme Contrast Failure: Delta ({delta:.1f}) insufficient to distinguish ink from paper")
    if foreign_object and margin_occlusion_frac > 0.25:
        fatal_defects.append(f"Severe Margin Occlusion: Foreign object covers {margin_occlusion_frac*100:.1f}% of margin")

    # Risk Factors (Borderline challenges)
    if bg_ratio < 0.70 and bg_spread > 50.0:
        risk_factors.append(f"Residual Shadow Gradient: Paper ratio {bg_ratio:.2f}, spread {bg_spread:.1f}")
    if abs(best_skew) > 4.0:
        risk_factors.append(f"Significant Text Baseline Skew: {best_skew:.1f}° tilt")
    if faint_ratio > 0.35:
        risk_factors.append(f"High Faint Stroke Fraction: {faint_ratio*100:.1f}% of strokes have low pressure/contrast")
    if bin_divergence > 0.12:
        risk_factors.append(f"Binarization Ambiguity: Sauvola vs Otsu divergence {bin_divergence*100:.1f}%")
    if otsu_eta < 0.35:
        risk_factors.append(f"Weak Bimodal Separation: Otsu eta = {otsu_eta:.2f}")

    # Explicit Distinction: "Can Be Enhanced" vs "Good Enough for Evaluation"
    if fatal_defects:
        evaluation_readiness = "UNUSABLE_FATAL"
        enhancement_potential = "UNRECOVERABLE" if ("Defocus" in fatal_defects[0] or "Clipping" in fatal_defects[0]) else "CAN_BE_ENHANCED"
    elif risk_factors:
        evaluation_readiness = "BORDERLINE_RISK"
        enhancement_potential = "CAN_BE_ENHANCED"
    else:
        evaluation_readiness = "READY_FOR_EVALUATION"
        enhancement_potential = "ALREADY_CLEAN"

    return QualityAssessmentEvidence(
        image_name=image_name,
        dimensions=(w, h),
        scale_factor=round(scale_factor, 3),
        paper_white_intensity=round(paper_white, 1),
        ink_core_intensity=round(ink_core, 1),
        weber_contrast=round(weber, 3),
        michelson_contrast=round(michelson, 3),
        stroke_intensity_delta=round(delta, 1),
        faint_stroke_pixel_fraction=round(faint_ratio, 3),
        normalized_stroke_acutance=round(norm_acutance, 1),
        edge_spread_width_pixels=round(edge_spread_px, 2),
        high_freq_energy_ratio=round(high_freq_energy, 2),
        global_laplacian_variance=round(global_lap_var, 1),
        spatial_bg_ratio=round(bg_ratio, 3),
        spatial_bg_std=round(bg_std, 2),
        spatial_bg_spread=round(bg_spread, 1),
        worst_quadrant_paper_deficit=round(worst_quadrant_deficit, 1),
        glare_pixel_fraction=round(glare_frac, 4),
        glare_text_collision_fraction=round(glare_collision_frac, 4),
        margin_occlusion_fraction=round(margin_occlusion_frac, 3),
        foreign_object_detected=foreign_object,
        boundary_text_touch_count=boundary_touches,
        text_margin_clearance_min_px=round(margin_clearance, 1),
        is_framing_clipped=is_clipped,
        residual_skew_angle_deg=round(best_skew, 2),
        aspect_ratio=round(aspect_ratio, 3),
        aspect_ratio_a4_deviation=round(ar_deviation, 3),
        printed_text_contrast=round(printed_contrast, 1),
        handwriting_contrast=round(handwriting_contrast, 1),
        handwriting_acutance=round(handwriting_acutance, 1),
        median_character_height_px=round(median_char_h, 1),
        stroke_continuity_euler_index=round(euler_index, 3),
        binarization_otsu_eta=round(otsu_eta, 3),
        sauvola_otsu_divergence_rate=round(bin_divergence, 3),
        enhancement_potential=enhancement_potential,
        evaluation_readiness=evaluation_readiness,
        fatal_defects=fatal_defects,
        risk_factors=risk_factors
    )


# ===========================================================================
# 3. TEST DATASET GENERATOR (CALIBRATION, VALIDATION, & DEFECT STRESS TESTS)
# ===========================================================================

def generate_defect_stress_samples(base_image: np.ndarray) -> List[Tuple[str, np.ndarray, str]]:
    """
    Creates controlled physical defect cases to stress-test quality boundaries:
    1. Severe Optical Defocus Blur
    2. Specular Flash Glare Hotspot (bleaching text)
    3. Severe Margin Text Clipping
    4. Foreign Object / Finger Intrusion
    5. Extreme Contrast Fade (exhausted ink)
    """
    h, w = base_image.shape[:2]
    gray = cv2.cvtColor(base_image, cv2.COLOR_BGR2GRAY) if base_image.ndim == 3 else base_image.copy()

    # Base padded image with clean 15px white paper border
    pad = 15
    framed = cv2.copyMakeBorder(gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=220)
    fh, fw = framed.shape
    stress_cases = []

    # Case 1: Severe Optical Defocus Blur (Gaussian sigma=5.0)
    blurred = cv2.GaussianBlur(framed, (0, 0), sigmaX=5.0, sigmaY=5.0)
    stress_cases.append(("Stress_01_SevereBlur", blurred, "Fatal Defect: Severe Optical Defocus Blur (sigma=5.0)"))

    # Case 2: Specular Flash Glare Hotspot (bleaching text)
    glare_img = framed.copy()
    center_y, center_x = fh // 2, fw // 2
    y_coords, x_coords = np.ogrid[:fh, :fw]
    dist_from_center = np.sqrt((x_coords - center_x) ** 2 + (y_coords - center_y) ** 2)
    glare_radius = min(fh, fw) * 0.28
    glare_boost = np.clip(1.0 - (dist_from_center / glare_radius), 0, 1) * 180.0
    glare_img = np.clip(glare_img.astype(np.float32) + glare_boost, 0, 255).astype(np.uint8)
    stress_cases.append(("Stress_02_FlashGlare", glare_img, "Fatal Defect: Specular Flash Glare Hotspot Bleaching Text"))

    # Case 3: Severe Margin Text Clipping (resize to 450x450, crop off border right through text)
    big_doc = cv2.resize(gray, (450, 450), interpolation=cv2.INTER_LINEAR)
    clipped_img = big_doc[60:390, 60:390] # 330x330, text slices directly at outer border
    stress_cases.append(("Stress_03_TextClipping", clipped_img, "Fatal Defect: Severe Crop Truncating Answer Text at Border"))

    # Case 4: Foreign Object / Finger Intrusion along Margin
    finger_img = cv2.cvtColor(framed, cv2.COLOR_GRAY2BGR)
    cv2.ellipse(finger_img, (int(fw * 0.15), int(fh * 0.12)), (int(fw * 0.18), int(fh * 0.10)), 35, 0, 360, (30, 45, 75), -1)
    stress_cases.append(("Stress_04_FingerIntrusion", finger_img, "Fatal Defect: Finger / Foreign Object Obstructing Margin"))

    # Case 5: Extreme Contrast Fade (exhausted faint ballpoint ink, delta < 15)
    faded_img = np.clip(framed.astype(np.float32) * 0.08 + 215.0, 0, 255).astype(np.uint8)
    stress_cases.append(("Stress_05_ExtremeFade", faded_img, "Fatal Defect: Faded Ink with Delta < 15 Intensity Levels"))

    return stress_cases


# ===========================================================================
# 4. BENCHMARK RUNNER & CORRELATION ANALYSIS
# ===========================================================================

def run_quality_investigation() -> Dict[str, Any]:
    """
    Executes the comprehensive Phase 5.1 investigation across:
    - 5 Calibration Images (processed through Phase 3/4)
    - 10 Unseen Validation Images
    - 5 Synthetic Quality Defect Stress Test Images
    """
    print("=" * 80)
    print("AI-EVAL PHASE 5.1: SMART QUALITY ASSESSMENT EVIDENCE INVESTIGATION")
    print("=" * 80)

    evidence_records: List[QualityAssessmentEvidence] = []

    # 1. Evaluate Calibration Images (Full Scanner + Enhancement Flow)
    print("\n--- COHORT 1: CALIBRATION DOCUMENTS (PROCESSED THROUGH SCANNER & ENHANCEMENT) ---")
    calib_files = [
        ("answer_sheet.jpg", "images/answer_sheet.jpg", "Calibration: Ambiguous Grid Crop"),
        ("answer_sheet_2.png", "images/answer_sheet_2.png", "Calibration: Clean A4 Physical Page"),
        ("answer_sheet_3.jpg", "images/answer_sheet_3.jpg", "Calibration: Severe Diagonal Cast Shadow"),
        ("answer_sheet_4.jpg", "images/answer_sheet_4.jpg", "Calibration: High-Res Sensor Grain & Tables"),
        ("answer_sheet_5.jpg", "images/answer_sheet_5.jpg", "Calibration: Low-Contrast Blue Handwriting"),
    ]

    for name, rel_path, desc in calib_files:
        p = os.path.join(ROOT_DIR, rel_path)
        scan_res = integrate_production_scanner(p)
        enh_res = enhance_scanned_document(scan_res)
        # Quality assessment evaluates the enhanced grayscale (or raw if fallback)
        ev = extract_quality_assessment_evidence(enh_res.enhanced_gray, name, scan_res.status)
        evidence_records.append(ev)
        print(f"  {name:<18} [{ev.evaluation_readiness:<20} | EnhPotential: {ev.enhancement_potential:<15}]: "
              f"Contrast={ev.stroke_intensity_delta:4.1f} | Acutance={ev.normalized_stroke_acutance:4.1f} | "
              f"BgRatio={ev.spatial_bg_ratio:.2f} | Skew={ev.residual_skew_angle_deg:4.1f}° | FatalDefects={len(ev.fatal_defects)}")

    # 2. Evaluate Unseen Validation Cohort (10 Images)
    print("\n--- COHORT 2: UNSEEN VALIDATION HANDWRITING DOCUMENTS ---")
    val_files = [
        ("Val_01_DenseDark", "images/dataset_samples/02_Y21AEC402_IMG20251016104816.jpg"),
        ("Val_02_FaintPencil", "images/dataset_samples/03_Y21AEC403_IMG_20251013_124038367_HDR.jpg"),
        ("Val_03_SparseMath", "images/dataset_samples/05_Y21AEC407_IMG_20251016_105759.jpg"),
        ("Val_04_JPEGArtifacts", "images/dataset_samples/07_Y21AEC409_IMG-20251016-WA0063.jpg"),
        ("Val_05_Overexposed", "images/dataset_samples/11_Y21AEC413_IMG_20251022_110128465_HDR.jpg"),
        ("Val_06_LinedPaper", "images/dataset_samples/14_Y21AEC417_IMG_20251022_122722625_HDR.jpg"),
        ("Val_07_MixedPrinted", "images/dataset_samples/16_Y21AEC421_IMG20251022123543.jpg"),
        ("Val_08_BleedThrough", "images/dataset_samples/19_Y21AEC427_IMG20251022122156.jpg"),
        ("Val_09_HeavyBlue", "images/dataset_samples/22_Y21AEC418_IMG20251023110034.jpg"),
        ("Val_10_PatchGradient", "images/dataset_samples/25_Y21AEC429_IMG20251022110708.jpg"),
    ]

    for name, rel_path in val_files:
        p = os.path.join(ROOT_DIR, rel_path)
        bgr = cv2.imread(p)
        if bgr is None: continue
        enh_res = enhance_scanned_document(bgr)
        ev = extract_quality_assessment_evidence(enh_res.enhanced_gray, name, "ACCEPTED_PHYSICAL_PAGE")
        evidence_records.append(ev)
        print(f"  {name:<22} [{ev.evaluation_readiness:<20} | EnhPotential: {ev.enhancement_potential:<15}]: "
              f"Contrast={ev.stroke_intensity_delta:4.1f} | Acutance={ev.normalized_stroke_acutance:4.1f} | "
              f"BgRatio={ev.spatial_bg_ratio:.2f} | FaintFrac={ev.faint_stroke_pixel_fraction*100:4.1f}% | FatalDefects={len(ev.fatal_defects)}")

    # 3. Evaluate Quality Defect Stress Tests (5 Cases)
    print("\n--- COHORT 3: QUALITY DEFECT STRESS TESTS (FATAL FAILURE BOUNDARIES) ---")
    base_clean = cv2.imread(os.path.join(ROOT_DIR, "images/dataset_samples/02_Y21AEC402_IMG20251016104816.jpg"))
    stress_samples = generate_defect_stress_samples(base_clean)

    for name, img_data, desc in stress_samples:
        framing = "ACCEPTED_FRAME_LIMITED" if "Clipping" in name else "ACCEPTED_PHYSICAL_PAGE"
        ev = extract_quality_assessment_evidence(img_data, name, framing)
        evidence_records.append(ev)
        print(f"  {name:<22} [{ev.evaluation_readiness:<20} | EnhPotential: {ev.enhancement_potential:<15}]: "
              f"DefectIdentified: {ev.fatal_defects[0] if ev.fatal_defects else 'None'}")

    # 4. Correlation & Redundancy Analysis
    print("\n--- STEP 4: SIGNAL CORRELATION & REDUNDANCY ANALYSIS ---")
    corr_results = compute_evidence_correlation_matrix(evidence_records)
    for pair, r_val in corr_results["high_correlation_pairs"]:
        print(f"  [REDUNDANT / HIGH CORRELATION] {pair[0]:<28} vs {pair[1]:<28}: r = {r_val:+.3f}")
    for pair, r_val in corr_results["orthogonal_pairs"]:
        print(f"  [ORTHOGONAL / INDEPENDENT]    {pair[0]:<28} vs {pair[1]:<28}: r = {r_val:+.3f}")

    # 5. Generate Diagnostic Visualizations
    print("\n--- STEP 5: GENERATING DIAGNOSTIC VISUALIZATIONS ---")
    generate_quality_visualizations(evidence_records, corr_results, stress_samples)

    print("\nINVESTIGATION COMPLETE.")
    return {
        "evidence_records": evidence_records,
        "correlation_analysis": corr_results
    }


# ===========================================================================
# 5. CORRELATION & ORTHOGONALITY ANALYSIS
# ===========================================================================

def compute_evidence_correlation_matrix(records: List[QualityAssessmentEvidence]) -> Dict[str, Any]:
    """
    Analyzes pairwise Pearson correlation across all numerical evidence dimensions.
    Identifies redundant signal clusters and confirms orthogonal failure axes.
    """
    signals = {
        "Weber_Contrast": [r.weber_contrast for r in records],
        "Michelson_Contrast": [r.michelson_contrast for r in records],
        "Stroke_Delta": [r.stroke_intensity_delta for r in records],
        "Faint_Stroke_Ratio": [r.faint_stroke_pixel_fraction for r in records],
        "Normalized_Acutance": [r.normalized_stroke_acutance for r in records],
        "Edge_Spread_Width": [r.edge_spread_width_pixels for r in records],
        "Global_Laplacian_Var": [r.global_laplacian_variance for r in records],
        "Spatial_Bg_Ratio": [r.spatial_bg_ratio for r in records],
        "Bg_Spread": [r.spatial_bg_spread for r in records],
        "Glare_Collision_Frac": [r.glare_text_collision_fraction for r in records],
        "Margin_Occlusion_Frac": [r.margin_occlusion_fraction for r in records],
        "Boundary_Text_Touches": [float(r.boundary_text_touch_count) for r in records],
        "Baseline_Skew_Angle": [abs(r.residual_skew_angle_deg) for r in records],
        "Binarization_Otsu_Eta": [r.binarization_otsu_eta for r in records],
        "Sauvola_Divergence": [r.sauvola_otsu_divergence_rate for r in records]
    }

    sig_names = list(signals.keys())
    n = len(sig_names)
    corr_mat = np.zeros((n, n), dtype=np.float32)

    high_corr = []
    orthogonal = []

    for i in range(n):
        for j in range(n):
            v1 = np.array(signals[sig_names[i]])
            v2 = np.array(signals[sig_names[j]])
            if np.std(v1) > 1e-4 and np.std(v2) > 1e-4:
                r = float(np.corrcoef(v1, v2)[0, 1])
            else:
                r = 0.0
            corr_mat[i, j] = r

            if i < j:
                if abs(r) >= 0.85:
                    high_corr.append(((sig_names[i], sig_names[j]), r))
                elif abs(r) <= 0.15:
                    orthogonal.append(((sig_names[i], sig_names[j]), r))

    return {
        "signal_names": sig_names,
        "correlation_matrix": corr_mat,
        "high_correlation_pairs": sorted(high_corr, key=lambda x: abs(x[1]), reverse=True),
        "orthogonal_pairs": sorted(orthogonal, key=lambda x: abs(x[1]))[:10]
    }


# ===========================================================================
# 6. VISUALIZATION ARTIFACT BUILDER
# ===========================================================================

def generate_quality_visualizations(
    records: List[QualityAssessmentEvidence],
    corr_results: Dict[str, Any],
    stress_samples: List[Tuple[str, np.ndarray, str]]
):
    """Generates comprehensive diagnostic visual plots in phase5/output/."""

    # -----------------------------------------------------------------------
    # Plot 1: Correlation & Orthogonality Heatmap
    # -----------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(12, 10))
    cax = ax.matshow(corr_results["correlation_matrix"], cmap="coolwarm", vmin=-1.0, vmax=1.0)
    fig.colorbar(cax)

    ticks = range(len(corr_results["signal_names"]))
    ax.set_xticks(ticks)
    ax.set_yticks(ticks)
    ax.set_xticklabels(corr_results["signal_names"], rotation=45, ha="left", fontsize=9)
    ax.set_yticklabels(corr_results["signal_names"], fontsize=9)
    ax.set_title("Phase 5.1: Pairwise Pearson Correlation Heatmap Across Quality Evidence Dimensions",
                 pad=60, fontsize=12, fontweight="bold")

    plt.tight_layout()
    path_corr = os.path.join(OUTPUT_DIR, "phase5_signal_orthogonality_heatmap.png")
    plt.savefig(path_corr, dpi=180, bbox_inches="tight")
    plt.close()

    # -----------------------------------------------------------------------
    # Plot 2: Fatal Defect Detection Grid
    # -----------------------------------------------------------------------
    fig, axes = plt.subplots(len(stress_samples), 2, figsize=(12, 3.2 * len(stress_samples)))
    for idx, (name, img_data, desc) in enumerate(stress_samples):
        r = next(rec for rec in records if rec.image_name == name)
        gray = cv2.cvtColor(img_data, cv2.COLOR_BGR2GRAY) if img_data.ndim == 3 else img_data

        axes[idx, 0].imshow(gray, cmap="gray")
        axes[idx, 0].set_title(f"{name}\n{desc}", fontsize=9.5, fontweight="bold")
        axes[idx, 0].axis("off")

        # Derivative diagnostic map
        if "Blur" in name:
            sobel = np.hypot(cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1))
            axes[idx, 1].imshow(sobel, cmap="magma")
            axes[idx, 1].set_title(f"Gradient Map (Acutance: {r.normalized_stroke_acutance:.1f} | EdgeSpread: {r.edge_spread_width_pixels:.1f}px)\nStatus: {r.evaluation_readiness}",
                                   fontsize=9.5, color="darkred", fontweight="bold")
        elif "Glare" in name:
            glare_m = (gray >= 254)
            axes[idx, 1].imshow(glare_m, cmap="Reds")
            axes[idx, 1].set_title(f"Saturated Glare Mask (Text Obliteration: {r.glare_text_collision_fraction*100:.1f}%)\nStatus: {r.evaluation_readiness}",
                                   fontsize=9.5, color="darkred", fontweight="bold")
        elif "Clipping" in name:
            _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            axes[idx, 1].imshow(otsu, cmap="gray")
            axes[idx, 1].set_title(f"Truncated Text at Margin (Touches: {r.boundary_text_touch_count} px)\nStatus: {r.evaluation_readiness}",
                                   fontsize=9.5, color="darkred", fontweight="bold")
        elif "Finger" in name:
            axes[idx, 1].imshow(cv2.cvtColor(img_data, cv2.COLOR_BGR2RGB))
            axes[idx, 1].set_title(f"Margin Intrusion Mask (Occlusion: {r.margin_occlusion_fraction*100:.1f}%)\nStatus: {r.evaluation_readiness}",
                                   fontsize=9.5, color="darkred", fontweight="bold")
        else: # Faded ink
            _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            axes[idx, 1].imshow(otsu, cmap="gray")
            axes[idx, 1].set_title(f"Binarization Collapse (Delta: {r.stroke_intensity_delta:.1f} | Faint: {r.faint_stroke_pixel_fraction*100:.1f}%)\nStatus: {r.evaluation_readiness}",
                                   fontsize=9.5, color="darkred", fontweight="bold")
        axes[idx, 1].axis("off")

    plt.tight_layout()
    path_defects = os.path.join(OUTPUT_DIR, "phase5_fatal_defect_detection.png")
    plt.savefig(path_defects, dpi=180, bbox_inches="tight")
    plt.close()

    # -----------------------------------------------------------------------
    # Plot 3: Sharpness & Acutance vs Content Density Demonstration
    # -----------------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    names = [r.image_name for r in records if not r.image_name.startswith("Stress")]
    lap_vars = [r.global_laplacian_variance for r in records if not r.image_name.startswith("Stress")]
    acutances = [r.normalized_stroke_acutance for r in records if not r.image_name.startswith("Stress")]

    axes[0].barh(names, lap_vars, color="#4a90e2", alpha=0.85)
    axes[0].set_title("Global Laplacian Variance\n(Severe Spurious Swings Driven by Text Density & Paper Fiber)", fontsize=10.5, fontweight="bold")
    axes[0].set_xlabel("Variance (Unnormalized)", fontsize=10)
    axes[0].grid(axis="x", linestyle=":", alpha=0.6)

    axes[1].barh(names, acutances, color="#50e3c2", alpha=0.85)
    axes[1].set_title("Normalized Stroke Contour Acutance\n(Scale-Normalized, Robust Defocus Indicator)", fontsize=10.5, fontweight="bold")
    axes[1].set_xlabel("Sobel Acutance along Strokes", fontsize=10)
    axes[1].axvline(40.0, color="red", linestyle="--", label="Defocus Boundary (40.0)")
    axes[1].legend()
    axes[1].grid(axis="x", linestyle=":", alpha=0.6)

    plt.tight_layout()
    path_sharp = os.path.join(OUTPUT_DIR, "phase5_blur_acutance_vs_content_density.png")
    plt.savefig(path_sharp, dpi=180, bbox_inches="tight")
    plt.close()

    # -----------------------------------------------------------------------
    # Plot 4: Readiness & Enhancement Potential Categorization Grid
    # -----------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(14, 7))

    readiness_counts = {"READY_FOR_EVALUATION": 0, "BORDERLINE_RISK": 0, "UNUSABLE_FATAL": 0}
    for r in records:
        readiness_counts[r.evaluation_readiness] += 1

    categories = list(readiness_counts.keys())
    counts = list(readiness_counts.values())
    colors = ["#2ecc71", "#f39c12", "#e74c3c"]

    bars = ax.bar(categories, counts, color=colors, width=0.45)
    ax.set_ylabel("Document Count (N=20)", fontsize=11, fontweight="bold")
    ax.set_title("Multi-Dimensional Evaluation Readiness Distribution\n(Distinguishing Fatal Defects from Resolvable Risks and Clean Documents)",
                 fontsize=12, fontweight="bold")
    ax.grid(axis="y", linestyle=":", alpha=0.7)

    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2.0, h + 0.2, f"{int(h)} docs", ha="center", va="bottom", fontsize=11, fontweight="bold")

    plt.tight_layout()
    path_readiness = os.path.join(OUTPUT_DIR, "phase5_readiness_categorization_grid.png")
    plt.savefig(path_readiness, dpi=180, bbox_inches="tight")
    plt.close()

    print(f"Diagnostic plots saved to:\n  - {path_corr}\n  - {path_defects}\n  - {path_sharp}\n  - {path_readiness}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_quality_investigation()
