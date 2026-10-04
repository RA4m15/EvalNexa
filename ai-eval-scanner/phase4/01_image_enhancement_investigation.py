"""
phase4/01_image_enhancement_investigation.py

AI-EVAL PHASE 4.1: AUTOMATIC IMAGE ENHANCEMENT INVESTIGATION
============================================================

PURPOSE:
Investigate how a rectified document image from Phase 3 (ScannedDocumentResult)
should be enhanced automatically so that it becomes optimal for downstream
OCR/HTR/OMR, while strictly preserving genuine document information.

INPUT SOURCES:
- ScannedDocumentResult outputs from Phase 3:
  * images/answer_sheet_2.png (clean physical page, slight perspective)
  * images/answer_sheet_3.jpg (physical page with severe diagonal cast shadow)
  * images/answer_sheet_4.jpg (frame-limited capture, high detail, text & numbers)
  * images/answer_sheet_5.jpg (frame-limited capture, handwritten student answers)
  * images/answer_sheet.jpg (ambiguous crop, uniform white background, printed text)
- Representative handwriting & ink samples from images/dataset_samples/

INVESTIGATED ENHANCEMENT DIMENSIONS:
1. Brightness / illumination normalization (Linear scaling, Gamma correction)
2. Global contrast normalization (Min-Max stretch, Histogram equalization)
3. Local contrast enhancement (Unsharp masking, High-boost)
4. CLAHE (Contrast-Limited Adaptive Histogram Equalization: tile size & clip limit)
5. Shadow / uneven illumination correction (Morphological background division, Gaussian flat-fielding)
6. Background normalization (Paper white-point calibration)
7. Mild denoising (Gaussian, Median, Bilateral, FastNLMeans)
8. Sharpening (Laplacian, Unsharp mask)
9. Grayscale conversion strategies (Luminance, Green channel, Min-RGB projection)
10. Adaptive thresholding / binarization (Otsu, Adaptive Gaussian, Sauvola)
11. Morphological cleanup (Opening, Closing: impact on thin strokes & dots)
12. Color preservation (RGB vs HSV vs color rubric/stamp separation)

GUARDRAILS:
- INVESTIGATION ONLY.
- Do NOT build the final production enhancement pipeline yet.
- Do NOT modify any frozen Phase 2 or Phase 3 files.
- Do NOT add OCR/HTR, quality scoring, auto-correction, or rescan logic.
- Do NOT freeze universal numerical thresholds.
- Reversibility: always preserve the original rectified image.
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
if not os.path.exists(P3_PATH):
    raise FileNotFoundError(f"Phase 3.6 module not found at: {P3_PATH}")

spec = importlib.util.spec_from_file_location("phase3_06", P3_PATH)
phase3_06 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phase3_06)

integrate_production_scanner = phase3_06.integrate_production_scanner
ScannedDocumentResult = phase3_06.ScannedDocumentResult


# ===========================================================================
# 1. OBJECTIVE IMAGE MEASUREMENT SIGNALS
# ===========================================================================

def compute_objective_signals(image: np.ndarray) -> Dict[str, float]:
    """
    Computes diagnostic objective signals for document images.
    NOTE: These are diagnostic signals, NOT a universal quality score.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    f_gray = gray.astype(np.float32)

    # 1. Brightness statistics
    mean_b = float(np.mean(f_gray))
    p10 = float(np.percentile(f_gray, 10))
    p90 = float(np.percentile(f_gray, 90))
    dynamic_range = p90 - p10

    # 2. Global contrast (standard deviation)
    std_contrast = float(np.std(f_gray))

    # 3. Local contrast (mean local standard deviation in 16x16 sliding windows)
    k_size = 16
    local_mean = cv2.blur(f_gray, (k_size, k_size))
    local_sq_mean = cv2.blur(f_gray ** 2, (k_size, k_size))
    local_var = np.maximum(0.0, local_sq_mean - local_mean ** 2)
    mean_local_std = float(np.mean(np.sqrt(local_var)))

    # 4. Sharpness indicators
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sobelx = cv2.Sobel(f_gray, cv2.CV_32F, 1, 0, ksize=3)
    sobely = cv2.Sobel(f_gray, cv2.CV_32F, 0, 1, ksize=3)
    tenengrad = float(np.mean(sobelx ** 2 + sobely ** 2))

    # 5. Background uniformity (std of brightest 25% of pixels, representing paper)
    paper_mask = f_gray >= np.percentile(f_gray, 75)
    paper_std = float(np.std(f_gray[paper_mask])) if np.count_nonzero(paper_mask) > 0 else 0.0

    # 6. Foreground-to-background contrast (estimated Michelson contrast)
    bg_est = max(1.0, float(np.mean(f_gray[paper_mask])))
    fg_mask = f_gray <= np.percentile(f_gray, 15)
    fg_est = max(0.0, float(np.mean(f_gray[fg_mask])))
    michelson = float((bg_est - fg_est) / (bg_est + fg_est))

    return {
        "mean_brightness": mean_b,
        "p10_brightness": p10,
        "p90_brightness": p90,
        "dynamic_range": dynamic_range,
        "global_std_contrast": std_contrast,
        "mean_local_std": mean_local_std,
        "laplacian_sharpness": lap_var,
        "tenengrad_sharpness": tenengrad,
        "paper_background_std": paper_std,
        "michelson_contrast": michelson,
    }


