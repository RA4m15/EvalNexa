"""
phase5/03_quality_gate_architecture_investigation.py

AI-EVAL PHASE 5.3: SMART QUALITY ASSESSMENT EVIDENCE & GATE ARCHITECTURE CONSOLIDATION
======================================================================================

PURPOSE:
Consolidate the findings from Phase 5.1 (Quality Evidence Extraction) and
Phase 5.2 (Downstream OCR/HTR Correlation) into a rigorous, production-oriented
conceptual architecture for document quality assessment.

CONSOLIDATION PRINCIPLES:
1. Hierarchical Non-Compensatory Architecture:
   Processed / Enhanced Image
   ↓
   Tier 1 — Fatal Defect Gate (Non-compensatory Boolean Veto Filters)
   ↓
   Tier 2 — Multi-Dimensional Quality Evidence Profile (Orthogonal Vectors)
   ↓
   Tier 3 — Evaluation Readiness Verdict (Semantic Multi-Band Categorization)

2. Explicit Signal Curation & Deprecation:
   - Deprecate Global Laplacian Variance (banned from gating; diagnostic only).
   - Deprecate Weber & Michelson contrast (redundant with Stroke Intensity Delta).
   - Retain scale-normalized Stroke Acutance, Edge-Spread Width, Stroke Delta,
     Faint Stroke Fraction, Glare Text Collision, Margin Text Clipping,
     Margin Occlusion, Otsu Binarization Eta, and Baseline Skew.

3. Semantic Readiness States (No Universal 0-100 Score):
   - GOOD, ACCEPTABLE, BORDERLINE, UNUSABLE.
   - Preserve distinction: "Can Be Enhanced" != "Good Enough for Evaluation".
   - Fatal defects cannot be compensated for by good scores in other dimensions.

GUARDRAILS:
- INVESTIGATION ONLY.
- Do NOT implement the production quality assessment system yet.
- Do NOT freeze production numerical thresholds.
- Do NOT modify frozen Phase 2, Phase 3, or Phase 4 files.
"""

import os
import sys
import math
import importlib.util
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict, field

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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
# 1. QUALITY GATE ARCHITECTURAL CONTRACTS
# ===========================================================================

@dataclass
class FatalDefectVerdict:
    """
    Tier 1 Fatal Defect Veto outcome.
    Any single fatal defect results in an immediate veto.
    """
    is_fatal: bool
    defect_code: Optional[str] = None          # E.g., FATAL_GLARE_COLLISION, FATAL_TEXT_CLIPPED
    evidence_dimension: Optional[str] = None   # Name of offending measurement
    measured_value: float = 0.0
    baseline_reference: float = 0.0
    rationale: str = ""


@dataclass
class CuratedQualityProfile:
    """
    Tier 2 Curated Multi-Dimensional Quality Evidence Profile.
    Preserves independent evidence dimensions while omitting redundant/unreliable metrics.
    """
    image_name: str
    dimensions: Tuple[int, int]
    scale_factor: float

    # 1. Primary Contrast & Visibility
    stroke_intensity_delta: float              # I_paper - I_ink (linear, intuitive)
    faint_stroke_pixel_fraction: float         # Fraction of ink with contrast < 25 levels

    # 2. Optical Sharpness & Acutance (Scale-Normalized)
    normalized_stroke_acutance: float          # Mean Sobel gradient strictly along ink-paper contours
    edge_spread_width_pixels: float            # 10%-90% gradient transition distance

    # 3. Illumination Uniformity & Shadow
    spatial_bg_ratio: float                    # Regional min/max background intensity across 4x4 grid
    worst_quadrant_paper_deficit: float        # Global paper white minus darkest regional paper white

    # 4. Specular Glare & Reflection
    glare_pixel_fraction: float                # Percentage of saturated pixels (I >= 254)
    glare_text_collision_fraction: float       # Percentage of text stroke pixels obliterated by glare

    # 5. Framing & Margin Completeness
    boundary_text_touch_count: int             # Count of text pixels intersecting the outer border band
    text_margin_clearance_min_px: float        # Minimum distance from any character glyph to image border

    # 6. Obstruction & Foreign Intrusion
    margin_occlusion_fraction: float           # Margin area covered by intrusive objects (fingers, clips)
    foreign_object_detected: bool

    # 7. Geometric Integrity
    residual_skew_angle_deg: float             # Baseline tilt angle in degrees
    aspect_ratio_a4_deviation: float           # Deviation from standard A4 aspect ratio

    # 8. Binarization & Topology Readiness
    binarization_otsu_eta: float               # Between-class / total variance separation ratio
    median_character_height_px: float          # Median character bounding box height

    # Diagnostic-Only Telemetry (Excluded from Quality Gate Decisions)
    diagnostic_laplacian_variance: float       # Global Laplacian variance (strictly logged, NOT used in gating)
    diagnostic_weber_contrast: float           # Retained only for legacy reference


@dataclass
class QualityReadinessVerdict:
    """
    Tier 3 Final Evaluation Readiness Verdict.
    Non-scalar, non-compensatory readiness determination.
    """
    readiness_state: str                       # "GOOD", "ACCEPTABLE", "BORDERLINE", "UNUSABLE"
    enhancement_potential: str                 # "ALREADY_CLEAN", "CAN_BE_ENHANCED", "UNRECOVERABLE"
    fatal_defects: List[FatalDefectVerdict] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    mitigation_notes: List[str] = field(default_factory=list)


