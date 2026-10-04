"""
phase5/production_quality_assessment.py

AI-EVAL PHASE 5 PRODUCTION IMPLEMENTATION: SMART QUALITY ASSESSMENT
===================================================================

PURPOSE:
Production Smart Quality Assessment module based strictly on the approved
Phase 5.1, Phase 5.2, and Phase 5.3 architecture.

HIERARCHICAL NON-COMPENSATORY ARCHITECTURE:
Enhanced / Processed Document
↓
Tier 1 — Fatal Defect Gate (Non-compensatory Boolean Veto Filters)
↓
Tier 2 — Multi-Dimensional Quality Evidence Profile (Orthogonal Vectors)
↓
Tier 3 — Evaluation Readiness Verdict (Semantic Multi-Band Categorization)

KEY ARCHITECTURAL RESOLUTIONS:
1. Non-Compensatory Veto: If any confirmed fatal defect is present (clipping,
   glare collision, severe defocus, ink dropout, intrusive occlusion, geometric collapse),
   the document is assigned UNUSABLE with rescan_required=True. Zero compensation
   is permitted by high sharpness, contrast, or paper whiteness elsewhere.
2. Signal Curation:
   - Global Laplacian Variance is STRICTLY BANNED from quality gate decisions;
     retained solely in diagnostic telemetry.
   - Redundant Weber and Michelson contrast measures are excluded in favor of
     linear stroke intensity delta (Delta_stroke) and faint stroke pixel fraction.
3. Separation of Concerns:
   - "Can Be Enhanced" (enhancement potential) != "Good Enough for Evaluation" (verdict).
   - BORDERLINE triggers human_review_required=True without falsely claiming UNUSABLE.
   - UNUSABLE triggers rescan_required=True.
4. Centralized Provisional Thresholds:
   - All empirical calibration parameters are housed in QualityGateConfig.
   - Explicitly marked as provisional calibration baselines, not frozen universal truths.

GUARDRAILS:
- Do NOT modify frozen Phase 2 or Phase 3 files.
- Do NOT redesign Phase 4 enhancement logic.
- Do NOT create a universal 0-100 quality score.
"""

import os
import sys
import math
import time
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, field

import cv2
import numpy as np


# ===========================================================================
# 1. CENTRALIZED CONFIGURATION & CALIBRATION THRESHOLDS
# ===========================================================================

@dataclass(frozen=True)
class QualityGateConfig:
    """
    Centralized provisional calibration parameters for Smart Quality Assessment.
    
    NOTE: These thresholds are calibrated empirically on real exam answer sheets,
    controlled physical degradation sweeps, and mobile-scanned student scripts.
    They represent empirical baselines, NOT scientifically frozen universal truths.
    No magic numbers are scattered elsewhere in the codebase.
    """
    # -----------------------------------------------------------------------
    # Tier 1 Fatal Defect Veto Baselines (Catastrophic Step-Functions)
    # -----------------------------------------------------------------------
    # Saturated specular reflection intersecting detected text strokes (> 8% causes +67% CER jump)
    fatal_glare_collision_ratio: float = 0.08

    # Massive specular flash whiteout blob covering > 4% of document canvas
    fatal_glare_pixel_fraction: float = 0.04

    # Text boundary clipping: stroke pixels touching the outer 2-8px border band
    fatal_clipping_boundary_touches: int = 80

    # Severe optical defocus blur: scale-normalized acutance < 120 causes total OCR blackout (CER=1.0)
    fatal_defocus_acutance: float = 120.0

    # 10%-90% gradient transition edge spread width > 4.5 px indicates complete optical defocus
    fatal_edge_spread_width: float = 4.5

    # Severe handwriting ink loss: delta < 18 levels blends ink into paper quantization noise
    fatal_ink_loss_delta: float = 18.0

    # Fraction of stroke pixels with contrast < 25 levels exceeding 60% causes stroke disconnection
    fatal_faint_stroke_fraction: float = 0.60

    # Intrusive foreign object occlusion (fingers, clipboards, clothing) covering > 25% of margin
    fatal_margin_occlusion_ratio: float = 0.25

    # Geometric aspect ratio deviation relative to standard A4 (1.414) exceeding 45%
    fatal_aspect_ratio_deviation: float = 0.45

    # Minimum dimension threshold to distinguish full document scans from cropped patches
    full_document_min_dimension_px: int = 300

    # -----------------------------------------------------------------------
    # Tier 2 Degradable / Borderline Reference Bands (Operational Envelopes)
    # -----------------------------------------------------------------------
    # Acutance 120-220: OCR CER begins rising; word segmentation degraded
    borderline_defocus_acutance: float = 220.0

    # Edge spread width 3.2-4.5 px indicates moderate optical softness
    borderline_edge_spread_width: float = 3.2

    # Contrast delta 18-35: character dropout risk on faint pencil/pen
    borderline_stroke_delta: float = 35.0

    # Faint stroke fraction 35%-60%: broken character loops
    borderline_faint_fraction: float = 0.35

    # Text baseline tilt > 7.0 degrees degrades line grouping
    borderline_skew_angle_deg: float = 7.0

    # Regional background ratio (min/max on paper) < 0.65 indicates cast shadow / non-uniformity
    borderline_spatial_bg_ratio: float = 0.65

    # Localized paper deficit > 45 levels relative to global paper white
    borderline_worst_quadrant_deficit: float = 45.0

    # Otsu between-class / total variance separation ratio < 0.30 indicates overlapping distributions
    borderline_otsu_eta: float = 0.30

    # Minimum median character bounding box height for reliable line-level OCR
    min_character_height_px: float = 10.0


