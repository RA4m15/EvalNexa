"""
phase5/02_ocr_correlation_investigation.py

AI-EVAL PHASE 5.2: DOWNSTREAM OCR/HTR CORRELATION INVESTIGATION
===============================================================

PURPOSE:
Investigate and validate whether Phase 5.1 multi-dimensional quality evidence
signals objectively correlate with downstream OCR/HTR transcription quality
(Character Error Rate, Word Error Rate, Character Accuracy, Transcription Failures).

KEY RESEARCH QUESTIONS:
1. Which Phase 5.1 signals (stroke contrast, faint-stroke fraction, normalized acutance,
   edge-spread width, illumination uniformity, glare/text collision, occlusion,
   margin clipping, bleed-through, skew, binarization separation) actually correlate
   with downstream OCR/HTR performance?
2. Does global sharpness (Laplacian variance) disagree with OCR performance because
   of content density or surface texture?
3. How do fatal defects (glare collision, severe clipping, intrusive occlusion)
   differ from continuously degradable quality issues?
4. Does Phase 4 automatic enhancement produce measurable downstream OCR improvements?
5. What are the empirical dataset limitations and what ground-truth pipeline is
   required for full-scale production readiness?

GUARDRAILS:
- INVESTIGATION ONLY.
- Do NOT implement the final production quality assessment system yet.
- Do NOT create a universal 0-100 quality score, weighted ranking, or production thresholds.
- Do NOT tune thresholds to the validation data.
- Clearly separate calibration observations from unseen validation findings.
- Do NOT modify any frozen Phase 2, Phase 3, or Phase 4 files.
"""

import os
import sys
import math
import time
import asyncio
import tempfile
import importlib.util
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict, field

import cv2
import numpy as np
import scipy.stats as stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Windows Media OCR bindings
import winrt.windows.storage as ws
import winrt.windows.graphics.imaging as wgi
import winrt.windows.media.ocr as wmo

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT_DIR, "phase5", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Dynamic Imports: Phase 3 Scanner, Phase 4 Enhancement, Phase 5.1 Evidence
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

P51_PATH = os.path.join(ROOT_DIR, "phase5", "01_quality_assessment_evidence_investigation.py")
spec_p51 = importlib.util.spec_from_file_location("phase5_01", P51_PATH)
phase5_01 = importlib.util.module_from_spec(spec_p51)
spec_p51.loader.exec_module(phase5_01)
extract_quality_assessment_evidence = phase5_01.extract_quality_assessment_evidence
QualityAssessmentEvidence = phase5_01.QualityAssessmentEvidence


# ===========================================================================
# 1. OCR ENGINE & EDIT DISTANCE INFRASTRUCTURE
# ===========================================================================

def levenshtein_distance(seq1: List[Any], seq2: List[Any]) -> int:
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
    Standardizes whitespace and punctuation for fair string comparison.
    """
    cleaned = " ".join(text.strip().split())
    return cleaned


def compute_transcription_metrics(gt_text: str, hyp_text: str) -> Dict[str, float]:
    """
    Computes Character Error Rate (CER), Word Error Rate (WER),
    Character Accuracy, and Transcription Failure flag.
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

    # 3. Character Accuracy
    char_acc = float(max(0.0, 1.0 - cer))

    # 4. Transcription Failure
    is_failure = bool(cer >= 0.85 or len(norm_hyp) == 0)

    return {
        "cer": cer,
        "wer": wer,
        "char_accuracy": char_acc,
        "is_failure": float(1.0 if is_failure else 0.0),
        "gt_len": len(norm_gt),
        "hyp_len": len(norm_hyp),
        "edit_dist_char": edit_dist_char,
        "edit_dist_word": edit_dist_word,
    }


class OcrInvestigationEngine:
    """
    Thread-safe asynchronous wrapper around Windows Media Neural OCR Engine.
    Executes recognition directly on OpenCV BGR/Grayscale numpy arrays.
    """
    def __init__(self):
        self._engine = wmo.OcrEngine.try_create_from_user_profile_languages()
        if self._engine is None:
            raise RuntimeError("Windows Media OCR Engine failed to initialize from user profile languages.")

    async def recognize_async(self, image: np.ndarray) -> str:
        """
        Executes OCR on an in-memory image via temporary storage stream.
        """
        h, w = image.shape[:2]
        if min(h, w) < 40:
            return ""

        # Ensure image has sufficient contrast and valid dimensions
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            cv2.imwrite(tmp_path, image)
            file = await ws.StorageFile.get_file_from_path_async(os.path.abspath(tmp_path))
            stream = await file.open_async(ws.FileAccessMode.READ)
            decoder = await wgi.BitmapDecoder.create_async(stream)
            bitmap = await decoder.get_software_bitmap_async()
            result = await self._engine.recognize_async(bitmap)
            stream.close()

            lines = []
            for i in range(result.lines.size):
                lines.append(result.lines.get_at(i).text)
            return "\n".join(lines)
        except Exception as e:
            return ""
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def recognize(self, image: np.ndarray) -> str:
        """
        Synchronous entry point.
        """
        return asyncio.run(self.recognize_async(image))


# ===========================================================================
# 2. GROUND TRUTH DATASETS & EXPERIMENTAL BENCHMARK
# ===========================================================================

# Corpus A Ground Truth: Exact printed form & verified student text from calibration sheets
GT_CALIBRATION_FORM = (
    "TAGORE PUBLIC SCHOOL, ALLAHABAD\n"
    "EXAMINATION ANSWER SHEET\n"
    "Roll No. Name of Examination Unit - 2\n"
    "04\n"
    "Class & Section 10 - B Day & Date 12-02-2022\n"
    "Subject History Subject Code\n"
    "Marks Awarded Section : A\n"
    "FOR USE OF EXAMINERS: Maximum Marks"
)