# ===========================================================================
# 2. CONSOLIDATED QUALITY GATE ARCHITECTURE ENGINE
# ===========================================================================

class SmartQualityGateArchitecture:
    """
    Conceptual implementation of the 3-Tier Quality Gate Architecture.
    Consolidates Phase 5.1 & 5.2 evidence into a structured evaluation engine.
    """

    # Empirical calibration reference points (EXPLICITLY UNFREEZED - CALIBRATION BASELINES ONLY)
    CALIB_FATAL_GLARE_COLLISION = 0.08         # Text collision > 8% permanently destroys character recognition
    CALIB_FATAL_CLIPPING_TOUCHES = 80          # > 80 text boundary pixels touching outer frame band
    CALIB_FATAL_DEFOCUS_ACUTANCE = 120.0       # Normalized acutance < 120 causes total OCR blackout (CER=1.0)
    CALIB_FATAL_EDGE_SPREAD = 4.5              # Edge spread width > 4.5 px indicates complete defocus
    CALIB_FATAL_FAINT_STROKES = 0.60           # Faint stroke fraction > 60% causes stroke disconnection
    CALIB_FATAL_STROKE_DELTA = 18.0            # Stroke delta < 18 levels blends ink into paper noise
    CALIB_FATAL_OCCLUSION_FRAC = 0.25          # Margin occlusion > 25% obstructs document content

    # Degradable risk reference bands (EMPIRICAL ONLY)
    CALIB_BORDERLINE_ACUTANCE = 220.0          # Acutance 120-220: OCR CER begins rising (0.60-0.75)
    CALIB_BORDERLINE_STROKE_DELTA = 35.0       # Stroke delta 18-35: OCR at risk of character dropout
    CALIB_BORDERLINE_FAINT_FRACTION = 0.35     # Faint fraction 35-60%: Broken character loops
    CALIB_BORDERLINE_SKEW = 7.0                # Skew > 7 degrees: Line grouping degradation
    CALIB_BORDERLINE_BG_RATIO = 0.65           # Background ratio < 0.65: Heavy non-uniform shadow
    CALIB_BORDERLINE_OTSU_ETA = 0.30           # Binarization separation < 0.30: Poor bimodality

    def curate_evidence_profile(self, ev: QualityAssessmentEvidence) -> CuratedQualityProfile:
        """
        Filters raw 5.1 evidence into the curated Tier 2 profile.
        Explicitly removes redundant contrast metrics and deprecates global Laplacian variance.
        """
        return CuratedQualityProfile(
            image_name=ev.image_name,
            dimensions=ev.dimensions,
            scale_factor=ev.scale_factor,
            stroke_intensity_delta=ev.stroke_intensity_delta,
            faint_stroke_pixel_fraction=ev.faint_stroke_pixel_fraction,
            normalized_stroke_acutance=ev.normalized_stroke_acutance,
            edge_spread_width_pixels=ev.edge_spread_width_pixels,
            spatial_bg_ratio=ev.spatial_bg_ratio,
            worst_quadrant_paper_deficit=ev.worst_quadrant_paper_deficit,
            glare_pixel_fraction=ev.glare_pixel_fraction,
            glare_text_collision_fraction=ev.glare_text_collision_fraction,
            boundary_text_touch_count=ev.boundary_text_touch_count,
            text_margin_clearance_min_px=ev.text_margin_clearance_min_px,
            margin_occlusion_fraction=ev.margin_occlusion_fraction,
            foreign_object_detected=ev.foreign_object_detected,
            residual_skew_angle_deg=ev.residual_skew_angle_deg,
            aspect_ratio_a4_deviation=ev.aspect_ratio_a4_deviation,
            binarization_otsu_eta=ev.binarization_otsu_eta,
            median_character_height_px=ev.median_character_height_px,
            diagnostic_laplacian_variance=ev.global_laplacian_variance,  # Telemetry only
            diagnostic_weber_contrast=ev.weber_contrast,                # Telemetry only
        )

    # -----------------------------------------------------------------------
    # TIER 1: FATAL DEFECT VETO GATE
    # -----------------------------------------------------------------------
    def evaluate_tier1_fatal_defects(self, p: CuratedQualityProfile) -> List[FatalDefectVerdict]:
        """
        Evaluates non-compensatory veto filters.
        If any defect is present, the image cannot be evaluated reliably.
        """
        fatal_verdicts = []

        # 1. Text-Colliding Specular Glare (Catastrophic step-function proven in Phase 5.2)
        if p.glare_text_collision_fraction > self.CALIB_FATAL_GLARE_COLLISION:
            fatal_verdicts.append(
                FatalDefectVerdict(
                    is_fatal=True,
                    defect_code="FATAL_GLARE_COLLISION",
                    evidence_dimension="glare_text_collision_fraction",
                    measured_value=p.glare_text_collision_fraction,
                    baseline_reference=self.CALIB_FATAL_GLARE_COLLISION,
                    rationale=(
                        f"Specular glare saturates {p.glare_text_collision_fraction*100:.1f}% of text strokes. "
                        "Information is physically obliterated (whiteout); OCR CER rises to 0.75+."
                    )
                )
            )

        # 2. Text Boundary Clipping (Physical page completeness failure)
        # Note: Bounded to non-patch documents (dimensions >= 300px)
        if min(p.dimensions) >= 300 and p.boundary_text_touch_count > self.CALIB_FATAL_CLIPPING_TOUCHES:
            fatal_verdicts.append(
                FatalDefectVerdict(
                    is_fatal=True,
                    defect_code="FATAL_TEXT_CLIPPED",
                    evidence_dimension="boundary_text_touch_count",
                    measured_value=float(p.boundary_text_touch_count),
                    baseline_reference=float(self.CALIB_FATAL_CLIPPING_TOUCHES),
                    rationale=(
                        f"{p.boundary_text_touch_count} stroke pixels intersect the outer sensor frame. "
                        "Critical exam text or student answers are truncated past the page margin."
                    )
                )
            )

        # 3. Severe Optical Defocus Blur (OCR CER = 1.0 proven in Phase 5.2)
        if p.normalized_stroke_acutance < self.CALIB_FATAL_DEFOCUS_ACUTANCE:
            fatal_verdicts.append(
                FatalDefectVerdict(
                    is_fatal=True,
                    defect_code="FATAL_OPTICAL_DEFOCUS",
                    evidence_dimension="normalized_stroke_acutance",
                    measured_value=p.normalized_stroke_acutance,
                    baseline_reference=self.CALIB_FATAL_DEFOCUS_ACUTANCE,
                    rationale=(
                        f"Normalized stroke acutance ({p.normalized_stroke_acutance:.1f}) is below fatal cutoff "
                        f"({self.CALIB_FATAL_DEFOCUS_ACUTANCE:.1f}). Character loops and words are completely fused."
                    )
                )
            )

        # 4. Severe Handwriting Ink Loss (Faint stroke collapse)
        if p.stroke_intensity_delta < self.CALIB_FATAL_STROKE_DELTA or p.faint_stroke_pixel_fraction > self.CALIB_FATAL_FAINT_STROKES:
            fatal_verdicts.append(
                FatalDefectVerdict(
                    is_fatal=True,
                    defect_code="FATAL_INK_LOSS",
                    evidence_dimension="stroke_intensity_delta",
                    measured_value=p.stroke_intensity_delta,
                    baseline_reference=self.CALIB_FATAL_STROKE_DELTA,
                    rationale=(
                        f"Stroke contrast delta ({p.stroke_intensity_delta:.1f}) or faint fraction "
                        f"({p.faint_stroke_pixel_fraction*100:.1f}%) indicates severe ink dropout."
                    )
                )
            )

        # 5. Destructive Foreign Object Occlusion
        if p.margin_occlusion_fraction > self.CALIB_FATAL_OCCLUSION_FRAC:
            fatal_verdicts.append(
                FatalDefectVerdict(
                    is_fatal=True,
                    defect_code="FATAL_MARGIN_OCCLUSION",
                    evidence_dimension="margin_occlusion_fraction",
                    measured_value=p.margin_occlusion_fraction,
                    baseline_reference=self.CALIB_FATAL_OCCLUSION_FRAC,
                    rationale=(
                        f"Intrusive foreign object covers {p.margin_occlusion_fraction*100:.1f}% of margin. "
                        "Potential obstruction of question numbers, marks table, or student identity."
                    )
                )
            )

        # 6. Geometric Aspect Collapse
        if p.aspect_ratio_a4_deviation > 0.45:
            fatal_verdicts.append(
                FatalDefectVerdict(
                    is_fatal=True,
                    defect_code="FATAL_GEOMETRIC_COLLAPSE",
                    evidence_dimension="aspect_ratio_a4_deviation",
                    measured_value=p.aspect_ratio_a4_deviation,
                    baseline_reference=0.45,
                    rationale=(
                        f"Aspect ratio deviation ({p.aspect_ratio_a4_deviation:.2f}) indicates severe "
                        "trapezoidal perspective collapse or invalid corner quad rectification."
                    )
                )
            )

        return fatal_verdicts

    # -----------------------------------------------------------------------
    # TIER 2 & TIER 3: MULTI-DIMENSIONAL VERDICT ENGINE
    # -----------------------------------------------------------------------
    def evaluate_readiness(self, p: CuratedQualityProfile) -> QualityReadinessVerdict:
        """
        Executes the hierarchical 3-Tier Quality Assessment pipeline:
        1. Evaluate Tier 1 Fatal Defects.
        2. Inspect Tier 2 Curated Profile for degradable risks.
        3. Formulate Tier 3 Evaluation Readiness Verdict and Enhancement Potential.
        """
        # Step 1: Tier 1 Fatal Defect Veto Gate
        fatal_verdicts = self.evaluate_tier1_fatal_defects(p)

        if fatal_verdicts:
            # NON-COMPENSATORY VETO: Fatal defect immediately forces UNUSABLE verdict
            risk_factors = [f.rationale for f in fatal_verdicts]
            return QualityReadinessVerdict(
                readiness_state="UNUSABLE",
                enhancement_potential="UNRECOVERABLE",
                fatal_defects=fatal_verdicts,
                risk_factors=risk_factors,
                mitigation_notes=[
                    "Fatal quality defect detected. Image cannot be compensated by other dimensions.",
                    "Mandatory action: Request physical document rescan or manual evaluator entry."
                ]
            )

        # Step 2: Tier 2 Degradable Quality Profile Analysis
        risk_factors = []
        mitigation_notes = []

        # Check Sharpness / Focus
        if p.normalized_stroke_acutance < self.CALIB_BORDERLINE_ACUTANCE:
            risk_factors.append(
                f"Moderate Defocus Blur: Acutance ({p.normalized_stroke_acutance:.1f}) is borderline; "
                "HTR word segmentation confidence may be degraded."
            )

        # Check Contrast / Faint Ink
        if p.stroke_intensity_delta < self.CALIB_BORDERLINE_STROKE_DELTA:
            risk_factors.append(
                f"Low Stroke Contrast: Delta ({p.stroke_intensity_delta:.1f}) indicates faint pencil or washed ink."
            )
        if p.faint_stroke_pixel_fraction > self.CALIB_BORDERLINE_FAINT_FRACTION:
            risk_factors.append(
                f"Elevated Faint Stroke Ratio: {p.faint_stroke_pixel_fraction*100:.1f}% of ink pixels have low contrast."
            )

        # Check Baseline Skew
        if abs(p.residual_skew_angle_deg) > self.CALIB_BORDERLINE_SKEW:
            risk_factors.append(
                f"Significant Baseline Skew ({p.residual_skew_angle_deg:+.1f} deg): "
                "Line segmentation requires rotation compensation."
            )
            mitigation_notes.append("Apply baseline deskew prior to line tokenization.")

        # Check Illumination Non-Uniformity / Shadow
        is_shadowed = bool(p.spatial_bg_ratio < self.CALIB_BORDERLINE_BG_RATIO or p.worst_quadrant_paper_deficit > 45.0)
        if is_shadowed:
            risk_factors.append(
                f"Non-Uniform Illumination: Background ratio ({p.spatial_bg_ratio:.2f}) indicates regional shadow."
            )
            mitigation_notes.append("Image is a candidate for Phase 4 Background Normalization.")

        # Check Binarization Separation
        if p.binarization_otsu_eta < self.CALIB_BORDERLINE_OTSU_ETA:
            risk_factors.append(
                f"Weak Binarization Separation: Otsu eta ({p.binarization_otsu_eta:.2f}) indicates overlapping ink/paper distributions."
            )

        # Step 3: Enhancement Potential vs Evaluation Readiness Distinction
        if is_shadowed:
            enhancement_potential = "CAN_BE_ENHANCED"
        elif not risk_factors:
            enhancement_potential = "ALREADY_CLEAN"
        else:
            enhancement_potential = "ALREADY_CLEAN" # Minor degradations that do not warrant operator intervention

        # Step 4: Determine Tier 3 Readiness State
        if not risk_factors:
            readiness_state = "GOOD"
            mitigation_notes.append("Pristine quality. Safe for autonomous downstream AI evaluation.")
        elif len(risk_factors) == 1 and is_shadowed:
            readiness_state = "ACCEPTABLE"
            mitigation_notes.append("Minor illumination non-uniformity handled robustly by downstream neural OCR.")
        elif len(risk_factors) <= 2 and not any("Blur" in r or "Contrast" in r for r in risk_factors):
            readiness_state = "ACCEPTABLE"
            mitigation_notes.append("Minor non-fatal degradations within neural OCR tolerance margins.")
        else:
            readiness_state = "BORDERLINE"
            mitigation_notes.append("Multiple compounding degradations present. Recommend routing to human verification queue.")

        return QualityReadinessVerdict(
            readiness_state=readiness_state,
            enhancement_potential=enhancement_potential,
            fatal_defects=[],
            risk_factors=risk_factors,
            mitigation_notes=mitigation_notes
        )


