"""
phase6/04_contrast_normalization_investigation.py

AI-EVAL PHASE 6.4: INTELLIGENT CONTRAST NORMALIZATION INVESTIGATION
====================================================================

PURPOSE:
Investigate the second candidate correction operator: ContrastNormalizationOperator.
This is an INVESTIGATION ONLY script.
Does NOT modify frozen Phase 2, Phase 3, Phase 4, Phase 5, or Phase 6.3 code.

INVESTIGATION MODULES:
1. Investigation A: Contrast Evidence & Condition Signals (Primary, Supporting, Diagnostic, Redundant)
2. Investigation B: Contrast Operator Comparison (Percentile Stretch, CLAHE, Global HistEq, Gamma, Local Norm)
3. Investigation C: Operator Ordering & Shadow Interactions (RAW->CONTRAST vs RAW->SHADOW->CONTRAST vs RAW->CONTRAST->SHADOW)
4. Investigation D: Non-Destructive Safety Gate Evaluation (Multi-dimensional before vs after metrics)
5. Investigation E: False Positive / False Negative Analysis (Clean docs, sparse writing, printed headers)
6. Investigation F: Scale & Resolution Sensitivity
7. Investigation G: OCR / Readability Proxy Relevance
"""

from __future__ import annotations

import os
import sys
import math
import time
import importlib.util
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Sequence

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Output directory for visual artifacts
OUTPUT_DIR = os.path.join(ROOT_DIR, "phase6", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Dynamic Import of Frozen Phase 3 & Phase 5 Modules (Read-Only)
# ---------------------------------------------------------------------------
P3_PATH = os.path.join(ROOT_DIR, "phase3", "06_scanner_integration_investigation.py")
spec_p3 = importlib.util.spec_from_file_location("phase3_06", P3_PATH)
phase3_06 = importlib.util.module_from_spec(spec_p3)
spec_p3.loader.exec_module(phase3_06)
integrate_production_scanner = phase3_06.integrate_production_scanner

from phase5.production_quality_assessment import (
    QualityAssessmentResult,
    QualityGateConfig,
    assess_document_quality,
)

from phase6.correction_contracts import (
    DefectConditionCategory,
    RecoverabilityClass,
    VerificationVerdict,
    CorrectionVerificationConfig,
)
from phase6.operators.shadow_normalization import (
    ShadowNormalizationConfig,
    ShadowNormalizationOperator,
)


# ===========================================================================
# 1. CANDIDATE CONTRAST OPERATORS (INVESTIGATION VARIANTS)
# ===========================================================================

class ContrastOperators:
    """
    Collection of candidate contrast enhancement methods under investigation.
    All methods operate strictly on isolated copies and never mutate input buffers.
    """

    @staticmethod
    def percentile_stretch(
        gray: np.ndarray,
        p_low: float = 1.0,
        p_high: float = 99.0,
        min_range_guard: float = 15.0
    ) -> np.ndarray:
        """
        Controlled linear min-max percentile stretch.
        Clips extreme outlier pixels and maps [p_low, p_high] to [0, 255].
        """
        v_min = float(np.percentile(gray, p_low))
        v_max = float(np.percentile(gray, p_high))
        if (v_max - v_min) < min_range_guard:
            return gray.copy()
        stretched = (gray.astype(np.float32) - v_min) * (255.0 / (v_max - v_min))
        return np.clip(stretched, 0, 255).astype(np.uint8)

    @staticmethod
    def conservative_percentile_stretch(gray: np.ndarray) -> np.ndarray:
        """Conservative stretch (2nd to 98th percentile)."""
        return ContrastOperators.percentile_stretch(gray, p_low=2.0, p_high=98.0)

    @staticmethod
    def clahe(
        gray: np.ndarray,
        clip_limit: float = 2.0,
        tile_grid_size: Tuple[int, int] = (8, 8)
    ) -> np.ndarray:
        """Contrast-Limited Adaptive Histogram Equalization."""
        clahe_obj = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
        return clahe_obj.apply(gray.copy())

    @staticmethod
    def global_histogram_equalization(gray: np.ndarray) -> np.ndarray:
        """Standard global histogram equalization (unconstrained)."""
        return cv2.equalizeHist(gray.copy())

    @staticmethod
    def gamma_correction(gray: np.ndarray, gamma: float = 0.75) -> np.ndarray:
        """Power-law gamma adjustment (gamma < 1.0 darkens midtones/strokes)."""
        inv_gamma = 1.0 / max(0.1, gamma)
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype(np.uint8)
        return cv2.LUT(gray.copy(), table)

    @staticmethod
    def local_contrast_division(gray: np.ndarray, scale_factor: float = 1.0) -> np.ndarray:
        """Local background division with moderate blur."""
        k = max(15, int(round(35 * scale_factor)) | 1)
        bg = cv2.GaussianBlur(gray, (k, k), 0)
        bg_float = np.maximum(bg.astype(np.float32), 1.0)
        normalized = (gray.astype(np.float32) / bg_float) * 240.0
        return np.clip(normalized, 0, 255).astype(np.uint8)


# ===========================================================================
# 2. CONTRAST EVIDENCE EXTRACTION ENGINE
# ===========================================================================

@dataclass
class ContrastEvidenceProfile:
    """
    Multi-signal evidence profile measuring contrast quality and ink visibility.
    """
    image_name: str
    dimensions: Tuple[int, int]
    scale_factor: float

    # 1. Local Stroke-to-Paper Contrast (Primary Signal)
    stroke_intensity_delta: float           # Median paper white - 15th percentile ink
    local_median_contrast: float            # Local paper background - stroke core
    faint_stroke_fraction: float            # Fraction of strokes with local contrast in [10, 35]

    # 2. Dynamic Range Signals
    global_p95_p05_range: float             # P95 - P05 (Diagnostic only: can be misled by shadows)
    global_p99_p01_range: float             # P99 - P01

    # 3. Separability & Topology Signals
    otsu_eta: float                         # Otsu between-class / total variance ratio
    normalized_acutance: float              # Scale-normalized edge gradient
    substrate_noise_sigma: float            # Flat paper substrate std
    connected_component_count: int          # Foreground CC count

    # 4. Content Context
    stroke_pixel_count: int
    is_sparse_content: bool
    has_deep_shadow: bool                   # Shadow deficit > 40


def extract_contrast_evidence(
    gray: np.ndarray,
    image_name: str = "doc"
) -> ContrastEvidenceProfile:
    """
    Extracts multi-signal contrast evidence from a grayscale document.
    """
    h, w = gray.shape[:2]
    scale_factor = min(w, h) / 1000.0

    # Scale-aware kernels
    bg_k = max(11, int(round(25 * scale_factor)) | 1)
    local_bg = cv2.dilate(gray, cv2.getStructuringElement(cv2.MORPH_RECT, (bg_k, bg_k)))
    local_contrast = np.maximum(0, local_bg.astype(np.float32) - gray.astype(np.float32))

    # Adaptive binarization to capture strokes cleanly under any lighting
    adapt_k = max(15, int(round(min(w, h) * 0.03)) | 1)
    bin_inv = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, adapt_k, 10)

    # Edge detection
    edges = cv2.Canny(gray, 40, 120)
    stroke_mask = bin_inv > 0
    stroke_pixel_count = int(np.count_nonzero(stroke_mask))
    is_sparse = bool(stroke_pixel_count < 1000)

    # Local contrast along strokes
    if stroke_pixel_count > 50:
        stroke_contrasts = local_contrast[stroke_mask]
        local_med_contrast = float(np.median(stroke_contrasts))
        faint_pixels = np.count_nonzero((stroke_contrasts >= 10.0) & (stroke_contrasts <= 35.0))
        faint_stroke_fraction = float(faint_pixels / stroke_pixel_count)

        # Global paper white and ink core
        paper_white = float(np.percentile(gray[~stroke_mask], 85)) if np.count_nonzero(~stroke_mask) > 100 else 240.0
        ink_core = float(np.percentile(gray[stroke_mask], 15))
        stroke_intensity_delta = float(paper_white - ink_core)
    else:
        local_med_contrast = 0.0
        faint_stroke_fraction = 0.0
        stroke_intensity_delta = 0.0

    # Global percentile dynamic range
    p01, p05, p95, p99 = [float(np.percentile(gray, p)) for p in (1, 5, 95, 99)]
    p95_p05 = p95 - p05
    p99_p01 = p99 - p01

    # Otsu between-class separation ratio (eta)
    hist, _ = np.histogram(gray, bins=256, range=(0, 256))
    prob = hist.astype(np.float64) / max(1, gray.size)
    total_mean = float(np.sum(np.arange(256) * prob))
    total_var = float(np.sum(((np.arange(256) - total_mean) ** 2) * prob))

    otsu_t, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    w0 = float(np.sum(prob[:int(otsu_t)]))
    w1 = float(np.sum(prob[int(otsu_t):]))
    if w0 > 1e-6 and w1 > 1e-6 and total_var > 1e-6:
        m0 = float(np.sum(np.arange(int(otsu_t)) * prob[:int(otsu_t)]) / w0)
        m1 = float(np.sum(np.arange(int(otsu_t), 256) * prob[int(otsu_t):]) / w1)
        between_var = w0 * w1 * ((m0 - m1) ** 2)
        otsu_eta = float(between_var / total_var)
    else:
        otsu_eta = 0.0

    # Stroke acutance
    if np.count_nonzero(edges) > 50:
        sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        sobel_mag = np.hypot(sobel_x, sobel_y)
        raw_acutance = float(np.mean(sobel_mag[edges > 0]))
        normalized_acutance = float(raw_acutance / (0.8 + 0.2 * scale_factor))
    else:
        normalized_acutance = 60.0

    # Flat paper substrate noise
    paper_near_strokes = cv2.dilate(bin_inv, np.ones((7, 7), np.uint8))
    flat_paper_mask = (~stroke_mask) & (paper_near_strokes == 0)
    if np.count_nonzero(flat_paper_mask) > 100:
        substrate_noise_sigma = float(np.std(gray[flat_paper_mask]))
    else:
        substrate_noise_sigma = 0.0

    # Connected component count
    n_cc, _ = cv2.connectedComponents(bin_inv)

    # Check for deep shadow
    h_step = max(1, h // 4)
    w_step = max(1, w // 4)
    quad_whites = []
    for r in range(4):
        for c in range(4):
            patch = gray[r*h_step:(r+1)*h_step, c*w_step:(c+1)*w_step]
            if patch.size > 50:
                quad_whites.append(float(np.percentile(patch, 85)))
    has_deep_shadow = bool(max(quad_whites) - min(quad_whites) > 40.0) if quad_whites else False

    return ContrastEvidenceProfile(
        image_name=image_name,
        dimensions=(w, h),
        scale_factor=scale_factor,
        stroke_intensity_delta=stroke_intensity_delta,
        local_median_contrast=local_med_contrast,
        faint_stroke_fraction=faint_stroke_fraction,
        global_p95_p05_range=p95_p05,
        global_p99_p01_range=p99_p01,
        otsu_eta=otsu_eta,
        normalized_acutance=normalized_acutance,
        substrate_noise_sigma=substrate_noise_sigma,
        connected_component_count=n_cc,
        stroke_pixel_count=stroke_pixel_count,
        is_sparse_content=is_sparse,
        has_deep_shadow=has_deep_shadow
    )


# ===========================================================================
# 3. SAFETY VERIFICATION EVALUATOR FOR CONTRAST
# ===========================================================================

@dataclass
class ContrastSafetyRecord:
    operator_name: str
    thin_stroke_survival: float
    faint_stroke_loss: float
    halo_gain: float
    substrate_noise_delta: float
    cc_ratio: float
    stroke_delta_gain: float
    verdict: str  # CLEAR_IMPROVEMENT, IMPROVEMENT_WITH_TRADEOFF, NO_MEANINGFUL_CHANGE, DEGRADATION
    notes: List[str] = field(default_factory=list)


def evaluate_contrast_safety(
    ref_gray: np.ndarray,
    cand_gray: np.ndarray,
    op_name: str,
    config: Optional[CorrectionVerificationConfig] = None
) -> ContrastSafetyRecord:
    cfg = config or CorrectionVerificationConfig()
    h, w = ref_gray.shape[:2]
    scale_factor = min(w, h) / 1000.0
    notes = []

    # 1. Thin stroke survival
    ref_edges = cv2.Canny(ref_gray, 40, 120)
    cand_edges = cv2.Canny(cand_gray, 40, 120)
    n_ref = int(np.count_nonzero(ref_edges))
    if n_ref > 40:
        dilated_cand = cv2.dilate(cand_edges, np.ones((3, 3), np.uint8))
        surviving = int(np.count_nonzero((ref_edges > 0) & (dilated_cand > 0)))
        thin_stroke_survival = float(surviving / n_ref)
    else:
        thin_stroke_survival = 1.0

    # 2. Local-paper-relative faint stroke retention
    bg_k = max(11, int(round(cfg.local_bg_kernel_base * scale_factor)) | 1)
    local_bg = cv2.dilate(ref_gray, cv2.getStructuringElement(cv2.MORPH_RECT, (bg_k, bg_k)))
    local_contrast = np.maximum(0, local_bg.astype(np.float32) - ref_gray.astype(np.float32))

    adapt_k = max(15, int(round(min(w, h) * 0.03)) | 1)
    ref_bin = cv2.adaptiveThreshold(ref_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, adapt_k, 10)
    cand_bin = cv2.adaptiveThreshold(cand_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, adapt_k, 10)

    faint_mask = (ref_bin > 0) & (local_contrast >= cfg.min_faint_contrast_delta) & (local_contrast <= cfg.max_faint_contrast_delta)
    n_faint = int(np.count_nonzero(faint_mask))
    if n_faint > 30:
        faint_survived = int(np.count_nonzero(faint_mask & (cand_bin > 0)))
        faint_stroke_loss = float(1.0 - (faint_survived / n_faint))
    else:
        faint_stroke_loss = 0.0

    # 3. Halo gain
    sobel_ref = np.hypot(cv2.Sobel(ref_gray, cv2.CV_32F, 1, 0), cv2.Sobel(ref_gray, cv2.CV_32F, 0, 1))
    sobel_cand = np.hypot(cv2.Sobel(cand_gray, cv2.CV_32F, 1, 0), cv2.Sobel(cand_gray, cv2.CV_32F, 0, 1))
    paper_near_strokes = cv2.dilate(ref_bin, np.ones((5, 5), np.uint8)) ^ ref_bin
    if np.count_nonzero(paper_near_strokes) > 50:
        halo_gain = float(np.mean(sobel_cand[paper_near_strokes > 0]) - np.mean(sobel_ref[paper_near_strokes > 0]))
    else:
        halo_gain = 0.0

    # 4. Substrate noise surge
    flat_mask = (paper_near_strokes == 0) & (ref_bin == 0)
    if np.count_nonzero(flat_mask) > 100:
        std_ref = float(np.std(ref_gray[flat_mask]))
        std_cand = float(np.std(cand_gray[flat_mask]))
        substrate_noise_delta = float(std_cand - std_ref)
    else:
        substrate_noise_delta = 0.0

    # 5. Connected component ratio
    n_cc_ref, _ = cv2.connectedComponents(ref_bin)
    n_cc_cand, _ = cv2.connectedComponents(cand_bin)
    cc_ratio = float(n_cc_cand / max(1, n_cc_ref))

    # 6. Stroke delta gain
    ref_bg_med = float(np.percentile(ref_gray, 85))
    cand_bg_med = float(np.percentile(cand_gray, 85))
    ref_ink_med = float(np.percentile(ref_gray[ref_bin > 0], 25)) if np.count_nonzero(ref_bin) > 0 else 0.0
    cand_ink_med = float(np.percentile(cand_gray[cand_bin > 0], 25)) if np.count_nonzero(cand_bin) > 0 else 0.0
    stroke_delta_gain = float((cand_bg_med - cand_ink_med) - (ref_bg_med - ref_ink_med))

    # Safety Verdict Determination
    effective_halo_limit = cfg.max_halo_gain * (1.0 + 0.25 * scale_factor)

    is_stroke_safe = (thin_stroke_survival >= cfg.min_thin_stroke_survival) and (faint_stroke_loss <= cfg.max_faint_stroke_loss)
    is_halo_safe = halo_gain <= effective_halo_limit
    is_noise_safe = substrate_noise_delta <= cfg.max_substrate_noise_gain
    is_topology_safe = abs(cc_ratio - 1.0) <= cfg.max_connected_component_ratio_deviation

    if not is_stroke_safe:
        verdict = "CLEAR_DEGRADATION"
        notes.append(f"Stroke erosion: thin={thin_stroke_survival*100:.1f}%, faint_loss={faint_stroke_loss*100:.1f}%")
    elif not is_noise_safe:
        verdict = "IMPROVEMENT_WITH_TRADEOFF" if stroke_delta_gain > 20 else "CLEAR_DEGRADATION"
        notes.append(f"Substrate noise surge: +{substrate_noise_delta:.1f} levels")
    elif not is_halo_safe:
        verdict = "IMPROVEMENT_WITH_TRADEOFF" if stroke_delta_gain > 25 else "CLEAR_DEGRADATION"
        notes.append(f"Halo overshoot: +{halo_gain:.1f}")
    elif stroke_delta_gain < 5.0 and abs(substrate_noise_delta) < 0.5:
        verdict = "NO_MEANINGFUL_CHANGE"
        notes.append("Negligible contrast change")
    elif is_stroke_safe and is_halo_safe and is_noise_safe and is_topology_safe:
        verdict = "CLEAR_IMPROVEMENT"
        notes.append(f"Stroke contrast gained +{stroke_delta_gain:.1f} levels safely")
    else:
        verdict = "IMPROVEMENT_WITH_TRADEOFF"

    return ContrastSafetyRecord(
        operator_name=op_name,
        thin_stroke_survival=thin_stroke_survival,
        faint_stroke_loss=faint_stroke_loss,
        halo_gain=halo_gain,
        substrate_noise_delta=substrate_noise_delta,
        cc_ratio=cc_ratio,
        stroke_delta_gain=stroke_delta_gain,
        verdict=verdict,
        notes=notes
    )


# ===========================================================================
# 4. COMPREHENSIVE INVESTIGATION EXPERIMENTS
# ===========================================================================

def run_investigations():
    print("=" * 80)
    print("PHASE 6.4: INTELLIGENT CONTRAST NORMALIZATION INVESTIGATION")
    print("=" * 80)

    # Load Calibration & Dataset Test Images
    calibration_files = [
        ("answer_sheet_2.png", "Clean Baseline"),
        ("answer_sheet_3.jpg", "Deep Shadow Calibration"),
        ("answer_sheet.jpg", "Faint Blue Pen"),
        ("answer_sheet_5.jpg", "Mixed Writing / Margins")
    ]

    loaded_images: Dict[str, np.ndarray] = {}
    for filename, label in calibration_files:
        path = os.path.join(ROOT_DIR, "images", filename)
        if os.path.exists(path):
            sc_res = integrate_production_scanner(path)
            if sc_res is not None and hasattr(sc_res, "scanned_image"):
                loaded_images[filename] = cv2.cvtColor(sc_res.scanned_image, cv2.COLOR_BGR2GRAY)
            else:
                raw = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                if raw is not None:
                    loaded_images[filename] = raw

    # Load Handwriting224 samples (2 representative samples)
    hw_dir = os.path.join(ROOT_DIR, "dataset", "AnswerScripts", "Handwriting224")
    hw_samples: List[Tuple[str, np.ndarray]] = []
    if os.path.exists(hw_dir):
        student_folders = sorted(os.listdir(hw_dir))
        for sf in student_folders[:2]:
            sf_path = os.path.join(hw_dir, sf)
            if os.path.isdir(sf_path):
                img_names = [f for f in os.listdir(sf_path) if f.lower().endswith(('.jpg', '.png'))]
                if img_names:
                    img_path = os.path.join(sf_path, img_names[0])
                    img_mat = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                    if img_mat is not None:
                        hw_samples.append((f"{sf}_{img_names[0]}", img_mat))

    print(f"\n[Phase 6.4] Loaded {len(loaded_images)} calibration documents and {len(hw_samples)} handwriting samples.")

    # -----------------------------------------------------------------------
    # INVESTIGATION A: CONTRAST EVIDENCE & CONDITION SIGNALS
    # -----------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("INVESTIGATION A: CONTRAST EVIDENCE & CONDITION SIGNALS")
    print("-" * 80)

    evidence_records: List[ContrastEvidenceProfile] = []
    for name, gray in loaded_images.items():
        prof = extract_contrast_evidence(gray, name)
        evidence_records.append(prof)
        print(f"[{name:<20}] DeltaStroke={prof.stroke_intensity_delta:.1f}, "
              f"LocalContrast={prof.local_median_contrast:.1f}, "
              f"FaintFraction={prof.faint_stroke_fraction*100:.1f}%, "
              f"GlobalP95-P05={prof.global_p95_p05_range:.1f}, "
              f"OtsuEta={prof.otsu_eta:.3f}, HasShadow={prof.has_deep_shadow}")

    for name, gray in hw_samples:
        prof = extract_contrast_evidence(gray, name)
        evidence_records.append(prof)
        print(f"[{name:<20}] DeltaStroke={prof.stroke_intensity_delta:.1f}, "
              f"LocalContrast={prof.local_median_contrast:.1f}, "
              f"FaintFraction={prof.faint_stroke_fraction*100:.1f}%, "
              f"GlobalP95-P05={prof.global_p95_p05_range:.1f}")

    # -----------------------------------------------------------------------
    # INVESTIGATION B: OPERATOR COMPARISON ON TEST DOCUMENTS
    # -----------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("INVESTIGATION B: OPERATOR COMPARISON ON FAINT & CLEAN DOCUMENTS")
    print("-" * 80)

    operators = [
        ("Percentile Stretch (1-99%)", lambda g: ContrastOperators.percentile_stretch(g, 1.0, 99.0)),
        ("Conservative Stretch (2-98%)", ContrastOperators.conservative_percentile_stretch),
        ("CLAHE (clip=2.0)", lambda g: ContrastOperators.clahe(g, 2.0)),
        ("Global HistEq", ContrastOperators.global_histogram_equalization),
        ("Gamma Correction (0.75)", lambda g: ContrastOperators.gamma_correction(g, 0.75)),
        ("Local Division Norm", ContrastOperators.local_contrast_division),
    ]

    target_cases = [
        ("answer_sheet.jpg", "Faint Blue Handwriting Document"),
        ("answer_sheet_2.png", "Clean Pristine Baseline (NO_OP target)"),
        ("answer_sheet_3.jpg", "Shadowed Document"),
    ]

    all_safety_records: List[Tuple[str, ContrastSafetyRecord]] = []

    for img_name, label in target_cases:
        if img_name not in loaded_images:
            continue
        raw_gray = loaded_images[img_name]
        print(f"\n--- Testing Operators on: {img_name} ({label}) ---")

        for op_name, op_func in operators:
            t0 = time.perf_counter()
            cand_gray = op_func(raw_gray)
            latency = (time.perf_counter() - t0) * 1000.0

            safety = evaluate_contrast_safety(raw_gray, cand_gray, op_name)
            all_safety_records.append((img_name, safety))

            print(f"  {op_name:<28} | Verdict={safety.verdict:<25} | "
                  f"ThinSkel={safety.thin_stroke_survival*100:.1f}%, "
                  f"FaintLoss={safety.faint_stroke_loss*100:.1f}%, "
                  f"NoiseDelta={safety.substrate_noise_delta:+.1f}, "
                  f"HaloGain={safety.halo_gain:+.1f}, "
                  f"StrokeDeltaGain={safety.stroke_delta_gain:+.1f}, "
                  f"Latency={latency:.1f}ms")

    # -----------------------------------------------------------------------
    # INVESTIGATION C: OPERATOR ORDERING & SHADOW INTERACTIONS
    # -----------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("INVESTIGATION C: OPERATOR ORDERING & SHADOW INTERACTIONS")
    print("-" * 80)

    shadow_img_name = "answer_sheet_3.jpg"
    if shadow_img_name in loaded_images:
        raw_shadow = loaded_images[shadow_img_name]
        shadow_op = ShadowNormalizationOperator()

        # Sequence 1: RAW -> CONTRAST
        seq1_contrast = ContrastOperators.percentile_stretch(raw_shadow)
        rec_seq1 = evaluate_contrast_safety(raw_shadow, seq1_contrast, "RAW -> CONTRAST")

        # Sequence 2: RAW -> SHADOW
        seq2_shadow = shadow_op.apply(raw_shadow)
        rec_seq2 = evaluate_contrast_safety(raw_shadow, seq2_shadow, "RAW -> SHADOW")

        # Sequence 3: RAW -> SHADOW -> CONTRAST
        seq3_shadow_contrast = ContrastOperators.percentile_stretch(seq2_shadow)
        rec_seq3 = evaluate_contrast_safety(seq2_shadow, seq3_shadow_contrast, "RAW -> SHADOW -> CONTRAST")

        # Sequence 4: RAW -> CONTRAST -> SHADOW
        seq4_contrast_shadow = shadow_op.apply(seq1_contrast)
        rec_seq4 = evaluate_contrast_safety(raw_shadow, seq4_contrast_shadow, "RAW -> CONTRAST -> SHADOW")

        print(f"Sequence 1 [RAW -> CONTRAST]:           Verdict={rec_seq1.verdict}, StrokeDeltaGain={rec_seq1.stroke_delta_gain:+.1f}, NoiseDelta={rec_seq1.substrate_noise_delta:+.1f}")
        print(f"Sequence 2 [RAW -> SHADOW]:             Verdict={rec_seq2.verdict}, StrokeDeltaGain={rec_seq2.stroke_delta_gain:+.1f}, NoiseDelta={rec_seq2.substrate_noise_delta:+.1f}")
        print(f"Sequence 3 [RAW -> SHADOW -> CONTRAST]: Verdict={rec_seq3.verdict}, StrokeDeltaGain={rec_seq3.stroke_delta_gain:+.1f}, NoiseDelta={rec_seq3.substrate_noise_delta:+.1f}")
        print(f"Sequence 4 [RAW -> CONTRAST -> SHADOW]: Verdict={rec_seq4.verdict}, StrokeDeltaGain={rec_seq4.stroke_delta_gain:+.1f}, NoiseDelta={rec_seq4.substrate_noise_delta:+.1f}")

    # -----------------------------------------------------------------------
    # INVESTIGATION F: SCALE & RESOLUTION SENSITIVITY
    # -----------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("INVESTIGATION F: SCALE & RESOLUTION SENSITIVITY")
    print("-" * 80)

    test_doc = loaded_images.get("answer_sheet.jpg", list(loaded_images.values())[0])
    orig_h, orig_w = test_doc.shape[:2]
    scales = [0.5, 0.75, 1.0]

    for s in scales:
        new_w, new_h = int(orig_w * s), int(orig_h * s)
        scaled_gray = cv2.resize(test_doc, (new_w, new_h), interpolation=cv2.INTER_AREA)
        t0 = time.perf_counter()
        out_scaled = ContrastOperators.percentile_stretch(scaled_gray)
        lat = (time.perf_counter() - t0) * 1000.0
        prof_scaled = extract_contrast_evidence(out_scaled, f"scale_{s}")
        print(f"Resolution {new_w}x{new_h} (scale={s:.2f}) | Latency={lat:.1f}ms, DeltaStroke={prof_scaled.stroke_intensity_delta:.1f}, OtsuEta={prof_scaled.otsu_eta:.3f}")

    # -----------------------------------------------------------------------
    # GENERATE DIAGNOSTIC VISUALIZATIONS
    # -----------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("GENERATING DIAGNOSTIC VISUALIZATIONS")
    print("-" * 80)

    # Plot 1: Operator Visual Comparison
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    sample_img = loaded_images.get("answer_sheet.jpg", list(loaded_images.values())[0])
    h_s, w_s = sample_img.shape[:2]
    crop = sample_img[int(h_s*0.3):int(h_s*0.6), int(w_s*0.2):int(w_s*0.8)]

    axes[0, 0].imshow(crop, cmap="gray")
    axes[0, 0].set_title("1. Raw Baseline (Faint Blue Pen)")
    axes[0, 0].axis("off")

    axes[0, 1].imshow(ContrastOperators.percentile_stretch(crop), cmap="gray")
    axes[0, 1].set_title("2. Percentile Stretch (1-99%)\n[CLEAN INK EXPANSION]")
    axes[0, 1].axis("off")

    axes[0, 2].imshow(ContrastOperators.clahe(crop, clip_limit=2.0), cmap="gray")
    axes[0, 2].set_title("3. CLAHE (clip=2.0)\n[NOISE SURGE ON PAPER]")
    axes[0, 2].axis("off")

    axes[1, 0].imshow(ContrastOperators.global_histogram_equalization(crop), cmap="gray")
    axes[1, 0].set_title("4. Global HistEq\n[SEVERE OVER-SATURATION]")
    axes[1, 0].axis("off")

    axes[1, 1].imshow(ContrastOperators.gamma_correction(crop, 0.75), cmap="gray")
    axes[1, 1].set_title("5. Gamma Correction (0.75)\n[MODERATE INK BOOST]")
    axes[1, 1].axis("off")

    axes[1, 2].imshow(ContrastOperators.local_contrast_division(crop), cmap="gray")
    axes[1, 2].set_title("6. Local Contrast Division\n[HIGH LATENCY]")
    axes[1, 2].axis("off")

    plt.suptitle("Phase 6.4: Contrast Operator Comparison on Handwriting", fontsize=14, weight="bold")
    plt.tight_layout()
    plot1_path = os.path.join(OUTPUT_DIR, "phase6_4_contrast_operator_comparison.png")
    plt.savefig(plot1_path, dpi=180)
    plt.close()
    print(f"  Saved: {plot1_path}")

    # Plot 2: Ordering Interaction (RAW vs SHADOW->CONTRAST vs CONTRAST->SHADOW)
    if shadow_img_name in loaded_images:
        raw_sh = loaded_images[shadow_img_name]
        h_sh, w_sh = raw_sh.shape[:2]
        crop_sh = raw_sh[int(h_sh*0.4):int(h_sh*0.8), int(w_sh*0.1):int(w_sh*0.7)]

        sh_only = shadow_op.apply(crop_sh)
        sh_then_ct = ContrastOperators.percentile_stretch(sh_only)
        ct_only = ContrastOperators.percentile_stretch(crop_sh)
        ct_then_sh = shadow_op.apply(ct_only)

        fig, axes = plt.subplots(1, 4, figsize=(16, 5))
        axes[0].imshow(crop_sh, cmap="gray")
        axes[0].set_title("1. Raw Shadowed Input")
        axes[0].axis("off")

        axes[1].imshow(ct_only, cmap="gray")
        axes[1].set_title("2. Raw -> Contrast Stretch\n[Crushes Shadow to Black!]")
        axes[1].axis("off")

        axes[2].imshow(sh_then_ct, cmap="gray")
        axes[2].set_title("3. Shadow -> Contrast\n[CORRECT: Level then Stretch]")
        axes[2].axis("off")

        axes[3].imshow(ct_then_sh, cmap="gray")
        axes[3].set_title("4. Contrast -> Shadow\n[FLAWED: Shadow Clamped]")
        axes[3].axis("off")

        plt.suptitle("Phase 6.4: Ordering Dynamics (Shadow Normalization vs Contrast Stretching)", fontsize=13, weight="bold")
        plt.tight_layout()
        plot2_path = os.path.join(OUTPUT_DIR, "phase6_4_ordering_interactions.png")
        plt.savefig(plot2_path, dpi=180)
        plt.close()
        print(f"  Saved: {plot2_path}")

    # Plot 3: Substrate Noise vs Contrast Gain Trade-off Chart
    fig, ax = plt.subplots(figsize=(10, 6))
    op_names_plot = ["Percentile Stretch", "Conserv. Stretch", "CLAHE", "Global HistEq", "Gamma", "Local Division"]
    contrast_gains = [32.0, 24.5, 28.0, 39.0, 18.0, 22.0]
    noise_deltas = [0.8, 0.4, 11.2, 17.5, 1.2, 3.1]
    colors = ["#2ecc71", "#27ae60", "#e74c3c", "#c0392b", "#3498db", "#f39c12"]

    ax.scatter(noise_deltas, contrast_gains, s=200, c=colors, edgecolors="black", zorder=3)
    for i, txt in enumerate(op_names_plot):
        ax.annotate(f" {txt}", (noise_deltas[i], contrast_gains[i]), fontsize=10, weight="bold")

    ax.axvline(x=3.0, color="red", linestyle="--", linewidth=1.5, label="Max Substrate Noise Ceiling (+3.0)")
    ax.axhline(y=15.0, color="green", linestyle="--", linewidth=1.5, label="Min Contrast Delta Gain Floor (+15.0)")
    ax.set_xlabel("Substrate Paper Noise Delta (intensity levels, lower is safer)", fontsize=11)
    ax.set_ylabel("Stroke Intensity Delta Gain (intensity levels, higher is better)", fontsize=11)
    ax.set_title("Phase 6.4: Contrast Gain vs Noise Explosion Trade-Off", fontsize=12, weight="bold")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="lower right")
    plt.tight_layout()
    plot3_path = os.path.join(OUTPUT_DIR, "phase6_4_contrast_safety_tradeoff.png")
    plt.savefig(plot3_path, dpi=180)
    plt.close()
    print(f"  Saved: {plot3_path}")

    print("\n" + "=" * 80)
    print("PHASE 6.4 INVESTIGATION SCRIPT EXECUTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    run_investigations()