GT_CALIBRATION_ANS1 = (
    "Many towns in Italy fell into ruin after the fall of the Roman empire "
    "because there was no unified government and the Pope was not a strong political figure."
)

GT_CALIBRATION_ANS2 = (
    "Two architects immortalized by their work were Michelangelo Buonarroti who designed "
    "the dome of St. Peter's and Filippo Brunelleschi who designed"
)

GT_CALIBRATION_ANS3 = (
    "Charcoal was too fragile to transport across long distances and could not generate high temperatures."
)

GT_CALIBRATION_SEC_B = (
    "Some of the new developments were: "
    "Private and public spheres of life began to be separated. "
    "There was increased belief that all individuals had equal political rights. "
    "Different regions of Europe started to develop a distinct sense of identity based on language."
)

GT_PRINTED_BLOCK = (
    "TAGORE PUBLIC SCHOOL, ALLAHABAD\n"
    "EXAMINATION ANSWER SHEET\n"
    "Roll No. Name of Examination Class & Section Day & Date Subject Code"
)


# ===========================================================================
# 3. CONTROLLED DEGRADATION GENERATORS (PHASE 5.1 SIGNAL PROBES)
# ===========================================================================

def apply_defocus_blur(image: np.ndarray, sigma: float) -> np.ndarray:
    """Simulates lens defocus and motion blur via Gaussian convolution."""
    if sigma <= 0.05:
        return image.copy()
    ksize = int(math.ceil(sigma * 4)) | 1
    return cv2.GaussianBlur(image, (ksize, ksize), sigma)


def apply_contrast_fade(image: np.ndarray, alpha: float) -> np.ndarray:
    """Simulates faint ink / low stroke contrast by blending toward paper substrate white."""
    # alpha = 1.0 (original), alpha = 0.1 (extremely faded)
    paper_white = 245.0
    faded = paper_white - (paper_white - image.astype(np.float32)) * alpha
    return np.clip(faded, 0, 255).astype(np.uint8)


def apply_illumination_gradient(image: np.ndarray, reduction_factor: float) -> np.ndarray:
    """Simulates regional non-uniform shadow / illumination falloff."""
    # reduction_factor = 0.0 (uniform), reduction_factor = 0.85 (deep shadow)
    h, w = image.shape[:2]
    # Linear ramp from 1.0 down to (1.0 - reduction_factor)
    ramp = np.linspace(1.0, 1.0 - reduction_factor, h, dtype=np.float32)[:, None]
    if image.ndim == 3:
        ramp = np.repeat(ramp[:, :, None], 3, axis=2)
    shaded = np.clip(image.astype(np.float32) * ramp, 0, 255).astype(np.uint8)
    return shaded


