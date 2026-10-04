"""
phase8/04_representation_evaluation_investigation.py

AI-EVAL PHASE 8.5: RECOGNITION REPRESENTATION EVALUATION & CONTROLLED OCR EVIDENCE
====================================================================================

PURPOSE:
    Empirically evaluate whether different prepared image representations produced by the
    existing Phase 8 pipeline (R0, R1, R2, R3) affect downstream OCR recognition quality
    under controlled and multi-condition experiments.

    Key Research Questions:
        1. Does Phase 8.2 normalized preparation (R1: de-rotation + Radon deskew)
           improve, degrade, or leave OCR unchanged relative to raw grayscale (R0)?
           (Note: CLAHE is NOT part of frozen Phase 8.2).
        2. Does binarization (R2) produce consistent degradation, or are there conditions
           where it is benign or beneficial?
        3. Does experimental ruled-line suppression (R3: Telea inpainting derived during
           Phase 8.5 via Phase 8.2 rule mask) assist or disrupt downstream text recognition?
           (Note: Telea inpainting is NOT a frozen Phase 8.2 output).
        4. What does empirical evaluation show on real exam sheets (e.g. answer_sheet_2.png)
           where preprocessing previously produced counter-intuitive outcomes?
        5. Are observed effects universal or strictly condition-specific?

GOVERNANCE / FROZEN STATE CONSTRAINTS:
    - INVESTIGATION ONLY.
    - DO NOT modify phase2/ through phase7/.
    - DO NOT modify Phase 8.1, 8.2, 8.3, or 8.4 code or reports.
    - DO NOT train or fine-tune any OCR/HTR model.
    - DO NOT implement a production readiness classifier.
    - DO NOT freeze thresholds or representation selection rules.
    - If evidence is insufficient, explicitly report INSUFFICIENT EVIDENCE.
    - Preserve all existing regression tests.
"""

from __future__ import annotations