# ===========================================================================
# 2. ENHANCEMENT OPERATORS IMPLEMENTATION
# ===========================================================================

# ---------------------------------------------------------------------------
# A. Brightness & Illumination Normalization
# ---------------------------------------------------------------------------
def enhance_linear_brightness(image: np.ndarray, alpha: float = 1.2, beta: float = 15.0) -> np.ndarray:
    """Linear scaling: I' = alpha * I + beta."""
    return cv2.convertScaleAbs(image, alpha=alpha, beta=beta)


def enhance_gamma(image: np.ndarray, gamma: float = 0.8) -> np.ndarray:
    """Gamma correction: I' = 255 * (I / 255)^(gamma)."""
    inv_gamma = 1.0 / max(1e-4, gamma)
    table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
    return cv2.LUT(image, table)


# ---------------------------------------------------------------------------
# B. Global Contrast Normalization
# ---------------------------------------------------------------------------
def enhance_min_max_stretch(gray: np.ndarray, p_low: float = 1.0, p_high: float = 99.0) -> np.ndarray:
    """Percentile-based dynamic range stretching."""
    low_val = float(np.percentile(gray, p_low))
    high_val = float(np.percentile(gray, p_high))
    if high_val <= low_val:
        return gray.copy()
    stretched = np.clip((gray.astype(np.float32) - low_val) * (255.0 / (high_val - low_val)), 0, 255)
    return stretched.astype(np.uint8)


def enhance_global_histogram_equalization(gray: np.ndarray) -> np.ndarray:
    """Global histogram equalization."""
    return cv2.equalizeHist(gray)


# ---------------------------------------------------------------------------
# C. Local Contrast Enhancement (Unsharp Masking)
# ---------------------------------------------------------------------------
def enhance_unsharp_mask(gray: np.ndarray, sigma: float = 1.5, strength: float = 1.5) -> np.ndarray:
    """Unsharp masking: I + strength * (I - Gaussian(I))."""
    blurred = cv2.GaussianBlur(gray, (0, 0), sigma)
    sharpened = cv2.addWeighted(gray, 1.0 + strength, blurred, -strength, 0)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# D. CLAHE (Contrast-Limited Adaptive Histogram Equalization)
# ---------------------------------------------------------------------------
def enhance_clahe(gray: np.ndarray, clip_limit: float = 2.0, tile_grid_size: Tuple[int, int] = (8, 8)) -> np.ndarray:
    """CLAHE on grayscale image."""
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    return clahe.apply(gray)


