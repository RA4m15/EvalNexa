"""
phase8/02_ocr_correlation_investigation.py

AI-EVAL PHASE 8.3: OCR/HTR CORRELATION INVESTIGATION
====================================================

PURPOSE:
Investigate and determine empirically how the image representations and
topological telemetry produced by Phase 8.2 relate to actual downstream
OCR/HTR recognition performance (CER, WER, Line Detection, Recognition Failures).

KEY RESEARCH QUESTIONS:
1. Multi-Representation Comparison:
   How do R0 (Raw Grayscale), R1 (Phase 8.2 Prepared Grayscale),
   R2 (Phase 8.2 Binary Derivative), and R3 (Phase 8.2 Ruled-Line Handled)
   compare in downstream OCR Character Error Rate (CER) and Word Error Rate (WER)?
2. The Binarization Trap:
   Does feeding a binary derivative (R2) into modern neural OCR degrade or improve
   accuracy compared to normalized grayscale (R1)? Why?
3. Reading Orientation Impact:
   What is the quantitative failure mode of rotated text (90°, 180°, 270°)?
   Does OCR fail completely (CER=1.0) or hallucinate spurious tokens?
4. Baseline Skew Sensitivity:
   At what tilt angle (|theta| in [0°, 4°]) does line-level segmentation degrade,
   and how much error is eliminated by Phase 8.2 fine baseline deskew?
5. Ruled-Line Interference & Suppression Trade-Off:
   Does morphological ruling line suppression eliminate spurious hyphens/underscores,
   or does it risk eroding genuine handwriting characters?
6. Telemetry Correlation:
   Which Phase 8.2 signals (PVR, line collision ratio, character height, stroke width)
   strongly correlate with downstream recognition performance?

GUARDRAILS:
- INVESTIGATION ONLY.
- DO NOT modify phase2/, phase3/, phase4/, phase5/, phase6/, or phase7/.
- DO NOT modify Phase 8.2 production engine code.
- DO NOT train or fine-tune models.
- DO NOT freeze production thresholds.
- STOP after Phase 8.3.
"""

from __future__ import annotations

import os
import sys
import math
import time
import asyncio
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from dataclasses import dataclass, field

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# WinRT Offline Windows Media OCR bindings
import winrt.windows.storage as ws
import winrt.windows.graphics.imaging as wgi
import winrt.windows.media.ocr as wmo

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

# Phase 8.2 Production Modules
from phase8.ocr_readiness_contracts import (
    ReadingOrientation,
    OCRReadinessVerdict,
    ProvisionalReadinessObservation,
    PreprocessedImageBundle,
    TextTopologyMetrics,
    ReadinessPreparationConfig,
    OCRReadinessPreparationResult,
)
from phase8.ocr_readiness_engine import prepare_ocr_readiness


# ===========================================================================
# 1. OCR ENGINE & EDIT DISTANCE INFRASTRUCTURE
# ===========================================================================

def levenshtein_distance(seq1: Sequence[Any], seq2: Sequence[Any]) -> int:
    """
    Standard dynamic programming Levenshtein distance between two sequences.
    """
    m, n = len(seq1), len(seq2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i - 1] == seq2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[m][n]


def normalize_ocr_text(text: str) -> str:
    """
    Normalizes whitespace and standardizes formatting for fair comparison.
    """
    return " ".join(text.strip().split())


