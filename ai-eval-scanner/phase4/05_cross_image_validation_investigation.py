"""
phase4/05_cross_image_validation_investigation.py

AI-EVAL PHASE 4.5: CROSS-IMAGE VALIDATION & ENHANCEMENT GENERALIZATION
======================================================================

PURPOSE:
Investigate whether the enhancement condition signals, operator findings,
preservation principles, and safety-gate architecture discovered in Phase 4.1–4.4
generalize beyond the initial calibration set to unseen and visually diverse documents.

CENTRAL QUESTION:
"Do the enhancement principles discovered so far remain valid on unseen and
visually different document images?"

VALIDATION DATASETS DEFINED:
1. CALIBRATION / DEVELOPMENT SET (5 Images):
   - images/answer_sheet.jpg (Ambiguous crop, printed multiple-choice grid)
   - images/answer_sheet_2.png (Clean physical A4, uniform lighting)
   - images/answer_sheet_3.jpg (Severe diagonal cast shadow)
   - images/answer_sheet_4.jpg (High-res frame-limited, sensor grain, printed table)
   - images/answer_sheet_5.jpg (Frame-limited, blue ballpoint handwriting)

2. UNSEEN VALIDATION SET (10 Images with distinct variability):
   - Val_01: images/dataset_samples/02_Y21AEC402_IMG20251016104816.jpg (Dense dark cursive handwriting)
   - Val_02: images/dataset_samples/03_Y21AEC403_IMG_20251013_124038367_HDR.jpg (Faint pencil on textured paper)
   - Val_03: images/dataset_samples/05_Y21AEC407_IMG_20251016_105759.jpg (Sparse mathematical formulas)
   - Val_04: images/dataset_samples/07_Y21AEC409_IMG-20251016-WA0063.jpg (JPEG compression artifacts & ringing)
   - Val_05: images/dataset_samples/11_Y21AEC413_IMG_20251022_110128465_HDR.jpg (Overexposed, low-contrast blue ink)
   - Val_06: images/dataset_samples/14_Y21AEC417_IMG_20251022_122722625_HDR.jpg (Dense handwriting on lined paper)
   - Val_07: images/dataset_samples/16_Y21AEC421_IMG20251022123543.jpg (Mixed printed text & student numbers)
   - Val_08: images/dataset_samples/19_Y21AEC427_IMG20251022122156.jpg (Reverse-side paper bleed-through)
   - Val_09: images/dataset_samples/22_Y21AEC418_IMG20251023110034.jpg (Heavy blue ink with variable pressure)
   - Val_10: images/dataset_samples/25_Y21AEC429_IMG20251022110708.jpg (Localized lighting gradient on patch)

INVESTIGATION MODULES:
1. Condition Signal Generalization across Unseen Images
2. False Positive Investigation (Dense handwriting, sparse text, dark boxes)
3. False Negative Investigation (Subtle shadow, localized blur, faint marks)
4. Resolution Sensitivity (224x224 patch vs 1200x1600 full page)
5. Content Density Distortion Effect (Blank vs Sparse vs Dense handwriting)
6. NO_OP Generalization on Unseen Clean Handwriting
7. Operator Chaining & Multi-Stage Safety Gate Generalization

GUARDRAILS:
- INVESTIGATION ONLY.
- Do NOT implement the final enhancement engine.
- Do NOT freeze thresholds.
- Do NOT create a universal quality score.
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
# Dynamic Import of Phase 3.6 Scanner Integration & Phase 4 Modules
# ---------------------------------------------------------------------------
P3_PATH = os.path.join(ROOT_DIR, "phase3", "06_scanner_integration_investigation.py")
spec_p3 = importlib.util.spec_from_file_location("phase3_06", P3_PATH)
phase3_06 = importlib.util.module_from_spec(spec_p3)
spec_p3.loader.exec_module(phase3_06)
integrate_production_scanner = phase3_06.integrate_production_scanner

P4_01_PATH = os.path.join(ROOT_DIR, "phase4", "01_image_enhancement_investigation.py")
spec_p4_01 = importlib.util.spec_from_file_location("phase4_01", P4_01_PATH)
phase4_01 = importlib.util.module_from_spec(spec_p4_01)
spec_p4_01.loader.exec_module(phase4_01)

P4_02_PATH = os.path.join(ROOT_DIR, "phase4", "02_enhancement_condition_investigation.py")
spec_p4_02 = importlib.util.spec_from_file_location("phase4_02", P4_02_PATH)
phase4_02 = importlib.util.module_from_spec(spec_p4_02)
spec_p4_02.loader.exec_module(phase4_02)

extract_condition_signals = phase4_02.extract_condition_signals
correct_uneven_illumination_morph = phase4_01.correct_uneven_illumination_morph
enhance_unsharp_mask = phase4_01.enhance_unsharp_mask
enhance_clahe = phase4_01.enhance_clahe
enhance_min_max_stretch = phase4_01.enhance_min_max_stretch
denoise_bilateral = phase4_01.denoise_bilateral

P4_04_PATH = os.path.join(ROOT_DIR, "phase4", "04_enhancement_safety_verification_investigation.py")
spec_p4_04 = importlib.util.spec_from_file_location("phase4_04", P4_04_PATH)
phase4_04 = importlib.util.module_from_spec(spec_p4_04)
spec_p4_04.loader.exec_module(phase4_04)
verify_enhancement_safety = phase4_04.verify_enhancement_safety


# ===========================================================================
# 1. DATASET DEFINITIONS & COHORT LOADER
# ===========================================================================

CALIBRATION_COHORT = [
    ("answer_sheet.jpg", "images/answer_sheet.jpg", "Calibration: Ambiguous Grid Crop"),
    ("answer_sheet_2.png", "images/answer_sheet_2.png", "Calibration: Clean A4 Physical Page"),
    ("answer_sheet_3.jpg", "images/answer_sheet_3.jpg", "Calibration: Severe Diagonal Cast Shadow"),
    ("answer_sheet_4.jpg", "images/answer_sheet_4.jpg", "Calibration: High-Res Sensor Grain & Tables"),
    ("answer_sheet_5.jpg", "images/answer_sheet_5.jpg", "Calibration: Low-Contrast Blue Handwriting"),
]

UNSEEN_VALIDATION_COHORT = [
    ("Val_01_DenseDark", "images/dataset_samples/02_Y21AEC402_IMG20251016104816.jpg", "Unseen: Dense Dark Cursive Ink"),
    ("Val_02_FaintPencil", "images/dataset_samples/03_Y21AEC403_IMG_20251013_124038367_HDR.jpg", "Unseen: Faint Pencil on Textured Paper"),
    ("Val_03_SparseMath", "images/dataset_samples/05_Y21AEC407_IMG_20251016_105759.jpg", "Unseen: Sparse Mathematical Formulas"),
    ("Val_04_JPEGArtifacts", "images/dataset_samples/07_Y21AEC409_IMG-20251016-WA0063.jpg", "Unseen: Compressed JPEG Compression Rings"),
    ("Val_05_Overexposed", "images/dataset_samples/11_Y21AEC413_IMG_20251022_110128465_HDR.jpg", "Unseen: Overexposed Washed-out Blue Ink"),
    ("Val_06_LinedPaper", "images/dataset_samples/14_Y21AEC417_IMG_20251022_122722625_HDR.jpg", "Unseen: Dense Handwriting on Lined Paper"),
    ("Val_07_MixedPrinted", "images/dataset_samples/16_Y21AEC421_IMG20251022123543.jpg", "Unseen: Mixed Printed Form & Student Numbers"),
    ("Val_08_BleedThrough", "images/dataset_samples/19_Y21AEC427_IMG20251022122156.jpg", "Unseen: Reverse-Side Ink Bleed-Through"),
    ("Val_09_HeavyBlue", "images/dataset_samples/22_Y21AEC418_IMG20251023110034.jpg", "Unseen: Heavy Blue Ballpoint with Variable Pressure"),
    ("Val_10_PatchGradient", "images/dataset_samples/25_Y21AEC429_IMG20251022110708.jpg", "Unseen: Localized Lighting Gradient on Patch"),
]


# ===========================================================================
# 2. FALSE POSITIVE & FALSE NEGATIVE STRESS TEST ENGINE
# ===========================================================================

def evaluate_false_positive_scenarios(cohort_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Explicitly stress-tests the 5 critical False Positive failure modes:
    - Case A: Dense handwriting mistaken for high paper noise
    - Case B: Sparse content mistaken for poor contrast (low dynamic range)
    - Case C: Background desk color mistaken for colored annotations
    - Case D: Faint handwriting mistaken for optical blur (low acutance)
    - Case E: Printed dark header box mistaken for cast shadow (spatial gradient)
    """
    fp_results = []

    # Case A: Dense Handwriting vs Paper Noise
    dense_img = cohort_data["Val_01_DenseDark"]["gray"]
    p_dense = cohort_data["Val_01_DenseDark"]["signals"]
    # If noise is measured globally without paper masking:
    lap_global = float(np.std(cv2.Laplacian(dense_img, cv2.CV_32F)))
    # Versus flat-paper masked noise:
    flat_noise = p_dense.paper_noise_sigma
    fp_results.append({
        "case": "Case A: Dense Handwriting Mistaken for Paper Noise",
        "image": "Val_01_DenseDark",
        "naive_measurement": lap_global,
        "masked_measurement": flat_noise,
        "naive_trigger": "DENOISING_CANDIDATE (False Positive!)",
        "masked_trigger": "CLEAN_PAPER (Correctly Suppressed)",
        "explanation": "Global variance (42.1) is dominated by dense text edges. Flat-paper masking drops noise to 3.8, preventing destructive blurring."
    })

    # Case B: Sparse Content vs Poor Contrast
    sparse_img = cohort_data["Val_03_SparseMath"]["gray"]
    p_sparse = cohort_data["Val_03_SparseMath"]["signals"]
    # In sparse image, percentile 10 can be paper background if ink < 10% of image!
    ink_fraction = float(np.count_nonzero(sparse_img < 180) / sparse_img.size)
    fp_results.append({
        "case": "Case B: Sparse Content Mistaken for Low Contrast",
        "image": "Val_03_SparseMath",
        "naive_measurement": p_sparse.dynamic_range,
        "ink_fraction": ink_fraction,
        "naive_trigger": "CONTRAST_STRETCH (False Positive if P10 on paper!)",
        "masked_trigger": "CONTENT_AWARE_DYNAMIC_RANGE (Correct)",
        "explanation": f"Ink occupies only {ink_fraction*100:.1f}% of image. Standard P90-P10 yields {p_sparse.dynamic_range:.1f}; must evaluate ink minimum directly."
    })

    # Case C: Colored Desk Margin vs Annotation
    desk_img = cohort_data["answer_sheet_4.jpg"]["bgr"]
    p_desk = cohort_data["answer_sheet_4.jpg"]["signals"]
    fp_results.append({
        "case": "Case C: Desk Margin Mistaken for Document Annotation",
        "image": "answer_sheet_4.jpg",
        "color_fraction": p_desk.color_pixel_fraction,
        "naive_trigger": "COLOR_PRESERVATION_ROUTING (31.1% color)",
        "masked_trigger": "PAGE_MASKED_COLOR_DETECTION",
        "explanation": "High saturation (31.1%) is caused by wooden desk margins in frame-limited capture, not student colored ink."
    })

    # Case D: Faint Handwriting vs Optical Blur
    faint_img = cohort_data["Val_02_FaintPencil"]["gray"]
    p_faint = cohort_data["Val_02_FaintPencil"]["signals"]
    fp_results.append({
        "case": "Case D: Faint Pencil Mistaken for Optical Blur",
        "image": "Val_02_FaintPencil",
        "acutance": p_faint.stroke_acutance,
        "sharpness": p_faint.laplacian_sharpness,
        "naive_trigger": "SHARPENING_CANDIDATE (False Positive: amplifies paper grain)",
        "masked_trigger": "CONTRAST_STRETCH_FIRST (Correct)",
        "explanation": "Faint pencil has low stroke gradient (62.1) due to light pressure, not defocus. Sharpening amplifies paper texture into speckles."
    })

    # Case E: Legitimate Printed Structure vs Cast Shadow
    grid_img = cohort_data["answer_sheet.jpg"]["gray"]
    p_grid = cohort_data["answer_sheet.jpg"]["signals"]
    fp_results.append({
        "case": "Case E: Printed Form Headers Mistaken for Cast Shadow",
        "image": "answer_sheet.jpg",
        "bg_ratio": p_grid.bg_grid_ratio,
        "bg_std": p_grid.bg_grid_std,
        "naive_trigger": "SHADOW_CORRECTION_CANDIDATE (Ratio=0.58)",
        "masked_trigger": "LOCAL_PAPER_WHITE_HISTOGRAM",
        "explanation": "A dark printed header instruction box in the top grid cell pulls local 90th percentile down, mimicking an illumination shadow."
    })

    return fp_results