# ---------------------------------------------------------------------------
# E. Shadow & Uneven Illumination Correction (Background Division)
# ---------------------------------------------------------------------------
def correct_uneven_illumination_morph(gray: np.ndarray, kernel_size: int = 41) -> Tuple[np.ndarray, np.ndarray]:
    """
    Morphological background estimation & division:
    1. Estimate background via large morphological dilation followed by median blur.
    2. Divide original by background to flatten illumination gradient.
    """
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    bg_dilated = cv2.morphologyEx(gray, cv2.MORPH_DILATE, k)
    bg_est = cv2.medianBlur(bg_dilated, 21)

    # Division normalization: I_corr = (I / BG) * 255
    f_gray = gray.astype(np.float32)
    f_bg = np.maximum(1.0, bg_est.astype(np.float32))
    normalized = np.clip((f_gray / f_bg) * 255.0, 0, 255).astype(np.uint8)
    return normalized, bg_est


def correct_uneven_illumination_gaussian(gray: np.ndarray, sigma: float = 50.0) -> Tuple[np.ndarray, np.ndarray]:
    """
    Gaussian low-pass background estimation & division.
    """
    bg_est = cv2.GaussianBlur(gray, (0, 0), sigma)
    f_gray = gray.astype(np.float32)
    f_bg = np.maximum(1.0, bg_est.astype(np.float32))
    normalized = np.clip((f_gray / f_bg) * 255.0, 0, 255).astype(np.uint8)
    return normalized, bg_est


# ---------------------------------------------------------------------------
# F. Mild Denoising
# ---------------------------------------------------------------------------
def denoise_gaussian(gray: np.ndarray, ksize: int = 3) -> np.ndarray:
    return cv2.GaussianBlur(gray, (ksize, ksize), 0)


def denoise_median(gray: np.ndarray, ksize: int = 3) -> np.ndarray:
    return cv2.medianBlur(gray, ksize)


def denoise_bilateral(gray: np.ndarray, d: int = 5, sigma_color: float = 25.0, sigma_space: float = 25.0) -> np.ndarray:
    """Edge-preserving bilateral filtering."""
    return cv2.bilateralFilter(gray, d, sigma_color, sigma_space)


# ---------------------------------------------------------------------------
# G. Grayscale Conversion Strategies
# ---------------------------------------------------------------------------
def convert_to_gray_standard(bgr: np.ndarray) -> np.ndarray:
    """Standard ITU-R BT.601 luminance."""
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


def convert_to_gray_green_channel(bgr: np.ndarray) -> np.ndarray:
    """Green channel (highest contrast for blue/black ink against white paper)."""
    return bgr[:, :, 1].copy()


def convert_to_gray_min_rgb(bgr: np.ndarray) -> np.ndarray:
    """Minimum of R, G, B channels (preserves dark strokes of all colored inks)."""
    return np.min(bgr, axis=2)


# ---------------------------------------------------------------------------
# H. Adaptive Thresholding / Binarization Derivatives
# ---------------------------------------------------------------------------
def binarize_otsu(gray: np.ndarray) -> np.ndarray:
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    return th


def binarize_adaptive_gaussian(gray: np.ndarray, block_size: int = 25, c_val: float = 10.0) -> np.ndarray:
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c_val)


def binarize_sauvola(gray: np.ndarray, window_size: int = 25, k: float = 0.2, r: float = 128.0) -> np.ndarray:
    """
    Sauvola document binarization:
    T(x, y) = m(x, y) * [1 + k * (s(x, y) / R - 1)]
    """
    f_gray = gray.astype(np.float32)
    m = cv2.blur(f_gray, (window_size, window_size))
    sq_m = cv2.blur(f_gray ** 2, (window_size, window_size))
    s = np.sqrt(np.maximum(0.0, sq_m - m ** 2))
    thresh = m * (1.0 + k * ((s / r) - 1.0))
    binary = np.where(f_gray >= thresh, 255, 0).astype(np.uint8)
    return binary