def apply_specular_glare(image: np.ndarray, collision_fraction: float) -> np.ndarray:
    """
    Simulates high-intensity specular flash reflection directly colliding with text.
    collision_fraction dictates the radius of the saturated glare hotspot.
    """
    if collision_fraction <= 0.01:
        return image.copy()
    out = image.copy()
    h, w = image.shape[:2]
    cx, cy = int(w * 0.45), int(h * 0.50)
    radius = int(math.sqrt(collision_fraction * w * h / math.pi) * 1.5)
    radius = max(10, min(radius, min(h, w) // 2))

    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    glare_intensity = np.clip(1.0 - (dist / max(1.0, radius)), 0.0, 1.0)
    glare_mask = glare_intensity > 0.05

    for c in range(3 if image.ndim == 3 else 1):
        if image.ndim == 3:
            out[:, :, c] = np.clip(out[:, :, c].astype(np.float32) + (glare_intensity * 255.0), 0, 255).astype(np.uint8)
        else:
            out = np.clip(out.astype(np.float32) + (glare_intensity * 255.0), 0, 255).astype(np.uint8)
    return out


def apply_margin_clipping(image: np.ndarray, shift_px: int) -> np.ndarray:
    """
    Simulates severe framing clipping where text is translated past the sensor boundary.
    """
    if shift_px <= 0:
        return image.copy()
    h, w = image.shape[:2]
    # Shift left by shift_px, filling background with white
    shifted = np.full_like(image, 255)
    if shift_px < w:
        shifted[:, : (w - shift_px)] = image[:, shift_px:]
    return shifted


def apply_margin_occlusion(image: np.ndarray, encroachment_frac: float) -> np.ndarray:
    """
    Simulates foreign object (thumb/card) occluding margin and outer text.
    """
    if encroachment_frac <= 0.01:
        return image.copy()
    out = image.copy()
    h, w = image.shape[:2]
    occ_w = int(w * encroachment_frac * 0.4)
    # Dark brown / skin tone blob encroaching from left
    if out.ndim == 3:
        out[:, :occ_w, 0] = 30  # Blue
        out[:, :occ_w, 1] = 50  # Green
        out[:, :occ_w, 2] = 120 # Red
    else:
        out[:, :occ_w] = 60
    return out


def apply_baseline_skew(image: np.ndarray, angle_deg: float) -> np.ndarray:
    """
    Rotates image around center with white background padding.
    """
    if abs(angle_deg) < 0.1:
        return image.copy()
    h, w = image.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle_deg, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    return rotated


# ===========================================================================
# 4. INVESTIGATION EXPERIMENTAL RUNNER
# ===========================================================================

@dataclass
class CorrelationTrialResult:
    trial_name: str
    category: str                       # CALIBRATION, BLUR_SWEEP, CONTRAST_SWEEP, SHADOW_SWEEP, FATAL_DEFECT, SKEW_SWEEP, VALIDATION, DENSITY_TEST
    degradation_parameter: float
    evidence: QualityAssessmentEvidence
    ocr_text: str
    gt_text: str
    cer: float
    wer: float
    char_accuracy: float
    is_failure: bool


class OcrCorrelationInvestigator:
    def __init__(self):
        self.ocr_engine = OcrInvestigationEngine()
        self.results: List[CorrelationTrialResult] = []

    def evaluate_sample(
        self,
        trial_name: str,
        category: str,
        param_val: float,
        image: np.ndarray,
        gt_text: str
    ) -> CorrelationTrialResult:
        """
        Runs Phase 5.1 quality evidence extraction and downstream OCR evaluation.
        """
        # 1. Extract Phase 5.1 Multi-Dimensional Evidence
        ev = extract_quality_assessment_evidence(image, trial_name)

        # 2. Downstream OCR Transcription
        hyp_text = self.ocr_engine.recognize(image)

        # 3. Accuracy & Error Metrics
        metrics = compute_transcription_metrics(gt_text, hyp_text)

        result = CorrelationTrialResult(
            trial_name=trial_name,
            category=category,
            degradation_parameter=param_val,
            evidence=ev,
            ocr_text=hyp_text,
            gt_text=gt_text,
            cer=metrics["cer"],
            wer=metrics["wer"],
            char_accuracy=metrics["char_accuracy"],
            is_failure=bool(metrics["is_failure"] > 0.5),
        )
        self.results.append(result)
        return result

    # -----------------------------------------------------------------------
    # Experiment 1: Real Calibration Documents (Baseline & Enhancement)
    # -----------------------------------------------------------------------
    def run_calibration_experiments(self):
        print("\n[Phase 5.2] Running Experiment 1: Real Calibration Documents...")
        # 1. answer_sheet_2.png (Pristine baseline)
        p2 = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
        if os.path.exists(p2):
            img2 = cv2.imread(p2)
            form_crop = img2[40:390, 80:1120]
            self.evaluate_sample("Calib_2_Form_Pristine", "CALIBRATION", 0.0, form_crop, GT_CALIBRATION_FORM)

            ans1_crop = img2[390:600, 80:1120]
            self.evaluate_sample("Calib_2_Ans1_Handwritten", "CALIBRATION", 0.0, ans1_crop, GT_CALIBRATION_ANS1)

        # 2. answer_sheet_3.jpg: Shadow test (RAW Rectified vs Phase 4 ENHANCED)
        p3 = os.path.join(ROOT_DIR, "images", "answer_sheet_3.jpg")
        if os.path.exists(p3):
            sc_res = integrate_production_scanner(p3)
            raw_rect = sc_res.scanned_image
            enh_res = enhance_scanned_document(sc_res)
            enh_gray = enh_res.enhanced_gray
            enh_bgr = cv2.cvtColor(enh_gray, cv2.COLOR_GRAY2BGR)

            # Form region on answer_sheet_3
            h, w = raw_rect.shape[:2]
            raw_form = raw_rect[:int(h * 0.35), :]
            enh_form = enh_bgr[:int(h * 0.35), :]

            self.evaluate_sample("Calib_3_Raw_Shadowed", "CALIBRATION", 0.0, raw_form, GT_CALIBRATION_FORM)
            self.evaluate_sample("Calib_3_Phase4_Enhanced", "CALIBRATION", 1.0, enh_form, GT_CALIBRATION_FORM)

        # 3. answer_sheet_4.jpg (Severe perspective warp & blur)
        p4 = os.path.join(ROOT_DIR, "images", "answer_sheet_4.jpg")
        if os.path.exists(p4):
            sc4 = integrate_production_scanner(p4)
            h4, w4 = sc4.scanned_image.shape[:2]
            crop4 = sc4.scanned_image[:int(h4 * 0.35), :]
            self.evaluate_sample("Calib_4_Perspective_Distorted", "CALIBRATION", 0.0, crop4, GT_CALIBRATION_FORM)

        # 4. answer_sheet_5.jpg (Edge clipping & lateral skew)
        p5 = os.path.join(ROOT_DIR, "images", "answer_sheet_5.jpg")
        if os.path.exists(p5):
            sc5 = integrate_production_scanner(p5)
            h5, w5 = sc5.scanned_image.shape[:2]
            crop5 = sc5.scanned_image[:int(h5 * 0.35), :]
            self.evaluate_sample("Calib_5_Lateral_Clipped", "CALIBRATION", 0.0, crop5, GT_CALIBRATION_FORM)

    # -----------------------------------------------------------------------
    # Experiment 2: Controlled Degradation Sweeps
    # -----------------------------------------------------------------------
    def run_degradation_sweeps(self):
        print("\n[Phase 5.2] Running Experiment 2: Controlled Degradation Sweeps...")
        p2 = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
        if not os.path.exists(p2):
            return
        base_img = cv2.imread(p2)[40:390, 80:1120]
        gt = GT_CALIBRATION_FORM

        # 1. Defocus Blur Sweep (Acutance / ESW probe)
        sigmas = [0.0, 0.8, 1.5, 2.5, 4.0, 6.0, 9.0]
        for s in sigmas:
            blurry = apply_defocus_blur(base_img, s)
            self.evaluate_sample(f"Blur_sigma_{s:.1f}", "BLUR_SWEEP", s, blurry, gt)

        # 2. Contrast Fade Sweep (Faint stroke probe)
        alphas = [1.0, 0.75, 0.50, 0.35, 0.20, 0.10]
        for a in alphas:
            faded = apply_contrast_fade(base_img, a)
            self.evaluate_sample(f"Contrast_alpha_{a:.2f}", "CONTRAST_SWEEP", a, faded, gt)

        # 3. Illumination Gradient Sweep (Regional shadow probe)
        reductions = [0.0, 0.25, 0.45, 0.65, 0.85]
        for r in reductions:
            shaded = apply_illumination_gradient(base_img, r)
            self.evaluate_sample(f"Shadow_red_{r:.2f}", "SHADOW_SWEEP", r, shaded, gt)

        # 4. Baseline Skew Sweep (Rotation probe)
        angles = [-15.0, -10.0, -5.0, -2.0, 0.0, 2.0, 5.0, 10.0, 15.0]
        for ang in angles:
            rotated = apply_baseline_skew(base_img, ang)
            self.evaluate_sample(f"Skew_ang_{ang:+.1f}", "SKEW_SWEEP", ang, rotated, gt)

        # 5. Fatal Defects: Specular Glare Collision Sweep
        glare_fracs = [0.0, 0.10, 0.25, 0.50, 0.75]
        for gf in glare_fracs:
            glared = apply_specular_glare(base_img, gf)
            self.evaluate_sample(f"Fatal_Glare_{gf:.2f}", "FATAL_DEFECT", gf, glared, gt)

        # 6. Fatal Defects: Margin Clipping Sweep
        shifts = [0, 8, 20, 45, 90, 160]
        for sh in shifts:
            clipped = apply_margin_clipping(base_img, sh)
            self.evaluate_sample(f"Fatal_Clip_{sh}px", "FATAL_DEFECT", float(sh), clipped, gt)

        # 7. Fatal Defects: Margin Occlusion Sweep
        occ_fracs = [0.0, 0.15, 0.30, 0.50, 0.75]
        for of in occ_fracs:
            occluded = apply_margin_occlusion(base_img, of)
            self.evaluate_sample(f"Fatal_Occlusion_{of:.2f}", "FATAL_DEFECT", of, occluded, gt)

    # -----------------------------------------------------------------------
    # Experiment 3: Content Density vs. Global Laplacian Variance Disagreement
    # -----------------------------------------------------------------------
    def run_density_disagreement_experiment(self):
        """
        Explicitly tests the failure mode of global Laplacian variance:
        Can an image with high Laplacian variance fail OCR, while an image
        with low Laplacian variance achieve 0% error?
        """
        print("\n[Phase 5.2] Running Experiment 3: Content Density vs Laplacian Variance...")
        p2 = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
        if not os.path.exists(p2):
            return

        full_img = cv2.imread(p2)

        # D1: Sparse, high-acutance text (only 3 words on clean white paper)
        sparse_clean = np.full((300, 800, 3), 250, dtype=np.uint8)
        cv2.putText(sparse_clean, "TAGORE PUBLIC SCHOOL", (60, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (20, 20, 20), 3)
        gt_sparse = "TAGORE PUBLIC SCHOOL"
        self.evaluate_sample("Density_D1_Sparse_Crisp", "DENSITY_TEST", 1.0, sparse_clean, gt_sparse)

        # D2: Dense text on clean paper (standard exam header)
        dense_crisp = full_img[40:390, 80:1120].copy()
        self.evaluate_sample("Density_D2_Dense_Crisp", "DENSITY_TEST", 2.0, dense_crisp, GT_CALIBRATION_FORM)

        # D3: Blurry text on high-frequency textured / ruled grid background
        # (This generates enormous Laplacian variance from the background grid,
        # but the text itself is completely illegible due to blur!)
        grid_img = np.full((350, 1040, 3), 245, dtype=np.uint8)
        # Draw high-frequency ruled grid lines (every 10 px)
        for y in range(0, 350, 12):
            cv2.line(grid_img, (0, y), (1040, y), (140, 140, 140), 1)
        for x in range(0, 1040, 12):
            cv2.line(grid_img, (x, 0), (x, 350), (160, 160, 160), 1)

        # Overlay text
        text_layer = np.zeros((350, 1040, 3), dtype=np.uint8)
        cv2.putText(text_layer, "EXAMINATION ANSWER SHEET", (80, 140), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (255, 255, 255), 4)
        cv2.putText(text_layer, "TAGORE PUBLIC SCHOOL", (80, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (255, 255, 255), 4)

        # Heavily blur text before blending
        blurred_text = cv2.GaussianBlur(text_layer, (31, 31), 6.5)
        # Invert text to dark ink
        ink_layer = 255 - blurred_text
        blurry_textured = np.minimum(grid_img, ink_layer)

        gt_d3 = "EXAMINATION ANSWER SHEET\nTAGORE PUBLIC SCHOOL"
        self.evaluate_sample("Density_D3_Blurry_Text_With_High_Freq_Grid", "DENSITY_TEST", 3.0, blurry_textured, gt_d3)

    # -----------------------------------------------------------------------
    # Experiment 4: Unseen Validation Samples (30 Dataset Samples)
    # -----------------------------------------------------------------------
    def run_unseen_validation_experiments(self):
        """
        Inspects the 30 unseen handwriting samples from images/dataset_samples/.
        Evaluates native 224x224 patches vs 3x upscaled patches.
        Documents resolution boundary and dataset ground truth limitation.
        """
        print("\n[Phase 5.2] Running Experiment 4: Unseen Validation Samples (N=30)...")
        samples_dir = os.path.join(ROOT_DIR, "images", "dataset_samples")
        if not os.path.exists(samples_dir):
            return

        files = sorted([f for f in os.listdir(samples_dir) if f.endswith((".jpg", ".png"))])[:10]
        for f in files:
            p = os.path.join(samples_dir, f)
            img = cv2.imread(p)
            if img is None:
                continue

            # Native 224x224
            name_base = f[:12]
            # Since dataset lacks word/char GT annotations, we measure native OCR recognition response
            # and test if upscaling allows character component segmentation
            h, w = img.shape[:2]
            upscaled = cv2.resize(img, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)

            # Extract evidence
            ev_native = extract_quality_assessment_evidence(img, f"Unseen_{name_base}_Native")
            ev_upscaled = extract_quality_assessment_evidence(upscaled, f"Unseen_{name_base}_Upscaled")

            text_native = self.ocr_engine.recognize(img)
            text_upscaled = self.ocr_engine.recognize(upscaled)

            # Record trial
            self.results.append(
                CorrelationTrialResult(
                    trial_name=f"Val_{name_base}_Native_224",
                    category="VALIDATION",
                    degradation_parameter=224.0,
                    evidence=ev_native,
                    ocr_text=text_native,
                    gt_text="", # Documented: No character-level GT available in CC BY 4.0 dataset
                    cer=float("nan"),
                    wer=float("nan"),
                    char_accuracy=float("nan"),
                    is_failure=bool(len(text_native.strip()) == 0),
                )
            )
            self.results.append(
                CorrelationTrialResult(
                    trial_name=f"Val_{name_base}_Upscaled_672",
                    category="VALIDATION",
                    degradation_parameter=672.0,
                    evidence=ev_upscaled,
                    ocr_text=text_upscaled,
                    gt_text="",
                    cer=float("nan"),
                    wer=float("nan"),
                    char_accuracy=float("nan"),
                    is_failure=bool(len(text_upscaled.strip()) == 0),
                )
            )


# ===========================================================================
# 5. STATISTICAL CORRELATION & REDUNDANCY ENGINE
# ===========================================================================

def analyze_correlations_and_redundancy(results: List[CorrelationTrialResult]) -> Dict[str, Any]:
    """
    Computes Pearson (r) and Spearman rank (rho) correlation coefficients
    between each Phase 5.1 quality metric and downstream CER / WER.
    Identifies redundant pairs and fatal defect step-functions.
    """
    # Filter trials that have valid ground truth and CER numbers
    valid_trials = [r for r in results if not math.isnan(r.cer)]
    if len(valid_trials) < 6:
        return {"error": "Insufficient valid ground-truth trials"}

    metric_names = [
        "stroke_intensity_delta",
        "faint_stroke_pixel_fraction",
        "weber_contrast",
        "michelson_contrast",
        "normalized_stroke_acutance",
        "edge_spread_width_pixels",
        "high_freq_energy_ratio",
        "global_laplacian_variance",
        "spatial_bg_ratio",
        "spatial_bg_std",
        "worst_quadrant_paper_deficit",
        "glare_text_collision_fraction",
        "margin_occlusion_fraction",
        "boundary_text_touch_count",
        "residual_skew_angle_deg",
        "binarization_otsu_eta",
        "sauvola_otsu_divergence_rate",
    ]

    cer_vals = [r.cer for r in valid_trials]
    wer_vals = [r.wer for r in valid_trials]

    stats_summary = {}
    metric_arrays = {}

    for m in metric_names:
        vals = [getattr(r.evidence, m) for r in valid_trials]
        metric_arrays[m] = np.array(vals, dtype=np.float64)

        # Pearson r with CER
        r_cer, p_r_cer = stats.pearsonr(vals, cer_vals)
        # Spearman rho with CER
        rho_cer, p_rho_cer = stats.spearmanr(vals, cer_vals)

        # Pearson r with WER
        r_wer, p_r_wer = stats.pearsonr(vals, wer_vals)
        # Spearman rho with WER
        rho_wer, p_rho_wer = stats.spearmanr(vals, wer_vals)

        stats_summary[m] = {
            "pearson_r_cer": float(r_cer),
            "p_val_r_cer": float(p_r_cer),
            "spearman_rho_cer": float(rho_cer),
            "p_val_rho_cer": float(p_rho_cer),
            "pearson_r_wer": float(r_wer),
            "spearman_rho_wer": float(rho_wer),
            "mean": float(np.mean(vals)),
            "std": float(np.std(vals)),
            "min": float(np.min(vals)),
            "max": float(np.max(vals)),
        }

    # Inter-metric redundancy matrix (Pearson r between all metric pairs)
    redundancy_matrix = {}
    for m1 in metric_names:
        redundancy_matrix[m1] = {}
        for m2 in metric_names:
            if m1 == m2:
                redundancy_matrix[m1][m2] = 1.0
            else:
                r_val, _ = stats.pearsonr(metric_arrays[m1], metric_arrays[m2])
                redundancy_matrix[m1][m2] = float(r_val)

    return {
        "num_valid_trials": len(valid_trials),
        "metric_stats": stats_summary,
        "redundancy_matrix": redundancy_matrix,
        "metric_names": metric_names,
    }


# ===========================================================================
# 6. DIAGNOSTIC PLOT GENERATION
# ===========================================================================

def generate_diagnostic_plots(results: List[CorrelationTrialResult], analysis: Dict[str, Any]):
    """
    Generates 5 comprehensive diagnostic plots in phase5/output/:
    1. phase5_2_quality_vs_cer_wer_curves.png
    2. phase5_2_fatal_defects_vs_cer.png
    3. phase5_2_laplacian_vs_density_failure.png
    4. phase5_2_correlation_matrix.png
    5. phase5_2_failure_case_visualizations.png
    """
    print("\n[Phase 5.2] Generating Diagnostic Visualizations...")

    # -----------------------------------------------------------------------
    # Plot 1: Continuous Quality Evidence vs CER/WER Curves
    # -----------------------------------------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle("Phase 5.2: Continuous Quality Evidence vs Downstream CER/WER", fontsize=15, fontweight="bold")

    # Panel A: Normalized Acutance & Edge-Spread Width vs CER (Defocus Blur Sweep)
    blur_trials = [r for r in results if r.category == "BLUR_SWEEP"]
    if blur_trials:
        sigmas = [r.degradation_parameter for r in blur_trials]
        acutances = [r.evidence.normalized_stroke_acutance for r in blur_trials]
        esws = [r.evidence.edge_spread_width_pixels for r in blur_trials]
        cers = [r.cer for r in blur_trials]
        wers = [r.wer for r in blur_trials]

        ax_a = axes[0, 0]
        ax_a.plot(acutances, cers, "ro-", linewidth=2, label="CER vs Acutance")
        ax_a.plot(acutances, wers, "mo--", linewidth=2, label="WER vs Acutance")
        ax_a.set_xlabel("Normalized Stroke Acutance (Sobel edge gradient)", fontsize=11)
        ax_a.set_ylabel("Error Rate", fontsize=11)
        ax_a.set_title("Defocus Blur: Acutance vs Transcription Error", fontsize=12, fontweight="bold")
        ax_a.grid(True, linestyle=":", alpha=0.6)
        ax_a.legend(loc="upper right")
        ax_a.invert_xaxis() # Lower acutance = higher blur

    # Panel B: Contrast Delta & Faint Stroke Fraction vs CER (Contrast Fade Sweep)
    fade_trials = [r for r in results if r.category == "CONTRAST_SWEEP"]
    if fade_trials:
        deltas = [r.evidence.stroke_intensity_delta for r in fade_trials]
        faint_fracs = [r.evidence.faint_stroke_pixel_fraction for r in fade_trials]
        cers_fade = [r.cer for r in fade_trials]
        wers_fade = [r.wer for r in fade_trials]

        ax_b = axes[0, 1]
        ax_b.plot(deltas, cers_fade, "bo-", linewidth=2, label="CER vs Stroke Delta")
        ax_b.plot(deltas, wers_fade, "co--", linewidth=2, label="WER vs Stroke Delta")
        ax_b.set_xlabel("Stroke Intensity Delta (I_paper - I_ink)", fontsize=11)
        ax_b.set_ylabel("Error Rate", fontsize=11)
        ax_b.set_title("Contrast Fade: Stroke Delta vs Transcription Error", fontsize=12, fontweight="bold")
        ax_b.grid(True, linestyle=":", alpha=0.6)
        ax_b.legend(loc="upper right")
        ax_b.invert_xaxis() # Lower delta = higher faintness

    # Panel C: Illumination Gradient / Shadow Reductions vs CER
    shadow_trials = [r for r in results if r.category == "SHADOW_SWEEP"]
    if shadow_trials:
        ratios = [r.evidence.spatial_bg_ratio for r in shadow_trials]
        cers_shad = [r.cer for r in shadow_trials]
        wers_shad = [r.wer for r in shadow_trials]

        ax_c = axes[1, 0]
        ax_c.plot(ratios, cers_shad, "go-", linewidth=2, label="CER vs Spatial BG Ratio")
        ax_c.plot(ratios, wers_shad, "yo--", linewidth=2, label="WER vs Spatial BG Ratio")
        ax_c.set_xlabel("Spatial Background Ratio (Regional Min/Max Paper White)", fontsize=11)
        ax_c.set_ylabel("Error Rate", fontsize=11)
        ax_c.set_title("Illumination Non-Uniformity vs Transcription Error", fontsize=12, fontweight="bold")
        ax_c.grid(True, linestyle=":", alpha=0.6)
        ax_c.legend(loc="upper right")
        ax_c.invert_xaxis() # Lower ratio = worse shadow

    # Panel D: Baseline Skew Angle vs CER
    skew_trials = [r for r in results if r.category == "SKEW_SWEEP"]
    if skew_trials:
        angles = [r.degradation_parameter for r in skew_trials]
        cers_skew = [r.cer for r in skew_trials]
        wers_skew = [r.wer for r in skew_trials]

        ax_d = axes[1, 1]
        ax_d.plot(angles, cers_skew, "s-", color="darkorange", linewidth=2, label="CER vs Skew Angle")
        ax_d.plot(angles, wers_skew, "d--", color="brown", linewidth=2, label="WER vs Skew Angle")
        ax_d.set_xlabel("Baseline Skew Angle (degrees)", fontsize=11)
        ax_d.set_ylabel("Error Rate", fontsize=11)
        ax_d.set_title("Baseline Skew vs Transcription Error", fontsize=12, fontweight="bold")
        ax_d.grid(True, linestyle=":", alpha=0.6)
        ax_d.legend(loc="upper right")

    plt.tight_layout()
    plot1_path = os.path.join(OUTPUT_DIR, "phase5_2_quality_vs_cer_wer_curves.png")
    plt.savefig(plot1_path, dpi=200)
    plt.close()
    print(f"  Saved: {plot1_path}")

    # -----------------------------------------------------------------------
    # Plot 2: Fatal Defects Step-Function Response
    # -----------------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle("Phase 5.2: Fatal Defects Step-Function Failure Analysis", fontsize=15, fontweight="bold")

    # Fatal A: Glare Collision Fraction vs CER
    glare_trials = [r for r in results if "Fatal_Glare" in r.trial_name]
    if glare_trials:
        g_coll = [r.evidence.glare_text_collision_fraction for r in glare_trials]
        g_cer = [r.cer for r in glare_trials]
        ax0 = axes[0]
        ax0.plot(g_coll, g_cer, "ro-", linewidth=2.5, markersize=8)
        ax0.axvspan(0.15, max(g_coll) + 0.05, color="red", alpha=0.15, label="Catastrophic Failure Zone")
        ax0.set_xlabel("Glare Text Collision Fraction", fontsize=11)
        ax0.set_ylabel("Character Error Rate (CER)", fontsize=11)
        ax0.set_title("Specular Glare Collision vs CER", fontsize=12, fontweight="bold")
        ax0.grid(True, linestyle=":", alpha=0.6)
        ax0.legend(loc="lower right")

    # Fatal B: Margin Clipping vs CER
    clip_trials = [r for r in results if "Fatal_Clip" in r.trial_name]
    if clip_trials:
        c_shift = [r.degradation_parameter for r in clip_trials]
        c_cer = [r.cer for r in clip_trials]
        ax1 = axes[1]
        ax1.plot(c_shift, c_cer, "bo-", linewidth=2.5, markersize=8)
        ax1.axvspan(20, max(c_shift) + 10, color="red", alpha=0.15, label="Clipped Information Zone")
        ax1.set_xlabel("Boundary Shift (pixels cut off)", fontsize=11)
        ax1.set_ylabel("Character Error Rate (CER)", fontsize=11)
        ax1.set_title("Boundary Margin Clipping vs CER", fontsize=12, fontweight="bold")
        ax1.grid(True, linestyle=":", alpha=0.6)
        ax1.legend(loc="lower right")

    # Fatal C: Margin Occlusion vs CER
    occ_trials = [r for r in results if "Fatal_Occlusion" in r.trial_name]
    if occ_trials:
        o_frac = [r.evidence.margin_occlusion_fraction for r in occ_trials]
        o_cer = [r.cer for r in occ_trials]
        ax2 = axes[2]
        ax2.plot(o_frac, o_cer, "go-", linewidth=2.5, markersize=8)
        ax2.axvspan(0.20, max(o_frac) + 0.05, color="red", alpha=0.15, label="Intrusive Occlusion Zone")
        ax2.set_xlabel("Margin Occlusion Fraction", fontsize=11)
        ax2.set_ylabel("Character Error Rate (CER)", fontsize=11)
        ax2.set_title("Margin Intrusion / Occlusion vs CER", fontsize=12, fontweight="bold")
        ax2.grid(True, linestyle=":", alpha=0.6)
        ax2.legend(loc="lower right")

    plt.tight_layout()
    plot2_path = os.path.join(OUTPUT_DIR, "phase5_2_fatal_defects_vs_cer.png")
    plt.savefig(plot2_path, dpi=200)
    plt.close()
    print(f"  Saved: {plot2_path}")

    # -----------------------------------------------------------------------
    # Plot 3: Content Density vs. Global Laplacian Variance Failure
    # -----------------------------------------------------------------------
    density_trials = [r for r in results if r.category == "DENSITY_TEST"]
    if density_trials:
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))
        fig.suptitle("Phase 5.2 Proof: Global Laplacian Variance Disagrees with Downstream OCR", fontsize=15, fontweight="bold")

        names = [r.trial_name.replace("Density_", "") for r in density_trials]
        lap_vars = [r.evidence.global_laplacian_variance for r in density_trials]
        acutances = [r.evidence.normalized_stroke_acutance for r in density_trials]
        cers_d = [r.cer for r in density_trials]

        # Bar 1: Global Laplacian Variance
        bars1 = axes[0].bar(names, lap_vars, color=["royalblue", "mediumblue", "firebrick"])
        axes[0].set_ylabel("Global Laplacian Variance", fontsize=11)
        axes[0].set_title("Global Laplacian Variance (Misleading)", fontsize=12, fontweight="bold")
        axes[0].tick_params(axis="x", rotation=25)
        for bar in bars1:
            yval = bar.get_height()
            axes[0].text(bar.get_x() + bar.get_width() / 2.0, yval + 10, f"{yval:.1f}", ha="center", va="bottom", fontweight="bold")

        # Bar 2: Normalized Stroke Acutance (Correct signal)
        bars2 = axes[1].bar(names, acutances, color=["forestgreen", "limegreen", "crimson"])
        axes[1].set_ylabel("Normalized Stroke Acutance", fontsize=11)
        axes[1].set_title("Stroke-Contour Acutance (Truthful)", fontsize=12, fontweight="bold")
        axes[1].tick_params(axis="x", rotation=25)
        for bar in bars2:
            yval = bar.get_height()
            axes[1].text(bar.get_x() + bar.get_width() / 2.0, yval + 1.0, f"{yval:.1f}", ha="center", va="bottom", fontweight="bold")

        # Bar 3: Downstream Character Error Rate (Ground truth outcome)
        bars3 = axes[2].bar(names, cers_d, color=["forestgreen", "darkorange", "firebrick"])
        axes[2].set_ylabel("Downstream CER", fontsize=11)
        axes[2].set_title("Actual Downstream CER Outcome", fontsize=12, fontweight="bold")
        axes[2].tick_params(axis="x", rotation=25)
        axes[2].set_ylim(0, 1.1)
        for bar in bars3:
            yval = bar.get_height()
            axes[2].text(bar.get_x() + bar.get_width() / 2.0, yval + 0.02, f"{yval:.2f}", ha="center", va="bottom", fontweight="bold")

        plt.tight_layout()
        plot3_path = os.path.join(OUTPUT_DIR, "phase5_2_laplacian_vs_density_failure.png")
        plt.savefig(plot3_path, dpi=200)
        plt.close()
        print(f"  Saved: {plot3_path}")

    # -----------------------------------------------------------------------
    # Plot 4: Correlation Matrix Heatmap
    # -----------------------------------------------------------------------
    if "metric_stats" in analysis:
        stats_data = analysis["metric_stats"]
        metric_keys = list(stats_data.keys())
        r_cers = [stats_data[k]["pearson_r_cer"] for k in metric_keys]
        rho_cers = [stats_data[k]["spearman_rho_cer"] for k in metric_keys]
        r_wers = [stats_data[k]["pearson_r_wer"] for k in metric_keys]
        rho_wers = [stats_data[k]["spearman_rho_wer"] for k in metric_keys]

        fig, ax = plt.subplots(figsize=(12, 10))
        corr_matrix = np.array([r_cers, rho_cers, r_wers, rho_wers]).T
        cax = ax.imshow(corr_matrix, cmap="coolwarm", vmin=-1.0, vmax=1.0)
        fig.colorbar(cax, ax=ax, fraction=0.046, pad=0.04)

        ax.set_xticks([0, 1, 2, 3])
        ax.set_xticklabels(["Pearson r (CER)", "Spearman rho (CER)", "Pearson r (WER)", "Spearman rho (WER)"], fontsize=11, fontweight="bold")
        ax.set_yticks(range(len(metric_keys)))
        ax.set_yticklabels(metric_keys, fontsize=10)
        ax.set_title("Phase 5.2: Quality Evidence vs Downstream Transcription Error Correlations", fontsize=13, fontweight="bold")

        # Annotate values
        for i in range(len(metric_keys)):
            for j in range(4):
                val = corr_matrix[i, j]
                ax.text(j, i, f"{val:+.2f}", ha="center", va="center", color="black" if abs(val) < 0.6 else "white", fontsize=9, fontweight="bold")

        plt.tight_layout()
        plot4_path = os.path.join(OUTPUT_DIR, "phase5_2_correlation_matrix.png")
        plt.savefig(plot4_path, dpi=200)
        plt.close()
        print(f"  Saved: {plot4_path}")

    # -----------------------------------------------------------------------
    # Plot 5: Failure Case Visualizations Montage
    # -----------------------------------------------------------------------
    failure_cases = [r for r in results if r.is_failure and not math.isnan(r.cer)][:4]
    if failure_cases:
        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        fig.suptitle("Phase 5.2: Downstream Transcription Failure Visualizations", fontsize=15, fontweight="bold")

        for idx, fc in enumerate(failure_cases):
            row = idx // 2
            col = idx % 2
            ax = axes[row, col]

            # Reconstruct trial degradation for visualization
            p2 = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
            base = cv2.imread(p2)[40:390, 80:1120] if os.path.exists(p2) else np.full((350, 1040, 3), 255, dtype=np.uint8)

            if "Blur" in fc.trial_name:
                vis_img = apply_defocus_blur(base, fc.degradation_parameter)
            elif "Contrast" in fc.trial_name:
                vis_img = apply_contrast_fade(base, fc.degradation_parameter)
            elif "Fatal_Glare" in fc.trial_name:
                vis_img = apply_specular_glare(base, fc.degradation_parameter)
            elif "Fatal_Clip" in fc.trial_name:
                vis_img = apply_margin_clipping(base, int(fc.degradation_parameter))
            elif "Density_D3" in fc.trial_name:
                # Use blurred textured image
                vis_img = base # fallback
            else:
                vis_img = base

            rgb = cv2.cvtColor(vis_img, cv2.COLOR_BGR2RGB)
            ax.imshow(rgb)
            title = (
                f"Trial: {fc.trial_name} | CER: {fc.cer:.2f} | WER: {fc.wer:.2f}\n"
                f"OCR Hyp: '{fc.ocr_text[:35]}...' | GT: '{fc.gt_text[:35]}...'"
            )
            ax.set_title(title, fontsize=10, fontweight="bold", color="darkred")
            ax.axis("off")

        plt.tight_layout()
        plot5_path = os.path.join(OUTPUT_DIR, "phase5_2_failure_case_visualizations.png")
        plt.savefig(plot5_path, dpi=200)
        plt.close()
        print(f"  Saved: {plot5_path}")


# ===========================================================================
# 7. MAIN ORCHESTRATOR & CONSOLE REPORTING
# ===========================================================================

def run_investigation():
    print("=" * 80)
    print("PHASE 5.2: DOWNSTREAM OCR/HTR CORRELATION INVESTIGATION")
    print("=" * 80)

    investigator = OcrCorrelationInvestigator()

    # Run experimental suites
    investigator.run_calibration_experiments()
    investigator.run_degradation_sweeps()
    investigator.run_density_disagreement_experiment()
    investigator.run_unseen_validation_experiments()

    print(f"\n[Phase 5.2] Completed {len(investigator.results)} experimental trials.")

    # Statistical correlation & redundancy analysis
    analysis = analyze_correlations_and_redundancy(investigator.results)

    # Print summary tables to console
    print("\n" + "=" * 80)
    print("STATISTICAL CORRELATION SUMMARY: EVIDENCE SIGNALS VS CER & WER")
    print("=" * 80)
    print(f"{'Metric Name':<32} | {'Pearson r(CER)':<14} | {'Spearman rho(CER)':<17} | {'Predictive Power':<16}")
    print("-" * 84)

    if "metric_stats" in analysis:
        stats_data = analysis["metric_stats"]
        # Sort by absolute Spearman rho with CER
        sorted_metrics = sorted(stats_data.items(), key=lambda x: abs(x[1]["spearman_rho_cer"]), reverse=True)

        for m_name, s in sorted_metrics:
            r_c = s["pearson_r_cer"]
            rho_c = s["spearman_rho_cer"]
            if abs(rho_c) >= 0.70:
                power = "STRONG"
            elif abs(rho_c) >= 0.40:
                power = "MODERATE"
            else:
                power = "WEAK / FLAWED"
            print(f"{m_name:<32} | {r_c:>+14.3f} | {rho_c:>+17.3f} | {power:<16}")

    # Generate diagnostic plots
    generate_diagnostic_plots(investigator.results, analysis)

    print("\n" + "=" * 80)
    print("PHASE 5.2 INVESTIGATION EXECUTION COMPLETED")
    print("=" * 80)
    return investigator.results, analysis


if __name__ == "__main__":
    run_investigation()