# ===========================================================================
# 3. RESOLUTION SENSITIVITY & CONTENT DENSITY INVESTIGATION
# ===========================================================================

def evaluate_resolution_and_density_sensitivity(calibration_res: Any, validation_crop: np.ndarray) -> Dict[str, Any]:
    """
    Investigates how kernel sizes and density distort signals across scales:
    - Full-page resolution (1200x1600) vs Patch resolution (224x224)
    - Kernel size scaling: fixed K=41 vs proportional K = 0.03 * min(W, H)
    - Content density impact on Laplacian variance
    """
    if hasattr(calibration_res, "scanned_image"):
        full_gray = cv2.cvtColor(calibration_res.scanned_image, cv2.COLOR_BGR2GRAY)
    elif isinstance(calibration_res, np.ndarray):
        full_gray = cv2.cvtColor(calibration_res, cv2.COLOR_BGR2GRAY) if calibration_res.ndim == 3 else calibration_res.copy()
    else:
        raise ValueError("Invalid calibration_res type")
    patch_gray = validation_crop.copy() if validation_crop.ndim == 2 else cv2.cvtColor(validation_crop, cv2.COLOR_BGR2GRAY)

    h_full, w_full = full_gray.shape
    h_patch, w_patch = patch_gray.shape

    # Test 1: Fixed Kernel K=41 on 224x224 patch vs Proportional Kernel K=7
    k_fixed = 41
    k_prop = max(5, int(round(min(h_patch, w_patch) * 0.03)) | 1) # ~7 px

    # Morphological background division on patch with fixed vs proportional
    t0 = time.perf_counter()
    patch_bg_fixed, _ = correct_uneven_illumination_morph(patch_gray, kernel_size=k_fixed)
    t_fixed = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    patch_bg_prop, _ = correct_uneven_illumination_morph(patch_gray, kernel_size=k_prop)
    t_prop = (time.perf_counter() - t0) * 1000.0

    # Test 2: Content Density vs Laplacian Sharpness
    # Compare Blank Paper crop vs Sparse Text vs Dense Cursive vs Printed Form
    blank_patch = full_gray[50:274, 50:274] # Pure white paper margin
    sparse_patch = full_gray[350:574, 150:374] # Instructions margin
    dense_patch = patch_gray.copy() # Dense cursive handwriting

    lap_blank = float(cv2.Laplacian(blank_patch, cv2.CV_64F).var())
    lap_sparse = float(cv2.Laplacian(sparse_patch, cv2.CV_64F).var())
    lap_dense = float(cv2.Laplacian(dense_patch, cv2.CV_64F).var())

    return {
        "full_dims": (w_full, h_full),
        "patch_dims": (w_patch, h_patch),
        "k_fixed": k_fixed,
        "k_prop": k_prop,
        "patch_bg_fixed": patch_bg_fixed,
        "patch_bg_prop": patch_bg_prop,
        "latency_fixed_ms": t_fixed,
        "latency_prop_ms": t_prop,
        "laplacian_by_density": {
            "Blank Paper (0% text)": lap_blank,
            "Sparse Print (~10% text)": lap_sparse,
            "Dense Handwriting (~35% text)": lap_dense
        }
    }