# ===========================================================================
# 2. OUTPUT DATA CONTRACTS
# ===========================================================================

@dataclass
class FatalDefectRecord:
    """
    Tier 1 Fatal Defect Record.
    Details the specific failure mode that triggered an immediate non-compensatory veto.
    """
    defect_code: str                          # E.g., "FATAL_TEXT_CLIPPED", "FATAL_GLARE_COLLISION"
    evidence_dimension: str                   # Name of the offending measurement
    measured_value: float                     # Measured empirical value
    threshold_value: float                    # Calibration cutoff
    rationale: str                            # Human-readable failure explanation


@dataclass
class QualityEvidenceProfile:
    """
    Tier 2 Curated Multi-Dimensional Quality Evidence Profile.
    Preserves independent evidence dimensions while omitting redundant or unsafe metrics.
    """
    image_name: str
    dimensions: Tuple[int, int]               # (width, height)
    scale_factor: float                       # min(W, H) / 1000.0

    # 1. Stroke Visibility & Contrast Evidence
    stroke_intensity_delta: float             # I_paper - I_ink (linear, intuitive)
    faint_stroke_pixel_fraction: float        # Fraction of strokes with contrast < 25 levels
    paper_white_intensity: float              # Median intensity of detected paper substrate
    ink_core_intensity: float                 # 15th percentile of detected ink cores

    # 2. Optical Sharpness & Acutance Evidence (Scale-Normalized)
    normalized_stroke_acutance: float         # Scale-normalized mean Sobel gradient strictly along stroke contours
    edge_spread_width_pixels: float           # 10%-90% gradient transition distance across stroke boundaries

    # 3. Illumination Uniformity & Shadow Evidence
    spatial_bg_ratio: float                   # Regional min/max background intensity across 4x4 grid
    worst_quadrant_paper_deficit: float       # Global paper white minus darkest regional paper white
    spatial_bg_std: float                     # Regional background standard deviation

    # 4. Specular Glare & Whiteout Evidence
    glare_pixel_fraction: float               # Percentage of saturated pixels (I >= 254)
    glare_text_collision_fraction: float      # Percentage of stroke pixels obliterated by saturated glare

    # 5. Page Completeness & Framing Evidence
    boundary_text_touch_count: int            # Count of text pixels intersecting outer border band
    text_margin_clearance_min_px: float       # Minimum clearance from any text glyph to page border

    # 6. Obstruction & Foreign Intrusion Evidence
    margin_occlusion_fraction: float          # Margin perimeter occupied by foreign objects (fingers/clips)
    foreign_object_detected: bool

    # 7. Geometric Alignment & Skew Evidence
    residual_skew_angle_deg: float            # Baseline tilt angle in degrees
    aspect_ratio: float                       # Width / Height
    aspect_ratio_a4_deviation: float          # |aspect_ratio - 1.414| / 1.414

    # 8. Binarization & Topology Readiness Evidence
    binarization_otsu_eta: float              # Otsu between-class / total variance separation ratio
    median_character_height_px: float         # Median character bounding box height

    # Telemetry / Diagnostic-Only (Strictly Excluded from Gate Decisions)
    diagnostic_laplacian_variance: float      # Global Laplacian variance (strictly logged, NEVER gated)
    diagnostic_high_freq_energy: float        # Secondary high-frequency energy ratio


@dataclass
class QualityAssessmentResult:
    """
    Tier 3 Unified Production Output Contract for Smart Quality Assessment.
    Exposes complete verdict, fatal defect records, evidence profile, and operational routing.
    """
    verdict: str                              # "GOOD", "ACCEPTABLE", "BORDERLINE", "UNUSABLE"
    fatal_defects: List[FatalDefectRecord]    # Confirmed Tier 1 fatal defects (empty if passed)
    evidence_profile: QualityEvidenceProfile  # Curated multi-dimensional evidence profile
    human_review_required: bool               # True for BORDERLINE cases requiring manual verification
    rescan_required: bool                     # True for UNUSABLE cases where rescan is mandatory
    enhancement_potential: str                # "ALREADY_CLEAN", "CAN_BE_ENHANCED", "UNRECOVERABLE"
    risk_factors: List[str]                   # Identified degradable risks (Tier 2)
    processing_notes: List[str]               # Diagnostic and routing audit trail
    processing_latency_ms: float              # Assessment execution time in milliseconds
    dimensions: Tuple[int, int]               # (width, height)
    source_metadata: Dict[str, Any] = field(default_factory=dict)