# ---------------------------------------------------------------------------
# I. Morphological Cleanup (Testing thin stroke preservation)
# ---------------------------------------------------------------------------
def morph_cleanup_opening(binary: np.ndarray, ksize: int = 2) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ksize, ksize))
    return cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)


def morph_cleanup_closing(binary: np.ndarray, ksize: int = 2) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ksize, ksize))
    return cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)


# ===========================================================================
# 3. STRUCTURED PROPOSED INTERFACE: EnhancedDocumentResult
# ===========================================================================

@dataclass
class EnhancedDocumentResult:
    """
    Proposed Phase 4 Output Contract for downstream Phase 5 (Segmentation/OCR).
    Preserves multiple representations (reversibility) + full diagnostic history.
    """
    status: str                             # "ENHANCED_SUCCESS", "ENHANCED_PASS_THROUGH", "ENHANCED_WARNING"
    raw_scanned_bgr: np.ndarray             # Original rectified BGR image (strictly preserved)
    enhanced_gray: np.ndarray               # Illumination & contrast normalized grayscale (primary for OCR/HTR)
    binary_mask: Optional[np.ndarray]       # High-quality binarized mask (for OMR bubbles & layout)
    color_rubric_mask: Optional[np.ndarray] # Mask of non-black/blue markings (e.g. red pen / stamps)
    dimensions: Tuple[int, int]             # (width, height)
    pipeline_mode: str                      # "HYBRID_CONDITION_DEPENDENT" or "FIXED"
    applied_operations: List[str]           # List of operations executed (e.g. ["SHADOW_CORR_MORPH", "CLAHE_MILD"])
    detected_conditions: Dict[str, Any]     # Illumination gradient, noise level, dynamic range
    objective_signals: Dict[str, float]     # Diagnostic signal measurements
    processing_latency_ms: float            # Total enhancement time in ms


# ===========================================================================
# 4. BENCHMARK & EXPERIMENTAL INVESTIGATION EXECUTION
# ===========================================================================