def compute_transcription_metrics(gt_text: str, hyp_text: str) -> Dict[str, float]:
    """
    Computes Character Error Rate (CER), Word Error Rate (WER),
    Character Accuracy, and Failure indicator.
    """
    norm_gt = normalize_ocr_text(gt_text)
    norm_hyp = normalize_ocr_text(hyp_text)

    # 1. Character Error Rate (CER)
    gt_chars = list(norm_gt)
    hyp_chars = list(norm_hyp)
    n_chars = max(1, len(gt_chars))
    edit_dist_char = levenshtein_distance(gt_chars, hyp_chars)
    cer = float(edit_dist_char / n_chars)

    # 2. Word Error Rate (WER)
    gt_words = norm_gt.split() if norm_gt else []
    hyp_words = norm_hyp.split() if norm_hyp else []
    n_words = max(1, len(gt_words))
    edit_dist_word = levenshtein_distance(gt_words, hyp_words)
    wer = float(edit_dist_word / n_words)

    char_acc = float(max(0.0, 1.0 - cer))
    is_failure = bool(cer >= 0.85 or len(norm_hyp) == 0)

    return {
        "cer": cer,
        "wer": wer,
        "char_accuracy": char_acc,
        "is_failure": float(1.0 if is_failure else 0.0),
        "gt_len": float(len(norm_gt)),
        "hyp_len": float(len(norm_hyp)),
        "edit_dist_char": float(edit_dist_char),
        "edit_dist_word": float(edit_dist_word),
    }


class WindowsMediaOcrRunner:
    """
    Asynchronous and synchronous wrapper for the native Windows Media Neural OCR Engine.
    Executes recognition offline directly on in-memory images.
    """
    def __init__(self):
        self._engine = wmo.OcrEngine.try_create_from_user_profile_languages()
        if self._engine is None:
            raise RuntimeError("Windows Media OCR Engine failed to initialize.")

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
            full_text = "\n".join(lines)
            return full_text, lines
        except Exception as e:
            return f"", []
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def recognize(self, image: np.ndarray) -> Tuple[str, List[str]]:
        return asyncio.run(self.recognize_async(image))


# ===========================================================================
# 2. STATISTICAL UTILITIES (PURE NUMPY)
# ===========================================================================

def compute_pearson_correlation(x: Sequence[float], y: Sequence[float]) -> float:
    """Computes Pearson correlation coefficient r."""
    arr_x = np.asarray(x, dtype=np.float64)
    arr_y = np.asarray(y, dtype=np.float64)
    if len(arr_x) < 2 or np.std(arr_x) < 1e-9 or np.std(arr_y) < 1e-9:
        return 0.0
    r = float(np.corrcoef(arr_x, arr_y)[0, 1])
    return 0.0 if np.isnan(r) else r


def compute_spearman_correlation(x: Sequence[float], y: Sequence[float]) -> float:
    """Computes Spearman rank correlation rho."""
    arr_x = np.asarray(x, dtype=np.float64)
    arr_y = np.asarray(y, dtype=np.float64)
    if len(arr_x) < 2:
        return 0.0
    rank_x = np.argsort(np.argsort(arr_x))
    rank_y = np.argsort(np.argsort(arr_y))
    return compute_pearson_correlation(rank_x, rank_y)


# ===========================================================================
# 3. VERIFIED GROUND TRUTH STRINGS & BENCHMARKS
# ===========================================================================

GT_ANSWER_SHEET_2_HEADER = (
    "TAGORE PUBLIC SCHOOL, ALLAHABAD\n"
    "EXAMINATION ANSWER SHEET\n"
    "Roll No. Name of Examination\n"
    "Class & Section Day & Date Subject History"
)

GT_ANSWER_SHEET_2_BODY = (
    "Many towns in Italy fell into ruin after the fall of the Roman empire "
    "because there was no unified government and the Pope was not a strong political figure. "
    "Two architects immortalized by their work were Michelangelo Buonarroti who designed "
    "the dome of St. Peter's and Filippo Brunelleschi who designed the dome of Florence cathedral."
)

GT_SYNTHETIC_TEXT_BLOCK = (
    "Machine learning models require clean, uncorrupted input representations. "
    "When characters are rotated sideways or baselines are tilted by several degrees, "
    "horizontal projection profiling fails and character tokenizers become confused. "
    "Phase 8.2 prepares normalized grayscale images to safeguard downstream transcription."
)


# ===========================================================================
# 4. REPRESENTATION BUILDERS (R0, R1, R2, R3)
# ===========================================================================