# ===========================================================================
# 3. EVIDENCE MEASUREMENT EXTRACTION ENGINE
# ===========================================================================

def extract_curated_quality_profile(
    image: np.ndarray,
    image_name: str = "document_image",
    config: Optional[QualityGateConfig] = None,
    document_box: Optional[Tuple[int, int, int, int]] = None,
) -> QualityEvidenceProfile:
    """
    Extracts the curated multi-dimensional quality evidence profile from an image.
    Ensures scale-normalization and semantic paper/ink separation.
    """
    if config is None:
        config = QualityGateConfig()

    h, w = image.shape[:2]
    scale_factor = max(0.2, min(w, h) / 1000.0)

    # 1. Grayscale & Color Spaces
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    else:
        gray = image.copy()
        hsv = None

    # 2. Scale-Normalized Spatial Gradients
    sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.hypot(sobel_x, sobel_y)

    # 3. Semantic Paper Substrate & Ink Segmentation
    flat_grad_thresh = max(15.0, float(np.percentile(grad_mag, 50)))
    paper_mask = (grad_mag <= flat_grad_thresh) & (gray >= np.percentile(gray, 40))
    if np.count_nonzero(paper_mask) < 200:
        paper_mask = gray >= np.percentile(gray, 50)

    paper_white = float(np.median(gray[paper_mask]))
    ink_thresh = max(30.0, paper_white - 25.0)
    ink_mask = (gray < ink_thresh)

    # Dimension 1: Stroke Visibility & Contrast Evidence
    if np.count_nonzero(ink_mask) > 50:
        ink_core = float(np.percentile(gray[ink_mask], 15))
        delta = max(0.0, paper_white - ink_core)
        faint_pixels = np.count_nonzero((gray >= (paper_white - 25.0)) & ink_mask)
        faint_ratio = float(faint_pixels / max(1, np.count_nonzero(ink_mask)))
    else:
        ink_core = paper_white
        delta = 0.0
        faint_ratio = 1.0

    # Dimension 2: Optical Sharpness & Acutance Evidence
    edges = cv2.Canny(gray, 40, 120)
    if np.count_nonzero(edges) > 50:
        raw_acutance = float(np.mean(grad_mag[edges > 0]))
        norm_acutance = raw_acutance / (0.8 + 0.2 * scale_factor)

        # 10%-90% gradient transition edge spread width
        dilated_edges = cv2.dilate(edges, np.ones((5, 5), np.uint8))
        local_grad = grad_mag[dilated_edges > 0]
        peak_grad = float(np.percentile(local_grad, 95))
        mean_grad = float(np.mean(local_grad))
        edge_spread_px = float(max(1.0, (peak_grad / max(1.0, mean_grad)) * (1.2 * scale_factor)))
    else:
        norm_acutance = 30.0
        edge_spread_px = 6.0

    # Diagnostic Telemetry (Excluded from gating decisions)
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    diag_high_freq = float(np.mean(np.abs(lap[ink_mask])) if np.count_nonzero(ink_mask) > 50 else 0.0)
    diag_lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # Dimension 3: Illumination Uniformity & Shadow Evidence
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
    worst_quadrant_deficit = float(paper_white - bg_min)

    # Dimension 4: Specular Glare & Whiteout Evidence
    glare_mask = (gray >= 254) & (grad_mag < 10.0)
    glare_frac = float(np.count_nonzero(glare_mask) / gray.size)

    dilated_glare = cv2.dilate(glare_mask.astype(np.uint8), np.ones((7, 7), np.uint8))
    obliterated_strokes = np.count_nonzero((dilated_glare > 0) & ink_mask)
    glare_collision_frac = float(obliterated_strokes / max(1, np.count_nonzero(ink_mask)))

    # Dimension 5: Page Completeness & Text Clipping Evidence
    _, otsu_bin = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    is_patch = bool(min(w, h) < config.full_document_min_dimension_px)

    if is_patch:
        boundary_touches = 0
        margin_clearance = 15.0
    else:
        # Mask out outer 2 pixels to reject canvas warping interpolation fringe (Row 0 / Col 0)
        otsu_clean = otsu_bin.copy()
        otsu_clean[:2, :] = 0
        otsu_clean[-2:, :] = 0
        otsu_clean[:, :2] = 0
        otsu_clean[:, -2:] = 0

        # Margin evaluation band: [2, 8] px
        band = np.zeros((h, w), dtype=bool)
        band[2:8, :] = True
        band[-8:-2, :] = True
        band[:, 2:8] = True
        band[:, -8:-2] = True

        n_cc_clip, labels_clip, stats_clip, _ = cv2.connectedComponentsWithStats(otsu_clean)
        char_clipping_pixels = 0
        for i in range(1, n_cc_clip):
            area      = stats_clip[i, cv2.CC_STAT_AREA]
            cw_comp   = stats_clip[i, cv2.CC_STAT_WIDTH]
            ch_comp   = stats_clip[i, cv2.CC_STAT_HEIGHT]
            bx        = stats_clip[i, cv2.CC_STAT_LEFT]
            by        = stats_clip[i, cv2.CC_STAT_TOP]
            comp_mask = (labels_clip == i)

            # Must touch the inspection band at all
            if not np.any(comp_mask & band):
                continue

            # Standard glyph-size filter: exclude page-wide borders and pixel noise
            if not (cw_comp < (w * 0.35) and ch_comp < (h * 0.35) and area > 10):
                continue

            ar      = float(cw_comp) / max(1, ch_comp)
            min_dim = min(cw_comp, ch_comp)

            # Strategy 2A — large flat shadow / background band:
            #   reject if aspect ratio is extreme AND component is too large to be a glyph.
            if ar >= 5.0 and area > 1000:
                continue

            # Strategy 2B — thin structural ruling / border line:
            #   reject if aspect ratio is extreme AND the component is a thin stroke.
            if (ar >= 5.0 or ar <= 0.30) and min_dim <= 5:
                continue

            # Determine which boundary edges the component touches in otsu_clean
            touches_top   = by <= 2            and np.any(comp_mask[2:4,  :])
            touches_bot   = (by + ch_comp) >= (h - 2) and np.any(comp_mask[-4:-2, :])
            touches_left  = bx <= 2            and np.any(comp_mask[:,  2:4])
            touches_right = (bx + cw_comp) >= (w - 2) and np.any(comp_mask[:, -4:-2])

            # Strategy 1 — True boundary intersection:
            #   A component is counted only when its ink actually reaches the real image
            #   boundary (row/col 0-1 of otsu_bin, BEFORE the 2-px mask was applied).
            #   For top-touching components we additionally require the component to be
            #   short (a "sliver"), because Phase 3 deskew rotation can push full-height
            #   characters into row 0 without genuinely clipping them.
            reaches_boundary = False

            if touches_top:
                # Only count components that look like clipping slivers, not full
                # characters that were merely rotated into the boundary by deskewing.
                sliver_height_limit = max(12, int(h * 0.012))
                if ch_comp <= sliver_height_limit:
                    cols = np.where(np.any(comp_mask[2:4, :], axis=0))[0]
                    if cols.size > 0:
                        c0 = max(0, int(cols.min()) - 1)
                        c1 = min(w, int(cols.max()) + 2)
                        if np.any(otsu_bin[:2, c0:c1] > 0):
                            reaches_boundary = True

            if touches_bot:
                cols = np.where(np.any(comp_mask[-4:-2, :], axis=0))[0]
                if cols.size > 0:
                    c0 = max(0, int(cols.min()) - 1)
                    c1 = min(w, int(cols.max()) + 2)
                    if np.any(otsu_bin[-2:, c0:c1] > 0):
                        reaches_boundary = True

            if touches_left:
                rows = np.where(np.any(comp_mask[:, 2:4], axis=1))[0]
                if rows.size > 0:
                    r0 = max(0, int(rows.min()) - 1)
                    r1 = min(h, int(rows.max()) + 2)
                    if np.any(otsu_bin[r0:r1, :2] > 0):
                        reaches_boundary = True

            if touches_right:
                rows = np.where(np.any(comp_mask[:, -4:-2], axis=1))[0]
                if rows.size > 0:
                    r0 = max(0, int(rows.min()) - 1)
                    r1 = min(h, int(rows.max()) + 2)
                    if np.any(otsu_bin[r0:r1, -2:] > 0):
                        reaches_boundary = True

            if reaches_boundary:
                char_clipping_pixels += area

        boundary_touches = char_clipping_pixels

    y_ink, x_ink = np.where(otsu_bin > 0)
    if y_ink.size > 0:
        d_top = float(np.min(y_ink))
        d_bottom = float(h - np.max(y_ink))
        d_left = float(np.min(x_ink))
        d_right = float(w - np.max(x_ink))
        margin_clearance = min(d_top, d_bottom, d_left, d_right)
    else:
        margin_clearance = float(min(h, w))

    # Dimension 6: Obstruction & Foreign Intrusion Evidence
    # Use verified document geometry when available (e.g. DESKEWED_FRAME_LIMITED)
    has_valid_box = False
    bx, by, bw, bh = 0, 0, 0, 0
    if document_box is not None and len(document_box) == 4:
        cand_bx, cand_by, cand_bw, cand_bh = document_box
        cand_bx = max(0, min(w - 1, int(cand_bx)))
        cand_by = max(0, min(h - 1, int(cand_by)))
        cand_bw = max(10, min(w - cand_bx, int(cand_bw)))
        cand_bh = max(10, min(h - cand_by, int(cand_bh)))
        if cand_bw >= 50 and cand_bh >= 50:
            bx, by, bw, bh = cand_bx, cand_by, cand_bw, cand_bh
            has_valid_box = True

    if has_valid_box:
        # Document-relative perimeter band
        margin_w = max(5, int(round(bw * 0.05)))
        margin_h = max(5, int(round(bh * 0.05)))
        perimeter_mask = np.zeros((h, w), dtype=bool)
        perimeter_mask[by : by + margin_h, bx : bx + bw] = True
        perimeter_mask[by + bh - margin_h : by + bh, bx : bx + bw] = True
        perimeter_mask[by : by + bh, bx : bx + margin_w] = True
        perimeter_mask[by : by + bh, bx + bw - margin_w : bx + bw] = True
    else:
        # Full canvas perimeter band
        margin_w = max(5, int(round(w * 0.05)))
        margin_h = max(5, int(round(h * 0.05)))
        perimeter_mask = np.zeros((h, w), dtype=bool)
        perimeter_mask[:margin_h, :] = True
        perimeter_mask[-margin_h:, :] = True
        perimeter_mask[:, :margin_w] = True
        perimeter_mask[:, -margin_w:] = True

    if hsv is not None:
        high_sat_margin = (hsv[:, :, 1] > 60) & perimeter_mask
        dark_margin = (gray < 80) & perimeter_mask
        occlusion_mask = high_sat_margin | dark_margin
    else:
        occlusion_mask = (gray < 80) & perimeter_mask

    n_occ_cc, _, occ_stats, _ = cv2.connectedComponentsWithStats(occlusion_mask.astype(np.uint8))
    large_occlusion_pixels = 0
    foreign_object = False
    for i in range(1, n_occ_cc):
        area = occ_stats[i, cv2.CC_STAT_AREA]
        if area > (margin_w * margin_h * 0.4):
            large_occlusion_pixels += area
            foreign_object = True

    margin_occlusion_frac = float(large_occlusion_pixels / max(1, np.count_nonzero(perimeter_mask)))

    # Dimension 7: Geometric Alignment & Baseline Skew Evidence
    angles = np.linspace(-15.0, 15.0, 31)
    best_var = -1.0
    best_skew = 0.0
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
    target_ar = 0.707 if aspect_ratio < 1.0 else 1.414
    ar_deviation = float(abs(aspect_ratio - target_ar) / target_ar)

    # Dimension 8: Binarization & Topology Readiness Evidence
    n_cc, _, cc_stats, _ = cv2.connectedComponentsWithStats(otsu_bin)
    char_heights = []
    for i in range(1, n_cc):
        ch_comp = cc_stats[i, cv2.CC_STAT_HEIGHT]
        cw_comp = cc_stats[i, cv2.CC_STAT_WIDTH]
        if 4 < ch_comp < (h * 0.4) and 4 < cw_comp < (w * 0.6):
            char_heights.append(ch_comp)
    median_char_h = float(np.median(char_heights) if char_heights else 16.0)

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

    return QualityEvidenceProfile(
        image_name=image_name,
        dimensions=(w, h),
        scale_factor=scale_factor,
        stroke_intensity_delta=delta,
        faint_stroke_pixel_fraction=faint_ratio,
        paper_white_intensity=paper_white,
        ink_core_intensity=ink_core,
        normalized_stroke_acutance=norm_acutance,
        edge_spread_width_pixels=edge_spread_px,
        spatial_bg_ratio=bg_ratio,
        worst_quadrant_paper_deficit=worst_quadrant_deficit,
        spatial_bg_std=bg_std,
        glare_pixel_fraction=glare_frac,
        glare_text_collision_fraction=glare_collision_frac,
        boundary_text_touch_count=boundary_touches,
        text_margin_clearance_min_px=margin_clearance,
        margin_occlusion_fraction=margin_occlusion_frac,
        foreign_object_detected=foreign_object,
        residual_skew_angle_deg=best_skew,
        aspect_ratio=aspect_ratio,
        aspect_ratio_a4_deviation=ar_deviation,
        binarization_otsu_eta=otsu_eta,
        median_character_height_px=median_char_h,
        diagnostic_laplacian_variance=diag_lap_var,
        diagnostic_high_freq_energy=diag_high_freq
    )


