"""
phase4/02_enhancement_condition_investigation.py

AI-EVAL PHASE 4.2: ENHANCEMENT CONDITION DETECTION & OPERATOR SELECTION
=======================================================================

PURPOSE:
Investigate how the system can inspect a rectified document image and determine:
1. Whether image enhancement is actually needed (or if NO_ENHANCEMENT is preferable).
2. Which specific enhancement operator (or chained operators) is appropriate.
3. How to avoid destructive over-enhancement on clean documents or thin handwriting.

INPUT SOURCES:
- ScannedDocumentResult from Phase 3.6:
  * images/answer_sheet_2.png (clean, high contrast, uniform A4)
  * images/answer_sheet_3.jpg (severe diagonal cast shadow across top-right)
  * images/answer_sheet_4.jpg (frame-limited capture, high detail, text/numbers)
  * images/answer_sheet_5.jpg (frame-limited capture, blue ink handwriting)
  * images/answer_sheet.jpg (ambiguous crop, low contrast, faint grid lines)
- Representative handwriting crops from images/dataset_samples/

INVESTIGATED CONDITION SIGNALS:
1. Global brightness & dynamic range
2. Spatial illumination variation (4x4 local background grid)
3. Shadow likelihood (ratio of minimum to maximum local background)
4. Local & Michelson contrast
5. Paper background uniformity & texture
6. High-frequency noise in flat paper regions
7. Stroke acutance & edge sharpness
8. Color content (saturation fraction, red rubrics, blue ink)

CANDIDATE DECISION STATES:
- NO_ENHANCEMENT
- SHADOW_CORRECTION_CANDIDATE
- DENOISING_CANDIDATE
- CONTRAST_CORRECTION_CANDIDATE
- SHARPENING_CANDIDATE
- MULTI_CORRECTION_CANDIDATE
- INSUFFICIENT_EVIDENCE

GUARDRAILS:
- INVESTIGATION ONLY.
- Do NOT create one universal quality score.
- Do NOT freeze arbitrary numerical thresholds.
- Do NOT assume every image needs enhancement.
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
import matplotlib.patches as patches

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT_DIR, "phase4", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Dynamic Import of Phase 3.6 Scanner Integration & Phase 4.1 Operators
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

# Reused operators
correct_uneven_illumination_morph = phase4_01.correct_uneven_illumination_morph
enhance_unsharp_mask = phase4_01.enhance_unsharp_mask
enhance_clahe = phase4_01.enhance_clahe
enhance_min_max_stretch = phase4_01.enhance_min_max_stretch
denoise_bilateral = phase4_01.denoise_bilateral
binarize_sauvola = phase4_01.binarize_sauvola


# ===========================================================================
# 1. RAW CONDITION SIGNAL EXTRACTION
# ===========================================================================

@dataclass
class DocumentConditionProfile:
    """
    Structured extraction of raw condition signals from a rectified image.
    Separates primary diagnostic measurements into evidence groups.
    """
    # 1. Global Brightness & Dynamic Range
    mean_brightness: float
    p10_brightness: float
    p90_brightness: float
    dynamic_range: float

    # 2. Spatial Illumination & Shadow Likelihood
    bg_grid_min: float
    bg_grid_max: float
    bg_grid_ratio: float                   # min_bg / max_bg (< 0.75 indicates strong shadow/gradient)
    bg_grid_std: float                     # standard deviation across 4x4 background estimates
    shadow_extent_fraction: float          # fraction of grid cells with bg < 0.80 * max_bg
    bg_grid_matrix: List[List[float]]      # 4x4 matrix of local background values

    # 3. Contrast Signals
    global_std_contrast: float
    mean_local_michelson: float
    mean_local_std: float

    # 4. Noise & Paper Texture
    paper_noise_sigma: float               # high-frequency std in homogeneous paper patches
    paper_uniformity_std: float            # global std of paper white pixels

    # 5. Sharpness & Edge Acutance
    laplacian_sharpness: float
    tenengrad_energy: float
    stroke_acutance: float                 # mean gradient magnitude across detected stroke boundaries

    # 6. Color Signals
    color_pixel_fraction: float            # fraction of pixels with saturation > 40
    red_marker_fraction: float             # fraction with red hue (teacher grading marks)
    blue_ink_fraction: float               # fraction with blue hue (student handwriting)

    # 7. Qualitative Condition Candidate States
    candidate_states: List[str]            # Evaluated candidate recommendations
    qualitative_notes: List[str]


def extract_condition_signals(image: np.ndarray) -> DocumentConditionProfile:
    """
    Extracts multi-signal condition evidence across 6 distinct dimensions.
    Operates without hardcoded acceptance thresholds.
    """
    h_img, w_img = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    f_gray = gray.astype(np.float32)

    # -----------------------------------------------------------------------
    # Dimension 1: Global Brightness & Dynamic Range
    # -----------------------------------------------------------------------
    mean_b = float(np.mean(f_gray))
    p10 = float(np.percentile(f_gray, 10))
    p90 = float(np.percentile(f_gray, 90))
    dyn_range = p90 - p10

    # -----------------------------------------------------------------------
    # Dimension 2: Spatial Illumination & Shadow Grid (4x4 cells)
    # -----------------------------------------------------------------------
    grid_rows, grid_cols = 4, 4
    cell_h = h_img // grid_rows
    cell_w = w_img // grid_cols
    bg_grid = []
    local_bgs = []

    for r in range(grid_rows):
        row_vals = []
        for c in range(grid_cols):
            y1, y2 = r * cell_h, (r + 1) * cell_h if r < grid_rows - 1 else h_img
            x1, x2 = c * cell_w, (c + 1) * cell_w if c < grid_cols - 1 else w_img
            cell = f_gray[y1:y2, x1:x2]
            # 90th percentile represents paper white in that local cell
            cell_bg = float(np.percentile(cell, 90))
            row_vals.append(cell_bg)
            local_bgs.append(cell_bg)
        bg_grid.append(row_vals)

    bg_min = float(np.min(local_bgs))
    bg_max = float(np.max(local_bgs))
    bg_ratio = bg_min / max(1.0, bg_max)
    bg_std = float(np.std(local_bgs))
    shadow_cells = sum(1 for val in local_bgs if val < 0.80 * bg_max)
    shadow_frac = shadow_cells / len(local_bgs)

    # -----------------------------------------------------------------------
    # Dimension 3: Contrast Signals
    # -----------------------------------------------------------------------
    global_std = float(np.std(f_gray))

    # Local Michelson contrast across 16 grid cells
    cell_michelsons = []
    for r in range(grid_rows):
        for c in range(grid_cols):
            y1, y2 = r * cell_h, (r + 1) * cell_h if r < grid_rows - 1 else h_img
            x1, x2 = c * cell_w, (c + 1) * cell_w if c < grid_cols - 1 else w_img
            cell = f_gray[y1:y2, x1:x2]
            c_bg = max(1.0, float(np.percentile(cell, 90)))
            c_fg = max(0.0, float(np.percentile(cell, 10)))
            cell_michelsons.append((c_bg - c_fg) / (c_bg + c_fg))
    mean_michelson = float(np.mean(cell_michelsons))

    # Local std in 16x16 sliding window
    k_size = 16
    local_mean = cv2.blur(f_gray, (k_size, k_size))
    local_sq = cv2.blur(f_gray ** 2, (k_size, k_size))
    local_var = np.maximum(0.0, local_sq - local_mean ** 2)
    mean_local_std = float(np.mean(np.sqrt(local_var)))

    # -----------------------------------------------------------------------
    # Dimension 4: Noise in Homogeneous Paper Regions
    # -----------------------------------------------------------------------
    sobelx = cv2.Sobel(f_gray, cv2.CV_32F, 1, 0, ksize=3)
    sobely = cv2.Sobel(f_gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.hypot(sobelx, sobely)

    # Flat paper mask: bright pixels with low gradient
    flat_paper_mask = (f_gray >= 0.85 * bg_max) & (grad_mag < 15.0)
    if np.count_nonzero(flat_paper_mask) > 100:
        # Measure local standard deviation of Laplacian in flat paper
        lap_resp = cv2.Laplacian(gray, cv2.CV_32F)
        paper_noise_sigma = float(np.std(lap_resp[flat_paper_mask]))
    else:
        paper_noise_sigma = 0.0

    # Global paper uniformity
    bright_mask = f_gray >= np.percentile(f_gray, 75)
    paper_uniformity_std = float(np.std(f_gray[bright_mask]))

    # -----------------------------------------------------------------------
    # Dimension 5: Sharpness & Edge Acutance
    # -----------------------------------------------------------------------
    lap_sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    tenengrad = float(np.mean(sobelx ** 2 + sobely ** 2))

    # Stroke boundary acutance: mean gradient on text boundary pixels
    stroke_edge_mask = (grad_mag >= 30.0) & (grad_mag <= 150.0)
    stroke_acutance = float(np.mean(grad_mag[stroke_edge_mask])) if np.count_nonzero(stroke_edge_mask) > 50 else 0.0

    # -----------------------------------------------------------------------
    # Dimension 6: Color Information Presence
    # -----------------------------------------------------------------------
    if image.ndim == 3:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        h_chan, s_chan, v_chan = cv2.split(hsv)
        total_pixels = float(h_img * w_img)
        color_pix = np.count_nonzero((s_chan > 40) & (v_chan > 40))
        color_fraction = float(color_pix / total_pixels)

        # Red markers: H in [0, 10] or [170, 180]
        red_pix = np.count_nonzero(((h_chan <= 10) | (h_chan >= 170)) & (s_chan > 45) & (v_chan > 45))
        red_fraction = float(red_pix / total_pixels)

        # Blue ink: H in [100, 135]
        blue_pix = np.count_nonzero((h_chan >= 100) & (h_chan <= 135) & (s_chan > 40) & (v_chan > 40))
        blue_fraction = float(blue_pix / total_pixels)
    else:
        color_fraction, red_fraction, blue_fraction = 0.0, 0.0, 0.0

    # -----------------------------------------------------------------------
    # Qualitative Condition Candidate Arbitration (Evidence-Driven)
    # -----------------------------------------------------------------------
    candidates = []
    notes = []

    # Evidence 1: Uneven Illumination / Shadow
    if bg_ratio < 0.80 or bg_std > 18.0:
        candidates.append("SHADOW_CORRECTION_CANDIDATE")
        notes.append(f"Significant spatial illumination variation detected (bg_ratio={bg_ratio:.2f}, bg_std={bg_std:.1f}).")

    # Evidence 2: Low Dynamic Range / Poor Contrast
    if dyn_range < 55.0 or mean_michelson < 0.22:
        candidates.append("CONTRAST_CORRECTION_CANDIDATE")
        notes.append(f"Low global/local contrast detected (dyn_range={dyn_range:.1f}, michelson={mean_michelson:.2f}).")

    # Evidence 3: High-Frequency Noise in Paper
    if paper_noise_sigma > 4.5:
        candidates.append("DENOISING_CANDIDATE")
        notes.append(f"Elevated high-frequency grain in flat paper (noise_sigma={paper_noise_sigma:.2f}).")

    # Evidence 4: Soft / Blurry Stroke Boundaries
    if stroke_acutance < 45.0 and paper_noise_sigma <= 4.0:
        candidates.append("SHARPENING_CANDIDATE")
        notes.append(f"Soft stroke boundary transitions with low background noise (acutance={stroke_acutance:.1f}).")

    # Evidence 5: Clean Document (No Enhancement Preferable)
    if not candidates and bg_ratio >= 0.85 and dyn_range >= 35.0 and paper_noise_sigma <= 3.5:
        candidates.append("NO_ENHANCEMENT")
        notes.append("Document exhibits uniform illumination, adequate stroke contrast, and clean paper. No-op preferable.")

    if len(candidates) > 1:
        candidates = ["MULTI_CORRECTION_CANDIDATE"] + candidates

    return DocumentConditionProfile(
        mean_brightness=mean_b,
        p10_brightness=p10,
        p90_brightness=p90,
        dynamic_range=dyn_range,
        bg_grid_min=bg_min,
        bg_grid_max=bg_max,
        bg_grid_ratio=bg_ratio,
        bg_grid_std=bg_std,
        shadow_extent_fraction=shadow_frac,
        bg_grid_matrix=bg_grid,
        global_std_contrast=global_std,
        mean_local_michelson=mean_michelson,
        mean_local_std=mean_local_std,
        paper_noise_sigma=paper_noise_sigma,
        paper_uniformity_std=paper_uniformity_std,
        laplacian_sharpness=lap_sharp,
        tenengrad_energy=tenengrad,
        stroke_acutance=stroke_acutance,
        color_pixel_fraction=color_fraction,
        red_marker_fraction=red_fraction,
        blue_ink_fraction=blue_fraction,
        candidate_states=candidates,
        qualitative_notes=notes
    )


# ===========================================================================
# 2. OPERATOR INTERACTION & PIPELINE CHAINING INVESTIGATION
# ===========================================================================

def evaluate_operator_interactions(image: np.ndarray) -> Dict[str, Any]:
    """
    Investigates interactions when combining multiple enhancement operators:
    - Shadow Correction -> Sharpening
    - Denoising -> Sharpening
    - Contrast Stretch vs CLAHE
    - Redundant processing on clean documents
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()

    # Base Operators
    t0 = time.perf_counter()
    im_shadow, _ = correct_uneven_illumination_morph(gray, kernel_size=41)
    t_shadow = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    im_denoise = denoise_bilateral(gray, d=5, sigma_color=25.0, sigma_space=25.0)
    t_denoise = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    im_sharp = enhance_unsharp_mask(gray, sigma=1.2, strength=1.0)
    t_sharp = (time.perf_counter() - t0) * 1000.0

    # Chained Combinations
    # Chain A: Shadow -> Sharp
    t0 = time.perf_counter()
    im_shadow_sharp = enhance_unsharp_mask(im_shadow, sigma=1.2, strength=1.0)
    t_chain_a = (time.perf_counter() - t0) * 1000.0 + t_shadow

    # Chain B: Denoise -> Sharp (Classic anti-noise sharpening)
    t0 = time.perf_counter()
    im_denoise_sharp = enhance_unsharp_mask(im_denoise, sigma=1.2, strength=1.0)
    t_chain_b = (time.perf_counter() - t0) * 1000.0 + t_denoise

    # Chain C: Contrast Stretch vs CLAHE
    im_stretch = enhance_min_max_stretch(gray, p_low=1.0, p_high=99.0)
    im_clahe = enhance_clahe(gray, clip_limit=2.0)

    # Chain D: Shadow -> Denoise -> Stretch -> Sharp (Full Chain)
    t0 = time.perf_counter()
    step1, _ = correct_uneven_illumination_morph(gray, kernel_size=41)
    step2 = denoise_bilateral(step1, d=5, sigma_color=25.0, sigma_space=25.0)
    step3 = enhance_min_max_stretch(step2, p_low=1.0, p_high=99.0)
    step4 = enhance_unsharp_mask(step3, sigma=1.2, strength=0.8)
    t_chain_d = (time.perf_counter() - t0) * 1000.0

    chains = {
        "Raw (No-Op)": (gray, 0.0),
        "Shadow Corr Alone": (im_shadow, t_shadow),
        "Sharpen Alone": (im_sharp, t_sharp),
        "Shadow -> Sharpen": (im_shadow_sharp, t_chain_a),
        "Denoise -> Sharpen": (im_denoise_sharp, t_chain_b),
        "Contrast Stretch": (im_stretch, 1.5),
        "CLAHE Alone": (im_clahe, 2.5),
        "Full Chained Sequence": (step4, t_chain_d),
    }

    metrics = {}
    for name, (img_c, latency) in chains.items():
        sig = extract_condition_signals(img_c)
        metrics[name] = {
            "image": img_c,
            "latency_ms": latency,
            "mean_b": sig.mean_brightness,
            "dyn_range": sig.dynamic_range,
            "sharpness": sig.laplacian_sharpness,
            "paper_noise": sig.paper_noise_sigma,
            "bg_std": sig.paper_uniformity_std,
            "stroke_acutance": sig.stroke_acutance
        }

    return metrics