def generate_four_representations(
    source_bgr: np.ndarray,
    document_id: str = "doc"
) -> Tuple[Dict[str, np.ndarray], OCRReadinessPreparationResult]:
    """
    Extracts R0, R1, R2, R3 representations without mutating the master source.
    - R0: Raw grayscale (no enhancement, no de-rotation, no deskew).
    - R1: Phase 8.2 prepared grayscale (de-rotated, deskewed, normalized).
    - R2: Phase 8.2 binary derivative (adaptive binarization mask).
    - R3: Phase 8.2 ruled-line handled representation (rule lines suppressed via horizontal inpainting).
    """
    # R0: Raw minimally processed grayscale
    r0_gray = cv2.cvtColor(source_bgr, cv2.COLOR_BGR2GRAY)

    # Execute Phase 8.2 Preprocessing Engine
    p8_res = prepare_ocr_readiness(source_bgr, document_id=document_id)
    bundle = p8_res.image_bundle

    # R1: Phase 8.2 prepared grayscale
    r1_gray = bundle.ready_gray.copy()

    # R2: Phase 8.2 binary derivative (inverted to dark text on white substrate for OCR engines)
    # Windows OCR expects black text on white substrate or white text on black substrate
    r2_bin = cv2.bitwise_not(bundle.ready_bin)

    # R3: Ruled-line handled representation
    if bundle.rule_lines_mask is not None and np.count_nonzero(bundle.rule_lines_mask) > 50:
        # Dilate rule mask slightly and inpaint horizontal ruling lines
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3))
        dilated_rule = cv2.dilate(bundle.rule_lines_mask, kernel, iterations=1)
        r3_ruled = cv2.inpaint(r1_gray, dilated_rule, inpaintRadius=2, flags=cv2.INPAINT_TELEA)
    else:
        # If unruled, R3 is identical to R1
        r3_ruled = r1_gray.copy()

    reps = {
        "R0_Raw": r0_gray,
        "R1_Prepared_Gray": r1_gray,
        "R2_Binary": r2_bin,
        "R3_Ruled_Handled": r3_ruled,
    }

    return reps, p8_res


# ===========================================================================
# 5. EXPERIMENT 1: MULTI-REPRESENTATION BENCHMARK (R0 vs R1 vs R2 vs R3)
# ===========================================================================