import os
import sys
import csv
import math
import time
import asyncio
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Path Configuration & Frozen Module Imports
# ---------------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
OUTPUT_DIR = os.path.join(CURRENT_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# WinRT Offline Windows Media OCR bindings
try:
    import winrt.windows.storage as ws
    import winrt.windows.graphics.imaging as wgi
    import winrt.windows.media.ocr as wmo
    WINRT_OCR_AVAILABLE = True
except ImportError:
    WINRT_OCR_AVAILABLE = False

# Phase 8.2 Production Modules (FROZEN - read only)
from phase8.ocr_readiness_contracts import (
    ReadinessPreparationConfig,
    PreprocessedImageBundle,
    OCRReadinessPreparationResult,
)
from phase8.ocr_readiness_engine import prepare_ocr_readiness


# ===========================================================================
# 1. EDIT-DISTANCE METRICS & BENCHMARK CORPUS
# ===========================================================================

def levenshtein_distance(seq1: Sequence[Any], seq2: Sequence[Any]) -> int:
    """Computes exact Levenshtein edit distance between two sequences."""
    l1, l2 = len(seq1), len(seq2)
    if l1 == 0:
        return l2
    if l2 == 0:
        return l1
    prev = list(range(l2 + 1))
    for i in range(1, l1 + 1):
        curr = [i] + [0] * l2
        for j in range(1, l2 + 1):
            cost = 0 if seq1[i - 1] == seq2[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[l2]


def normalize_text(text: str) -> str:
    """Normalizes whitespace for robust string comparison."""
    return " ".join(text.strip().split())


def compute_cer(hypothesis: str, reference: str) -> float:
    """Character Error Rate: Levenshtein(chars) / max(1, len(reference))."""
    ref_norm = normalize_text(reference)
    hyp_norm = normalize_text(hypothesis)
    if len(ref_norm) == 0:
        return 0.0 if len(hyp_norm) == 0 else 1.0
    dist = levenshtein_distance(list(hyp_norm), list(ref_norm))
    return min(1.0, float(dist) / float(len(ref_norm)))


def compute_wer(hypothesis: str, reference: str) -> float:
    """Word Error Rate: Levenshtein(words) / max(1, len(ref_words))."""
    ref_words = normalize_text(reference).split()
    hyp_words = normalize_text(hypothesis).split()
    if len(ref_words) == 0:
        return 0.0 if len(hyp_words) == 0 else 1.0
    dist = levenshtein_distance(hyp_words, ref_words)
    return min(1.0, float(dist) / float(len(ref_words)))


BENCHMARK_LINES: List[str] = [
    "EXAMINATION RECORD: ARTIFICIAL INTELLIGENCE & EVALUATION",
    "Candidate Name: Rajesh Sharma     Roll No: 2024-CSE-042",
    "Question 1: Explain the purpose of perspective transformation.",
    "Answer: Perspective rectification maps a skewed quadrilateral plane to a canonical rectangle.",
    "Question 2: State the difference between OCR and HTR systems.",
    "Answer: OCR handles printed typography while HTR must model cursive and unconstrained handwriting.",
    "Section B: Algorithmic Complexity Analysis (Total Marks: 20)",
    "Q3: Prove that binary search runs in logarithmic time complexity.",
]

GT_TEXT_CLEAN = "\n".join(BENCHMARK_LINES)
GT_TEXT_INLINE = " ".join(BENCHMARK_LINES)

GT_ANSWER_SHEET_2_HEADER = "TAGORE PUBLIC SCHOOL, ALLAHABAD EXAMINATION ANSWER SHEET Roll NO. Name of Examination Subject"


# ===========================================================================
# 2. SYNTHETIC BENCHMARK GENERATION & CONTROLLED DEGRADATIONS
# ===========================================================================

def generate_base_canvas(
    lines: List[str],
    width: int = 1400,
    line_pitch: int = 70,
    font_scale: float = 0.70,
    thickness: int = 2,
) -> np.ndarray:
    """Renders clean typographic lines onto a neutral paper background (245 DN)."""
    height = 80 + len(lines) * line_pitch + 50
    canvas = np.full((height, width, 3), 245, dtype=np.uint8)
    for idx, text in enumerate(lines):
        y = 80 + idx * line_pitch
        cv2.putText(
            canvas,
            text,
            (50, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (25, 25, 25),
            thickness,
            cv2.LINE_AA,
        )
    return canvas


def overlay_ruled_lines(canvas: np.ndarray, pitch: int = 70, offset: int = 90) -> np.ndarray:
    """Simulates lined exam paper by drawing faint horizontal guidelines."""
    out = canvas.copy()
    h, w = out.shape[:2]
    for y in range(offset, h - 20, pitch):
        cv2.line(out, (30, y), (w - 30, y), (185, 185, 185), 2, cv2.LINE_AA)
    return out


def inject_gaussian_noise(canvas: np.ndarray, sigma: float = 12.0) -> np.ndarray:
    """Injects zero-mean additive Gaussian sensor noise."""
    out = canvas.astype(np.float32)
    noise = np.random.normal(0, sigma, out.shape)
    return np.clip(out + noise, 0, 255).astype(np.uint8)


def attenuate_contrast(canvas: np.ndarray, factor: float = 0.55) -> np.ndarray:
    """Compresses dynamic range towards mid-gray (128) simulating low contrast."""
    out = canvas.astype(np.float32)
    out = 128.0 + (out - 128.0) * factor
    return np.clip(out, 0, 255).astype(np.uint8)


def simulate_shadow_gradient(canvas: np.ndarray) -> np.ndarray:
    """Simulates non-uniform lighting / diagonal illumination gradient."""
    h, w = canvas.shape[:2]
    X, Y = np.meshgrid(np.linspace(0, 1, w), np.linspace(0, 1, h))
    gradient = 1.0 - 0.40 * (X * 0.6 + Y * 0.4)
    out = canvas.astype(np.float32) * gradient[:, :, np.newaxis]
    return np.clip(out, 0, 255).astype(np.uint8)


def apply_geometric_skew(canvas: np.ndarray, angle_deg: float) -> np.ndarray:
    """Applies a controlled small angle tilt around canvas center."""
    h, w = canvas.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle_deg, 1.0)
    return cv2.warpAffine(canvas, M, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=(245, 245, 245))


def apply_cardinal_rotation(canvas: np.ndarray, degrees: int) -> np.ndarray:
    """Rotates image strictly by 90, 180, or 270 degrees."""
    if degrees == 90:
        return cv2.rotate(canvas, cv2.ROTATE_90_CLOCKWISE)
    elif degrees == 180:
        return cv2.rotate(canvas, cv2.ROTATE_180)
    elif degrees == 270:
        return cv2.rotate(canvas, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return canvas


# ===========================================================================
# 3. OCR RUNNER VIA WINRT (STORAGEFILE / BITMAPDECODER)
# ===========================================================================

class WindowsMediaOcrRunner:
    """
    Robust native Windows Media OCR runner using StorageFile and BitmapDecoder.
    Compatible with Windows 10/11 WinRT API surface.
    """
    def __init__(self):
        if not WINRT_OCR_AVAILABLE:
            raise RuntimeError("WinRT Windows.Media.Ocr not available.")
        self._engine = wmo.OcrEngine.try_create_from_user_profile_languages()
        if self._engine is None:
            raise RuntimeError("Windows Media OCR Engine initialization failed.")

    async def recognize_async(self, image: np.ndarray) -> Tuple[str, List[str]]:
        h, w = image.shape[:2]
        if min(h, w) < 20:
            return "", []

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            cv2.imwrite(tmp_path, image)
            sf = await ws.StorageFile.get_file_from_path_async(os.path.abspath(tmp_path))
            stream = await sf.open_async(ws.FileAccessMode.READ)
            decoder = await wgi.BitmapDecoder.create_async(stream)
            bitmap = await decoder.get_software_bitmap_async()
            result = await self._engine.recognize_async(bitmap)
            stream.close()

            lines = []
            for i in range(result.lines.size):
                lines.append(result.lines.get_at(i).text)
            full_text = " ".join(lines)
            return full_text, lines
        except Exception as e:
            return f"__ERROR__: {str(e)}", []
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def recognize(self, image: np.ndarray) -> Tuple[str, List[str], float]:
        t0 = time.perf_counter()
        full_text, lines = asyncio.run(self.recognize_async(image))
        dt = (time.perf_counter() - t0) * 1000.0
        return full_text, lines, dt


# ===========================================================================
# 4. REPRESENTATION EXTRACTION
# ===========================================================================

def extract_representation_bundle(
    bgr_image: np.ndarray,
    doc_id: str = "eval",
) -> Dict[str, Any]:
    """
    Extracts candidate representations R0, R1, R2, R3:
      - R0: Raw Grayscale (standard cv2.cvtColor BGR2GRAY; unprocessed baseline)
      - R1: Prepared Grayscale (Phase 8.2 ready_gray: 4-way de-rotated + fine Radon deskewed)
            Note: CLAHE is NOT part of frozen Phase 8.2 ready_gray.
      - R2: Binary Representation (Phase 8.2 ready_bin: inverted to dark-ink-on-white)
      - R3: Experimental Ruled-Line Handled Grayscale (derived during Phase 8.5 by applying
            Telea inpainting over Phase 8.2 rule_lines_mask; NOT a frozen Phase 8.2 output).
    """
    r0 = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)

    p82_res: OCRReadinessPreparationResult = prepare_ocr_readiness(bgr_image, document_id=doc_id)
    bundle = p82_res.image_bundle

    r1 = bundle.ready_gray.copy()
    r2 = cv2.bitwise_not(bundle.ready_bin)

    if bundle.rule_lines_mask is not None and np.sum(bundle.rule_lines_mask > 0) > 50:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3))
        dilated_mask = cv2.dilate(bundle.rule_lines_mask, kernel, iterations=1)
        r3 = cv2.inpaint(r1, dilated_mask, inpaintRadius=2, flags=cv2.INPAINT_TELEA)
    else:
        r3 = r1.copy()

    return {
        "R0": r0,
        "R1": r1,
        "R2": r2,
        "R3": r3,
        "_res": p82_res,
    }


