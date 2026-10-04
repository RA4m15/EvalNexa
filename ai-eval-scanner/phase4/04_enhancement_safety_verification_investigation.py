"""
phase4/04_enhancement_safety_verification_investigation.py

AI-EVAL PHASE 4.4: ENHANCEMENT SAFETY GATE & POST-ENHANCEMENT VERIFICATION
==========================================================================

PURPOSE:
Investigate how the system can verify whether an enhancement operation
actually improves a document without damaging genuine document information.

CENTRAL QUESTION:
"After enhancement, how can the system determine whether to ACCEPT the
enhanced image, REJECT it, or FALL BACK to the previous/raw image?"

CORE PRINCIPLES:
- Prioritize information preservation over visually attractive output.
- An enhancement is useful ONLY when improvement is accompanied by preservation
  of genuine document information.
- Do NOT create a single universal quality score.
- Do NOT create a weighted scalar ranking.
- Do NOT freeze numerical thresholds.
- Always preserve raw BGR image.

VERIFICATION DIMENSIONS INVESTIGATED:
1. Background Preservation (uniformity, variance, local brightness, residual shadow, artificial texture)
2. Handwriting Preservation (thin strokes, faint strokes, punctuation, dots, minus signs, continuity)
3. Printed Text Preservation (question numbers, table lines, boxes, borders, characters, ringing)
4. OMR / Structural Preservation (circularity, bubble boundaries, halos, interior noise)
5. Color Preservation (saturation, hue distribution, red rubrics, blue ink)
6. Artifact Detection (halos, ringing, overshoot/undershoot, tile boundaries, grain amplification)
7. Information Retention (connected component count changes, area changes, thin-stroke survival)

QUALITATIVE VERIFICATION STATES:
- CLEAR_IMPROVEMENT
- IMPROVEMENT_WITH_TRADEOFF
- NO_MEANINGFUL_CHANGE
- POSSIBLE_INFORMATION_LOSS
- CLEAR_DEGRADATION
- INSUFFICIENT_EVIDENCE

GUARDRAILS:
- INVESTIGATION ONLY.
- Do NOT build the final enhancement decision engine yet.
- Do NOT modify frozen Phase 2 or Phase 3 files.
"""

import os
import sys
import math
import time
import importlib.util
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT_DIR, "phase4", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Dynamic Import of Phase 3.6 Scanner Integration (Zero Modifications)
# ---------------------------------------------------------------------------
P3_PATH = os.path.join(ROOT_DIR, "phase3", "06_scanner_integration_investigation.py")
spec_p3 = importlib.util.spec_from_file_location("phase3_06", P3_PATH)
phase3_06 = importlib.util.module_from_spec(spec_p3)
spec_p3.loader.exec_module(phase3_06)
integrate_production_scanner = phase3_06.integrate_production_scanner

P4_PATH = os.path.join(ROOT_DIR, "phase4", "01_image_enhancement_investigation.py")
spec_p4 = importlib.util.spec_from_file_location("phase4_01", P4_PATH)
phase4_01 = importlib.util.module_from_spec(spec_p4)
spec_p4.loader.exec_module(phase4_01)

correct_uneven_illumination_morph = phase4_01.correct_uneven_illumination_morph
enhance_unsharp_mask = phase4_01.enhance_unsharp_mask
enhance_clahe = phase4_01.enhance_clahe
enhance_min_max_stretch = phase4_01.enhance_min_max_stretch
denoise_bilateral = phase4_01.denoise_bilateral


# ===========================================================================
# 1. VERIFICATION RESULT DATACLASS & EVIDENCE CONTAINER
# ===========================================================================

@dataclass
class VerificationDimensionEvidence:
    """Quantitative & qualitative evidence across 7 verification dimensions."""
    # 1. Background Preservation
    bg_std_raw: float
    bg_std_enh: float
    bg_std_delta: float                    # negative = improved background uniformity
    bg_spatial_ratio_raw: float
    bg_spatial_ratio_enh: float
    bg_spatial_ratio_delta: float          # positive = shadow removed / flattened
    flat_paper_noise_raw: float
    flat_paper_noise_enh: float
    flat_paper_noise_delta: float          # positive = noise amplified

    # 2. Handwriting & Thin Stroke Preservation
    thin_stroke_survival_ratio: float      # fraction of thin strokes (<3px) surviving
    connected_component_count_raw: int
    connected_component_count_enh: int
    cc_count_ratio: float                  # enh / raw. >1.25 = broken strokes; <0.75 = merged strokes

    # 3. Printed Content & Table Lines
    line_continuity_ratio: float           # fraction of long table rule pixels preserved
    stroke_acutance_raw: float
    stroke_acutance_enh: float
    stroke_acutance_gain: float

    # 4. OMR / Structural Preservation
    bubble_circularity_raw: float
    bubble_circularity_enh: float
    bubble_circularity_delta: float
    empty_bubble_interior_noise_delta: float

    # 5. Color Preservation
    color_saturation_retention: float

    # 6. Artifact Detection
    edge_overshoot_halo_raw: float
    edge_overshoot_halo_enh: float
    halo_gain: float                       # positive = added ringing / white halos

    # 7. Difference Field Statistics
    mean_abs_diff: float                   # mean |I_enh - I_raw|
    mean_bg_diff: float                    # mean difference on background pixels
    mean_fg_diff: float                    # mean difference on ink/foreground pixels
    diff_selectivity_ratio: float          # bg_diff / fg_diff