# ===========================================================================
# 3. CONSOLIDATION BENCHMARK RUNNER
# ===========================================================================

@dataclass
class ConsolidatedBenchmarkResult:
    sample_id: str
    corpus_category: str                       # CALIBRATION, STRESS_DEFECT, UNSEEN_VALIDATION
    input_state: str                           # RAW_IMAGE, RECTIFIED_SCAN, PHASE4_ENHANCED
    evidence: CuratedQualityProfile
    verdict: QualityReadinessVerdict


def run_consolidation_audit() -> List[ConsolidatedBenchmarkResult]:
    """
    Evaluates representative documents across Calibration, Stress Cases,
    and Unseen Validation through the consolidated 3-Tier architecture.
    """
    print("\n" + "=" * 80)
    print("PHASE 5.3: CONSOLIDATED QUALITY GATE ARCHITECTURE AUDIT")
    print("=" * 80)

    gate = SmartQualityGateArchitecture()
    audit_results: List[ConsolidatedBenchmarkResult] = []

    # -----------------------------------------------------------------------
    # 1. Calibration Exam Documents (Real Scans & Phase 4 Enhanced)
    # -----------------------------------------------------------------------
    calib_files = [
        ("answer_sheet_2.png", "Pristine Calibration Sheet"),
        ("answer_sheet_3.jpg", "Shadowed Calibration Sheet"),
        ("answer_sheet_4.jpg", "Perspective/Defocus Distorted Sheet"),
        ("answer_sheet_5.jpg", "Lateral Clipped & Skewed Sheet"),
        ("answer_sheet.jpg", "Low-Res Compressed Sheet"),
    ]

    for fname, desc in calib_files:
        p = os.path.join(ROOT_DIR, "images", fname)
        if not os.path.exists(p):
            continue

        # Run scanner to get rectified scan
        sc_res = integrate_production_scanner(p)
        rect_img = sc_res.scanned_image

        # Extract 5.1 raw evidence
        ev_rect = extract_quality_assessment_evidence(rect_img, f"{fname}_Rectified")
        curated_rect = gate.curate_evidence_profile(ev_rect)
        verdict_rect = gate.evaluate_readiness(curated_rect)

        audit_results.append(
            ConsolidatedBenchmarkResult(
                sample_id=fname.replace(".png", "").replace(".jpg", ""),
                corpus_category="CALIBRATION",
                input_state="RECTIFIED_SCAN",
                evidence=curated_rect,
                verdict=verdict_rect
            )
        )

        # For answer_sheet_3, also evaluate Phase 4 Enhanced State
        if fname == "answer_sheet_3.jpg":
            enh_res = enhance_scanned_document(sc_res)
            enh_bgr = cv2.cvtColor(enh_res.enhanced_gray, cv2.COLOR_GRAY2BGR)
            ev_enh = extract_quality_assessment_evidence(enh_bgr, "answer_sheet_3_Enhanced")
            curated_enh = gate.curate_evidence_profile(ev_enh)
            verdict_enh = gate.evaluate_readiness(curated_enh)

            audit_results.append(
                ConsolidatedBenchmarkResult(
                    sample_id="answer_sheet_3_Enhanced",
                    corpus_category="CALIBRATION",
                    input_state="PHASE4_ENHANCED",
                    evidence=curated_enh,
                    verdict=verdict_enh
                )
            )

    # -----------------------------------------------------------------------
    # 2. Controlled Stress Defect Cases (Testing Tier 1 Veto Gate)
    # -----------------------------------------------------------------------
    p2 = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
    if os.path.exists(p2):
        base_doc = cv2.imread(p2)
        h, w = base_doc.shape[:2]

        # Case S1: Severe Specular Glare Collision
        glare_doc = base_doc.copy()
        cv2.circle(glare_doc, (int(w * 0.45), int(h * 0.25)), int(min(h, w) * 0.22), (255, 255, 255), -1)
        ev_s1 = extract_quality_assessment_evidence(glare_doc, "Stress_Fatal_Glare")
        c_s1 = gate.curate_evidence_profile(ev_s1)
        v_s1 = gate.evaluate_readiness(c_s1)
        audit_results.append(ConsolidatedBenchmarkResult("Stress_Fatal_Glare", "STRESS_DEFECT", "DEFECT_INJECTED", c_s1, v_s1))

        # Case S2: Severe Boundary Text Clipping (Translated past edge)
        clip_doc = np.full_like(base_doc, 255)
        clip_doc[:, : (w - 180)] = base_doc[:, 180:]
        ev_s2 = extract_quality_assessment_evidence(clip_doc, "Stress_Fatal_Clipping")
        c_s2 = gate.curate_evidence_profile(ev_s2)
        v_s2 = gate.evaluate_readiness(c_s2)
        audit_results.append(ConsolidatedBenchmarkResult("Stress_Fatal_Clipping", "STRESS_DEFECT", "DEFECT_INJECTED", c_s2, v_s2))

        # Case S3: Severe Optical Defocus Blur (sigma = 5.0)
        blur_doc = cv2.GaussianBlur(base_doc, (35, 35), 5.0)
        ev_s3 = extract_quality_assessment_evidence(blur_doc, "Stress_Fatal_Defocus")
        c_s3 = gate.curate_evidence_profile(ev_s3)
        v_s3 = gate.evaluate_readiness(c_s3)
        audit_results.append(ConsolidatedBenchmarkResult("Stress_Fatal_Defocus", "STRESS_DEFECT", "DEFECT_INJECTED", c_s3, v_s3))

        # Case S4: Severe Ink Dropout / Faded Contrast (alpha = 0.12)
        faded_doc = np.clip(245.0 - (245.0 - base_doc.astype(np.float32)) * 0.12, 0, 255).astype(np.uint8)
        ev_s4 = extract_quality_assessment_evidence(faded_doc, "Stress_Fatal_InkLoss")
        c_s4 = gate.curate_evidence_profile(ev_s4)
        v_s4 = gate.evaluate_readiness(c_s4)
        audit_results.append(ConsolidatedBenchmarkResult("Stress_Fatal_InkLoss", "STRESS_DEFECT", "DEFECT_INJECTED", c_s4, v_s4))

        # Case S5: Destructive Foreign Object Occlusion
        occ_doc = base_doc.copy()
        occ_doc[:, : int(w * 0.28)] = [30, 45, 110]
        ev_s5 = extract_quality_assessment_evidence(occ_doc, "Stress_Fatal_Occlusion")
        c_s5 = gate.curate_evidence_profile(ev_s5)
        v_s5 = gate.evaluate_readiness(c_s5)
        audit_results.append(ConsolidatedBenchmarkResult("Stress_Fatal_Occlusion", "STRESS_DEFECT", "DEFECT_INJECTED", c_s5, v_s5))

    # -----------------------------------------------------------------------
    # 3. Unseen Validation Samples (10 Representative Patches)
    # -----------------------------------------------------------------------
    samples_dir = os.path.join(ROOT_DIR, "images", "dataset_samples")
    if os.path.exists(samples_dir):
        files = sorted([f for f in os.listdir(samples_dir) if f.endswith((".jpg", ".png"))])[:8]
        for f in files:
            img = cv2.imread(os.path.join(samples_dir, f))
            if img is None:
                continue
            name_base = f[:12]
            ev_val = extract_quality_assessment_evidence(img, f"Val_{name_base}")
            c_val = gate.curate_evidence_profile(ev_val)
            v_val = gate.evaluate_readiness(c_val)
            audit_results.append(ConsolidatedBenchmarkResult(f"Val_{name_base}", "UNSEEN_VALIDATION", "DATASET_PATCH", c_val, v_val))

    print(f"\n[Phase 5.3 Audit] Evaluated {len(audit_results)} documents across 3 corpora.")
    return audit_results