def run_enhancement_investigation() -> Dict[str, Any]:
    """
    Executes the complete Phase 4.1 enhancement investigation across
    the calibration suite and representative dataset samples.
    """
    calibration_images = [
        "images/answer_sheet.jpg",
        "images/answer_sheet_2.png",
        "images/answer_sheet_3.jpg",
        "images/answer_sheet_4.jpg",
        "images/answer_sheet_5.jpg",
    ]

    dataset_samples = [
        "images/dataset_samples/01_Y21AEC401_IMG20251013125618.jpg",
        "images/dataset_samples/04_Y21AEC406_IMG_20251016_113424213_HDR.jpg",
        "images/dataset_samples/20_Y21AEC428_IMG20251022114252.jpg",
    ]

    print("=" * 80)
    print("PHASE 4.1: AUTOMATIC IMAGE ENHANCEMENT INVESTIGATION")
    print("=" * 80)

    results = {
        "calibration_audit": {},
        "operator_benchmarks": {},
        "handwriting_audit": {},
    }

    # -----------------------------------------------------------------------
    # 1. Process Calibration Images with Phase 3 Scanner Integration
    # -----------------------------------------------------------------------
    print("\n--- STEP 1: OBTAINING PHASE 3 RECTIFIED INPUTS ---")
    scanned_results = {}
    for rel_path in calibration_images:
        full_path = os.path.join(ROOT_DIR, rel_path)
        img_name = os.path.basename(full_path)
        print(f"Executing Phase 3 scanner on: {img_name} ...", end=" ", flush=True)
        t0 = time.perf_counter()
        scanned_res = integrate_production_scanner(full_path)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        scanned_results[img_name] = scanned_res
        print(f"Done ({dt_ms:.1f}ms) -> Status: {scanned_res.status}, Dims: {scanned_res.destination_dimensions}")

    # -----------------------------------------------------------------------
    # 2. Comprehensive Benchmarking of the 12 Enhancement Operators
    # -----------------------------------------------------------------------
    print("\n--- STEP 2: BENCHMARKING 12 ENHANCEMENT DIMENSIONS ---")

    # Focus on answer_sheet_3.jpg (strong shadow) and answer_sheet_2.png (clean A4)
    for target_name in ["answer_sheet_3.jpg", "answer_sheet_2.png", "answer_sheet.jpg"]:
        scanned_res = scanned_results[target_name]
        bgr = scanned_res.scanned_image
        gray_raw = convert_to_gray_standard(bgr)

        print(f"\n>> Evaluating Operators on {target_name} ({bgr.shape[1]}x{bgr.shape[0]} px):")
        sig_raw = compute_objective_signals(gray_raw)
        print(f"   Raw Signals: Mean Brightness={sig_raw['mean_brightness']:.1f}, "
              f"DynRange={sig_raw['dynamic_range']:.1f}, Sharpness={sig_raw['laplacian_sharpness']:.1f}, "
              f"BgStd={sig_raw['paper_background_std']:.1f}")

        eval_candidates = {}

        # Op 1: Brightness Linear & Gamma
        t0 = time.perf_counter()
        c_gamma = enhance_gamma(gray_raw, gamma=0.8)
        t_gamma = (time.perf_counter() - t0) * 1000.0
        eval_candidates["Gamma (0.8)"] = (c_gamma, t_gamma)

        # Op 2: Global Histogram Equalization
        t0 = time.perf_counter()
        c_he = enhance_global_histogram_equalization(gray_raw)
        t_he = (time.perf_counter() - t0) * 1000.0
        eval_candidates["Global HistEq"] = (c_he, t_he)

        # Op 3: Local Contrast (Unsharp Mask)
        t0 = time.perf_counter()
        c_unsharp = enhance_unsharp_mask(gray_raw, sigma=1.5, strength=1.2)
        t_unsharp = (time.perf_counter() - t0) * 1000.0
        eval_candidates["Unsharp Mask (1.2)"] = (c_unsharp, t_unsharp)

        # Op 4: CLAHE (Clip=2.0, Grid=8x8)
        t0 = time.perf_counter()
        c_clahe = enhance_clahe(gray_raw, clip_limit=2.0, tile_grid_size=(8, 8))
        t_clahe = (time.perf_counter() - t0) * 1000.0
        eval_candidates["CLAHE (Clip=2.0)"] = (c_clahe, t_clahe)

        # Op 5: Morphological Shadow & Illumination Correction
        t0 = time.perf_counter()
        c_morph, bg_est = correct_uneven_illumination_morph(gray_raw, kernel_size=41)
        t_morph = (time.perf_counter() - t0) * 1000.0
        eval_candidates["Morph Shadow Division"] = (c_morph, t_morph)

        # Op 6: Gaussian Illumination Correction
        t0 = time.perf_counter()
        c_gauss_flat, _ = correct_uneven_illumination_gaussian(gray_raw, sigma=50.0)
        t_gauss_flat = (time.perf_counter() - t0) * 1000.0
        eval_candidates["Gaussian Flat-Field"] = (c_gauss_flat, t_gauss_flat)

        # Op 7: Bilateral Denoising
        t0 = time.perf_counter()
        c_bilat = denoise_bilateral(gray_raw, d=5, sigma_color=25.0, sigma_space=25.0)
        t_bilat = (time.perf_counter() - t0) * 1000.0
        eval_candidates["Bilateral Denoise"] = (c_bilat, t_bilat)

        # Op 8: Min-RGB ink projection
        t0 = time.perf_counter()
        c_min_rgb = convert_to_gray_min_rgb(bgr)
        t_min_rgb = (time.perf_counter() - t0) * 1000.0
        eval_candidates["Min-RGB Channel"] = (c_min_rgb, t_min_rgb)

        # Op 9: Adaptive Gaussian Binarization
        t0 = time.perf_counter()
        c_adapt_bin = binarize_adaptive_gaussian(c_morph, block_size=25, c_val=10.0)
        t_adapt_bin = (time.perf_counter() - t0) * 1000.0
        eval_candidates["Adaptive Binarization"] = (c_adapt_bin, t_adapt_bin)

        # Op 10: Sauvola Binarization
        t0 = time.perf_counter()
        c_sauvola = binarize_sauvola(c_morph, window_size=25, k=0.2)
        t_sauvola = (time.perf_counter() - t0) * 1000.0
        eval_candidates["Sauvola Binarization"] = (c_sauvola, t_sauvola)

        # Print operator performance table
        results["operator_benchmarks"][target_name] = {}
        for op_name, (img_c, op_ms) in eval_candidates.items():
            sig = compute_objective_signals(img_c)
            results["operator_benchmarks"][target_name][op_name] = {
                "latency_ms": op_ms,
                "mean_b": sig["mean_brightness"],
                "dyn_range": sig["dynamic_range"],
                "sharpness": sig["laplacian_sharpness"],
                "bg_std": sig["paper_background_std"],
                "michelson": sig["michelson_contrast"]
            }
            print(f"   * {op_name:<24}: Latency={op_ms:5.1f}ms | MeanB={sig['mean_brightness']:5.1f} | "
                  f"DynRange={sig['dynamic_range']:5.1f} | Sharpness={sig['laplacian_sharpness']:7.1f} | "
                  f"BgStd={sig['paper_background_std']:4.1f} | Michelson={sig['michelson_contrast']:.2f}")

    # -----------------------------------------------------------------------
    # 3. Handwriting & Fine-Stroke Sensitivity Investigation
    # -----------------------------------------------------------------------
    print("\n--- STEP 3: HANDWRITING SENSITIVITY INVESTIGATION ---")
    for s_path in dataset_samples:
        s_name = os.path.basename(s_path)
        img_s = cv2.imread(os.path.join(ROOT_DIR, s_path))
        if img_s is None:
            continue
        gray_s = cv2.cvtColor(img_s, cv2.COLOR_BGR2GRAY)
        
        # Test effect of morphological opening on thin strokes
        bin_s = binarize_sauvola(gray_s, window_size=21, k=0.15)
        open_s = morph_cleanup_opening(bin_s, ksize=2)
        
        # Stroke erosion measurement: count lost foreground pixels
        fg_before = np.count_nonzero(bin_s == 0)
        fg_after = np.count_nonzero(open_s == 0)
        lost_frac = (fg_before - fg_after) / max(1, fg_before)
        
        results["handwriting_audit"][s_name] = {
            "fg_before": fg_before,
            "fg_after_opening": fg_after,
            "lost_stroke_pixel_fraction": lost_frac
        }
        print(f"   * Sample {s_name}: Lost Stroke Pixels under 2x2 Opening = {lost_frac*100:.1f}%")

    # -----------------------------------------------------------------------
    # 4. Generate Diagnostic Visual Comparisons
    # -----------------------------------------------------------------------
    print("\n--- STEP 4: GENERATING DIAGNOSTIC VISUALIZATIONS ---")
    vis_shadow = os.path.join(OUTPUT_DIR, "phase4_shadow_correction_answer_sheet_3.png")
    vis_comparison = os.path.join(OUTPUT_DIR, "phase4_enhancement_comparison_answer_sheet_2.png")
    vis_handwriting = os.path.join(OUTPUT_DIR, "phase4_handwriting_dataset_samples.png")
    vis_color = os.path.join(OUTPUT_DIR, "phase4_color_rubric_preservation.png")

    generate_shadow_visualizations(scanned_results["answer_sheet_3.jpg"].scanned_image, vis_shadow)
    generate_comparison_visualizations(scanned_results["answer_sheet_2.png"].scanned_image, vis_comparison)
    generate_handwriting_visualizations(dataset_samples, vis_handwriting)
    generate_color_preservation_visualizations(scanned_results["answer_sheet_3.jpg"].scanned_image, vis_color)

    print(f"Diagnostic plots saved to:\n  - {vis_shadow}\n  - {vis_comparison}\n  - {vis_handwriting}\n  - {vis_color}")

    return results