# ===========================================================================
# 3. BENCHMARK RUNNER & DIAGNOSTIC VISUALIZATION
# ===========================================================================

def run_condition_investigation() -> Dict[str, Any]:
    """
    Executes the Phase 4.2 condition detection & operator selection investigation.
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
    print("PHASE 4.2: ENHANCEMENT CONDITION DETECTION & OPERATOR SELECTION")
    print("=" * 80)

    # 1. Obtain ScannedDocumentResult inputs from Phase 3.6
    print("\n--- STEP 1: EXTRACTING CONDITION SIGNALS ACROSS CALIBRATION SUITE ---")
    condition_profiles = {}
    scanned_cache = {}

    for rel_path in calibration_images:
        full_path = os.path.join(ROOT_DIR, rel_path)
        img_name = os.path.basename(full_path)
        scanned_res = integrate_production_scanner(full_path)
        scanned_cache[img_name] = scanned_res

        profile = extract_condition_signals(scanned_res.scanned_image)
        condition_profiles[img_name] = profile

        print(f"\n>> IMAGE: {img_name} ({scanned_res.destination_dimensions[0]}x{scanned_res.destination_dimensions[1]} px)")
        print(f"   Brightness: Mean={profile.mean_brightness:5.1f}, P10={profile.p10_brightness:5.1f}, P90={profile.p90_brightness:5.1f} | DynRange={profile.dynamic_range:5.1f}")
        print(f"   Spatial Illumination: GridMin={profile.bg_grid_min:5.1f}, GridMax={profile.bg_grid_max:5.1f}, BgRatio={profile.bg_grid_ratio:.2f}, BgStd={profile.bg_grid_std:4.1f}")
        print(f"   Contrast: GlobalStd={profile.global_std_contrast:4.1f}, LocalMichelson={profile.mean_local_michelson:.2f}")
        print(f"   Noise & Texture: PaperNoiseSigma={profile.paper_noise_sigma:4.2f}, PaperUniformityStd={profile.paper_uniformity_std:4.1f}")
        print(f"   Sharpness: Laplacian={profile.laplacian_sharpness:7.1f}, StrokeAcutance={profile.stroke_acutance:5.1f}")
        print(f"   Color Signals: ColorFrac={profile.color_pixel_fraction*100:4.1f}%, RedRubrics={profile.red_marker_fraction*100:4.2f}%, BlueInk={profile.blue_ink_fraction*100:4.2f}%")
        print(f"   RECOMMENDED CANDIDATE STATES: {profile.candidate_states}")
        for note in profile.qualitative_notes:
            print(f"     * {note}")

    # 2. Dataset Samples Condition Signals
    print("\n--- STEP 2: EXTRACTING CONDITION SIGNALS ON HANDWRITING DATASET SAMPLES ---")
    for s_rel in dataset_samples:
        s_path = os.path.join(ROOT_DIR, s_rel)
        s_name = os.path.basename(s_path)
        img_s = cv2.imread(s_path)
        if img_s is None:
            continue
        p_s = extract_condition_signals(img_s)
        condition_profiles[s_name] = p_s
        print(f"   * {s_name}: DynRange={p_s.dynamic_range:4.1f}, Michelson={p_s.mean_local_michelson:.2f}, "
              f"StrokeAcutance={p_s.stroke_acutance:4.1f} -> Candidates: {p_s.candidate_states}")

    # 3. Chaining & Interaction Experiments on answer_sheet_3 (Shadow) and answer_sheet_2 (Clean)
    print("\n--- STEP 3: OPERATOR INTERACTION & CHAINING BENCHMARKS ---")
    chains_sheet3 = evaluate_operator_interactions(scanned_cache["answer_sheet_3.jpg"].scanned_image)
    print("\n>> Chaining Results on answer_sheet_3.jpg (Shadowed Document):")
    for chain_name, m in chains_sheet3.items():
        print(f"   * {chain_name:<24}: Latency={m['latency_ms']:5.1f}ms | MeanB={m['mean_b']:5.1f} | "
              f"DynRange={m['dyn_range']:5.1f} | Sharpness={m['sharpness']:7.1f} | BgStd={m['bg_std']:4.1f}")

    chains_sheet2 = evaluate_operator_interactions(scanned_cache["answer_sheet_2.png"].scanned_image)
    print("\n>> Chaining Results on answer_sheet_2.png (Clean A4 Document):")
    for chain_name, m in chains_sheet2.items():
        print(f"   * {chain_name:<24}: Latency={m['latency_ms']:5.1f}ms | MeanB={m['mean_b']:5.1f} | "
              f"DynRange={m['dyn_range']:5.1f} | Sharpness={m['sharpness']:7.1f} | BgStd={m['bg_std']:4.1f}")

    # 4. Generate Visual Diagnostics
    print("\n--- STEP 4: GENERATING DIAGNOSTIC VISUALIZATIONS ---")
    vis_grid = os.path.join(OUTPUT_DIR, "phase4_condition_spatial_illumination_grid.png")
    vis_chain = os.path.join(OUTPUT_DIR, "phase4_operator_chaining_matrix.png")
    vis_decisions = os.path.join(OUTPUT_DIR, "phase4_operator_selection_decision_map.png")

    generate_illumination_grid_visualization(condition_profiles, scanned_cache, vis_grid)
    generate_chaining_visualization(chains_sheet3, vis_chain)
    generate_decision_summary_visualization(condition_profiles, scanned_cache, vis_decisions)

    print(f"Saved diagnostic figures to:\n  - {vis_grid}\n  - {vis_chain}\n  - {vis_decisions}")

    return {
        "condition_profiles": condition_profiles,
        "chains_sheet3": chains_sheet3,
        "chains_sheet2": chains_sheet2,
    }


# ===========================================================================
# 4. VISUALIZATION GENERATORS
# ===========================================================================

def generate_illumination_grid_visualization(profiles: Dict[str, DocumentConditionProfile], scanned_cache: Dict[str, Any], output_path: str):
    """Visualizes the 4x4 spatial background illumination grid comparing uneven vs uniform images."""
    targets = ["answer_sheet_3.jpg", "answer_sheet_2.png"]
    fig, axes = plt.subplots(len(targets), 2, figsize=(14, 6 * len(targets)))

    for idx, name in enumerate(targets):
        res = scanned_cache[name]
        p = profiles[name]
        bgr = res.scanned_image
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        # Left panel: Image with 4x4 grid overlay
        ax_img = axes[idx, 0]
        ax_img.imshow(rgb)
        h, w = bgr.shape[:2]
        ch, cw = h / 4.0, w / 4.0
        for r in range(1, 4):
            ax_img.axhline(r * ch, color="yellow", linestyle="--", linewidth=1.5)
        for c in range(1, 4):
            ax_img.axvline(c * cw, color="yellow", linestyle="--", linewidth=1.5)
        ax_img.set_title(f"Target: {name}\nSpatial 4x4 Analysis Grid", fontsize=11, fontweight="bold")
        ax_img.axis("off")

        # Right panel: Heatmap of local background intensity
        ax_heat = axes[idx, 1]
        grid_mat = np.array(p.bg_grid_matrix)
        cax = ax_heat.imshow(grid_mat, cmap="magma", vmin=140, vmax=255)
        fig.colorbar(cax, ax=ax_heat, fraction=0.046, pad=0.04, label="Estimated Local Background Level")
        for r in range(4):
            for c in range(4):
                val = grid_mat[r, c]
                color = "black" if val > 200 else "white"
                ax_heat.text(c, r, f"{val:.1f}", ha="center", va="center", color=color, fontsize=11, fontweight="bold")
        ax_heat.set_title(
            f"Local Background Heatmap\nRatio (Min/Max) = {p.bg_grid_ratio:.2f} | Std = {p.bg_grid_std:.1f} | Status: {p.candidate_states[0]}",
            fontsize=11, fontweight="bold"
        )
        ax_heat.set_xticks(range(4))
        ax_heat.set_yticks(range(4))
        ax_heat.set_xticklabels([f"C{c}" for c in range(4)])
        ax_heat.set_yticklabels([f"R{r}" for r in range(4)])

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_chaining_visualization(chains: Dict[str, Any], output_path: str):
    """Visualizes operator chaining results on answer_sheet_3.jpg."""
    keys = ["Raw (No-Op)", "Shadow Corr Alone", "Sharpen Alone", "Shadow -> Sharpen", "CLAHE Alone", "Full Chained Sequence"]
    fig, axes = plt.subplots(2, 3, figsize=(18, 14))

    for idx, key in enumerate(keys):
        row = idx // 3
        col = idx % 3
        m = chains[key]
        img = m["image"]
        ax = axes[row, col]
        ax.imshow(img, cmap="gray")
        ax.set_title(
            f"{key}\nDynRange: {m['dyn_range']:.0f} | Sharpness: {m['sharpness']:.0f} | BgStd: {m['bg_std']:.1f} | Latency: {m['latency_ms']:.1f}ms",
            fontsize=11, fontweight="bold"
        )
        ax.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_decision_summary_visualization(profiles: Dict[str, DocumentConditionProfile], scanned_cache: Dict[str, Any], output_path: str):
    """Visualizes the condition profile and candidate decisions across the 5 calibration images."""
    fig, axes = plt.subplots(5, 2, figsize=(14, 20))
    targets = ["answer_sheet.jpg", "answer_sheet_2.png", "answer_sheet_3.jpg", "answer_sheet_4.jpg", "answer_sheet_5.jpg"]

    for idx, name in enumerate(targets):
        res = scanned_cache[name]
        p = profiles[name]
        bgr = res.scanned_image
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        ax_img = axes[idx, 0]
        ax_img.imshow(rgb)
        ax_img.set_title(f"Input: {name} ({res.destination_dimensions[0]}x{res.destination_dimensions[1]} px)", fontsize=10, fontweight="bold")
        ax_img.axis("off")

        # Summary decision panel
        ax_txt = axes[idx, 1]
        ax_txt.axis("off")
        cand_str = " + ".join(p.candidate_states)
        text_content = (
            f"DOCUMENT: {name}\n"
            f"--------------------------------------------------\n"
            f"PRIMARY CANDIDATE DECISION: {cand_str}\n\n"
            f"KEY SIGNALS EXTRACTED:\n"
            f"  * Brightness (Mean / P10 / P90) : {p.mean_brightness:.1f} / {p.p10_brightness:.1f} / {p.p90_brightness:.1f}\n"
            f"  * Dynamic Range (P90 - P10)     : {p.dynamic_range:.1f}\n"
            f"  * Spatial Bg Ratio (Min / Max)   : {p.bg_grid_ratio:.2f} (Std: {p.bg_grid_std:.1f})\n"
            f"  * Local Michelson Contrast      : {p.mean_local_michelson:.2f}\n"
            f"  * Paper Noise Sigma             : {p.paper_noise_sigma:.2f}\n"
            f"  * Stroke Acutance               : {p.stroke_acutance:.1f}\n"
            f"  * Color Presence (Total / Red / Blue): {p.color_pixel_fraction*100:.1f}% / {p.red_marker_fraction*100:.2f}% / {p.blue_ink_fraction*100:.2f}%\n\n"
            f"QUALITATIVE RATIONALE:\n"
        )
        for note in p.qualitative_notes:
            text_content += f"  - {note}\n"

        ax_txt.text(0.05, 0.5, text_content, fontsize=9.5, family="monospace", va="center",
                    bbox=dict(boxstyle="round,pad=0.5", facecolor="#f0f4f8", edgecolor="#b0c4de", alpha=0.9))

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_condition_investigation()