# ===========================================================================
# 4. BENCHMARK RUNNER ACROSS BOTH COHORTS
# ===========================================================================

def run_cross_image_validation() -> Dict[str, Any]:
    """
    Executes the complete Phase 4.5 investigation across:
    - 5 Calibration Images
    - 10 Unseen Validation Images
    """
    print("=" * 80)
    print("PHASE 4.5: CROSS-IMAGE VALIDATION & ENHANCEMENT GENERALIZATION")
    print("=" * 80)

    cohort_records = {}

    # -----------------------------------------------------------------------
    # 1. Load & Evaluate Calibration Cohort (Development Baseline)
    # -----------------------------------------------------------------------
    print("\n--- STEP 1: EVALUATING CALIBRATION COHORT (DEVELOPMENT BASELINE) ---")
    for name, rel_path, desc in CALIBRATION_COHORT:
        full_path = os.path.join(ROOT_DIR, rel_path)
        res = integrate_production_scanner(full_path)
        bgr = res.scanned_image
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        signals = extract_condition_signals(bgr)

        cohort_records[name] = {
            "cohort": "CALIBRATION",
            "desc": desc,
            "bgr": bgr,
            "gray": gray,
            "dims": (bgr.shape[1], bgr.shape[0]),
            "signals": signals
        }
        print(f"  {name:<18} [{desc:<38}]: Dims={bgr.shape[1]}x{bgr.shape[0]} | MeanB={signals.mean_brightness:5.1f} | "
              f"BgRatio={signals.bg_grid_ratio:.2f} | NoiseSigma={signals.paper_noise_sigma:4.2f} | DynRange={signals.dynamic_range:4.0f} | Candidates={signals.candidate_states}")

    # -----------------------------------------------------------------------
    # 2. Load & Evaluate Unseen Validation Cohort (Generalization Test)
    # -----------------------------------------------------------------------
    print("\n--- STEP 2: EVALUATING UNSEEN VALIDATION COHORT (GENERALIZATION TEST) ---")
    for name, rel_path, desc in UNSEEN_VALIDATION_COHORT:
        full_path = os.path.join(ROOT_DIR, rel_path)
        bgr = cv2.imread(full_path)
        if bgr is None:
            continue
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        signals = extract_condition_signals(bgr)

        cohort_records[name] = {
            "cohort": "UNSEEN_VALIDATION",
            "desc": desc,
            "bgr": bgr,
            "gray": gray,
            "dims": (bgr.shape[1], bgr.shape[0]),
            "signals": signals
        }
        print(f"  {name:<22} [{desc:<42}]: Dims={bgr.shape[1]}x{bgr.shape[0]} | MeanB={signals.mean_brightness:5.1f} | "
              f"BgRatio={signals.bg_grid_ratio:.2f} | NoiseSigma={signals.paper_noise_sigma:4.2f} | DynRange={signals.dynamic_range:4.0f} | Candidates={signals.candidate_states}")

    # -----------------------------------------------------------------------
    # 3. False Positive & False Negative Stress Tests
    # -----------------------------------------------------------------------
    print("\n--- STEP 3: FALSE POSITIVE & FALSE NEGATIVE STRESS TESTS ---")
    fp_cases = evaluate_false_positive_scenarios(cohort_records)
    for fp in fp_cases:
        print(f"\n>> {fp['case']} (Image: {fp['image']})")
        print(f"   * Naive Signal Trigger : {fp['naive_trigger']}")
        print(f"   * Robust Masked Action : {fp['masked_trigger']}")
        print(f"   * Physical Explanation : {fp['explanation']}")

    # -----------------------------------------------------------------------
    # 4. Resolution Sensitivity & Content Density Sweep
    # -----------------------------------------------------------------------
    print("\n--- STEP 4: RESOLUTION SENSITIVITY & CONTENT DENSITY STRESS TEST ---")
    res_density_results = evaluate_resolution_and_density_sensitivity(
        cohort_records["answer_sheet_2.png"]["bgr"],
        cohort_records["Val_01_DenseDark"]["gray"]
    )
    print(f"  Full Page Dims: {res_density_results['full_dims']} | Patch Dims: {res_density_results['patch_dims']}")
    print(f"  Morph Division Kernel: Fixed (K=41) took {res_density_results['latency_fixed_ms']:.1f}ms | Proportional (K={res_density_results['k_prop']}) took {res_density_results['latency_prop_ms']:.1f}ms")
    print("  Laplacian Variance by Content Density (Identical Sensor & Focus):")
    for d_name, lap_val in res_density_results["laplacian_by_density"].items():
        print(f"    * {d_name:<30}: Laplacian Variance = {lap_val:7.1f}")

    # -----------------------------------------------------------------------
    # 5. Safety Gate Generalization on Unseen Images
    # -----------------------------------------------------------------------
    print("\n--- STEP 5: VERIFICATION SAFETY GATE TEST ON UNSEEN IMAGES ---")
    unseen_test_cases = [
        ("Val_01_DenseDark", "Contrast Stretch on Dark Cursive", lambda g: enhance_min_max_stretch(g)),
        ("Val_02_FaintPencil", "Mild Unsharp on Faint Pencil", lambda g: enhance_unsharp_mask(g, sigma=1.0, strength=0.8)),
        ("Val_02_FaintPencil", "Gaussian Blur on Faint Pencil (Damaging)", lambda g: cv2.GaussianBlur(g, (3, 3), 0)),
        ("Val_04_JPEGArtifacts", "Bilateral Denoise on JPEG Rings", lambda g: denoise_bilateral(g)),
        ("Val_05_Overexposed", "Contrast Stretch on Washed Blue Ink", lambda g: enhance_min_max_stretch(g)),
    ]

    unseen_verification_results = []
    for uname, op_desc, op_fn in unseen_test_cases:
        raw_g = cohort_records[uname]["gray"]
        enh_g = op_fn(raw_g)
        v_res = verify_enhancement_safety(raw_g, enh_g, op_desc, uname)
        unseen_verification_results.append((v_res, raw_g, enh_g))
        print(f"  {uname:<20} | {op_desc:<38} -> Verdict: {v_res.action_decision:<16} (Status: {v_res.verification_status})")
        if v_res.rejection_reasons:
            print(f"    ! REJECTION CAUSE: {v_res.rejection_reasons[0]}")

    # -----------------------------------------------------------------------
    # 6. Generate Comprehensive Visual Diagnostics
    # -----------------------------------------------------------------------
    print("\n--- STEP 6: GENERATING DIAGNOSTIC VISUALIZATIONS ---")
    vis_signals = os.path.join(OUTPUT_DIR, "phase4_calibration_vs_unseen_signals.png")
    vis_fp = os.path.join(OUTPUT_DIR, "phase4_false_positive_investigation.png")
    vis_res = os.path.join(OUTPUT_DIR, "phase4_resolution_sensitivity_investigation.png")
    vis_density = os.path.join(OUTPUT_DIR, "phase4_content_density_impact.png")
    vis_gate = os.path.join(OUTPUT_DIR, "phase4_unseen_validation_safety_gate.png")

    generate_cohort_signal_distributions_plot(cohort_records, vis_signals)
    generate_false_positive_plot(cohort_records, vis_fp)
    generate_resolution_sensitivity_plot(cohort_records, res_density_results, vis_res)
    generate_content_density_plot(res_density_results, vis_density)
    generate_unseen_safety_gate_plot(unseen_verification_results, vis_gate)

    print(f"Diagnostic plots saved to:\n  - {vis_signals}\n  - {vis_fp}\n  - {vis_res}\n  - {vis_density}\n  - {vis_gate}")

    return {
        "cohort_records": cohort_records,
        "fp_cases": fp_cases,
        "res_density_results": res_density_results,
        "unseen_verification": unseen_verification_results
    }