# ===========================================================================
# 5. CONTROLLED EXPERIMENT EXECUTION
# ===========================================================================

def run_controlled_experiments(ocr_runner: WindowsMediaOcrRunner) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Constructs multi-condition cases and executes controlled OCR on R0, R1, R2, R3.
    """
    print("[Phase 8.5] Building controlled synthetic test conditions...")
    base_canvas = generate_base_canvas(BENCHMARK_LINES)

    cases: List[Tuple[str, np.ndarray, str, str]] = [
        # (case_id, bgr_image, ground_truth, category)
        ("A_CLEAN_BASELINE", base_canvas.copy(), GT_TEXT_INLINE, "Clean Typography"),
        ("B_RULED_PAPER_COARSE", overlay_ruled_lines(base_canvas, pitch=70, offset=90), GT_TEXT_INLINE, "Ruled Paper"),
        ("C_RULED_PAPER_FINE", overlay_ruled_lines(base_canvas, pitch=45, offset=75), GT_TEXT_INLINE, "Ruled Paper"),
        ("D_GAUSSIAN_NOISE_MODERATE", inject_gaussian_noise(base_canvas, sigma=15.0), GT_TEXT_INLINE, "Sensor Noise"),
        ("E_GAUSSIAN_NOISE_HEAVY", inject_gaussian_noise(base_canvas, sigma=28.0), GT_TEXT_INLINE, "Sensor Noise"),
        ("F_LOW_CONTRAST_MODERATE", attenuate_contrast(base_canvas, factor=0.55), GT_TEXT_INLINE, "Low Contrast"),
        ("G_LOW_CONTRAST_SEVERE", attenuate_contrast(base_canvas, factor=0.35), GT_TEXT_INLINE, "Low Contrast"),
        ("H_SHADOW_GRADIENT", simulate_shadow_gradient(base_canvas), GT_TEXT_INLINE, "Illumination Gradient"),
        ("I_MILD_SKEW_1.5DEG", apply_geometric_skew(base_canvas, 1.5), GT_TEXT_INLINE, "Baseline Skew"),
        ("J_MILD_SKEW_3.0DEG", apply_geometric_skew(base_canvas, 3.0), GT_TEXT_INLINE, "Baseline Skew"),
        ("K_ROTATED_90_CW", apply_cardinal_rotation(base_canvas, 90), GT_TEXT_INLINE, "Orientation Defect"),
        ("L_ROTATED_180_INVERTED", apply_cardinal_rotation(base_canvas, 180), GT_TEXT_INLINE, "Orientation Defect"),
        ("M_ROTATED_270_CCW", apply_cardinal_rotation(base_canvas, 270), GT_TEXT_INLINE, "Orientation Defect"),
        ("N_RULED_PLUS_NOISE", inject_gaussian_noise(overlay_ruled_lines(base_canvas, 60, 85), sigma=14.0), GT_TEXT_INLINE, "Combined"),
        ("O_SHADOW_PLUS_LOW_CONTRAST", attenuate_contrast(simulate_shadow_gradient(base_canvas), factor=0.60), GT_TEXT_INLINE, "Combined"),
    ]

    results: List[Dict[str, Any]] = []

    print(f"[Phase 8.5] Running OCR evaluation on {len(cases)} controlled cases across 4 representations...")
    for case_id, img_bgr, gt_text, category in cases:
        bundle = extract_representation_bundle(img_bgr, doc_id=case_id)
        p82_res: OCRReadinessPreparationResult = bundle["_res"]

        case_entry: Dict[str, Any] = {
            "case_id": case_id,
            "category": category,
            "gt_char_len": len(gt_text),
            "pvr": round(p82_res.metrics.peak_to_valley_ratio, 3),
            "line_collision": round(p82_res.metrics.line_collision_ratio, 3),
            "median_char_height": round(p82_res.metrics.median_char_height_px, 1),
            "detected_orientation": p82_res.detected_orientation.value,
            "detected_skew": round(p82_res.detected_skew_angle_deg, 2),
        }

        for rep_name in ["R0", "R1", "R2", "R3"]:
            rep_img = bundle[rep_name]
            hyp_text, lines_det, lat_ms = ocr_runner.recognize(rep_img)

            cer = compute_cer(hyp_text, gt_text)
            wer = compute_wer(hyp_text, gt_text)

            case_entry[f"{rep_name}_cer"] = round(cer, 4)
            case_entry[f"{rep_name}_wer"] = round(wer, 4)
            case_entry[f"{rep_name}_lines"] = len(lines_det)
            case_entry[f"{rep_name}_chars"] = len(hyp_text)
            case_entry[f"{rep_name}_latency_ms"] = round(lat_ms, 1)
            case_entry[f"{rep_name}_text_sample"] = hyp_text[:80]

        results.append(case_entry)
        print(f"  [{case_id:28}] R0 CER={case_entry['R0_cer']:.4f} | R1 CER={case_entry['R1_cer']:.4f} | R2 CER={case_entry['R2_cer']:.4f} | R3 CER={case_entry['R3_cer']:.4f}")

    # Real exam sheet evaluation (answer_sheet_2.png)
    real_sheet_path = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
    real_results: Dict[str, Any] = {}
    if os.path.exists(real_sheet_path):
        print(f"\n[Phase 8.5] Evaluating real exam sheet: {os.path.basename(real_sheet_path)}...")
        real_bgr = cv2.imread(real_sheet_path)
        if real_bgr is not None:
            r_bundle = extract_representation_bundle(real_bgr, doc_id="real_answer_sheet_2")
            r_p82_res: OCRReadinessPreparationResult = r_bundle["_res"]

            real_results["image_name"] = "answer_sheet_2.png"
            real_results["detected_orientation"] = r_p82_res.detected_orientation.value
            real_results["applied_rotation_deg"] = r_p82_res.applied_rotation_deg
            real_results["detected_skew"] = round(r_p82_res.detected_skew_angle_deg, 2)
            real_results["pvr"] = round(r_p82_res.metrics.peak_to_valley_ratio, 3)
            real_results["warnings"] = r_p82_res.warnings

            for rep_name in ["R0", "R1", "R2", "R3"]:
                r_img = r_bundle[rep_name]
                r_text, r_lines, r_lat = ocr_runner.recognize(r_img)
                # Compare header match
                r_header_cer = compute_cer(r_text[:len(GT_ANSWER_SHEET_2_HEADER) + 30], GT_ANSWER_SHEET_2_HEADER)
                real_results[f"{rep_name}_lines"] = len(r_lines)
                real_results[f"{rep_name}_chars"] = len(r_text)
                real_results[f"{rep_name}_header_cer"] = round(r_header_cer, 4)
                real_results[f"{rep_name}_latency_ms"] = round(r_lat, 1)
                real_results[f"{rep_name}_text_sample"] = r_text[:120]
                print(f"    {rep_name:4}: Lines={len(r_lines):2d}, Chars={len(r_text):4d}, Header CER={r_header_cer:.4f}, Sample='{r_text[:45]}...'")

    return results, real_results


# ===========================================================================
# 6. STATISTICAL & PAIRWISE CONDITION ANALYSIS
# ===========================================================================

def analyze_representation_effects(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes condition-specific improvements, degradations, or equivalence
    without declaring universal rankings.
    """
    stats: Dict[str, Any] = {
        "N": len(results),
        "R0_CER_mean": round(float(np.mean([r["R0_cer"] for r in results])), 4),
        "R1_CER_mean": round(float(np.mean([r["R1_cer"] for r in results])), 4),
        "R2_CER_mean": round(float(np.mean([r["R2_cer"] for r in results])), 4),
        "R3_CER_mean": round(float(np.mean([r["R3_cer"] for r in results])), 4),
        "R0_CER_median": round(float(np.median([r["R0_cer"] for r in results])), 4),
        "R1_CER_median": round(float(np.median([r["R1_cer"] for r in results])), 4),
        "R2_CER_median": round(float(np.median([r["R2_cer"] for r in results])), 4),
        "R3_CER_median": round(float(np.median([r["R3_cer"] for r in results])), 4),
    }

    # NOTE: The 0.01 delta boundary is an exploratory analysis grouping criterion
    # used solely for internal summarization in Phase 8.5; it is NOT a production
    # threshold and is NOT frozen.
    delta_r1_r0 = [round(r["R1_cer"] - r["R0_cer"], 4) for r in results]
    stats["raw_deltas_r1_r0"] = delta_r1_r0
    stats["R1_vs_R0_improved"] = sum(1 for d in delta_r1_r0 if d < -0.01)
    stats["R1_vs_R0_degraded"] = sum(1 for d in delta_r1_r0 if d > 0.01)
    stats["R1_vs_R0_no_material_diff"] = sum(1 for d in delta_r1_r0 if abs(d) <= 0.01)
    stats["R1_vs_R0_equivalent"] = stats["R1_vs_R0_no_material_diff"]  # backward compat

    # Pairwise comparison counts (R2 vs R1)
    delta_r2_r1 = [round(r["R2_cer"] - r["R1_cer"], 4) for r in results]
    stats["raw_deltas_r2_r1"] = delta_r2_r1
    stats["R2_vs_R1_improved"] = sum(1 for d in delta_r2_r1 if d < -0.01)
    stats["R2_vs_R1_degraded"] = sum(1 for d in delta_r2_r1 if d > 0.01)
    stats["R2_vs_R1_no_material_diff"] = sum(1 for d in delta_r2_r1 if abs(d) <= 0.01)
    stats["R2_vs_R1_equivalent"] = stats["R2_vs_R1_no_material_diff"]  # backward compat

    # Pairwise comparison counts (R3 vs R1)
    delta_r3_r1 = [round(r["R3_cer"] - r["R1_cer"], 4) for r in results]
    stats["raw_deltas_r3_r1"] = delta_r3_r1
    stats["R3_vs_R1_improved"] = sum(1 for d in delta_r3_r1 if d < -0.01)
    stats["R3_vs_R1_degraded"] = sum(1 for d in delta_r3_r1 if d > 0.01)
    stats["R3_vs_R1_no_material_diff"] = sum(1 for d in delta_r3_r1 if abs(d) <= 0.01)
    stats["R3_vs_R1_equivalent"] = stats["R3_vs_R1_no_material_diff"]  # backward compat

    return stats