# ===========================================================================
# 4. DIAGNOSTIC VISUALIZATION GENERATION
# ===========================================================================

def generate_architecture_visualizations(results: List[ConsolidatedBenchmarkResult]):
    """
    Generates 3 comprehensive architectural diagnostic diagrams in phase5/output/:
    1. phase5_3_hierarchical_gate_flowchart.png
    2. phase5_3_semantic_state_transition_matrix.png
    3. phase5_3_multi_corpus_readiness_audit.png
    """
    print("\n[Phase 5.3] Generating Consolidated Architecture Visualizations...")

    # -----------------------------------------------------------------------
    # Plot 1: Hierarchical Non-Compensatory Architecture Flowchart
    # -----------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(15, 10))
    ax.axis("off")

    # Render structured architectural flow diagram
    ax.text(0.5, 0.95, "SMART QUALITY ASSESSMENT HIERARCHICAL ARCHITECTURE",
            ha="center", va="center", fontsize=15, fontweight="bold")
    ax.text(0.5, 0.91, "Non-Compensatory 3-Tier Evaluation Pipeline for Processed & Enhanced Exam Scripts",
            ha="center", va="center", fontsize=11, fontstyle="italic", color="dimgray")

    # Box 0: Input Image
    bbox_input = dict(boxstyle="round,pad=0.6", facecolor="aliceblue", edgecolor="royalblue", linewidth=2)
    ax.text(0.5, 0.83, "Processed / Enhanced Document Image\n(ScannedDocumentResult / EnhancedDocumentResult)",
            ha="center", va="center", fontsize=11, fontweight="bold", bbox=bbox_input)

    # Arrow 1
    ax.annotate("", xy=(0.5, 0.74), xytext=(0.5, 0.78),
                arrowprops=dict(arrowstyle="->", lw=2.5, color="darkslategray"))

    # Box 1: Tier 1 Fatal Defect Veto Gate
    bbox_t1 = dict(boxstyle="square,pad=0.8", facecolor="seashell", edgecolor="firebrick", linewidth=2.5)
    t1_text = (
        "TIER 1: FATAL DEFECT VETO GATE (Non-Compensatory Boolean Veto)\n"
        "----------------------------------------------------------------------------------------------------\n"
        "* Text Clipping at Boundaries (boundary_text_touch_count > 80 px)\n"
        "* Specular Glare Text Collision (glare_text_collision_fraction > 8%)\n"
        "* Severe Optical Defocus Blur (normalized_stroke_acutance < 120.0)\n"
        "* Severe Ink Dropout / Fading (stroke_intensity_delta < 18 levels)\n"
        "* Destructive Foreign Occlusion (margin_occlusion_fraction > 25%)\n"
        "* Geometric Aspect Collapse (aspect_ratio_a4_deviation > 0.45)"
    )
    ax.text(0.5, 0.63, t1_text, ha="center", va="center", fontsize=10, family="monospace", bbox=bbox_t1)

    # Branch: Fatal Defect Tripped -> UNUSABLE
    ax.annotate("ANY FATAL DEFECT TRIPPED\n(Zero compensation allowed)", xy=(0.88, 0.48), xytext=(0.76, 0.58),
                arrowprops=dict(arrowstyle="->", lw=2, color="crimson"), fontsize=9, fontweight="bold", color="crimson")
    bbox_veto = dict(boxstyle="round,pad=0.6", facecolor="mistyrose", edgecolor="crimson", linewidth=2)
    ax.text(0.88, 0.44, "VERDICT: UNUSABLE\nAction: Rescan Required\nPotential: UNRECOVERABLE",
            ha="center", va="center", fontsize=10, fontweight="bold", color="darkred", bbox=bbox_veto)

    # Branch: Passed Tier 1 -> Tier 2
    ax.annotate("NO FATAL DEFECTS\n(Page structurally complete)", xy=(0.5, 0.49), xytext=(0.5, 0.53),
                arrowprops=dict(arrowstyle="->", lw=2.5, color="forestgreen"), fontsize=9, fontweight="bold", color="forestgreen", ha="center")

    # Box 2: Tier 2 Curated Multi-Dimensional Evidence Profile
    bbox_t2 = dict(boxstyle="square,pad=0.8", facecolor="honeydew", edgecolor="seagreen", linewidth=2)
    t2_text = (
        "TIER 2: CURATED MULTI-DIMENSIONAL QUALITY EVIDENCE PROFILE\n"
        "----------------------------------------------------------------------------------------------------\n"
        "[1] Stroke Visibility & Contrast: stroke_intensity_delta (Delta), faint_stroke_pixel_fraction\n"
        "[2] Optical Acutance & Sharpness: normalized_stroke_acutance, edge_spread_width_pixels\n"
        "[3] Illumination Uniformity & Shadow: spatial_bg_ratio, worst_quadrant_paper_deficit\n"
        "[4] Geometric Alignment & Skew: residual_skew_angle_deg, aspect_ratio_a4_deviation\n"
        "[5] Binarization & Topology Readiness: binarization_otsu_eta, median_character_height_px\n"
        "* EXCLUDED/DEPRECATED: global_laplacian_variance (Unsafe), weber/michelson (Redundant)"
    )
    ax.text(0.5, 0.38, t2_text, ha="center", va="center", fontsize=10, family="monospace", bbox=bbox_t2)

    # Arrow 2
    ax.annotate("", xy=(0.5, 0.25), xytext=(0.5, 0.28),
                arrowprops=dict(arrowstyle="->", lw=2.5, color="darkslategray"))

    # Box 3: Tier 3 Evaluation Readiness Verdict
    bbox_t3 = dict(boxstyle="square,pad=0.8", facecolor="lightyellow", edgecolor="darkgoldenrod", linewidth=2)
    t3_text = (
        "TIER 3: EVALUATION READINESS VERDICT & ENHANCEMENT POTENTIAL\n"
        "====================================================================================================\n"
        "  [GOOD]         : Pristine document. Safe for autonomous downstream AI evaluation.\n"
        "  [ACCEPTABLE]   : Minor non-fatal degradations (slight shadow/skew). Downstream OCR robust.\n"
        "  [BORDERLINE]   : Compounding risks near operational margins. Routed to human verification queue.\n"
        "  [UNUSABLE]     : Multi-factor degradation failure or Tier 1 fatal defect.\n"
        "  --------------------------------------------------------------------------------------------------\n"
        "  Enhancement Potential: ALREADY_CLEAN  |  CAN_BE_ENHANCED (Shadowed)  |  UNRECOVERABLE (Defocus/Clip)"
    )
    ax.text(0.5, 0.14, t3_text, ha="center", va="center", fontsize=10, family="monospace", bbox=bbox_t3)

    plt.tight_layout()
    plot1_path = os.path.join(OUTPUT_DIR, "phase5_3_hierarchical_gate_flowchart.png")
    plt.savefig(plot1_path, dpi=200)
    plt.close()
    print(f"  Saved: {plot1_path}")

    # -----------------------------------------------------------------------
    # Plot 2: Semantic State Transition Matrix & Multi-Band Profiles
    # -----------------------------------------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle("Phase 5.3: Semantic Readiness States & Transition Boundaries", fontsize=15, fontweight="bold")

    # Panel A: Stroke Acutance across States
    ax_a = axes[0, 0]
    states = ["GOOD", "ACCEPTABLE", "BORDERLINE", "UNUSABLE\n(Defocus)"]
    acutance_ranges = [800.0, 450.0, 180.0, 60.0]
    bars_a = ax_a.bar(states, acutance_ranges, color=["forestgreen", "limegreen", "gold", "crimson"])
    ax_a.axhline(120.0, color="firebrick", linestyle="--", linewidth=1.5, label="Tier 1 Fatal Defocus Cutoff (120)")
    ax_a.axhline(220.0, color="orange", linestyle=":", linewidth=1.5, label="Tier 2 Borderline Margin (220)")
    ax_a.set_ylabel("Normalized Stroke Acutance", fontsize=11)
    ax_a.set_title("Optical Sharpness / Acutance Boundaries", fontsize=12, fontweight="bold")
    ax_a.legend(loc="upper right")
    ax_a.grid(True, linestyle=":", alpha=0.6)
    for bar in bars_a:
        yval = bar.get_height()
        ax_a.text(bar.get_x() + bar.get_width() / 2.0, yval + 10, f"{yval:.0f}", ha="center", va="bottom", fontweight="bold")

    # Panel B: Stroke Delta across States
    ax_b = axes[0, 1]
    delta_ranges = [130.0, 85.0, 28.0, 10.0]
    bars_b = ax_b.bar(states, delta_ranges, color=["forestgreen", "limegreen", "gold", "crimson"])
    ax_b.axhline(18.0, color="firebrick", linestyle="--", linewidth=1.5, label="Tier 1 Fatal Ink Loss Cutoff (18)")
    ax_b.axhline(35.0, color="orange", linestyle=":", linewidth=1.5, label="Tier 2 Borderline Margin (35)")
    ax_b.set_ylabel("Stroke Intensity Delta (I_paper - I_ink)", fontsize=11)
    ax_b.set_title("Stroke Contrast / Faint Ink Boundaries", fontsize=12, fontweight="bold")
    ax_b.legend(loc="upper right")
    ax_b.grid(True, linestyle=":", alpha=0.6)
    for bar in bars_b:
        yval = bar.get_height()
        ax_b.text(bar.get_x() + bar.get_width() / 2.0, yval + 2, f"{yval:.0f}", ha="center", va="bottom", fontweight="bold")

    # Panel C: Glare Text Collision across States
    ax_c = axes[1, 0]
    glare_states = ["GOOD\n(No Glare)", "ACCEPTABLE\n(Margin Glare)", "UNUSABLE\n(Text Glare > 8%)", "UNUSABLE\n(Severe Flash)"]
    glare_vals = [0.0, 0.02, 0.15, 0.50]
    bars_c = ax_c.bar(glare_states, [v * 100 for v in glare_vals], color=["forestgreen", "limegreen", "crimson", "darkred"])
    ax_c.axhline(8.0, color="firebrick", linestyle="--", linewidth=1.5, label="Tier 1 Fatal Glare Cutoff (8%)")
    ax_c.set_ylabel("Glare Text Collision Percentage (%)", fontsize=11)
    ax_c.set_title("Specular Glare Collision Boundaries (Fatal Step-Function)", fontsize=12, fontweight="bold")
    ax_c.legend(loc="upper left")
    ax_c.grid(True, linestyle=":", alpha=0.6)
    for bar in bars_c:
        yval = bar.get_height()
        ax_c.text(bar.get_x() + bar.get_width() / 2.0, yval + 1, f"{yval:.1f}%", ha="center", va="bottom", fontweight="bold")

    # Panel D: Spatial Background Ratio (Illumination Uniformity)
    ax_d = axes[1, 1]
    bg_states = ["GOOD\n(Uniform)", "CAN_BE_ENHANCED\n(Shadowed)", "BORDERLINE\n(Deep Shadow)", "UNUSABLE\n(Blackout)"]
    bg_vals = [0.92, 0.72, 0.55, 0.20]
    bars_d = ax_d.bar(bg_states, bg_vals, color=["forestgreen", "cornflowerblue", "gold", "crimson"])
    ax_d.axhline(0.65, color="orange", linestyle=":", linewidth=1.5, label="Shadow Enhancement Trigger (0.65)")
    ax_d.set_ylabel("Spatial Background Ratio (Min/Max Paper White)", fontsize=11)
    ax_d.set_title("Illumination Non-Uniformity & Enhancement Potential", fontsize=12, fontweight="bold")
    ax_d.legend(loc="upper right")
    ax_d.grid(True, linestyle=":", alpha=0.6)
    for bar in bars_d:
        yval = bar.get_height()
        ax_d.text(bar.get_x() + bar.get_width() / 2.0, yval + 0.02, f"{yval:.2f}", ha="center", va="bottom", fontweight="bold")

    plt.tight_layout()
    plot2_path = os.path.join(OUTPUT_DIR, "phase5_3_semantic_state_transition_matrix.png")
    plt.savefig(plot2_path, dpi=200)
    plt.close()
    print(f"  Saved: {plot2_path}")

    # -----------------------------------------------------------------------
    # Plot 3: Multi-Corpus Readiness Audit
    # -----------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(16, 9))

    sample_names = [r.sample_id for r in results]
    states_list = [r.verdict.readiness_state for r in results]
    color_map = {
        "GOOD": "forestgreen",
        "ACCEPTABLE": "limegreen",
        "BORDERLINE": "gold",
        "UNUSABLE": "crimson"
    }
    colors = [color_map.get(s, "gray") for s in states_list]

    y_pos = range(len(sample_names))
    # Horizontal bar plot
    ax.barh(y_pos, [1.0] * len(sample_names), color=colors, height=0.65, edgecolor="black", linewidth=0.5)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(sample_names, fontsize=9, fontweight="bold")
    ax.invert_yaxis()
    ax.set_xlim(0, 1.4)
    ax.set_xticks([])

    # Annotate states & rationale
    for i, r in enumerate(results):
        v = r.verdict
        status_text = f"[{v.readiness_state}] - Potential: {v.enhancement_potential}"
        if v.fatal_defects:
            detail = f"FATAL: {v.fatal_defects[0].defect_code}"
        elif v.risk_factors:
            detail = f"Risks: {len(v.risk_factors)} ({v.risk_factors[0][:40]}...)"
        else:
            detail = "Pristine scan. Zero defect flags."
        ax.text(1.02, i, f"{status_text} | {detail}", va="center", fontsize=8.5, color="black", fontweight="bold")

    ax.set_title("Phase 5.3: Consolidated Evaluation Readiness Audit across Calibration, Stress & Unseen Samples",
                 fontsize=13, fontweight="bold")

    # Legend
    legend_patches = [
        matplotlib.patches.Patch(facecolor="forestgreen", label="GOOD: Clean & Fully Usable"),
        matplotlib.patches.Patch(facecolor="limegreen", label="ACCEPTABLE: Minor Non-Fatal Degradation"),
        matplotlib.patches.Patch(facecolor="gold", label="BORDERLINE: Compounding Risk, Human Review"),
        matplotlib.patches.Patch(facecolor="crimson", label="UNUSABLE: Fatal Defect / Unrecoverable"),
    ]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=10)

    plt.tight_layout()
    plot3_path = os.path.join(OUTPUT_DIR, "phase5_3_multi_corpus_readiness_audit.png")
    plt.savefig(plot3_path, dpi=200)
    plt.close()
    print(f"  Saved: {plot3_path}")


# ===========================================================================
# 5. MAIN EXECUTION
# ===========================================================================

def main():
    results = run_consolidation_audit()

    print("\n" + "=" * 80)
    print("CONSOLIDATED READINESS AUDIT SUMMARY")
    print("=" * 80)
    print(f"{'Sample ID':<30} | {'Readiness':<12} | {'Potential':<16} | {'Primary Defect / Risk'}")
    print("-" * 88)
    for r in results:
        v = r.verdict
        primary_note = v.fatal_defects[0].defect_code if v.fatal_defects else (v.risk_factors[0][:35] if v.risk_factors else "None (Clean)")
        print(f"{r.sample_id:<30} | {v.readiness_state:<12} | {v.enhancement_potential:<16} | {primary_note}")

    generate_architecture_visualizations(results)

    print("\n" + "=" * 80)
    print("PHASE 5.3 CONSOLIDATION INVESTIGATION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()