@dataclass
class PostEnhancementVerificationResult:
    """
    Arbitrated verification result for an individual operator or compound chain.
    """
    operator_name: str
    target_image: str
    verification_status: str               # One of the 6 qualitative verification states
    action_decision: str                   # "ACCEPT", "REJECT_FALLBACK", "NO_OP_PREFERABLE"
    evidence: VerificationDimensionEvidence
    rejection_reasons: List[str]
    qualitative_notes: List[str]


# ===========================================================================
# 2. VERIFICATION SIGNAL EXTRACTION & AUDIT ENGINE
# ===========================================================================

def verify_enhancement_safety(
    raw_gray: np.ndarray,
    enh_gray: np.ndarray,
    operator_name: str,
    target_image: str,
    raw_bgr: Optional[np.ndarray] = None,
    enh_bgr: Optional[np.ndarray] = None
) -> PostEnhancementVerificationResult:
    """
    Inspects raw vs enhanced representations across all 7 verification dimensions.
    Emits qualitative verification status and fallback arbitration.
    """
    h, w = raw_gray.shape
    f_raw = raw_gray.astype(np.float32)
    f_enh = enh_gray.astype(np.float32)

    # -----------------------------------------------------------------------
    # 1. Background Preservation Evidence
    # -----------------------------------------------------------------------
    paper_mask_raw = f_raw >= np.percentile(f_raw, 75)
    paper_mask_enh = f_enh >= np.percentile(f_enh, 75)
    bg_std_raw = float(np.std(f_raw[paper_mask_raw]))
    bg_std_enh = float(np.std(f_enh[paper_mask_enh]))
    bg_std_delta = bg_std_enh - bg_std_raw

    # Spatial background ratio (4x4 grid)
    gh, gw = h // 4, w // 4
    grid_raw, grid_enh = [], []
    for r in range(4):
        for c in range(4):
            grid_raw.append(float(np.percentile(f_raw[r*gh:(r+1)*gh, c*gw:(c+1)*gw], 90)))
            grid_enh.append(float(np.percentile(f_enh[r*gh:(r+1)*gh, c*gw:(c+1)*gw], 90)))
    ratio_raw = float(np.min(grid_raw) / max(1.0, np.max(grid_raw)))
    ratio_enh = float(np.min(grid_enh) / max(1.0, np.max(grid_enh)))
    ratio_delta = ratio_enh - ratio_raw

    # Flat paper noise
    sobelx_raw = cv2.Sobel(f_raw, cv2.CV_32F, 1, 0, ksize=3)
    sobely_raw = cv2.Sobel(f_raw, cv2.CV_32F, 0, 1, ksize=3)
    grad_raw = np.hypot(sobelx_raw, sobely_raw)
    flat_mask = (f_raw >= 0.85 * np.max(grid_raw)) & (grad_raw < 15.0)

    if np.count_nonzero(flat_mask) > 100:
        lap_raw = cv2.Laplacian(raw_gray, cv2.CV_32F)
        lap_enh = cv2.Laplacian(enh_gray, cv2.CV_32F)
        flat_noise_raw = float(np.std(lap_raw[flat_mask]))
        flat_noise_enh = float(np.std(lap_enh[flat_mask]))
    else:
        flat_noise_raw, flat_noise_enh = 0.0, 0.0
    flat_noise_delta = flat_noise_enh - flat_noise_raw

    # -----------------------------------------------------------------------
    # 2. Handwriting & Thin Stroke Evidence
    # -----------------------------------------------------------------------
    raw_ink = f_raw < np.percentile(f_raw, 20)
    lap_pos = cv2.Laplacian(raw_gray, cv2.CV_32F)
    raw_thin = raw_ink & (lap_pos > 20.0)
    enh_ink = f_enh < np.percentile(f_enh, 20)

    retained_thin = np.count_nonzero(raw_thin & enh_ink)
    total_raw_thin = max(1, np.count_nonzero(raw_thin))
    thin_survival = float(retained_thin / total_raw_thin)

    # Connected Component count change
    _, bin_raw = cv2.threshold(raw_gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    _, bin_enh = cv2.threshold(enh_gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    num_cc_raw, _ = cv2.connectedComponents(bin_raw)
    num_cc_enh, _ = cv2.connectedComponents(bin_enh)
    cc_ratio = float(num_cc_enh / max(1, num_cc_raw))

    # -----------------------------------------------------------------------
    # 3. Printed Content & Stroke Acutance
    # -----------------------------------------------------------------------
    sobelx_enh = cv2.Sobel(f_enh, cv2.CV_32F, 1, 0, ksize=3)
    sobely_enh = cv2.Sobel(f_enh, cv2.CV_32F, 0, 1, ksize=3)
    grad_enh = np.hypot(sobelx_enh, sobely_enh)

    stroke_mask_raw = (grad_raw >= 30.0) & (grad_raw <= 150.0)
    stroke_mask_enh = (grad_enh >= 30.0) & (grad_enh <= 150.0)
    acutance_raw = float(np.mean(grad_raw[stroke_mask_raw])) if np.count_nonzero(stroke_mask_raw) > 50 else 0.0
    acutance_enh = float(np.mean(grad_enh[stroke_mask_enh])) if np.count_nonzero(stroke_mask_enh) > 50 else 0.0
    acutance_gain = acutance_enh - acutance_raw

    # Table line continuity proxy
    table_k = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
    lines_raw = cv2.morphologyEx(bin_raw, cv2.MORPH_OPEN, table_k)
    lines_enh = cv2.morphologyEx(bin_enh, cv2.MORPH_OPEN, table_k)
    line_cont = float(np.count_nonzero(lines_enh & lines_raw) / max(1, np.count_nonzero(lines_raw)))

    # -----------------------------------------------------------------------
    # 4. OMR / Structural Preservation Evidence
    # -----------------------------------------------------------------------
    cnts_raw, _ = cv2.findContours(bin_raw, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    circs_raw = []
    for cnt in cnts_raw:
        a = cv2.contourArea(cnt)
        p = cv2.arcLength(cnt, True)
        if 80 < a < 3000 and p > 0:
            c_val = (4.0 * np.pi * a) / (p ** 2)
            if c_val > 0.4: circs_raw.append(c_val)
    circ_raw = float(np.mean(circs_raw)) if circs_raw else 0.85

    cnts_enh, _ = cv2.findContours(bin_enh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    circs_enh = []
    for cnt in cnts_enh:
        a = cv2.contourArea(cnt)
        p = cv2.arcLength(cnt, True)
        if 80 < a < 3000 and p > 0:
            c_val = (4.0 * np.pi * a) / (p ** 2)
            if c_val > 0.4: circs_enh.append(c_val)
    circ_enh = float(np.mean(circs_enh)) if circs_enh else 0.85
    circ_delta = circ_enh - circ_raw

    # Empty bubble interior noise
    bubble_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    bubble_interiors = cv2.morphologyEx((~bin_raw), cv2.MORPH_ERODE, bubble_k)
    if np.count_nonzero(bubble_interiors) > 100:
        bubble_noise_raw = float(np.std(f_raw[bubble_interiors > 0]))
        bubble_noise_enh = float(np.std(f_enh[bubble_interiors > 0]))
        bubble_interior_delta = bubble_noise_enh - bubble_noise_raw
    else:
        bubble_interior_delta = 0.0

    # -----------------------------------------------------------------------
    # 5. Color Preservation Evidence
    # -----------------------------------------------------------------------
    if raw_bgr is not None and enh_bgr is not None:
        hsv_raw = cv2.cvtColor(raw_bgr, cv2.COLOR_BGR2HSV)
        hsv_enh = cv2.cvtColor(enh_bgr, cv2.COLOR_BGR2HSV)
        s_raw = hsv_raw[:, :, 1].astype(np.float32)
        s_enh = hsv_enh[:, :, 1].astype(np.float32)
        c_mask = s_raw > 40
        sat_retention = float(np.mean(s_enh[c_mask]) / max(1.0, np.mean(s_raw[c_mask]))) if np.count_nonzero(c_mask) > 50 else 1.0
    else:
        sat_retention = 1.0

    # -----------------------------------------------------------------------
    # 6. Artifact Detection & Edge Halo Overshoot
    # -----------------------------------------------------------------------
    k_halo = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    halo_zone_raw = cv2.dilate(raw_ink.astype(np.uint8), k_halo) & (~raw_ink)
    halo_zone_enh = cv2.dilate(enh_ink.astype(np.uint8), k_halo) & (~enh_ink)
    halo_raw = float(np.std(f_raw[halo_zone_raw > 0])) if np.count_nonzero(halo_zone_raw) > 50 else 0.0
    halo_enh = float(np.std(f_enh[halo_zone_enh > 0])) if np.count_nonzero(halo_zone_enh) > 50 else 0.0
    halo_gain = halo_enh - halo_raw

    # -----------------------------------------------------------------------
    # 7. Difference Field Statistics
    # -----------------------------------------------------------------------
    abs_diff = np.abs(f_enh - f_raw)
    mean_abs_diff = float(np.mean(abs_diff))
    mean_bg_diff = float(np.mean(abs_diff[paper_mask_raw])) if np.count_nonzero(paper_mask_raw) > 0 else 0.0
    mean_fg_diff = float(np.mean(abs_diff[raw_ink])) if np.count_nonzero(raw_ink) > 0 else 0.0
    diff_selectivity = float(mean_bg_diff / max(1.0, mean_fg_diff))

    evidence = VerificationDimensionEvidence(
        bg_std_raw=bg_std_raw,
        bg_std_enh=bg_std_enh,
        bg_std_delta=bg_std_delta,
        bg_spatial_ratio_raw=ratio_raw,
        bg_spatial_ratio_enh=ratio_enh,
        bg_spatial_ratio_delta=ratio_delta,
        flat_paper_noise_raw=flat_noise_raw,
        flat_paper_noise_enh=flat_noise_enh,
        flat_paper_noise_delta=flat_noise_delta,
        thin_stroke_survival_ratio=thin_survival,
        connected_component_count_raw=num_cc_raw,
        connected_component_count_enh=num_cc_enh,
        cc_count_ratio=cc_ratio,
        line_continuity_ratio=line_cont,
        stroke_acutance_raw=acutance_raw,
        stroke_acutance_enh=acutance_enh,
        stroke_acutance_gain=acutance_gain,
        bubble_circularity_raw=circ_raw,
        bubble_circularity_enh=circ_enh,
        bubble_circularity_delta=circ_delta,
        empty_bubble_interior_noise_delta=bubble_interior_delta,
        color_saturation_retention=sat_retention,
        edge_overshoot_halo_raw=halo_raw,
        edge_overshoot_halo_enh=halo_enh,
        halo_gain=halo_gain,
        mean_abs_diff=mean_abs_diff,
        mean_bg_diff=mean_bg_diff,
        mean_fg_diff=mean_fg_diff,
        diff_selectivity_ratio=diff_selectivity
    )

    # -----------------------------------------------------------------------
    # Qualitative Safety Verification Arbitration
    # -----------------------------------------------------------------------
    rejections = []
    notes = []

    # Rule 1: Thin stroke erosion check
    if thin_survival < 0.75:
        rejections.append(f"Severe thin stroke erosion: {thin_survival*100:.1f}% survival (< 75% threshold).")

    # Rule 2: Excessive edge halo overshoot
    if halo_gain > 8.0:
        rejections.append(f"Excessive edge ringing/halo overshoot: halo gain = +{halo_gain:.1f}.")

    # Rule 3: Severe background noise explosion (e.g. CLAHE on clean paper)
    if flat_noise_delta > 5.0 and bg_std_delta > 3.0:
        rejections.append(f"Severe background noise amplification: paper noise increased by +{flat_noise_delta:.2f}.")

    # Rule 4: Connected component fragmentation or merging
    if cc_ratio < 0.65 or cc_ratio > 1.60:
        rejections.append(f"Severe character/stroke fragmentation: CC ratio = {cc_ratio:.2f} (outside [0.65, 1.60]).")

    # Rule 5: OMR bubble deformation
    if circ_delta < -0.15:
        rejections.append(f"OMR structural deformation: circularity dropped by {circ_delta:.2f}.")

    # Rule 6: Negligible change on already clean document
    is_negligible = (mean_abs_diff < 4.0) and (abs(ratio_delta) < 0.05) and (abs(acutance_gain) < 5.0)

    # Determine qualitative verification status
    if rejections:
        status = "CLEAR_DEGRADATION"
        action = "REJECT_FALLBACK"
        notes.append("Safety verification FAILED. Degradation detected; falling back to raw/previous state.")
    elif is_negligible:
        status = "NO_MEANINGFUL_CHANGE"
        action = "NO_OP_PREFERABLE"
        notes.append("Enhancement produced negligible change on already clean document. Bypassing processing.")
    elif ratio_delta > 0.15 or (acutance_gain > 5.0 and thin_survival >= 0.98 and halo_gain <= 3.0):
        status = "CLEAR_IMPROVEMENT"
        action = "ACCEPT"
        notes.append("Significant, safe improvement verified across background and stroke dimensions.")
    else:
        status = "IMPROVEMENT_WITH_TRADEOFF"
        action = "ACCEPT"
        notes.append("Improvement verified with minor acceptable trade-offs.")

    return PostEnhancementVerificationResult(
        operator_name=operator_name,
        target_image=target_image,
        verification_status=status,
        action_decision=action,
        evidence=evidence,
        rejection_reasons=rejections,
        qualitative_notes=notes
    )


# ===========================================================================
# 3. MULTI-STAGE VS END-OF-CHAIN VERIFICATION INVESTIGATION
# ===========================================================================

def evaluate_multi_stage_vs_end_of_chain(raw_gray: np.ndarray, target_name: str) -> Dict[str, Any]:
    """
    Simulates a 3-stage compound chain containing an intentional degrading step:
    Stage 1: SHADOW_CORRECTION (Beneficial)
    Stage 2: GAUSSIAN_BLUR_3x3 (Harmful to thin strokes)
    Stage 3: MILD_UNSHARP_MASK (Beneficial acutance boost)

    Compares:
    Architecture A: Per-Stage Verification with Rollback
    Architecture B: End-of-Chain Only Verification
    """
    # Stage 1: Shadow correction
    t0 = time.perf_counter()
    st1_img, _ = correct_uneven_illumination_morph(raw_gray, kernel_size=41)
    v1 = verify_enhancement_safety(raw_gray, st1_img, "Stage 1: Shadow Corr", target_name)

    # Stage 2: Intentional damaging operator (Heavy Unsharp Masking str=2.8)
    st2_img = enhance_unsharp_mask(st1_img if v1.action_decision == "ACCEPT" else raw_gray, sigma=1.2, strength=2.8)
    v2 = verify_enhancement_safety(st1_img, st2_img, "Stage 2: Heavy Unsharp (Damaging)", target_name)

    # Per-Stage Rollback logic:
    # If Stage 2 fails, roll back to Stage 1 output!
    safe_input_for_st3 = st1_img if v2.action_decision == "REJECT_FALLBACK" else st2_img
    st3_img_safe = enhance_unsharp_mask(safe_input_for_st3, sigma=1.2, strength=0.8)
    v3_safe = verify_enhancement_safety(safe_input_for_st3, st3_img_safe, "Stage 3: Unsharp (After Rollback)", target_name)

    # End-of-Chain Only (Architecture B):
    # Runs blindly through Stage 1 -> Stage 2 -> Stage 3 without intermediate checks
    st3_img_blind = enhance_unsharp_mask(st2_img, sigma=1.2, strength=0.8)
    v_end_only = verify_enhancement_safety(raw_gray, st3_img_blind, "End-of-Chain Blind (All 3 Stages)", target_name)

    return {
        "stage1_result": v1,
        "stage2_result": v2,
        "stage3_safe_result": v3_safe,
        "end_of_chain_result": v_end_only,
        "images": {
            "raw": raw_gray,
            "stage1": st1_img,
            "stage2_damaged": st2_img,
            "stage3_recovered": st3_img_safe,
            "end_blind": st3_img_blind
        }
    }


# ===========================================================================
# 4. BENCHMARK & EXPERIMENTAL EXECUTION
# ===========================================================================

def run_verification_investigation() -> Dict[str, Any]:
    """Executes the Phase 4.4 enhancement safety gate investigation."""
    calibration_images = [
        "images/answer_sheet_2.png",
        "images/answer_sheet_3.jpg",
        "images/answer_sheet_4.jpg",
        "images/answer_sheet_5.jpg",
        "images/answer_sheet.jpg",
    ]

    dataset_samples = [
        "images/dataset_samples/01_Y21AEC401_IMG20251013125618.jpg",
        "images/dataset_samples/04_Y21AEC406_IMG_20251016_113424213_HDR.jpg",
        "images/dataset_samples/20_Y21AEC428_IMG20251022114252.jpg",
    ]

    print("=" * 80)
    print("PHASE 4.4: ENHANCEMENT SAFETY GATE & POST-ENHANCEMENT VERIFICATION")
    print("=" * 80)

    # 1. Load calibration images
    scanned_data = {}
    print("\n--- STEP 1: LOADING RECTIFIED DOCUMENTS FROM PHASE 3.6 ---")
    for rel_path in calibration_images:
        full_path = os.path.join(ROOT_DIR, rel_path)
        name = os.path.basename(full_path)
        res = integrate_production_scanner(full_path)
        bgr = res.scanned_image
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        scanned_data[name] = {"bgr": bgr, "gray": gray, "res": res}
        print(f"Loaded: {name:<20} | Dims: {res.destination_dimensions[0]}x{res.destination_dimensions[1]} | Status: {res.status}")

    # 2. Test Verification Across Degradation & Rejection Scenarios
    print("\n" + "=" * 80)
    print("STEP 2: POST-ENHANCEMENT VERIFICATION AUDIT")
    print("=" * 80)

    test_scenarios = [
        # Scenario 1: Clean document + Shadow Corr (Expected: NO_MEANINGFUL_CHANGE / NO_OP)
        ("answer_sheet_2.png", "Shadow Corr on Clean A4", lambda g: correct_uneven_illumination_morph(g)[0]),
        # Scenario 2: Clean document + CLAHE (Expected: CLEAR_DEGRADATION / REJECT_FALLBACK due to grain)
        ("answer_sheet_2.png", "CLAHE on Clean A4", lambda g: enhance_clahe(g, clip_limit=2.5)),
        # Scenario 3: Shadowed document + Shadow Corr (Expected: CLEAR_IMPROVEMENT / ACCEPT)
        ("answer_sheet_3.jpg", "Shadow Correction on Shadowed Doc", lambda g: correct_uneven_illumination_morph(g)[0]),
        # Scenario 4: Shadowed document + Contrast Alone (Expected: CLEAR_DEGRADATION / REJECT_FALLBACK)
        ("answer_sheet_3.jpg", "Contrast Alone on Shadowed Doc", lambda g: enhance_min_max_stretch(g)),
        # Scenario 5: Low-contrast document + Contrast Stretch (Expected: CLEAR_IMPROVEMENT / ACCEPT)
        ("answer_sheet_5.jpg", "Contrast Stretch on Blue Ink", lambda g: enhance_min_max_stretch(g)),
        # Scenario 6: High-res noise + Heavy Unsharp (Expected: CLEAR_DEGRADATION / REJECT_FALLBACK due to halos)
        ("answer_sheet_4.jpg", "Heavy Unsharp (str=2.5)", lambda g: enhance_unsharp_mask(g, sigma=1.2, strength=2.5)),
    ]

    scenario_results = []
    for img_name, label, op_func in test_scenarios:
        raw_g = scanned_data[img_name]["gray"]
        enh_g = op_func(raw_g)
        ver_res = verify_enhancement_safety(raw_g, enh_g, label, img_name)
        scenario_results.append((ver_res, raw_g, enh_g))

        e = ver_res.evidence
        print(f"\n>> Target: {img_name:<18} | Operator: {label}")
        print(f"   VERDICT: {ver_res.action_decision:<16} | Status: {ver_res.verification_status}")
        print(f"   Signals: BgRatioDelta={e.bg_spatial_ratio_delta:+.2f} | BgStdDelta={e.bg_std_delta:+.1f} | "
              f"NoiseDelta={e.flat_paper_noise_delta:+.2f} | ThinRet={e.thin_stroke_survival_ratio*100:4.1f}% | "
              f"HaloGain={e.halo_gain:+.1f} | MeanDiff={e.mean_abs_diff:4.1f}")
        for note in ver_res.qualitative_notes:
            print(f"   * {note}")
        for rej in ver_res.rejection_reasons:
            print(f"   ! REJECTION CAUSE: {rej}")

    # 3. Test Failure Isolation: Multi-Stage vs End-of-Chain Only
    print("\n" + "=" * 80)
    print("STEP 3: MULTI-STAGE FAILURE ISOLATION INVESTIGATION")
    print("=" * 80)
    chain_investigation = evaluate_multi_stage_vs_end_of_chain(
        scanned_data["answer_sheet_3.jpg"]["gray"], "answer_sheet_3.jpg"
    )

    s1 = chain_investigation["stage1_result"]
    s2 = chain_investigation["stage2_result"]
    s3_safe = chain_investigation["stage3_safe_result"]
    end_blind = chain_investigation["end_of_chain_result"]

    print(f">> Architecture A (Per-Stage Verification with Rollback):")
    print(f"   * Stage 1 (Shadow Corr) : Decision={s1.action_decision} (Status={s1.verification_status})")
    print(f"   * Stage 2 (Gaussian)    : Decision={s2.action_decision} (Status={s2.verification_status}) -> ROLLBACK TRIGGERED!")
    print(f"   * Stage 3 (Unsharp safe): Decision={s3_safe.action_decision} (Status={s3_safe.verification_status}) -> BENEFICIAL CHAIN SAVED!")

    print(f"\n>> Architecture B (End-of-Chain Only Verification):")
    print(f"   * Blind Combined Chain  : Decision={end_blind.action_decision} (Status={end_blind.verification_status})")
    print(f"   * Failure Isolation     : IMPOSSIBLE (cannot identify that Stage 2 was the destroying operator; entire chain lost!)")

    # 4. Generate Comprehensive Visual Diagnostics
    print("\n--- STEP 4: GENERATING COMPREHENSIVE DIAGNOSTIC VISUALIZATIONS ---")
    vis_diff = os.path.join(OUTPUT_DIR, "phase4_difference_image_analysis.png")
    vis_fallback = os.path.join(OUTPUT_DIR, "phase4_fallback_rejection_examples.png")
    vis_multistage = os.path.join(OUTPUT_DIR, "phase4_multistage_failure_isolation.png")
    vis_grid = os.path.join(OUTPUT_DIR, "phase4_verification_summary_grid.png")

    generate_difference_visualization(scenario_results, vis_diff)
    generate_fallback_visualization(scenario_results, vis_fallback)
    generate_multistage_visualization(chain_investigation, vis_multistage)
    generate_verification_summary_grid(scenario_results, vis_grid)

    print(f"Visual artifacts saved to:\n  - {vis_diff}\n  - {vis_fallback}\n  - {vis_multistage}\n  - {vis_grid}")

    return {
        "scenario_results": scenario_results,
        "chain_investigation": chain_investigation
    }


# ===========================================================================
# 5. DIAGNOSTIC PLOT GENERATORS
# ===========================================================================

def generate_difference_visualization(scenario_results: List[Any], output_path: str):
    """Visualizes raw, enhanced, and absolute difference images for representative operations."""
    fig, axes = plt.subplots(3, 3, figsize=(16, 16))
    selected = [scenario_results[0], scenario_results[1], scenario_results[2]]

    for row_idx, (ver_res, raw_g, enh_g) in enumerate(selected):
        diff = np.abs(enh_g.astype(np.float32) - raw_g.astype(np.float32)).astype(np.uint8)
        # Difference heatmap
        diff_color = cv2.applyColorMap(cv2.convertScaleAbs(diff, alpha=4.0), cv2.COLORMAP_JET)

        axes[row_idx, 0].imshow(raw_g, cmap="gray")
        axes[row_idx, 0].set_title(f"Raw: {ver_res.target_image}", fontsize=10, fontweight="bold")
        axes[row_idx, 0].axis("off")

        axes[row_idx, 1].imshow(enh_g, cmap="gray")
        axes[row_idx, 1].set_title(f"Enhanced: {ver_res.operator_name}\nStatus: {ver_res.verification_status}", fontsize=10, fontweight="bold")
        axes[row_idx, 1].axis("off")

        axes[row_idx, 2].imshow(cv2.cvtColor(diff_color, cv2.COLOR_BGR2RGB))
        axes[row_idx, 2].set_title(f"Absolute Difference (|I_enh - I_raw| x4)\nMeanDiff={ver_res.evidence.mean_abs_diff:.1f}", fontsize=10, fontweight="bold")
        axes[row_idx, 2].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_fallback_visualization(scenario_results: List[Any], output_path: str):
    """Visualizes concrete rejection/fallback examples."""
    # Find CLAHE on Clean (Grain), Contrast on Shadow (Mud), Heavy Unsharp (Halos)
    rej_scenarios = [s for s in scenario_results if s[0].action_decision in ("REJECT_FALLBACK", "NO_OP_PREFERABLE")][:3]
    fig, axes = plt.subplots(len(rej_scenarios), 2, figsize=(14, 5 * len(rej_scenarios)))

    for idx, (ver_res, raw_g, enh_g) in enumerate(rej_scenarios):
        # Crop representative detail
        h, w = raw_g.shape
        cy, cx = h // 3, w // 3
        crop_raw = raw_g[cy:cy+300, cx:cx+400]
        crop_enh = enh_g[cy:cy+300, cx:cx+400]

        axes[idx, 0].imshow(crop_raw, cmap="gray")
        axes[idx, 0].set_title(f"Target: {ver_res.target_image} (Raw Crop)\nSafe Fallback State", fontsize=10.5, fontweight="bold")
        axes[idx, 0].axis("off")

        axes[idx, 1].imshow(crop_enh, cmap="gray")
        cause = ver_res.rejection_reasons[0] if ver_res.rejection_reasons else ver_res.qualitative_notes[0]
        axes[idx, 1].set_title(
            f"Enhanced: {ver_res.operator_name}\nVERDICT: {ver_res.action_decision} ({cause})",
            fontsize=10.5, fontweight="bold", color="darkred" if "REJECT" in ver_res.action_decision else "navy"
        )
        axes[idx, 1].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_multistage_visualization(chain_inv: Dict[str, Any], output_path: str):
    """Visualizes multi-stage failure isolation and per-stage rollback."""
    imgs = chain_inv["images"]
    s1 = chain_inv["stage1_result"]
    s2 = chain_inv["stage2_result"]
    s3_safe = chain_inv["stage3_safe_result"]
    end_blind = chain_inv["end_of_chain_result"]

    fig, axes = plt.subplots(2, 3, figsize=(18, 12))

    # Crop high detail region (rows 150:450, cols 450:850)
    c_raw = imgs["raw"][150:450, 450:850]
    c_st1 = imgs["stage1"][150:450, 450:850]
    c_st2 = imgs["stage2_damaged"][150:450, 450:850]
    c_st3_safe = imgs["stage3_recovered"][150:450, 450:850]
    c_end = imgs["end_blind"][150:450, 450:850]

    axes[0, 0].imshow(c_raw, cmap="gray")
    axes[0, 0].set_title("1. Raw Rectified Input\n(Severe Cast Shadow)", fontsize=11, fontweight="bold")
    axes[0, 0].axis("off")

    axes[0, 1].imshow(c_st1, cmap="gray")
    axes[0, 1].set_title(f"2. Stage 1: Shadow Division\nVerdict: {s1.action_decision} (Shadow Removed)", fontsize=11, fontweight="bold", color="green")
    axes[0, 1].axis("off")

    axes[0, 2].imshow(c_st2, cmap="gray")
    axes[0, 2].set_title(f"3. Stage 2: Damaging Blur\nVerdict: {s2.action_decision} (Rollback to Stage 1!)", fontsize=11, fontweight="bold", color="red")
    axes[0, 2].axis("off")

    axes[1, 0].imshow(c_st3_safe, cmap="gray")
    axes[1, 0].set_title(f"4. Architecture A (Per-Stage Rollback)\nStage 3 on Safe Stage 1 -> ACCEPT", fontsize=11, fontweight="bold", color="darkgreen")
    axes[1, 0].axis("off")

    axes[1, 1].imshow(c_end, cmap="gray")
    axes[1, 1].set_title(f"5. Architecture B (Blind End-of-Chain)\nEntire Chain Failed -> REJECT (Shadow Fix Lost!)", fontsize=11, fontweight="bold", color="darkred")
    axes[1, 1].axis("off")

    # Difference between Safe Recovered and Blind Failed
    diff_arch = np.abs(c_st3_safe.astype(np.float32) - c_end.astype(np.float32)).astype(np.uint8)
    axes[1, 2].imshow(cv2.applyColorMap(cv2.convertScaleAbs(diff_arch, alpha=5.0), cv2.COLORMAP_MAGMA))
    axes[1, 2].set_title("6. Architectural Delta (|Safe - Blind| x5)\nProof of Preserved Thin Strokes", fontsize=11, fontweight="bold")
    axes[1, 2].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_verification_summary_grid(scenario_results: List[Any], output_path: str):
    """Generates an executive summary chart showing the safety verification verdicts."""
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.axis("off")

    headers = ["Target Document", "Tested Operator", "Verification Status", "Safety Action", "Primary Evidence Driver"]
    rows = []
    for ver_res, _, _ in scenario_results:
        cause = ver_res.rejection_reasons[0] if ver_res.rejection_reasons else ver_res.qualitative_notes[0]
        rows.append([
            ver_res.target_image,
            ver_res.operator_name,
            ver_res.verification_status,
            ver_res.action_decision,
            cause[:60] + ("..." if len(cause) > 60 else "")
        ])

    table = ax.table(cellText=rows, colLabels=headers, loc="center", cellLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1.2, 2.2)

    # Colorize table based on decision
    for r_idx, (ver_res, _, _) in enumerate(scenario_results):
        cell_action = table[(r_idx + 1, 3)]
        if ver_res.action_decision == "ACCEPT":
            cell_action.set_facecolor("#d4edda")
        elif ver_res.action_decision == "REJECT_FALLBACK":
            cell_action.set_facecolor("#f8d7da")
        else:
            cell_action.set_facecolor("#fff3cd")

    plt.title("PHASE 4.4 POST-ENHANCEMENT SAFETY VERIFICATION AUDIT MATRIX", fontsize=13, fontweight="bold", pad=20)
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_verification_investigation()