# ===========================================================================
# 7. GENERATE ARTIFACT PLOTS
# ===========================================================================

def generate_visual_artifacts(
    results: List[Dict[str, Any]],
    stats: Dict[str, Any],
    real_results: Dict[str, Any],
) -> None:
    """Generates the four diagnostic figures for Phase 8.5."""
    print("\n[Phase 8.5] Generating diagnostic plots...")

    # 1. phase8_5_representation_comparison.png (CER across conditions)
    case_ids = [r["case_id"] for r in results]
    x = np.arange(len(case_ids))
    width = 0.20

    fig, ax = plt.subplots(figsize=(16, 7))
    ax.bar(x - 1.5 * width, [r["R0_cer"] for r in results], width, label="R0: Raw Grayscale", color="#4e79a7")
    ax.bar(x - 0.5 * width, [r["R1_cer"] for r in results], width, label="R1: Phase 8.2 Prepared", color="#59a14f")
    ax.bar(x + 0.5 * width, [r["R2_cer"] for r in results], width, label="R2: Binary Derivative", color="#e15759")
    ax.bar(x + 1.5 * width, [r["R3_cer"] for r in results], width, label="R3: Ruled Handled", color="#edc948")

    ax.set_ylabel("Character Error Rate (CER)", fontsize=11, fontweight="bold")
    ax.set_title("Phase 8.5: Downstream OCR CER by Input Representation Across Controlled Conditions", fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(case_ids, rotation=35, ha="right", fontsize=8.5)
    ax.legend(loc="upper right", frameon=True, shadow=True)
    ax.set_ylim(-0.02, 1.05)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    p1 = os.path.join(OUTPUT_DIR, "phase8_5_representation_comparison.png")
    plt.savefig(p1, dpi=150)
    plt.close()
    print(f"  Saved: {p1}")

    # 2. phase8_5_cer_distribution.png (Boxplot / Violin of CER per Representation)
    fig, ax = plt.subplots(figsize=(8, 6))
    data_cer = [
        [r["R0_cer"] for r in results],
        [r["R1_cer"] for r in results],
        [r["R2_cer"] for r in results],
        [r["R3_cer"] for r in results],
    ]
    bp = ax.boxplot(data_cer, tick_labels=["R0 (Raw)", "R1 (Prepared)", "R2 (Binary)", "R3 (Ruled)"], patch_artist=True)
    colors = ["#4e79a7", "#59a14f", "#e15759", "#edc948"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    for i, col_data in enumerate(data_cer):
        jitter = np.random.normal(0, 0.04, size=len(col_data))
        ax.scatter(np.full_like(col_data, i + 1) + jitter, col_data, color="black", alpha=0.6, s=25, zorder=3)

    ax.set_ylabel("Character Error Rate (CER)", fontsize=11, fontweight="bold")
    ax.set_title(f"Phase 8.5: CER Distribution Across All Controlled Test Cases (N={len(results)})", fontsize=12, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    p2 = os.path.join(OUTPUT_DIR, "phase8_5_cer_distribution.png")
    plt.savefig(p2, dpi=150)
    plt.close()
    print(f"  Saved: {p2}")

    # 3. phase8_5_failure_analysis.png (Categorized Effects: Improvement vs Degradation)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    
    cat_mapping = [
        ("Clean", ["A_"]),
        ("Ruled Paper", ["B_", "C_"]),
        ("Sensor Noise", ["D_", "E_"]),
        ("Low Contrast", ["F_", "G_"]),
        ("Shadow", ["H_"]),
        ("Skew", ["I_", "J_"]),
        ("Rotation", ["K_", "L_", "M_"]),
        ("Combined", ["N_", "O_"]),
    ]

    cat_deltas_r1_r0 = []
    cat_deltas_r2_r1 = []
    cat_names = []

    for cat_name, prefixes in cat_mapping:
        matching = [r for r in results if any(r["case_id"].startswith(p) for p in prefixes)]
        if matching:
            d_r10 = float(np.mean([m["R1_cer"] - m["R0_cer"] for m in matching]))
            d_r21 = float(np.mean([m["R2_cer"] - m["R1_cer"] for m in matching]))
            cat_deltas_r1_r0.append(d_r10)
            cat_deltas_r2_r1.append(d_r21)
            cat_names.append(cat_name)

    bar_cols1 = ["#59a14f" if d < -0.005 else ("#e15759" if d > 0.005 else "#79706e") for d in cat_deltas_r1_r0]
    ax1.barh(cat_names, cat_deltas_r1_r0, color=bar_cols1)
    ax1.axvline(0, color="black", linestyle="-", linewidth=1)
    ax1.set_xlabel("Mean CER Delta (R1 - R0)\n[< 0 indicates R1 Preparation Improves]", fontsize=10, fontweight="bold")
    ax1.set_title("Preparation Effect: R1 vs R0", fontsize=11, fontweight="bold")
    ax1.grid(axis="x", linestyle="--", alpha=0.5)

    bar_cols2 = ["#e15759" if d > 0.005 else ("#59a14f" if d < -0.005 else "#79706e") for d in cat_deltas_r2_r1]
    ax2.barh(cat_names, cat_deltas_r2_r1, color=bar_cols2)
    ax2.axvline(0, color="black", linestyle="-", linewidth=1)
    ax2.set_xlabel("Mean CER Delta (R2 - R1)\n[> 0 indicates Binarization Degrades]", fontsize=10, fontweight="bold")
    ax2.set_title("Binarization Impact: R2 vs R1", fontsize=11, fontweight="bold")
    ax2.grid(axis="x", linestyle="--", alpha=0.5)

    plt.suptitle("Phase 8.5: Failure & Sensitivity Mode Decomposition by Document Condition", fontsize=12, fontweight="bold")
    plt.tight_layout()
    p3 = os.path.join(OUTPUT_DIR, "phase8_5_failure_analysis.png")
    plt.savefig(p3, dpi=150)
    plt.close()
    print(f"  Saved: {p3}")

    # 4. phase8_5_evaluation_matrix.png (Heatmap Table of CER & Line Counts)
    fig, ax = plt.subplots(figsize=(10, 8))
    table_matrix = []
    col_labels = ["R0 CER", "R1 CER", "R2 CER", "R3 CER"]
    row_labels = [r["case_id"] for r in results]

    for r in results:
        table_matrix.append([r["R0_cer"], r["R1_cer"], r["R2_cer"], r["R3_cer"]])

    arr_mat = np.array(table_matrix)
    im = ax.imshow(arr_mat, cmap="YlOrRd", vmin=0.0, vmax=1.0, aspect="auto")

    ax.set_xticks(np.arange(len(col_labels)))
    ax.set_yticks(np.arange(len(row_labels)))
    ax.set_xticklabels(col_labels, fontsize=10, fontweight="bold")
    ax.set_yticklabels(row_labels, fontsize=9)

    for i in range(len(row_labels)):
        for j in range(len(col_labels)):
            val = arr_mat[i, j]
            txt_col = "white" if val > 0.55 else "black"
            ax.text(j, i, f"{val:.4f}", ha="center", va="center", color=txt_col, fontsize=8)

    cbar = ax.figure.colorbar(im, ax=ax)
    cbar.ax.set_ylabel("CER", rotation=-90, va="bottom", fontweight="bold")
    ax.set_title("Phase 8.5: Controlled Recognition CER Evaluation Matrix", fontsize=12, fontweight="bold")
    plt.tight_layout()
    p4 = os.path.join(OUTPUT_DIR, "phase8_5_evaluation_matrix.png")
    plt.savefig(p4, dpi=150)
    plt.close()
    print(f"  Saved: {p4}")


# ===========================================================================
# 8. CSV EXPORT
# ===========================================================================

def export_results_to_csv(results: List[Dict[str, Any]], real_results: Dict[str, Any]) -> str:
    """Exports structured metrics to CSV."""
    csv_path = os.path.join(OUTPUT_DIR, "phase8_5_representation_evaluation.csv")
    fieldnames = [
        "case_id", "category", "gt_char_len", "pvr", "line_collision", "median_char_height",
        "detected_orientation", "detected_skew",
        "R0_cer", "R0_wer", "R0_lines", "R0_chars", "R0_latency_ms",
        "R1_cer", "R1_wer", "R1_lines", "R1_chars", "R1_latency_ms",
        "R2_cer", "R2_wer", "R2_lines", "R2_chars", "R2_latency_ms",
        "R3_cer", "R3_wer", "R3_lines", "R3_chars", "R3_latency_ms",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    print(f"[Phase 8.5] Results exported to CSV: {csv_path}")
    return csv_path


# ===========================================================================
# 9. MAIN ENTRY POINT
# ===========================================================================

def main() -> None:
    print("=" * 80)
    print("PHASE 8.5: RECOGNITION REPRESENTATION EVALUATION & CONTROLLED OCR EVIDENCE")
    print("=" * 80)

    try:
        ocr_runner = WindowsMediaOcrRunner()
    except Exception as e:
        print(f"[CRITICAL ERROR] Failed to initialize OCR Runner: {e}")
        return

    # Execute controlled suite
    results, real_results = run_controlled_experiments(ocr_runner)

    # Analyze statistics
    stats = analyze_representation_effects(results)

    print("\n" + "=" * 80)
    print("EMPIRICAL EVALUATION SUMMARY (N=15 controlled cases):")
    print("-" * 80)
    print(f"Mean CER:   R0={stats['R0_CER_mean']:.4f} | R1={stats['R1_CER_mean']:.4f} | R2={stats['R2_CER_mean']:.4f} | R3={stats['R3_CER_mean']:.4f}")
    print(f"Median CER: R0={stats['R0_CER_median']:.4f} | R1={stats['R1_CER_median']:.4f} | R2={stats['R2_CER_median']:.4f} | R3={stats['R3_CER_median']:.4f}")
    print("-" * 80)
    print(f"R1 vs R0: Improved in {stats['R1_vs_R0_improved']}, Degraded in {stats['R1_vs_R0_degraded']}, No Material Diff in {stats['R1_vs_R0_no_material_diff']}")
    print(f"R2 vs R1: Improved in {stats['R2_vs_R1_improved']}, Degraded in {stats['R2_vs_R1_degraded']}, No Material Diff in {stats['R2_vs_R1_no_material_diff']}")
    print(f"R3 vs R1: Improved in {stats['R3_vs_R1_improved']}, Degraded in {stats['R3_vs_R1_degraded']}, No Material Diff in {stats['R3_vs_R1_no_material_diff']}")
    print("NOTE: 'No Material Diff' uses an exploratory comparison criterion (|ΔCER| <= 0.01)")
    print("      solely for internal analysis in Phase 8.5; not a production threshold and not frozen.")
    print("=" * 80)

    # Generate plots and CSV
    generate_visual_artifacts(results, stats, real_results)
    export_results_to_csv(results, real_results)

    print("\n[Phase 8.5] Investigation complete. Ready to synthesize findings into report.")


if __name__ == "__main__":
    main()