def run_experiment_1_representation_benchmark(
    ocr_runner: WindowsMediaOcrRunner
) -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print("EXPERIMENT 1: MULTI-REPRESENTATION RECOGNITION BENCHMARK (R0 vs R1 vs R2 vs R3)")
    print("=" * 80)

    # 1. Test Sheet: Synthetic Standard Text Sheet (Ground Truth = GT_SYNTHETIC_TEXT_BLOCK)
    h, w = 900, 1200
    canvas = np.full((h, w, 3), 245, dtype=np.uint8)
    cv2.putText(canvas, "Machine learning models require clean, uncorrupted input representations.", (60, 150),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (25, 25, 25), 2)
    cv2.putText(canvas, "When characters are rotated sideways or baselines are tilted by several degrees,", (60, 250),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (25, 25, 25), 2)
    cv2.putText(canvas, "horizontal projection profiling fails and character tokenizers become confused.", (60, 350),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (25, 25, 25), 2)
    cv2.putText(canvas, "Phase 8.2 prepares normalized grayscale images to safeguard downstream transcription.", (60, 450),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (25, 25, 25), 2)

    # Add ruling lines to test R3
    for y in range(165, 550, 100):
        cv2.line(canvas, (40, y), (w - 40, y), (180, 180, 180), 2)

    reps, p8_res = generate_four_representations(canvas, document_id="benchmark_synthetic")

    results = {}
    print(f"\nEvaluating representations for Synthetic Benchmark Document:")
    for rep_name, img in reps.items():
        t0 = time.perf_counter()
        hyp_text, lines = ocr_runner.recognize(img)
        lat_ms = (time.perf_counter() - t0) * 1000.0

        metrics = compute_transcription_metrics(GT_SYNTHETIC_TEXT_BLOCK, hyp_text)
        results[rep_name] = {
            "metrics": metrics,
            "hyp_text": hyp_text,
            "line_count": len(lines),
            "latency_ms": lat_ms,
        }
        print(f"  {rep_name:18} -> CER: {metrics['cer']:.4f} | WER: {metrics['wer']:.4f} | Lines: {len(lines):2d} | Latency: {lat_ms:.1f}ms")
        if lines:
            print(f"     Hypothesis sample: '{lines[0][:60]}...'")

    # 2. Calibration Sheet: answer_sheet_2.png (Header block comparison)
    cal_path = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
    if os.path.exists(cal_path):
        print(f"\nEvaluating representations for Calibration Exam Sheet (answer_sheet_2.png):")
        cal_bgr = cv2.imread(cal_path)
        cal_reps, cal_p8 = generate_four_representations(cal_bgr, document_id="answer_sheet_2")

        cal_results = {}
        for rep_name, img in cal_reps.items():
            t0 = time.perf_counter()
            hyp_text, lines = ocr_runner.recognize(img)
            lat_ms = (time.perf_counter() - t0) * 1000.0

            # Compare against header ground truth
            m = compute_transcription_metrics(GT_ANSWER_SHEET_2_HEADER, hyp_text[:len(GT_ANSWER_SHEET_2_HEADER) + 50])
            cal_results[rep_name] = {
                "metrics": m,
                "total_chars": len(hyp_text),
                "total_lines": len(lines),
                "latency_ms": lat_ms,
            }
            print(f"  {rep_name:18} -> Detected Lines: {len(lines):2d} | Total Chars: {len(hyp_text):4d} | Header CER: {m['cer']:.4f} | Latency: {lat_ms:.1f}ms")
        results["calibration_sheet"] = cal_results

    return results


# ===========================================================================
# 6. EXPERIMENT 2: READING ORIENTATION DEGRADATION SWEEP
# ===========================================================================