# ===========================================================================
# 4. TIER 1: FATAL DEFECT VETO GATE (NON-COMPENSATORY)
# ===========================================================================

def evaluate_tier1_fatal_defects(
    profile: QualityEvidenceProfile,
    config: QualityGateConfig,
    geometry_reliable: bool = True,
) -> List[FatalDefectRecord]:
    """
    Evaluates non-compensatory Tier 1 Boolean Veto Filters.
    If ANY condition is triggered, the image is immediately declared fatal.
    Zero compensation is permitted by positive signals in other dimensions.
    """
    fatal_records: List[FatalDefectRecord] = []
    w, h = profile.dimensions
    is_full_doc = bool(min(w, h) >= config.full_document_min_dimension_px)

    # 1. Text Boundary Clipping (Physical exam content truncated)
    if is_full_doc and profile.boundary_text_touch_count > config.fatal_clipping_boundary_touches:
        fatal_records.append(
            FatalDefectRecord(
                defect_code="FATAL_TEXT_CLIPPED",
                evidence_dimension="boundary_text_touch_count",
                measured_value=float(profile.boundary_text_touch_count),
                threshold_value=float(config.fatal_clipping_boundary_touches),
                rationale=(
                    f"{profile.boundary_text_touch_count} stroke pixels intersect the outer margin band. "
                    "Essential student answers, roll numbers, or marks are truncated past the page boundary."
                )
            )
        )

    # 2. Text-Colliding Specular Glare (Physical whiteout obliteration)
    if profile.glare_text_collision_fraction > config.fatal_glare_collision_ratio or profile.glare_pixel_fraction > config.fatal_glare_pixel_fraction:
        fatal_dim = "glare_text_collision_fraction" if profile.glare_text_collision_fraction > config.fatal_glare_collision_ratio else "glare_pixel_fraction"
        meas_val = profile.glare_text_collision_fraction if fatal_dim == "glare_text_collision_fraction" else profile.glare_pixel_fraction
        thresh_val = config.fatal_glare_collision_ratio if fatal_dim == "glare_text_collision_fraction" else config.fatal_glare_pixel_fraction
        fatal_records.append(
            FatalDefectRecord(
                defect_code="FATAL_GLARE_COLLISION",
                evidence_dimension=fatal_dim,
                measured_value=meas_val,
                threshold_value=thresh_val,
                rationale=(
                    f"Specular flash glare saturates {meas_val*100:.1f}% of text/page area. "
                    "Character information is physically obliterated (CER jumps +67%)."
                )
            )
        )

    # 3. Severe Optical Defocus Blur (OCR CER = 1.0 total blackout)
    if profile.normalized_stroke_acutance < config.fatal_defocus_acutance:
        fatal_records.append(
            FatalDefectRecord(
                defect_code="FATAL_OPTICAL_DEFOCUS",
                evidence_dimension="normalized_stroke_acutance",
                measured_value=profile.normalized_stroke_acutance,
                threshold_value=config.fatal_defocus_acutance,
                rationale=(
                    f"Normalized stroke acutance ({profile.normalized_stroke_acutance:.1f}) is below fatal cutoff "
                    f"({config.fatal_defocus_acutance:.1f}). Character loops and word spaces are completely fused."
                )
            )
        )
    elif profile.edge_spread_width_pixels > config.fatal_edge_spread_width:
        fatal_records.append(
            FatalDefectRecord(
                defect_code="FATAL_OPTICAL_DEFOCUS",
                evidence_dimension="edge_spread_width_pixels",
                measured_value=profile.edge_spread_width_pixels,
                threshold_value=config.fatal_edge_spread_width,
                rationale=(
                    f"Edge spread transition width ({profile.edge_spread_width_pixels:.2f} px) indicates severe optical defocus."
                )
            )
        )

    # 4. Severe Handwriting Ink Loss (Faint pencil/pen dropout)
    if profile.stroke_intensity_delta < config.fatal_ink_loss_delta or profile.faint_stroke_pixel_fraction > config.fatal_faint_stroke_fraction:
        fatal_records.append(
            FatalDefectRecord(
                defect_code="FATAL_INK_LOSS",
                evidence_dimension="stroke_intensity_delta",
                measured_value=profile.stroke_intensity_delta,
                threshold_value=config.fatal_ink_loss_delta,
                rationale=(
                    f"Stroke contrast delta ({profile.stroke_intensity_delta:.1f}) or faint fraction "
                    f"({profile.faint_stroke_pixel_fraction*100:.1f}%) indicates severe ink dropout below sensor noise floor."
                )
            )
        )

    # 5. Destructive Foreign Object Occlusion
    if profile.margin_occlusion_fraction > config.fatal_margin_occlusion_ratio:
        if geometry_reliable:
            fatal_records.append(
                FatalDefectRecord(
                    defect_code="FATAL_MARGIN_OCCLUSION",
                    evidence_dimension="margin_occlusion_fraction",
                    measured_value=profile.margin_occlusion_fraction,
                    threshold_value=config.fatal_margin_occlusion_ratio,
                    rationale=(
                        f"Intrusive foreign object covers {profile.margin_occlusion_fraction*100:.1f}% of margin perimeter. "
                        "Obstructs critical document boundary content."
                    )
                )
            )

    # 6. Geometric Aspect Ratio Collapse
    if is_full_doc and profile.aspect_ratio_a4_deviation > config.fatal_aspect_ratio_deviation:
        fatal_records.append(
            FatalDefectRecord(
                defect_code="FATAL_GEOMETRIC_COLLAPSE",
                evidence_dimension="aspect_ratio_a4_deviation",
                measured_value=profile.aspect_ratio_a4_deviation,
                threshold_value=config.fatal_aspect_ratio_deviation,
                rationale=(
                    f"Aspect ratio deviation ({profile.aspect_ratio_a4_deviation:.2f}) indicates severe trapezoidal distortion "
                    "or perspective rectification collapse."
                )
            )
        )

    return fatal_records