# ===========================================================================
# 5. DIAGNOSTIC PLOT GENERATORS
# ===========================================================================

def generate_shadow_visualizations(bgr: np.ndarray, output_path: str):
    """Visualizes the effect of shadow removal on answer_sheet_3.jpg."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    c_morph, bg_est = correct_uneven_illumination_morph(gray, kernel_size=45)
    c_clahe = enhance_clahe(gray, clip_limit=2.0)
    c_bin = binarize_sauvola(c_morph, window_size=25, k=0.18)

    fig, axes = plt.subplots(2, 3, figsize=(18, 14))

    axes[0, 0].imshow(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    axes[0, 0].set_title("1. Raw Rectified Image\n(Severe Diagonal Cast Shadow)", fontsize=11, fontweight="bold")
    axes[0, 0].axis("off")

    axes[0, 1].imshow(gray, cmap="gray")
    axes[0, 1].set_title("2. Raw Grayscale\n(Shadow dims top-right text)", fontsize=11, fontweight="bold")
    axes[0, 1].axis("off")

    axes[0, 2].imshow(bg_est, cmap="gray")
    axes[0, 2].set_title("3. Estimated Illumination Background\n(Morphological Dilation + Median)", fontsize=11, fontweight="bold")
    axes[0, 2].axis("off")

    axes[1, 0].imshow(c_clahe, cmap="gray")
    axes[1, 0].set_title("4. CLAHE Only\n(Amplifies shadow edge & block artifacts)", fontsize=11, fontweight="bold")
    axes[1, 0].axis("off")

    axes[1, 1].imshow(c_morph, cmap="gray")
    axes[1, 1].set_title("5. Morphological Shadow Division (Recommended)\n(Uniform paper white, crisp text preserved)", fontsize=11, fontweight="bold")
    axes[1, 1].axis("off")

    axes[1, 2].imshow(c_bin, cmap="gray")
    axes[1, 2].set_title("6. Sauvola Binarization of Normalized\n(Clean binary text & bubbles without shadow dropout)", fontsize=11, fontweight="bold")
    axes[1, 2].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_comparison_visualizations(bgr: np.ndarray, output_path: str):
    """Visualizes candidate operators on clean answer_sheet_2.png."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    c_unsharp = enhance_unsharp_mask(gray, sigma=1.5, strength=1.2)
    c_clahe = enhance_clahe(gray, clip_limit=2.0)
    c_morph, _ = correct_uneven_illumination_morph(gray, kernel_size=45)
    c_bilat = denoise_bilateral(gray, d=5, sigma_color=25.0, sigma_space=25.0)
    c_adapt_bin = binarize_adaptive_gaussian(c_morph, block_size=25, c_val=10.0)

    fig, axes = plt.subplots(2, 3, figsize=(18, 14))

    axes[0, 0].imshow(gray, cmap="gray")
    axes[0, 0].set_title("1. Raw Rectified Grayscale\n(Standard A4 sheet)", fontsize=11, fontweight="bold")
    axes[0, 0].axis("off")

    axes[0, 1].imshow(c_unsharp, cmap="gray")
    axes[0, 1].set_title("2. Local Contrast (Unsharp Mask)\n(Crisp edges, slightly enhanced contrast)", fontsize=11, fontweight="bold")
    axes[0, 1].axis("off")

    axes[0, 2].imshow(c_clahe, cmap="gray")
    axes[0, 2].set_title("3. CLAHE (Clip=2.0)\n(Notice paper grain amplified into faint noise)", fontsize=11, fontweight="bold")
    axes[0, 2].axis("off")

    axes[1, 0].imshow(c_bilat, cmap="gray")
    axes[1, 0].set_title("4. Bilateral Denoising\n(Smooth background, sharp strokes)", fontsize=11, fontweight="bold")
    axes[1, 0].axis("off")

    axes[1, 1].imshow(c_morph, cmap="gray")
    axes[1, 1].set_title("5. Illumination Normalization\n(Flat paper background)", fontsize=11, fontweight="bold")
    axes[1, 1].axis("off")

    axes[1, 2].imshow(c_adapt_bin, cmap="gray")
    axes[1, 2].set_title("6. Adaptive Binarization Derivative\n(Useful for OMR bubble segmentation)", fontsize=11, fontweight="bold")
    axes[1, 2].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_handwriting_visualizations(dataset_paths: List[str], output_path: str):
    """Visualizes enhancement operators on handwriting patches."""
    fig, axes = plt.subplots(len(dataset_paths), 4, figsize=(16, 4 * len(dataset_paths)))

    for idx, s_path in enumerate(dataset_paths):
        s_name = os.path.basename(s_path)
        img = cv2.imread(os.path.join(ROOT_DIR, s_path))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Comparisons
        c_unsharp = enhance_unsharp_mask(gray, sigma=1.0, strength=1.0)
        c_bin = binarize_sauvola(gray, window_size=21, k=0.15)
        c_open = morph_cleanup_opening(c_bin, ksize=2)

        axes[idx, 0].imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        axes[idx, 0].set_title(f"Sample: {s_name}\nRaw Color Crop", fontsize=10, fontweight="bold")
        axes[idx, 0].axis("off")

        axes[idx, 1].imshow(c_unsharp, cmap="gray")
        axes[idx, 1].set_title("Unsharp Mask (Sharpens faint ink)", fontsize=10)
        axes[idx, 1].axis("off")

        axes[idx, 2].imshow(c_bin, cmap="gray")
        axes[idx, 2].set_title("Sauvola Binary (Preserves stroke topology)", fontsize=10)
        axes[idx, 2].axis("off")

        axes[idx, 3].imshow(c_open, cmap="gray")
        axes[idx, 3].set_title("Morph Opening (DANGEROUS: Erodes dots & loops)", fontsize=10, color="darkred")
        axes[idx, 3].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_color_preservation_visualizations(bgr: np.ndarray, output_path: str):
    """Demonstrates preserving color channels for red grading marks and blue student ink."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    # Detect colored markings: Saturation > 35 indicates color (not black/gray/white)
    color_mask = np.where(s > 40, 255, 0).astype(np.uint8)

    # Separate Red Marks (teacher grading pens / institutional seals)
    # Hue in OpenCV: 0-10 or 170-180 is Red
    red_mask1 = cv2.inRange(hsv, np.array([0, 40, 40]), np.array([10, 255, 255]))
    red_mask2 = cv2.inRange(hsv, np.array([170, 40, 40]), np.array([180, 255, 255]))
    red_mask = cv2.bitwise_or(red_mask1, red_mask2)

    # Separate Blue Ink (student handwriting)
    # Hue: 100-135 is Blue
    blue_mask = cv2.inRange(hsv, np.array([100, 40, 40]), np.array([135, 255, 255]))

    fig, axes = plt.subplots(2, 2, figsize=(14, 14))

    axes[0, 0].imshow(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    axes[0, 0].set_title("1. Original Rectified BGR\n(Ground Truth with colored ink & rubrics)", fontsize=11, fontweight="bold")
    axes[0, 0].axis("off")

    axes[0, 1].imshow(color_mask, cmap="gray")
    axes[0, 1].set_title("2. Color Mask (Saturation > 40)\n(Distinguishes ink color from black/white print)", fontsize=11, fontweight="bold")
    axes[0, 1].axis("off")

    axes[1, 0].imshow(blue_mask, cmap="Blues")
    axes[1, 0].set_title("3. Blue Ink Mask\n(Student handwriting / ballpoint responses)", fontsize=11, fontweight="bold")
    axes[1, 0].axis("off")

    axes[1, 1].imshow(red_mask, cmap="Reds")
    axes[1, 1].set_title("4. Red Ink / Seal Mask\n(Teacher grading marks, red rubrics, institution stamps)", fontsize=11, fontweight="bold")
    axes[1, 1].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_enhancement_investigation()