def run_experiment_2_orientation_sweep(
    ocr_runner: WindowsMediaOcrRunner
) -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print("EXPERIMENT 2: READING ORIENTATION IMPACT & DE-ROTATION RECOVERY")
    print("=" * 80)

    # Create clean upright text sheet with header
    h, w = 1000, 800
    base_canvas = np.full((h, w, 3), 245, dtype=np.uint8)
    cv2.rectangle(base_canvas, (60, 50), (w - 60, 110), (40, 40, 40), -1)
    cv2.putText(base_canvas, "ACADEMIC EXAM EVALUATION PORTAL", (80, 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (245, 245, 245), 2)

    lines_text = [
        "First question requires thorough explanation of mathematical models.",
        "Differential calculus is fundamental to machine learning optimization.",
        "Gradient descent iteratively updates model weights along the steepest descent.",
        "Loss functions compute the quantitative penalty between predictions and targets."
    ]
    gt_orient = "\n".join(lines_text)

    for idx, line in enumerate(lines_text):
        cv2.putText(base_canvas, line, (60, 200 + (idx * 90)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (30, 30, 30), 2)

    quadrants = [
        ("0° UPRIGHT", base_canvas, ReadingOrientation.UPRIGHT_0),
        ("90° ROTATED CW", cv2.rotate(base_canvas, cv2.ROTATE_90_CLOCKWISE), ReadingOrientation.ROTATED_90_CW),
        ("180° INVERTED", cv2.rotate(base_canvas, cv2.ROTATE_180), ReadingOrientation.ROTATED_180_INVERTED),
        ("270° ROTATED CCW", cv2.rotate(base_canvas, cv2.ROTATE_90_COUNTERCLOCKWISE), ReadingOrientation.ROTATED_270_CCW),
    ]

    sweep_results = {}

    for label, canvas_rot, expected_orient in quadrants:
        # A. Uncorrected OCR (feeding raw rotated canvas)
        hyp_uncorrected, lines_uncorr = ocr_runner.recognize(canvas_rot)
        m_uncorr = compute_transcription_metrics(gt_orient, hyp_uncorrected)

        # B. Phase 8.2 Corrected OCR (feeding Phase 8.2 R1 prepared gray)
        p8_res = prepare_ocr_readiness(canvas_rot, document_id=label)
        ready_gray = p8_res.image_bundle.ready_gray
        hyp_corrected, lines_corr = ocr_runner.recognize(ready_gray)
        m_corr = compute_transcription_metrics(gt_orient, hyp_corrected)

        sweep_results[label] = {
            "uncorrected": {"cer": m_uncorr["cer"], "lines": len(lines_uncorr), "text": hyp_uncorrected},
            "corrected": {"cer": m_corr["cer"], "lines": len(lines_corr), "text": hyp_corrected},
            "detected_orientation": p8_res.detected_orientation.value,
            "applied_rotation_deg": p8_res.applied_rotation_deg,
        }

        print(f"  {label:18} -> Uncorrected CER: {m_uncorr['cer']:.4f} (Lines: {len(lines_uncorr):2d}) | Phase 8.2 Corrected CER: {m_corr['cer']:.4f} (Lines: {len(lines_corr):2d})")

    return sweep_results


# ===========================================================================
# 7. EXPERIMENT 3: BASELINE SKEW SENSITIVITY SWEEP
# ===========================================================================

def run_experiment_3_skew_sweep(
    ocr_runner: WindowsMediaOcrRunner
) -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print("EXPERIMENT 3: RESIDUAL BASELINE SKEW SENSITIVITY & DESKEW BENEFIT")
    print("=" * 80)

    # Base horizontal text canvas
    h, w = 900, 1100
    base_canvas = np.full((h, w), 245, dtype=np.uint8)
    cv2.rectangle(base_canvas, (60, 40), (w - 60, 95), 40, -1)
    cv2.putText(base_canvas, "DEPARTMENT OF COMPUTER SCIENCE", (80, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, 245, 2)

    text_rows = [
        "Autonomous document evaluation requires precise spatial alignment.",
        "Sub-orthogonal tilt distorts horizontal bounding box projections.",
        "Lines of text begin colliding vertically when tilt exceeds two degrees.",
        "Fine baseline deskew restores strictly horizontal baseline projection peaks.",
        "Word segmentation accuracy is directly proportional to projection sharpness."
    ]
    gt_skew = "\n".join(text_rows)

    for idx, row in enumerate(text_rows):
        cv2.putText(base_canvas, row, (60, 180 + (idx * 80)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, 30, 2)

    angles = [-3.5, -2.0, -1.0, 0.0, 1.0, 2.0, 3.5]
    skew_results = {}

    center = (w // 2, h // 2)

    for angle in angles:
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        tilted = cv2.warpAffine(base_canvas, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

        # Uncorrected OCR
        hyp_uncorr, lines_uncorr = ocr_runner.recognize(tilted)
        m_uncorr = compute_transcription_metrics(gt_skew, hyp_uncorr)

        # Phase 8.2 Preprocessed OCR
        p8_res = prepare_ocr_readiness(tilted, document_id=f"skew_{angle}")
        hyp_corr, lines_corr = ocr_runner.recognize(p8_res.image_bundle.ready_gray)
        m_corr = compute_transcription_metrics(gt_skew, hyp_corr)

        skew_results[angle] = {
            "uncorrected_cer": m_uncorr["cer"],
            "corrected_cer": m_corr["cer"],
            "detected_skew_deg": p8_res.detected_skew_angle_deg,
            "applied_deskew_deg": p8_res.applied_deskew_angle_deg,
            "pvr_raw": p8_res.metrics.peak_to_valley_ratio,
        }

        print(f"  Tilt: {angle:+4.1f}° -> Uncorrected CER: {m_uncorr['cer']:.4f} | Phase 8.2 Deskewed CER: {m_corr['cer']:.4f} (Detected: {p8_res.detected_skew_angle_deg:+.2f}°)")

    return skew_results


# ===========================================================================
# 8. EXPERIMENT 4: TELEMETRY SIGNALS VS OCR CER CORRELATION
# ===========================================================================

def run_experiment_4_telemetry_correlation(
    ocr_runner: WindowsMediaOcrRunner
) -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print("EXPERIMENT 4: PHASE 8.2 TELEMETRY SIGNALS VS DOWNSTREAM CER CORRELATION")
    print("=" * 80)

    # Evaluate correlation across a cohort of varied degradation and scale conditions
    trials = []

    # 1. Scale variation sweep (Character heights 8px to 32px)
    for font_scale in [0.35, 0.45, 0.55, 0.70, 0.85, 1.10]:
        canvas = np.full((700, 1000), 245, dtype=np.uint8)
        sentence = "Optical character recognition requires adequate stroke resolution."
        cv2.putText(canvas, sentence, (60, 200), cv2.FONT_HERSHEY_SIMPLEX, font_scale, 25, 2)
        cv2.putText(canvas, "Connected components below twelve pixels collapse letter loops.", (60, 320), cv2.FONT_HERSHEY_SIMPLEX, font_scale, 25, 2)
        gt = f"{sentence}\nConnected components below twelve pixels collapse letter loops."

        p8_res = prepare_ocr_readiness(canvas, document_id=f"scale_{font_scale}")
        hyp, _ = ocr_runner.recognize(p8_res.image_bundle.ready_gray)
        m = compute_transcription_metrics(gt, hyp)

        trials.append({
            "name": f"scale_{font_scale}",
            "cer": m["cer"],
            "wer": m["wer"],
            "pvr": p8_res.metrics.peak_to_valley_ratio,
            "collision_ratio": p8_res.metrics.line_collision_ratio,
            "char_h": p8_res.metrics.median_char_height_px,
            "stroke_w": p8_res.metrics.estimated_stroke_width_px,
            "rule_collision": p8_res.metrics.ruled_line_stroke_collision_ratio,
        })

    # 2. Line spacing / collision variation sweep
    for line_gap in [25, 35, 50, 70, 95]:
        canvas = np.full((700, 1000), 245, dtype=np.uint8)
        lines = [
            "Ascenders reach upward toward the previous line text.",
            "Descenders reach downward toward the subsequent line.",
            "Tight line spacing causes glyph ascenders to collide."
        ]
        gt = "\n".join(lines)
        for i, l in enumerate(lines):
            cv2.putText(canvas, l, (60, 150 + (i * line_gap)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, 30, 2)

        p8_res = prepare_ocr_readiness(canvas, document_id=f"gap_{line_gap}")
        hyp, _ = ocr_runner.recognize(p8_res.image_bundle.ready_gray)
        m = compute_transcription_metrics(gt, hyp)

        trials.append({
            "name": f"gap_{line_gap}",
            "cer": m["cer"],
            "wer": m["wer"],
            "pvr": p8_res.metrics.peak_to_valley_ratio,
            "collision_ratio": p8_res.metrics.line_collision_ratio,
            "char_h": p8_res.metrics.median_char_height_px,
            "stroke_w": p8_res.metrics.estimated_stroke_width_px,
            "rule_collision": p8_res.metrics.ruled_line_stroke_collision_ratio,
        })

    # Compute correlation coefficients against CER
    cers = [t["cer"] for t in trials]
    pvrs = [t["pvr"] for t in trials]
    collisions = [t["collision_ratio"] for t in trials]
    char_hs = [t["char_h"] for t in trials]
    stroke_ws = [t["stroke_w"] for t in trials]

    corr_pvr_r = compute_pearson_correlation(pvrs, cers)
    corr_pvr_rho = compute_spearman_correlation(pvrs, cers)

    corr_coll_r = compute_pearson_correlation(collisions, cers)
    corr_coll_rho = compute_spearman_correlation(collisions, cers)

    corr_charh_r = compute_pearson_correlation(char_hs, cers)
    corr_charh_rho = compute_spearman_correlation(char_hs, cers)

    print("\nStatistical Correlation with Downstream Character Error Rate (CER):")
    print(f"  1. Peak-to-Valley Ratio (PVR):      Pearson r = {corr_pvr_r:+.4f} | Spearman rho = {corr_pvr_rho:+.4f}")
    print(f"  2. Line Collision Ratio:            Pearson r = {corr_coll_r:+.4f} | Spearman rho = {corr_coll_rho:+.4f}")
    print(f"  3. Character Height (x-height px):  Pearson r = {corr_charh_r:+.4f} | Spearman rho = {corr_charh_rho:+.4f}")

    return {
        "trials": trials,
        "pvr_corr": (corr_pvr_r, corr_pvr_rho),
        "collision_corr": (corr_coll_r, corr_coll_rho),
        "char_height_corr": (corr_charh_r, corr_charh_rho),
    }


# ===========================================================================
# 9. DIAGNOSTIC VISUALIZATION GENERATOR
# ===========================================================================

def generate_phase8_3_visualizations(
    exp1_res: Dict[str, Any],
    exp2_res: Dict[str, Any],
    exp3_res: Dict[str, Any],
    exp4_res: Dict[str, Any]
) -> None:
    print("\n--- Generating Phase 8.3 Diagnostic Visualizations ---")

    # 1. Figure 1: Representation CER/WER Comparison (R0 vs R1 vs R2 vs R3)
    fig, ax = plt.subplots(figsize=(10, 5))
    rep_names = ["R0_Raw", "R1_Prepared_Gray", "R2_Binary", "R3_Ruled_Handled"]
    cers = [exp1_res[r]["metrics"]["cer"] for r in rep_names]
    wers = [exp1_res[r]["metrics"]["wer"] for r in rep_names]

    x = np.arange(len(rep_names))
    width = 0.35

    ax.bar(x - width/2, cers, width, label="CER (Character Error Rate)", color="#d9534f")
    ax.bar(x + width/2, wers, width, label="WER (Word Error Rate)", color="#0275d8")
    ax.set_ylabel("Error Rate")
    ax.set_title("Phase 8.3: Downstream OCR Error Rate by Representation (R0 vs R1 vs R2 vs R3)")
    ax.set_xticks(x)
    ax.set_xticklabels(["R0: Raw Gray", "R1: Phase 8.2 Gray", "R2: Binary Mask", "R3: Ruled Handled"])
    ax.set_ylim(0, 1.05)
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    ax.legend()
    fig.tight_layout()
    fpath1 = os.path.join(OUTPUT_DIR, "phase8_3_representation_cer_wer_comparison.png")
    fig.savefig(fpath1, dpi=180)
    plt.close(fig)
    print(f"  Saved: {fpath1}")

    # 2. Figure 2: Orientation Degradation Profile
    fig, ax = plt.subplots(figsize=(10, 5))
    orients = list(exp2_res.keys())
    uncorr_cers = [exp2_res[o]["uncorrected"]["cer"] for o in orients]
    corr_cers = [exp2_res[o]["corrected"]["cer"] for o in orients]

    x = np.arange(len(orients))
    ax.bar(x - width/2, uncorr_cers, width, label="Uncorrected Input (Raw Orientation)", color="#e74c3c")
    ax.bar(x + width/2, corr_cers, width, label="Phase 8.2 Normalization (De-Rotated)", color="#2ecc71")
    ax.set_ylabel("Character Error Rate (CER)")
    ax.set_title("Phase 8.3: Reading Orientation Impact on Downstream OCR Transcription")
    ax.set_xticks(x)
    ax.set_xticklabels(orients)
    ax.set_ylim(0, 1.1)
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    ax.legend()
    fig.tight_layout()
    fpath2 = os.path.join(OUTPUT_DIR, "phase8_3_orientation_degradation_profile.png")
    fig.savefig(fpath2, dpi=180)
    plt.close(fig)
    print(f"  Saved: {fpath2}")

    # 3. Figure 3: Skew Angle vs OCR Error
    fig, ax = plt.subplots(figsize=(9, 5))
    angles = sorted(list(exp3_res.keys()))
    uncorr_skew_cers = [exp3_res[a]["uncorrected_cer"] for a in angles]
    corr_skew_cers = [exp3_res[a]["corrected_cer"] for a in angles]

    ax.plot(angles, uncorr_skew_cers, "o-", color="#c0392b", linewidth=2.0, label="Raw Tilted Canvas (Uncorrected)")
    ax.plot(angles, corr_skew_cers, "s--", color="#27ae60", linewidth=2.0, label="Phase 8.2 Deskewed Canvas")
    ax.set_xlabel("Injected Line Skew Angle (Degrees)")
    ax.set_ylabel("Character Error Rate (CER)")
    ax.set_title("Phase 8.3: Residual Baseline Skew vs OCR Character Error Rate")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.legend()
    fig.tight_layout()
    fpath3 = os.path.join(OUTPUT_DIR, "phase8_3_skew_angle_vs_ocr_error.png")
    fig.savefig(fpath3, dpi=180)
    plt.close(fig)
    print(f"  Saved: {fpath3}")

    # 4. Figure 4: Scale Cliff & Telemetry Scatter
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    trials = exp4_res["trials"]
    char_hs = [t["char_h"] for t in trials]
    cers = [t["cer"] for t in trials]
    pvrs = [t["pvr"] for t in trials]

    ax1.scatter(char_hs, cers, color="#8e44ad", s=60, edgecolors="black")
    ax1.set_xlabel("Median Character Height (px)")
    ax1.set_ylabel("Character Error Rate (CER)")
    ax1.set_title(f"Character Scale vs CER (r = {exp4_res['char_height_corr'][0]:.2f})")
    ax1.axvline(12.0, color="red", linestyle="--", label="Provisional Scale Floor (12px)")
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend()

    ax2.scatter(pvrs, cers, color="#2980b9", s=60, edgecolors="black")
    ax2.set_xlabel("Peak-to-Valley Ratio (PVR)")
    ax2.set_ylabel("Character Error Rate (CER)")
    ax2.set_title(f"Line Separation (PVR) vs CER (r = {exp4_res['pvr_corr'][0]:.2f})")
    ax2.grid(True, linestyle="--", alpha=0.5)

    fig.tight_layout()
    fpath4 = os.path.join(OUTPUT_DIR, "phase8_3_scale_cliff_and_telemetry_correlation.png")
    fig.savefig(fpath4, dpi=180)
    plt.close(fig)
    print(f"  Saved: {fpath4}")


# ===========================================================================
# 10. MAIN EXECUTION CONTROLLER
# ===========================================================================

def run_phase8_3_investigation():
    print("=" * 80)
    print("STARTING PHASE 8.3: OCR/HTR CORRELATION EVIDENCE INVESTIGATION")
    print("=" * 80)

    ocr_runner = WindowsMediaOcrRunner()

    # Execute all 4 investigation experiments
    exp1_res = run_experiment_1_representation_benchmark(ocr_runner)
    exp2_res = run_experiment_2_orientation_sweep(ocr_runner)
    exp3_res = run_experiment_3_skew_sweep(ocr_runner)
    exp4_res = run_experiment_4_telemetry_correlation(ocr_runner)

    # Generate diagnostic visualizations
    generate_phase8_3_visualizations(exp1_res, exp2_res, exp3_res, exp4_res)

    print("\n" + "=" * 80)
    print("PHASE 8.3 INVESTIGATION COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    run_phase8_3_investigation()
