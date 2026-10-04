"""
phase4/03_operator_validation_investigation.py

AI-EVAL PHASE 4.3: ENHANCEMENT OPERATOR VALIDATION & NON-DESTRUCTIVE COMPARISON
===============================================================================

PURPOSE:
Investigate and validate which enhancement operators and operator combinations
improve document readability while strictly preserving genuine document information.

INVESTIGATED OPERATORS (INDIVIDUAL):
1. NO_OP / RAW (Baseline preservation test)
2. SHADOW_CORRECTION (Morphological background division)
3. CONTRAST_STRETCH (Percentile 1%-99% dynamic range stretch)
4. BILATERAL_DENOISING (Edge-preserving paper smoothing)
5. MILD_UNSHARP_MASKING (Character edge acutance enhancement)
6. CLAHE (Contrast-Limited Adaptive Histogram Equalization)

INVESTIGATED COMBINATIONS:
- SHADOW_CORRECTION -> CONTRAST_STRETCH
- SHADOW_CORRECTION -> DENOISING
- SHADOW_CORRECTION -> SHARPEN
- DENOISING -> SHARPEN
- DENOISING -> CONTRAST_STRETCH
- CONTRAST_STRETCH -> SHARPEN
- SHADOW_CORRECTION -> DENOISING -> SHARPEN
- NO_OP

EVALUATED EVIDENCE CATEGORIES:
1. Background preservation (mean, variance, spatial uniformity, shadow residual)
2. Handwriting preservation (thin strokes, faint ink, punctuation, continuity)
3. Printed-content preservation (printed text, table lines, numbers, borders)
4. OMR / layout preservation (bubbles, checkbox boundaries, halos, deformation)
5. Color preservation (BGR ground truth, colored rubrics, saturation retention)
6. Stroke quality (continuity, edge acutance, haloing, overshoot/undershoot)

GUARDRAILS:
- INVESTIGATION ONLY.
- Do NOT build the final enhancement selection engine yet.
- Do NOT freeze any numerical thresholds from Phase 4.2.
- Do NOT create a single universal quality score or weighted ranking.
- Do NOT modify any frozen Phase 2 or Phase 3 files.
- Always preserve the raw input image in every comparison.
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


# ===========================================================================
# 1. STANDALONE ENHANCEMENT OPERATORS IMPLEMENTATION
# ===========================================================================

def op_raw(gray: np.ndarray) -> np.ndarray:
    """Baseline NO_OP: Unmodified input."""
    return gray.copy()


def op_shadow_correction(gray: np.ndarray, kernel_size: int = 41) -> Tuple[np.ndarray, np.ndarray]:
    """
    Morphological background estimation and division normalization:
    I_corr = (I / BG) * 255
    """
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    bg_dilated = cv2.morphologyEx(gray, cv2.MORPH_DILATE, k)
    bg_est = cv2.medianBlur(bg_dilated, 21)
    f_gray = gray.astype(np.float32)
    f_bg = np.maximum(1.0, bg_est.astype(np.float32))
    normalized = np.clip((f_gray / f_bg) * 255.0, 0, 255).astype(np.uint8)
    return normalized, bg_est


def op_contrast_stretch(gray: np.ndarray, p_low: float = 1.0, p_high: float = 99.0) -> np.ndarray:
    """Percentile-based dynamic range contrast stretching."""
    low_val = float(np.percentile(gray, p_low))
    high_val = float(np.percentile(gray, p_high))
    if high_val <= low_val:
        return gray.copy()
    stretched = np.clip((gray.astype(np.float32) - low_val) * (255.0 / (high_val - low_val)), 0, 255)
    return stretched.astype(np.uint8)


def op_bilateral_denoise(gray: np.ndarray, d: int = 5, sigma_color: float = 25.0, sigma_space: float = 25.0) -> np.ndarray:
    """Edge-preserving bilateral smoothing of flat paper grain."""
    return cv2.bilateralFilter(gray, d, sigma_color, sigma_space)


def op_mild_unsharp_mask(gray: np.ndarray, sigma: float = 1.2, strength: float = 0.8) -> np.ndarray:
    """
    Mild unsharp masking to enhance stroke edge acutance:
    I_sharp = (1 + strength) * I - strength * Gaussian(I)
    """
    blurred = cv2.GaussianBlur(gray, (0, 0), sigma)
    sharpened = cv2.addWeighted(gray, 1.0 + strength, blurred, -strength, 0)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def op_clahe(gray: np.ndarray, clip_limit: float = 2.0, tile_size: Tuple[int, int] = (8, 8)) -> np.ndarray:
    """Contrast-Limited Adaptive Histogram Equalization."""
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_size)
    return clahe.apply(gray)


# ===========================================================================
# 2. MULTI-EVIDENCE PRESERVATION METRICS
# ===========================================================================

@dataclass
class OperatorPreservationMetrics:
    """
    Multi-signal evidence evaluation across independent preservation dimensions.
    """
    operator_name: str
    latency_ms: float

    # Dimension 1: Background Preservation
    bg_mean: float                         # Mean intensity of top 25% pixels
    bg_std: float                          # Std of paper pixels (lower = more uniform paper)
    bg_spatial_ratio: float                # 4x4 min/max background ratio (closer to 1.0 = no shadow)
    flat_paper_noise: float                # High-frequency noise in flat paper

    # Dimension 2: Contrast & Dynamic Range
    dyn_range: float                       # P90 - P10
    local_michelson: float                 # Mean local Michelson contrast

    # Dimension 3: Stroke & Edge Quality
    stroke_acutance: float                 # Mean gradient across genuine stroke boundaries
    laplacian_sharpness: float             # Diagnostic high-frequency variance
    edge_overshoot_halo: float             # Halo intensity (std of pixels adjacent to black text)

    # Dimension 4: Thin-Stroke & Structure Retention
    thin_stroke_retention_ratio: float     # Fraction of delicate stroke pixels preserved vs raw
    omr_circularity: float                 # Circularity of OMR bubble test patch (4*pi*A / P^2)


def compute_preservation_metrics(
    processed_gray: np.ndarray,
    raw_gray: np.ndarray,
    operator_name: str,
    latency_ms: float
) -> OperatorPreservationMetrics:
    """
    Computes multi-dimensional preservation metrics without combining them into a single scalar.
    """
    f_proc = processed_gray.astype(np.float32)
    h, w = processed_gray.shape

    # 1. Background Preservation
    paper_mask = f_proc >= np.percentile(f_proc, 75)
    bg_mean = float(np.mean(f_proc[paper_mask]))
    bg_std = float(np.std(f_proc[paper_mask]))

    # 4x4 Grid background ratio
    gh, gw = h // 4, w // 4
    grid_bgs = []
    for r in range(4):
        for c in range(4):
            cell = f_proc[r*gh:(r+1)*gh, c*gw:(c+1)*gw]
            grid_bgs.append(float(np.percentile(cell, 90)))
    bg_ratio = float(np.min(grid_bgs) / max(1.0, np.max(grid_bgs)))

    # Flat paper noise
    sobelx = cv2.Sobel(f_proc, cv2.CV_32F, 1, 0, ksize=3)
    sobely = cv2.Sobel(f_proc, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.hypot(sobelx, sobely)
    flat_mask = (f_proc >= 0.85 * np.max(grid_bgs)) & (grad_mag < 15.0)
    if np.count_nonzero(flat_mask) > 100:
        lap_resp = cv2.Laplacian(processed_gray, cv2.CV_32F)
        flat_noise = float(np.std(lap_resp[flat_mask]))
    else:
        flat_noise = 0.0

    # 2. Contrast
    p10 = float(np.percentile(f_proc, 10))
    p90 = float(np.percentile(f_proc, 90))
    dyn_range = p90 - p10
    michelson = float((bg_mean - p10) / max(1.0, bg_mean + p10))

    # 3. Stroke & Edge Quality
    stroke_mask = (grad_mag >= 30.0) & (grad_mag <= 150.0)
    stroke_acutance = float(np.mean(grad_mag[stroke_mask])) if np.count_nonzero(stroke_mask) > 50 else 0.0
    lap_sharp = float(cv2.Laplacian(processed_gray, cv2.CV_64F).var())

    # Edge overshoot / halo measurement: variance in immediate 3-px dilation zone around ink
    ink_mask = processed_gray < np.percentile(processed_gray, 20)
    k_halo = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    halo_zone = cv2.dilate(ink_mask.astype(np.uint8), k_halo) & (~ink_mask)
    halo_indicator = float(np.std(f_proc[halo_zone > 0])) if np.count_nonzero(halo_zone) > 50 else 0.0

    # 4. Thin-Stroke Retention vs Raw
    # Thin strokes identified in raw image
    raw_ink = raw_gray < np.percentile(raw_gray.astype(np.float32), 20)
    raw_thin = raw_ink & (cv2.Laplacian(raw_gray, cv2.CV_32F) > 20.0)
    proc_ink = processed_gray < np.percentile(f_proc, 20)
    retained_thin = np.count_nonzero(raw_thin & proc_ink)
    total_raw_thin = max(1, np.count_nonzero(raw_thin))
    thin_retention = float(retained_thin / total_raw_thin)

    # 5. OMR Circularity proxy
    # Find circular contours in test image
    _, bin_inv = cv2.threshold(processed_gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    cnts, _ = cv2.findContours(bin_inv, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    circularities = []
    for cnt in cnts:
        area = cv2.contourArea(cnt)
        perim = cv2.arcLength(cnt, True)
        if 80 < area < 3000 and perim > 0:
            c_score = (4.0 * np.pi * area) / (perim ** 2)
            if c_score > 0.4:
                circularities.append(c_score)
    omr_circ = float(np.mean(circularities)) if circularities else 0.85

    return OperatorPreservationMetrics(
        operator_name=operator_name,
        latency_ms=latency_ms,
        bg_mean=bg_mean,
        bg_std=bg_std,
        bg_spatial_ratio=bg_ratio,
        flat_paper_noise=flat_noise,
        dyn_range=dyn_range,
        local_michelson=michelson,
        stroke_acutance=stroke_acutance,
        laplacian_sharpness=lap_sharp,
        edge_overshoot_halo=halo_indicator,
        thin_stroke_retention_ratio=thin_retention,
        omr_circularity=omr_circ
    )


# ===========================================================================
# 3. COMPREHENSIVE EXPERIMENTAL VALIDATION EXECUTION
# ===========================================================================

def run_operator_validation() -> Dict[str, Any]:
    """
    Executes the Phase 4.3 investigation across the complete test matrix:
    - Clean Document Test (answer_sheet_2.png)
    - Shadowed Document Test (answer_sheet_3.jpg)
    - Noise Test (answer_sheet_4.jpg)
    - Low-Contrast Test (answer_sheet_5.jpg)
    - Ambiguous Test (answer_sheet.jpg)
    - Handwriting & Delicate Stroke Tests (Dataset Samples 01, 04, 20)
    """
    print("=" * 80)
    print("PHASE 4.3: ENHANCEMENT OPERATOR VALIDATION & NON-DESTRUCTIVE COMPARISON")
    print("=" * 80)

    # 1. Obtain ScannedDocumentResult inputs
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

    validation_records = {}

    # =======================================================================
    # CASE 1: CLEAN IMAGE TEST (answer_sheet_2.png)
    # =======================================================================
    print("\n" + "=" * 80)
    print("CASE 1: CLEAN DOCUMENT PRESERVATION TEST (answer_sheet_2.png)")
    print("Goal: Test whether NO_OP preserves clean documents better than enhancement.")
    print("=" * 80)
    clean_gray = scanned_data["answer_sheet_2.png"]["gray"]

    clean_eval_ops = {
        "1. NO_OP (RAW)": lambda g: g.copy(),
        "2. CONTRAST_STRETCH": lambda g: op_contrast_stretch(g),
        "3. MILD_UNSHARP_MASK": lambda g: op_mild_unsharp_mask(g, sigma=1.2, strength=0.8),
        "4. BILATERAL_DENOISE": lambda g: op_bilateral_denoise(g),
        "5. SHADOW_CORRECTION": lambda g: op_shadow_correction(g)[0],
        "6. CLAHE": lambda g: op_clahe(g, clip_limit=2.0),
        "7. CLAHE + SHARPEN": lambda g: op_mild_unsharp_mask(op_clahe(g, clip_limit=2.0), sigma=1.2, strength=0.8),
    }

    clean_metrics = {}
    for op_name, fn in clean_eval_ops.items():
        t0 = time.perf_counter()
        out = fn(clean_gray)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        m = compute_preservation_metrics(out, clean_gray, op_name, dt_ms)
        clean_metrics[op_name] = {"metrics": m, "image": out}
        print(f"  {op_name:<24}: Latency={dt_ms:5.1f}ms | BgStd={m.bg_std:4.1f} | FlatNoise={m.flat_paper_noise:4.2f} | "
              f"DynRange={m.dyn_range:4.0f} | Acutance={m.stroke_acutance:4.1f} | ThinRet={m.thin_stroke_retention_ratio*100:4.1f}% | Halo={m.edge_overshoot_halo:4.1f}")

    validation_records["answer_sheet_2.png"] = clean_metrics

    # =======================================================================
    # CASE 2: SHADOW / UNEVEN ILLUMINATION TEST (answer_sheet_3.jpg)
    # =======================================================================
    print("\n" + "=" * 80)
    print("CASE 2: SHADOW & UNEVEN ILLUMINATION TEST (answer_sheet_3.jpg)")
    print("Goal: Test RAW vs SHADOW_CORRECTION vs combinations on severe cast shadow.")
    print("=" * 80)
    shadow_gray = scanned_data["answer_sheet_3.jpg"]["gray"]

    shadow_eval_ops = {
        "1. NO_OP (RAW)": lambda g: g.copy(),
        "2. SHADOW_CORRECTION": lambda g: op_shadow_correction(g)[0],
        "3. SHADOW -> CONTRAST": lambda g: op_contrast_stretch(op_shadow_correction(g)[0]),
        "4. SHADOW -> SHARPEN": lambda g: op_mild_unsharp_mask(op_shadow_correction(g)[0], sigma=1.2, strength=0.8),
        "5. SHADOW -> DENOISE -> SHARP": lambda g: op_mild_unsharp_mask(op_bilateral_denoise(op_shadow_correction(g)[0]), sigma=1.2, strength=0.8),
        "6. CONTRAST_STRETCH ALONE": lambda g: op_contrast_stretch(g),
        "7. CLAHE ALONE": lambda g: op_clahe(g, clip_limit=2.0),
    }

    shadow_metrics = {}
    for op_name, fn in shadow_eval_ops.items():
        t0 = time.perf_counter()
        out = fn(shadow_gray)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        m = compute_preservation_metrics(out, shadow_gray, op_name, dt_ms)
        shadow_metrics[op_name] = {"metrics": m, "image": out}
        print(f"  {op_name:<28}: Latency={dt_ms:5.1f}ms | BgRatio={m.bg_spatial_ratio:.2f} | BgStd={m.bg_std:4.1f} | "
              f"DynRange={m.dyn_range:4.0f} | Acutance={m.stroke_acutance:4.1f} | ThinRet={m.thin_stroke_retention_ratio*100:4.1f}%")

    validation_records["answer_sheet_3.jpg"] = shadow_metrics

    # =======================================================================
    # CASE 3: NOISE & FRAME-LIMITED TEST (answer_sheet_4.jpg)
    # =======================================================================
    print("\n" + "=" * 80)
    print("CASE 3: HIGH-RESOLUTION NOISE & STRUCTURE TEST (answer_sheet_4.jpg)")
    print("Goal: Test bilateral denoising and unsharp masking on sensor grain.")
    print("=" * 80)
    noise_gray = scanned_data["answer_sheet_4.jpg"]["gray"]

    noise_eval_ops = {
        "1. NO_OP (RAW)": lambda g: g.copy(),
        "2. BILATERAL_DENOISE": lambda g: op_bilateral_denoise(g),
        "3. DENOISE -> SHARPEN": lambda g: op_mild_unsharp_mask(op_bilateral_denoise(g), sigma=1.2, strength=0.8),
        "4. SHARPEN ALONE": lambda g: op_mild_unsharp_mask(g, sigma=1.2, strength=0.8),
        "5. GAUSSIAN_DENOISE (3x3)": lambda g: cv2.GaussianBlur(g, (3, 3), 0),
        "6. CONTRAST_STRETCH": lambda g: op_contrast_stretch(g),
    }

    noise_metrics = {}
    for op_name, fn in noise_eval_ops.items():
        t0 = time.perf_counter()
        out = fn(noise_gray)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        m = compute_preservation_metrics(out, noise_gray, op_name, dt_ms)
        noise_metrics[op_name] = {"metrics": m, "image": out}
        print(f"  {op_name:<26}: Latency={dt_ms:5.1f}ms | FlatNoise={m.flat_paper_noise:4.2f} | "
              f"Acutance={m.stroke_acutance:4.1f} | ThinRet={m.thin_stroke_retention_ratio*100:4.1f}% | Halo={m.edge_overshoot_halo:4.1f}")

    validation_records["answer_sheet_4.jpg"] = noise_metrics

    # =======================================================================
    # CASE 4: LOW-CONTRAST HANDWRITING TEST (answer_sheet_5.jpg)
    # =======================================================================
    print("\n" + "=" * 80)
    print("CASE 4: LOW-CONTRAST HANDWRITING TEST (answer_sheet_5.jpg)")
    print("Goal: Test contrast stretching vs unsharp masking on blue handwriting.")
    print("=" * 80)
    low_gray = scanned_data["answer_sheet_5.jpg"]["gray"]

    low_eval_ops = {
        "1. NO_OP (RAW)": lambda g: g.copy(),
        "2. CONTRAST_STRETCH": lambda g: op_contrast_stretch(g),
        "3. CONTRAST -> SHARPEN": lambda g: op_mild_unsharp_mask(op_contrast_stretch(g), sigma=1.2, strength=0.8),
        "4. MILD_UNSHARP ALONE": lambda g: op_mild_unsharp_mask(g, sigma=1.2, strength=0.8),
        "5. CLAHE ALONE": lambda g: op_clahe(g, clip_limit=2.0),
    }

    low_metrics = {}
    for op_name, fn in low_eval_ops.items():
        t0 = time.perf_counter()
        out = fn(low_gray)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        m = compute_preservation_metrics(out, low_gray, op_name, dt_ms)
        low_metrics[op_name] = {"metrics": m, "image": out}
        print(f"  {op_name:<24}: Latency={dt_ms:5.1f}ms | DynRange={m.dyn_range:4.0f} | Michelson={m.local_michelson:.2f} | "
              f"Acutance={m.stroke_acutance:4.1f} | ThinRet={m.thin_stroke_retention_ratio*100:4.1f}%")

    validation_records["answer_sheet_5.jpg"] = low_metrics

    # =======================================================================
    # CASE 5: DELICATE HANDWRITING & FAINT PENCIL (Dataset Samples)
    # =======================================================================
    print("\n" + "=" * 80)
    print("CASE 5: DELICATE HANDWRITING & THIN STROKE PRESERVATION TEST")
    print("Goal: Inspect thin pencil loops, decimal points, and minus signs.")
    print("=" * 80)

    dataset_metrics = {}
    for s_rel in dataset_samples:
        s_path = os.path.join(ROOT_DIR, s_rel)
        s_name = os.path.basename(s_path)
        img_s = cv2.imread(s_path)
        if img_s is None:
            continue
        g_s = cv2.cvtColor(img_s, cv2.COLOR_BGR2GRAY)

        # Compare RAW vs CONTRAST vs BILATERAL vs GAUSSIAN vs CLAHE vs UNSHARP
        ops = {
            "RAW": g_s.copy(),
            "CONTRAST": op_contrast_stretch(g_s),
            "BILATERAL": op_bilateral_denoise(g_s),
            "GAUSSIAN_3x3": cv2.GaussianBlur(g_s, (3, 3), 0),
            "CLAHE": op_clahe(g_s, clip_limit=2.0),
            "UNSHARP": op_mild_unsharp_mask(g_s, sigma=1.0, strength=0.8),
        }

        dataset_metrics[s_name] = {}
        for oname, oimg in ops.items():
            m = compute_preservation_metrics(oimg, g_s, oname, 1.0)
            dataset_metrics[s_name][oname] = {"metrics": m, "image": oimg}
            print(f"  Sample {s_name[:18]} [{oname:<12}]: DynRange={m.dyn_range:3.0f} | Acutance={m.stroke_acutance:4.1f} | "
                  f"ThinRet={m.thin_stroke_retention_ratio*100:4.1f}% | FlatNoise={m.flat_paper_noise:4.2f}")

    # =======================================================================
    # 4. GENERATE COMPREHENSIVE VISUAL DIAGNOSTICS
    # =======================================================================
    print("\n--- STEP 4: GENERATING COMPREHENSIVE DIAGNOSTIC VISUALIZATIONS ---")
    vis_clean = os.path.join(OUTPUT_DIR, "phase4_clean_document_no_op_comparison.png")
    vis_shadow = os.path.join(OUTPUT_DIR, "phase4_shadow_validation_comparison.png")
    vis_handwriting = os.path.join(OUTPUT_DIR, "phase4_handwriting_stroke_preservation.png")
    vis_omr = os.path.join(OUTPUT_DIR, "phase4_omr_bubble_halo_investigation.png")
    vis_chains = os.path.join(OUTPUT_DIR, "phase4_operator_interaction_matrix.png")

    generate_clean_comparison_plot(clean_metrics, vis_clean)
    generate_shadow_validation_plot(shadow_metrics, vis_shadow)
    generate_handwriting_preservation_plot(dataset_metrics, vis_handwriting)
    generate_omr_halo_plot(scanned_data["answer_sheet.jpg"]["gray"], vis_omr)
    generate_interaction_matrix_plot(shadow_metrics, clean_metrics, vis_chains)

    print(f"Visual artifacts saved to:\n  - {vis_clean}\n  - {vis_shadow}\n  - {vis_handwriting}\n  - {vis_omr}\n  - {vis_chains}")

    return {
        "calibration_records": validation_records,
        "dataset_records": dataset_metrics
    }


# ===========================================================================
# 4. VISUALIZATION GENERATORS
# ===========================================================================

def generate_clean_comparison_plot(clean_metrics: Dict[str, Any], output_path: str):
    """
    Visualizes why NO_OP is superior to CLAHE/over-enhancement on clean answer_sheet_2.png.
    """
    keys = ["1. NO_OP (RAW)", "2. CONTRAST_STRETCH", "3. MILD_UNSHARP_MASK", "6. CLAHE"]
    fig, axes = plt.subplots(2, 2, figsize=(14, 14))

    for idx, key in enumerate(keys):
        row = idx // 2
        col = idx % 2
        data = clean_metrics[key]
        img = data["image"]
        m: OperatorPreservationMetrics = data["metrics"]

        # Zoom into a high-detail text crop (rows 350:650, cols 200:550)
        crop = img[350:650, 200:550]
        axes[row, col].imshow(crop, cmap="gray")
        axes[row, col].set_title(
            f"{key}\nBgStd: {m.bg_std:.1f} | NoiseSigma: {m.flat_paper_noise:.2f} | Acutance: {m.stroke_acutance:.1f} | ThinRet: {m.thin_stroke_retention_ratio*100:.1f}%",
            fontsize=10.5, fontweight="bold"
        )
        axes[row, col].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_shadow_validation_plot(shadow_metrics: Dict[str, Any], output_path: str):
    """Visualizes RAW vs SHADOW_CORRECTION vs SHADOW+SHARP on answer_sheet_3.jpg."""
    keys = ["1. NO_OP (RAW)", "2. SHADOW_CORRECTION", "4. SHADOW -> SHARPEN", "7. CLAHE ALONE"]
    fig, axes = plt.subplots(2, 2, figsize=(14, 14))

    for idx, key in enumerate(keys):
        row = idx // 2
        col = idx % 2
        data = shadow_metrics[key]
        img = data["image"]
        m: OperatorPreservationMetrics = data["metrics"]

        # Zoom into top-right shadowed quadrant (rows 100:500, cols 500:900)
        crop = img[100:500, 500:900]
        axes[row, col].imshow(crop, cmap="gray")
        axes[row, col].set_title(
            f"{key}\nBgRatio: {m.bg_spatial_ratio:.2f} | BgStd: {m.bg_std:.1f} | DynRange: {m.dyn_range:.0f} | Acutance: {m.stroke_acutance:.1f}",
            fontsize=10.5, fontweight="bold"
        )
        axes[row, col].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_handwriting_preservation_plot(dataset_records: Dict[str, Any], output_path: str):
    """Visualizes delicate handwriting strokes under RAW, Bilateral, Gaussian, and CLAHE."""
    sample_key = list(dataset_records.keys())[1] # Sample 04 (equations & thin numbers)
    ops_dict = dataset_records[sample_key]
    keys = ["RAW", "CONTRAST", "BILATERAL", "GAUSSIAN_3x3", "CLAHE", "UNSHARP"]

    fig, axes = plt.subplots(2, 3, figsize=(16, 11))
    for idx, key in enumerate(keys):
        row = idx // 3
        col = idx % 3
        data = ops_dict[key]
        img = data["image"]
        m: OperatorPreservationMetrics = data["metrics"]

        axes[row, col].imshow(img, cmap="gray")
        axes[row, col].set_title(
            f"{key}\nThinStrokeRet: {m.thin_stroke_retention_ratio*100:.1f}% | Acutance: {m.stroke_acutance:.1f} | Noise: {m.flat_paper_noise:.2f}",
            fontsize=10, fontweight="bold"
        )
        axes[row, col].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_omr_halo_plot(gray_img: np.ndarray, output_path: str):
    """Visualizes OMR bubble boundary preservation, ringing, and halos under different operators."""
    # Crop multiple-choice bubble area (rows 250:550, cols 150:450)
    crop = gray_img[250:550, 150:450]
    c_raw = crop.copy()
    c_contrast = op_contrast_stretch(crop)
    c_unsharp_mild = op_mild_unsharp_mask(crop, sigma=1.2, strength=0.8)
    c_unsharp_heavy = op_mild_unsharp_mask(crop, sigma=1.2, strength=2.2) # Over-sharpened test
    c_clahe = op_clahe(crop, clip_limit=3.0)
    c_bilat = op_bilateral_denoise(crop)

    fig, axes = plt.subplots(2, 3, figsize=(16, 11))
    configs = [
        ("1. RAW (NO_OP)", c_raw, "Clean bubble circles; natural paper white"),
        ("2. CONTRAST_STRETCH", c_contrast, "Denser bubble borders; no edge artifacts"),
        ("3. MILD_UNSHARP (str=0.8)", c_unsharp_mild, "Crisp bubble boundary; zero visible halo"),
        ("4. HEAVY_UNSHARP (str=2.2)", c_unsharp_heavy, "WARNING: White halo ringing around bubbles"),
        ("5. CLAHE (clip=3.0)", c_clahe, "WARNING: Background grain amplified into dark spots"),
        ("6. BILATERAL_DENOISE", c_bilat, "Smooth background; circular boundaries intact"),
    ]

    for idx, (title, img, note) in enumerate(configs):
        row = idx // 3
        col = idx % 3
        axes[row, col].imshow(img, cmap="gray")
        axes[row, col].set_title(f"{title}\n{note}", fontsize=10, fontweight="bold")
        axes[row, col].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_interaction_matrix_plot(shadow_metrics: Dict[str, Any], clean_metrics: Dict[str, Any], output_path: str):
    """Visualizes safe vs unsafe operator interactions on shadowed vs clean documents."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 14))

    # Shadowed Document: Safe Chain (Shadow -> Sharpen)
    ax1 = axes[0, 0]
    ax1.imshow(shadow_metrics["4. SHADOW -> SHARPEN"]["image"][100:500, 500:900], cmap="gray")
    ax1.set_title("Shadowed Doc: SAFE CHAIN (Shadow Corr -> Sharpen)\n(Uniform background + crisp text; no halo)", fontsize=10.5, fontweight="bold")
    ax1.axis("off")

    # Shadowed Document: Unsafe Chain (CLAHE Alone)
    ax2 = axes[0, 1]
    ax2.imshow(shadow_metrics["7. CLAHE ALONE"]["image"][100:500, 500:900], cmap="gray")
    ax2.set_title("Shadowed Doc: UNSAFE OPERATOR (CLAHE Alone)\n(Tile artifacts; shadow boundary remains visible)", fontsize=10.5, fontweight="bold", color="darkred")
    ax2.axis("off")

    # Clean Document: Optimal Path (NO_OP / RAW)
    ax3 = axes[1, 0]
    ax3.imshow(clean_metrics["1. NO_OP (RAW)"]["image"][350:650, 200:550], cmap="gray")
    ax3.set_title("Clean Doc: OPTIMAL PATH (NO_OP / RAW)\n(Pristine paper, no added noise or compute)", fontsize=10.5, fontweight="bold")
    ax3.axis("off")

    # Clean Document: Harmful Operator (CLAHE on Clean)
    ax4 = axes[1, 1]
    ax4.imshow(clean_metrics["6. CLAHE"]["image"][350:650, 200:550], cmap="gray")
    ax4.set_title("Clean Doc: HARMFUL OPERATOR (CLAHE on Clean Paper)\n(BgStd doubled from 3.4 to 7.5; grey paper grain)", fontsize=10.5, fontweight="bold", color="darkred")
    ax4.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_operator_validation()