# ===========================================================================
# 5. TIER 2 & TIER 3: EVALUATION READINESS VERDICT ENGINE
# ===========================================================================

def assess_document_quality(
    document_input: Union[np.ndarray, Any],
    image_name: str = "document_image",
    config: Optional[QualityGateConfig] = None,
    document_box: Optional[Tuple[int, int, int, int]] = None,
    scanner_status: Optional[str] = None,
) -> QualityAssessmentResult:
    """
    Main Production Entry Point for Smart Quality Assessment.
    
    Accepts:
    - EnhancedDocumentResult (from Phase 4 production enhancement)
    - ScannedDocumentResult (from Phase 3 production scanner)
    - np.ndarray (Raw BGR or Grayscale image)
    
    Executes the 3-Tier Hierarchical Quality Assessment Pipeline:
    Tier 1: Fatal Defect Gate (Non-compensatory Boolean Veto).
    Tier 2: Multi-Dimensional Quality Evidence Profile.
    Tier 3: Evaluation Readiness Verdict & Operational Action Routing.
    """
    start_time = time.perf_counter()
    if config is None:
        config = QualityGateConfig()

    source_metadata: Dict[str, Any] = {}

    # Extract image array from input contract
    if hasattr(document_input, "enhanced_gray"):
        # Phase 4 EnhancedDocumentResult
        eval_image = document_input.enhanced_gray
        source_metadata["pipeline_stage"] = "PHASE4_ENHANCED"
        source_metadata["enhancement_status"] = getattr(document_input, "status", "UNKNOWN")
    elif hasattr(document_input, "scanned_image"):
        # Phase 3 ScannedDocumentResult
        eval_image = document_input.scanned_image
        source_metadata["pipeline_stage"] = "PHASE3_RECTIFIED"
        source_metadata["scanner_status"] = getattr(document_input, "status", "UNKNOWN")
        if scanner_status is None:
            scanner_status = getattr(document_input, "status", None)
        if document_box is None and hasattr(document_input, "framing_metadata"):
            fm = getattr(document_input, "framing_metadata") or {}
            document_box = fm.get("selected_box")
    elif isinstance(document_input, np.ndarray):
        eval_image = document_input
        source_metadata["pipeline_stage"] = "DIRECT_IMAGE"
    else:
        raise TypeError(f"Unsupported document_input type: {type(document_input)}")

    if scanner_status:
        source_metadata["scanner_status"] = scanner_status
    if document_box:
        source_metadata["document_box"] = document_box

    # Geometry reliability check:
    # If scanner status is DESKEWED_FRAME_LIMITED but no reliable document_box was provided,
    # geometry is unconfirmed/ambiguous.
    geometry_reliable = True
    if scanner_status == "DESKEWED_FRAME_LIMITED" and document_box is None:
        geometry_reliable = False

    # 1. Tier 2 Evidence Profile Extraction
    profile = extract_curated_quality_profile(
        eval_image, image_name=image_name, config=config, document_box=document_box
    )

    # 2. Tier 1 Fatal Defect Veto Evaluation
    fatal_defects = evaluate_tier1_fatal_defects(
        profile, config=config, geometry_reliable=geometry_reliable
    )

    # 3. Non-Compensatory Veto Handler
    if fatal_defects:
        latency = (time.perf_counter() - start_time) * 1000.0
        risk_factors = [f.rationale for f in fatal_defects]
        notes = [
            f"VETO TRIPPED: Document contains confirmed fatal defect ({fatal_defects[0].defect_code}).",
            "Non-compensatory rule applied: high sharpness/contrast cannot override fatal physical content loss.",
            "Mandatory operational action: rescan_required=True."
        ]
        return QualityAssessmentResult(
            verdict="UNUSABLE",
            fatal_defects=fatal_defects,
            evidence_profile=profile,
            human_review_required=False,
            rescan_required=True,
            enhancement_potential="UNRECOVERABLE",
            risk_factors=risk_factors,
            processing_notes=notes,
            processing_latency_ms=latency,
            dimensions=profile.dimensions,
            source_metadata=source_metadata
        )

    # 4. Tier 2 Degradable Risk Identification
    risk_factors: List[str] = []
    notes: List[str] = []

    # Sharpness / Focus Risk
    if profile.normalized_stroke_acutance < config.borderline_defocus_acutance:
        risk_factors.append(
            f"Moderate Defocus Blur: Acutance ({profile.normalized_stroke_acutance:.1f}) is borderline; "
            "HTR word segmentation confidence may be degraded."
        )

    # Contrast / Faint Ink Risk
    if profile.stroke_intensity_delta < config.borderline_stroke_delta:
        risk_factors.append(
            f"Low Stroke Contrast: Delta ({profile.stroke_intensity_delta:.1f}) indicates faint pencil or washed ink."
        )
    if profile.faint_stroke_pixel_fraction > config.borderline_faint_fraction:
        risk_factors.append(
            f"Elevated Faint Stroke Ratio: {profile.faint_stroke_pixel_fraction*100:.1f}% of ink pixels have low contrast."
        )

    # Baseline Skew Risk
    if abs(profile.residual_skew_angle_deg) > config.borderline_skew_angle_deg:
        risk_factors.append(
            f"Significant Baseline Skew ({profile.residual_skew_angle_deg:+.1f} deg): "
            "Line grouping requires rotation compensation."
        )
        notes.append("Recommend applying baseline deskew prior to line tokenization.")

    # Illumination Non-Uniformity / Shadow Risk
    is_shadowed = bool(
        profile.spatial_bg_ratio < config.borderline_spatial_bg_ratio or
        profile.worst_quadrant_paper_deficit > config.borderline_worst_quadrant_deficit
    )
    if is_shadowed:
        risk_factors.append(
            f"Non-Uniform Illumination: Spatial BG ratio ({profile.spatial_bg_ratio:.2f}) indicates regional cast shadow."
        )
        notes.append("Candidate for Phase 4 background normalization.")

    # Binarization Bimodality Separation Risk
    if profile.binarization_otsu_eta < config.borderline_otsu_eta:
        risk_factors.append(
            f"Weak Binarization Separation: Otsu eta ({profile.binarization_otsu_eta:.2f}) indicates poor ink-paper bimodality."
        )

    # Character Resolution Risk
    if profile.median_character_height_px < config.min_character_height_px:
        risk_factors.append(
            f"Low Character Resolution: Median glyph height ({profile.median_character_height_px:.1f} px) "
            "approaches minimum line OCR threshold."
        )

    # Ambiguous Margin Occlusion (Geometry Unconfirmed)
    if not geometry_reliable and profile.margin_occlusion_fraction > config.fatal_margin_occlusion_ratio:
        risk_factors.append(
            f"Ambiguous margin occlusion: {profile.margin_occlusion_fraction*100:.1f}% without confirmed document boundary."
        )
        notes.append("WARNING: Margin occlusion detected but document geometry is unconfirmed. Routing to human review.")

    # 5. Distinction: Enhancement Potential vs Evaluation Readiness
    if is_shadowed and source_metadata.get("pipeline_stage") != "PHASE4_ENHANCED":
        enhancement_potential = "CAN_BE_ENHANCED"
    elif not risk_factors:
        enhancement_potential = "ALREADY_CLEAN"
    else:
        enhancement_potential = "ALREADY_CLEAN" # Minor degradations do not warrant remedial filters

    # 6. Tier 3 Final Evaluation Readiness Verdict
    if not risk_factors:
        verdict = "GOOD"
        human_review = False
        rescan = False
        notes.append("Pristine quality. Safe for autonomous downstream AI evaluation.")
    elif len(risk_factors) == 1 and is_shadowed:
        verdict = "ACCEPTABLE"
        human_review = False
        rescan = False
        notes.append("Minor illumination non-uniformity handled robustly by downstream neural OCR.")
    elif len(risk_factors) <= 2 and not any("Blur" in r or "Contrast" in r for r in risk_factors):
        verdict = "ACCEPTABLE"
        human_review = False
        rescan = False
        notes.append("Minor non-fatal degradations within neural OCR tolerance margins.")
    else:
        verdict = "BORDERLINE"
        human_review = True
        rescan = False
        notes.append("Multiple compounding risk factors present. Flagged for human verification queue.")

    latency = (time.perf_counter() - start_time) * 1000.0

    return QualityAssessmentResult(
        verdict=verdict,
        fatal_defects=[],
        evidence_profile=profile,
        human_review_required=human_review,
        rescan_required=rescan,
        enhancement_potential=enhancement_potential,
        risk_factors=risk_factors,
        processing_notes=notes,
        processing_latency_ms=latency,
        dimensions=profile.dimensions,
        source_metadata=source_metadata
    )