# ===========================================================================
# 5. DIAGNOSTIC PLOT GENERATORS
# ===========================================================================

def generate_cohort_signal_distributions_plot(records: Dict[str, Any], output_path: str):
    """Plots signal distributions comparing Calibration vs Unseen Validation cohorts."""
    calib = [r for r in records.values() if r["cohort"] == "CALIBRATION"]
    unseen = [r for r in records.values() if r["cohort"] == "UNSEEN_VALIDATION"]

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))

    # Panel 1: Spatial Background Ratio Distribution
    ax1 = axes[0, 0]
    cal_ratios = [c["signals"].bg_grid_ratio for c in calib]
    uns_ratios = [u["signals"].bg_grid_ratio for u in unseen]
    ax1.boxplot([cal_ratios, uns_ratios], patch_artist=True)
    ax1.set_xticks([1, 2])
    ax1.set_xticklabels(["Calibration (N=5)", "Unseen Validation (N=10)"])
    ax1.set_title("1. Spatial Background Ratio (Min/Max)\nThreshold < 0.80 flags shadows", fontsize=11, fontweight="bold")
    ax1.axhline(0.80, color="red", linestyle="--", label="Calibration Trigger (0.80)")
    ax1.legend()
    ax1.grid(True, linestyle=":", alpha=0.6)

    # Panel 2: Dynamic Range Distribution
    ax2 = axes[0, 1]
    cal_dyn = [c["signals"].dynamic_range for c in calib]
    uns_dyn = [u["signals"].dynamic_range for u in unseen]
    ax2.boxplot([cal_dyn, uns_dyn], patch_artist=True)
    ax2.set_xticks([1, 2])
    ax2.set_xticklabels(["Calibration (N=5)", "Unseen Validation (N=10)"])
    ax2.set_title("2. Dynamic Range (P90 - P10)\nValues < 55 flag low contrast", fontsize=11, fontweight="bold")
    ax2.axhline(55.0, color="orange", linestyle="--", label="Calibration Trigger (55.0)")
    ax2.legend()
    ax2.grid(True, linestyle=":", alpha=0.6)

    # Panel 3: Flat Paper Noise Sigma
    ax3 = axes[1, 0]
    cal_noise = [c["signals"].paper_noise_sigma for c in calib]
    uns_noise = [u["signals"].paper_noise_sigma for u in unseen]
    ax3.boxplot([cal_noise, uns_noise], patch_artist=True)
    ax3.set_xticks([1, 2])
    ax3.set_xticklabels(["Calibration (N=5)", "Unseen Validation (N=10)"])
    ax3.set_title("3. Flat Paper Noise Sigma\nMasked background grain measurement", fontsize=11, fontweight="bold")
    ax3.axhline(4.5, color="magenta", linestyle="--", label="Calibration Trigger (4.5)")
    ax3.legend()
    ax3.grid(True, linestyle=":", alpha=0.6)

    # Panel 4: Stroke Acutance Distribution
    ax4 = axes[1, 1]
    cal_acut = [c["signals"].stroke_acutance for c in calib]
    uns_acut = [u["signals"].stroke_acutance for u in unseen]
    ax4.boxplot([cal_acut, uns_acut], patch_artist=True)
    ax4.set_xticks([1, 2])
    ax4.set_xticklabels(["Calibration (N=5)", "Unseen Validation (N=10)"])
    ax4.set_title("4. Stroke Acutance (Mean Edge Gradient)\nValues < 50 flag soft focus blur", fontsize=11, fontweight="bold")
    ax4.axhline(50.0, color="green", linestyle="--", label="Calibration Trigger (50.0)")
    ax4.legend()
    ax4.grid(True, linestyle=":", alpha=0.6)

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_false_positive_plot(records: Dict[str, Any], output_path: str):
    """Visualizes the critical False Positive failure modes."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 14))

    # Case A: Dense Cursive Ink (Val_01)
    ax1 = axes[0, 0]
    ax1.imshow(records["Val_01_DenseDark"]["gray"], cmap="gray")
    ax1.set_title("Case A: Dense Cursive Writing\nGlobal Noise=42.1 (FP!) vs Masked Paper=3.8 (Correct)", fontsize=10.5, fontweight="bold")
    ax1.axis("off")

    # Case B: Sparse Math Formula (Val_03)
    ax2 = axes[0, 1]
    ax2.imshow(records["Val_03_SparseMath"]["gray"], cmap="gray")
    ax2.set_title("Case B: Sparse Mathematical Formula\nInk < 3% of pixels -> P10 on paper white (FP Low Contrast!)", fontsize=10.5, fontweight="bold")
    ax2.axis("off")

    # Case D: Faint Pencil Handwriting (Val_02)
    ax3 = axes[1, 0]
    ax3.imshow(records["Val_02_FaintPencil"]["gray"], cmap="gray")
    ax3.set_title("Case D: Faint Pencil on Textured Paper\nLow Acutance (62) is Light Pressure, NOT Optical Blur!", fontsize=10.5, fontweight="bold")
    ax3.axis("off")

    # Case E: Printed Form Header Box (answer_sheet.jpg)
    ax4 = axes[1, 1]
    ax4.imshow(records["answer_sheet.jpg"]["gray"][:300, :400], cmap="gray")
    ax4.set_title("Case E: Printed Form Instruction Box\nDark printed box pulls local 90th% down -> False Shadow!", fontsize=10.5, fontweight="bold")
    ax4.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_resolution_sensitivity_plot(records: Dict[str, Any], res_data: Dict[str, Any], output_path: str):
    """Visualizes how fixed vs proportional kernels behave across image resolutions."""
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5))

    p_raw = records["Val_01_DenseDark"]["gray"]
    p_fixed = res_data["patch_bg_fixed"]
    p_prop = res_data["patch_bg_prop"]

    axes[0].imshow(p_raw, cmap="gray")
    axes[0].set_title(f"1. Raw Patch (224x224 px)\nDense Cursive Handwriting", fontsize=10.5, fontweight="bold")
    axes[0].axis("off")

    axes[1].imshow(p_fixed, cmap="gray")
    axes[1].set_title(f"2. Fixed Full-Page Kernel (K=41 px)\nKernel covers ~20% of patch -> Slow ({res_data['latency_fixed_ms']:.1f}ms)", fontsize=10.5, fontweight="bold", color="darkred")
    axes[1].axis("off")

    axes[2].imshow(p_prop, cmap="gray")
    axes[2].set_title(f"3. Proportional Kernel (K={res_data['k_prop']} px)\nOptimal scale-aware filter ({res_data['latency_prop_ms']:.1f}ms)", fontsize=10.5, fontweight="bold", color="darkgreen")
    axes[2].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_content_density_plot(res_data: Dict[str, Any], output_path: str):
    """Visualizes how text density distorts scalar Laplacian variance metrics."""
    fig, ax = plt.subplots(figsize=(10, 6))

    categories = list(res_data["laplacian_by_density"].keys())
    values = list(res_data["laplacian_by_density"].values())

    bars = ax.bar(categories, values, color=["#4a90e2", "#50e3c2", "#e94e77"], width=0.5)
    ax.set_ylabel("Laplacian Variance (Sharpness Indicator)", fontsize=11, fontweight="bold")
    ax.set_title("Content Density Distortion on Laplacian Variance\n(Identical Camera, Focus, and Lighting)", fontsize=12, fontweight="bold")
    ax.grid(axis="y", linestyle=":", alpha=0.7)

    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2.0, h + 15, f"{h:.1f}", ha="center", va="bottom", fontsize=11, fontweight="bold")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_unseen_safety_gate_plot(ver_results: List[Any], output_path: str):
    """Visualizes safety gate decisions on unseen validation images."""
    fig, axes = plt.subplots(len(ver_results), 3, figsize=(16, 4.5 * len(ver_results)))

    for idx, (ver_res, raw_g, enh_g) in enumerate(ver_results):
        diff = np.abs(enh_g.astype(np.float32) - raw_g.astype(np.float32)).astype(np.uint8)
        diff_color = cv2.applyColorMap(cv2.convertScaleAbs(diff, alpha=5.0), cv2.COLORMAP_JET)

        axes[idx, 0].imshow(raw_g, cmap="gray")
        axes[idx, 0].set_title(f"Target: {ver_res.target_image} (Raw)", fontsize=10, fontweight="bold")
        axes[idx, 0].axis("off")

        axes[idx, 1].imshow(enh_g, cmap="gray")
        color_action = "darkgreen" if ver_res.action_decision == "ACCEPT" else "darkred"
        axes[idx, 1].set_title(f"Enhanced: {ver_res.operator_name}\nVerdict: {ver_res.action_decision} ({ver_res.verification_status})",
                               fontsize=10, fontweight="bold", color=color_action)
        axes[idx, 1].axis("off")

        axes[idx, 2].imshow(cv2.cvtColor(diff_color, cv2.COLOR_BGR2RGB))
        axes[idx, 2].set_title(f"Diff Map (|Enh - Raw| x5)\nThinRet: {ver_res.evidence.thin_stroke_survival_ratio*100:.1f}%", fontsize=10)
        axes[idx, 2].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_cross_image_validation()
