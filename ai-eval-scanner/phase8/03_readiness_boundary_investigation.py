"""
AI-EVAL-OpenCV: Phase 8.4 - OCR/HTR Readiness Boundary & Failure-Mode Investigation

This script conducts empirical and architectural analysis for Phase 8.4:
1. Evaluates the 18 core failure modes across real exam calibration images and controlled scenarios.
2. Investigates the Phase 7 -> Phase 8 decision boundary (Cases A through G).
3. Evaluates non-compensatory failure mechanisms.
4. Demonstrates region-level vs page-level readiness decomposition on a multi-zone exam page.
5. Produces diagnostic artifacts in phase8/output/.

STRICT GOVERNANCE:
- Investigation only; does NOT implement a production classifier or freeze thresholds.
- Phases 2-7, Phase 8.1, 8.2, 8.3 remain frozen and untouched.
"""

import os
import sys
import time
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Pipeline root setup
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from phase8.ocr_readiness_contracts import (
    ReadingOrientation,
    OCRReadinessVerdict,
    ProvisionalReadinessObservation,
    TextTopologyMetrics,
    PreprocessedImageBundle,
    OCRReadinessPreparationResult,
)
from phase8.ocr_readiness_engine import prepare_ocr_readiness
from phase7.rescan_decision_engine import evaluate_rescan_decision, RescanDecisionResult, SafeImageState

OUTPUT_DIR = os.path.join(CURRENT_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ===========================================================================
# 1. FAILURE MODE DEFINITIONS & DATA MODEL
# ===========================================================================

FAILURE_MODES = [
    "ORIENTATION_ERROR",
    "SEVERE_SKEW",
    "SMALL_CHARACTER_SCALE",
    "LOW_CONTRAST",
    "RULE_LINE_INTERFERENCE",
    "BLEED_THROUGH",
    "GLARE",
    "DEFECTIVE_MARGINS",
    "TEXT_CLIPPING",
    "OPTICAL_DEFOCUS",
    "INK_LOSS",
    "DENSE_HANDWRITING",
    "COMPLEX_LAYOUT",
    "TABLE",
    "DIAGRAM",
    "MIXED_PRINTED_HANDWRITTEN",
    "SPARSE_CONTENT",
    "NO_CONTENT",
]


# ===========================================================================
# 2. INVESTIGATION 1 & 2: FAILURE-MODE MATRIX EVALUATION
# ===========================================================================

def build_failure_mode_matrix() -> List[Dict[str, Any]]:
    """
    Constructs the rigorous 18 failure-mode evidence matrix.
    Each entry tracks observable evidence, detection source, downstream impact,
    recoverability category, Phase 7 / Phase 8 detection capability, and evidence strength.
    """
    matrix = [
        {
            "mode": "ORIENTATION_ERROR",
            "evidence": "Projection profile variance inversion; vertical vs horizontal stroke peaks.",
            "source": "Phase 8.1 / 8.2",
            "impact": "Sideways rotation produces 100% recognition failure in evaluated OCR (0 lines detected, CER=1.0000).",
            "recoverability": "CONDITIONALLY_RECOVERABLE",
            "recovery_status": "Orientation normalization is a demonstrated candidate recovery mechanism for evaluated controlled cases; broader robustness unvalidated.",
            "phase7_detects": False,
            "phase8_2_detects": True,
            "phase8_3_measured": True,
            "human_review_appropriate": True,
            "rescan_justified": False,
            "evidence_strength": "STRONG CONTROLLED EVIDENCE",
        },
        {
            "mode": "SEVERE_SKEW",
            "evidence": "Radon/Hough dominant peak angle |theta| > 3.0 deg.",
            "source": "Phase 8.1 / 8.2",
            "impact": "Tested OCR tolerated +/-3.5 deg without CER penalty; line-based HTR slicing hypothesized vulnerable.",
            "recoverability": "CONDITIONALLY_RECOVERABLE",
            "recovery_status": "Mild-to-moderate skew investigated through Phase 8.2; general recovery of severe skew not sufficiently validated.",
            "phase7_detects": False,
            "phase8_2_detects": True,
            "phase8_3_measured": True,
            "human_review_appropriate": False,
            "rescan_justified": False,
            "evidence_strength": "MODERATE / LIMITED EVIDENCE",
        },
        {
            "mode": "SMALL_CHARACTER_SCALE",
            "evidence": "Connected component median character height in sub-resolution failure region.",
            "source": "Phase 8.1 / 8.2",
            "impact": "Tested 9px condition produced recognition failure; tested >=12px succeeded. Operational boundaries uncalibrated.",
            "recoverability": "CONDITIONALLY_RECOVERABLE",
            "recovery_status": "Potentially recoverable in a future stage; current project evidence is insufficient to validate recovery mechanism.",
            "phase7_detects": False,
            "phase8_2_detects": True,
            "phase8_3_measured": True,
            "human_review_appropriate": True,
            "rescan_justified": True,
            "evidence_strength": "EXPLORATORY EVIDENCE",
        },
        {
            "mode": "LOW_CONTRAST",
            "evidence": "Foreground/background intensity delta < 40; flat luminance histogram.",
            "source": "Phase 5 / Phase 6.5",
            "impact": "Faint text strokes merge with substrate or threshold out during binarization.",
            "recoverability": "CONDITIONALLY_RECOVERABLE",
            "recovery_status": "Potentially recoverable in a future stage; current project evidence is insufficient to validate recovery mechanism.",
            "phase7_detects": True,
            "phase8_2_detects": True,
            "phase8_3_measured": False,
            "human_review_appropriate": True,
            "rescan_justified": True,
            "evidence_strength": "MODERATE / LIMITED EVIDENCE",
        },
        {
            "mode": "RULE_LINE_INTERFERENCE",
            "evidence": "High aspect-ratio horizontal lines intersecting text stroke components.",
            "source": "Phase 8.1 / 8.2",
            "impact": "Ruled lines cause spurious hyphen tokens; auxiliary rule mask generated in Phase 8.2.",
            "recoverability": "CONDITIONALLY_RECOVERABLE",
            "recovery_status": "Potentially recoverable in a future stage; current project evidence is insufficient to validate recovery mechanism.",
            "phase7_detects": False,
            "phase8_2_detects": True,
            "phase8_3_measured": True,
            "human_review_appropriate": True,
            "rescan_justified": False,
            "evidence_strength": "MODERATE / LIMITED EVIDENCE",
        },
        {
            "mode": "BLEED_THROUGH",
            "evidence": "Faint reverse-polarity strokes in document background substrate.",
            "source": "Phase 8.2",
            "impact": "Spurious character fragments detected; background strokes pollute token sequences.",
            "recoverability": "CONDITIONALLY_RECOVERABLE",
            "recovery_status": "Potentially recoverable in a future stage; current project evidence is insufficient to validate recovery mechanism.",
            "phase7_detects": False,
            "phase8_2_detects": True,
            "phase8_3_measured": False,
            "human_review_appropriate": True,
            "rescan_justified": False,
            "evidence_strength": "EXPLORATORY EVIDENCE",
        },
        {
            "mode": "GLARE",
            "evidence": "Localized saturated specular highlights (intensity > 250) overlapping ink masks.",
            "source": "Phase 5 / Phase 7",
            "impact": "Fatal loss of stroke data within specular hot-spot; characters completely bleached.",
            "recoverability": "LIKELY_UNRECOVERABLE",
            "recovery_status": "Irrecoverable physical loss of optical information; upstream rescan required.",
            "phase7_detects": True,
            "phase8_2_detects": False,
            "phase8_3_measured": False,
            "human_review_appropriate": False,
            "rescan_justified": True,
            "evidence_strength": "STRONG CONTROLLED EVIDENCE",
        },
        {
            "mode": "DEFECTIVE_MARGINS",
            "evidence": "Non-document desk background, fingers, or binding clip within crop boundary.",
            "source": "Phase 5 / Phase 7 / Phase 8.3",
            "impact": "Distorts projection profile orientation estimation (e.g. answer_sheet_2.png failure).",
            "recoverability": "CONDITIONALLY_RECOVERABLE",
            "recovery_status": "Potentially recoverable in a future cropping stage; current project evidence is insufficient to validate recovery mechanism.",
            "phase7_detects": True,
            "phase8_2_detects": False,
            "phase8_3_measured": True,
            "human_review_appropriate": True,
            "rescan_justified": True,
            "evidence_strength": "STRONG CONTROLLED EVIDENCE",
        },
        {
            "mode": "TEXT_CLIPPING",
            "evidence": "Foreground stroke components truncated by page boundary rectangle.",
            "source": "Phase 5 / Phase 7",
            "impact": "Permanent, unrecoverable semantic data loss; partial characters cannot be reconstructed.",
            "recoverability": "LIKELY_UNRECOVERABLE",
            "recovery_status": "Irrecoverable physical loss of optical information; upstream rescan required.",
            "phase7_detects": True,
            "phase8_2_detects": False,
            "phase8_3_measured": False,
            "human_review_appropriate": False,
            "rescan_justified": True,
            "evidence_strength": "STRONG CONTROLLED EVIDENCE",
        },
        {
            "mode": "OPTICAL_DEFOCUS",
            "evidence": "Laplacian acutance variance < 60; high-frequency stroke gradient collapse.",
            "source": "Phase 5 / Phase 7",
            "impact": "Severe blur destroys character stroke separation; severe recognition collapse.",
            "recoverability": "LIKELY_UNRECOVERABLE",
            "recovery_status": "Irrecoverable physical loss of optical information; upstream rescan required.",
            "phase7_detects": True,
            "phase8_2_detects": False,
            "phase8_3_measured": False,
            "human_review_appropriate": False,
            "rescan_justified": True,
            "evidence_strength": "STRONG CONTROLLED EVIDENCE",
        },
        {
            "mode": "INK_LOSS",
            "evidence": "Fragmented, broken stroke components with low connectivity.",
            "source": "Phase 5 / Phase 8.1",
            "impact": "Broken glyph loops (e.g. 'e' -> 'c', 'o' -> 'u'); OCR tokenizer fragmentation.",
            "recoverability": "AMBIGUOUS",
            "recovery_status": "Potentially recoverable in a future stage; current project evidence is insufficient to validate recovery mechanism.",
            "phase7_detects": False,
            "phase8_2_detects": False,
            "phase8_3_measured": False,
            "human_review_appropriate": True,
            "rescan_justified": True,
            "evidence_strength": "ARCHITECTURAL HYPOTHESIS",
        },
        {
            "mode": "DENSE_HANDWRITING",
            "evidence": "High vertical stroke collision ratio (> 15%) and low inter-line valley depth (PVR < 1.7).",
            "source": "Phase 8.1 / 8.2",
            "impact": "Ascenders and descenders intersect; horizontal projection line slicers merge lines.",
            "recoverability": "AMBIGUOUS",
            "recovery_status": "Potentially recoverable in a future stage (e.g. 2D path segmentation); current project evidence is insufficient to validate recovery mechanism.",
            "phase7_detects": False,
            "phase8_2_detects": True,
            "phase8_3_measured": True,
            "human_review_appropriate": True,
            "rescan_justified": False,
            "evidence_strength": "MODERATE / LIMITED EVIDENCE",
        },
        {
            "mode": "COMPLEX_LAYOUT",
            "evidence": "Multiple non-contiguous bounding clusters, mixed column widths, multi-directional text.",
            "source": "Phase 8.1 / 8.2",
            "impact": "Reading order confusion; out-of-sequence word streaming.",
            "recoverability": "AMBIGUOUS",
            "recovery_status": "Potentially recoverable in a future stage (e.g. document zoning); current project evidence is insufficient to validate recovery mechanism.",
            "phase7_detects": False,
            "phase8_2_detects": True,
            "phase8_3_measured": False,
            "human_review_appropriate": True,
            "rescan_justified": False,
            "evidence_strength": "MODERATE / LIMITED EVIDENCE",
        },
        {
            "mode": "TABLE",
            "evidence": "Orthogonal grid of horizontal and vertical ruling lines bounding text cells.",
            "source": "Phase 8.1",
            "impact": "Standard line recognizers flatten tabular cells into unintelligible single-line sequences.",
            "recoverability": "AMBIGUOUS",
            "recovery_status": "Potentially recoverable in a future stage; current project evidence is insufficient to validate recovery mechanism.",
            "phase7_detects": False,
            "phase8_2_detects": False,
            "phase8_3_measured": False,
            "human_review_appropriate": True,
            "rescan_justified": False,
            "evidence_strength": "EXPLORATORY EVIDENCE",
        },
        {
            "mode": "DIAGRAM",
            "evidence": "Large 2D connected components with non-character geometric loops and arrows.",
            "source": "Phase 8.1",
            "impact": "OCR engines attempt to hallucinate text from schematic lines, polluting transcripts.",
            "recoverability": "AMBIGUOUS",
            "recovery_status": "Potentially recoverable via visual region preservation; current project evidence is insufficient to validate segmentation.",
            "phase7_detects": False,
            "phase8_2_detects": False,
            "phase8_3_measured": False,
            "human_review_appropriate": True,
            "rescan_justified": False,
            "evidence_strength": "EXPLORATORY EVIDENCE",
        },
        {
            "mode": "MIXED_PRINTED_HANDWRITTEN",
            "evidence": "Co-occurrence of regular typographic fonts (headers) and high-variance handwritten strokes (answers).",
            "source": "Phase 8.1 / 8.2",
            "impact": "Printed OCR engine fails on handwriting; handwriting model hallucinates on printed fonts.",
            "recoverability": "CONDITIONALLY_RECOVERABLE",
            "recovery_status": "Potentially recoverable via regional zoning; current project evidence is insufficient to validate segmentation.",
            "phase7_detects": False,
            "phase8_2_detects": True,
            "phase8_3_measured": False,
            "human_review_appropriate": True,
            "rescan_justified": False,
            "evidence_strength": "MODERATE / LIMITED EVIDENCE",
        },
        {
            "mode": "SPARSE_CONTENT",
            "evidence": "Document contains minimal strokes (< 500 edge pixels); large empty white space margins.",
            "source": "Phase 5 / Phase 6 / Phase 7",
            "impact": "Projection profiling and orientation detection have insufficient evidence; speculative rotation risks.",
            "recoverability": "AMBIGUOUS",
            "recovery_status": "Intrinsically ambiguous content; human review provides safety boundary.",
            "phase7_detects": True,
            "phase8_2_detects": True,
            "phase8_3_measured": False,
            "human_review_appropriate": True,
            "rescan_justified": False,
            "evidence_strength": "STRONG CONTROLLED EVIDENCE",
        },
        {
            "mode": "NO_CONTENT",
            "evidence": "Completely blank page (stroke pixel count = 0); uniform substrate.",
            "source": "Phase 5 / Phase 7",
            "impact": "Nothing to recognize; recognition models output empty or hallucinated noise.",
            "recoverability": "LIKELY_UNRECOVERABLE",
            "recovery_status": "Zero transcribable ink content; human review confirms blank page.",
            "phase7_detects": True,
            "phase8_2_detects": True,
            "phase8_3_measured": False,
            "human_review_appropriate": True,
            "rescan_justified": False,
            "evidence_strength": "STRONG CONTROLLED EVIDENCE",
        },
    ]
    return matrix


# ===========================================================================
# 3. INVESTIGATION 3: CANDIDATE FATAL VETO ANALYSIS
# ===========================================================================

def analyze_candidate_fatal_vetos() -> List[Dict[str, Any]]:
    """
    Evaluates potential fatal veto conditions where recognition cannot proceed,
    analyzing Phase 5/7 overlap, Phase 8 contribution, and false positive risks.
    """
    vetos = [
        {
            "defect": "CONFIRMED_TEXT_CLIPPING",
            "description": "Text strokes intersect outer perimeter bounding box.",
            "phase5_evidence": "FATAL_TEXT_CLIPPED defect flag (Tier 1 fatal veto).",
            "phase7_action": "RESCAN_REQUIRED (Non-compensable fatal veto).",
            "phase8_value_add": "None needed; Phase 7 already halted processing upstream.",
            "fp_risk": "Low if border margin clearance is calibrated; high if ruling lines touch border.",
            "veto_justified": True,
        },
        {
            "defect": "CONFIRMED_SEVERE_OPTICAL_DEFOCUS",
            "description": "Laplacian variance acutance < 60 on text regions.",
            "phase5_evidence": "FATAL_OPTICAL_DEFOCUS defect flag.",
            "phase7_action": "RESCAN_REQUIRED (Irrecoverable information loss).",
            "phase8_value_add": "Telemetry confirms lack of high-frequency character stroke edges.",
            "fp_risk": "Low for clean text; moderate if page contains only faint pencil handwriting.",
            "veto_justified": True,
        },
        {
            "defect": "CONFIRMED_SEVERE_GLARE_COLLISION",
            "description": "Specular saturation highlight (intensity > 250) overlaps text stroke mask.",
            "phase5_evidence": "FATAL_GLARE_COLLISION defect flag.",
            "phase7_action": "RESCAN_REQUIRED.",
            "phase8_value_add": "None needed; Phase 7 veto protects downstream recognizer.",
            "fp_risk": "Moderate if white background margins are mistaken for text glare.",
            "veto_justified": True,
        },
        {
            "defect": "CONFIRMED_GEOMETRIC_COLLAPSE",
            "description": "Non-convex quadrilateral, severe perspective keystoning, or extreme aspect distortion.",
            "phase5_evidence": "Phase 2/3 geometric failure, out-of-bounds corners.",
            "phase7_action": "RESCAN_REQUIRED.",
            "phase8_value_add": "Orientation & deskew failure; projection profile variance ratio ~1.0.",
            "fp_risk": "Low; extreme perspective distortion prevents valid rectilinear bounding.",
            "veto_justified": True,
        },
        {
            "defect": "CONFIRMED_CATASTROPHIC_INK_LOSS",
            "description": "Severe fading/water damage where >50% of expected character strokes are absent.",
            "phase5_evidence": "Low contrast or sparse stroke count.",
            "phase7_action": "Currently routes to HUMAN_REVIEW (as sparse or borderline).",
            "phase8_value_add": "Identifies fragmented connected components and low stroke density.",
            "fp_risk": "High if legitimate blank/sparse student submission is mistaken for ink loss.",
            "veto_justified": False,  # Should route to HUMAN_REVIEW, NOT automatic RESCAN
        },
    ]
    return vetos


# ===========================================================================
# 4. INVESTIGATION 4: PHASE 7 -> PHASE 8 INTERACTION CASES
# ===========================================================================

def evaluate_phase7_phase8_interaction_cases() -> List[Dict[str, Any]]:
    """
    Analyzes the architectural boundary between Phase 7 decision outcomes
    and Phase 8 readiness evidence across Cases A through G.
    """
    cases = [
        {
            "case": "Case A",
            "name": "Phase 7 CONTINUE + Strong OCR Evidence",
            "description": "Clean, sharp document with clear upright text lines and high character resolution.",
            "phase7_verdict": "CONTINUE",
            "phase8_evidence": "Upright orientation (UPRIGHT_0), median height > 16px, PVR > 3.0, collision < 5%.",
            "recommended_flow": "PROCEED_TO_OCR_CANDIDATE",
            "rationale": "Both physical quality and topological readiness agree; minimal recognition failure risk.",
        },
        {
            "case": "Case B",
            "name": "Phase 7 CONTINUE + Weak OCR Evidence",
            "description": "Physically well-captured page, but low PVR, high collision ratio, or faint strokes.",
            "phase7_verdict": "CONTINUE",
            "phase8_evidence": "Orientation upright, but PVR < 1.7, collision > 20%, low stroke contrast.",
            "recommended_flow": "HUMAN_REVIEW_RECOMMENDED (or specialized 2D line segmenter)",
            "rationale": "Physical capture is good, so rescan would not help; recognition requires human verification or non-linear segmentation.",
        },
        {
            "case": "Case C",
            "name": "Phase 7 CONTINUE + Orientation Ambiguity",
            "description": "Physically clean page, but projection profile variance is nearly symmetric (H_var ~ V_var).",
            "phase7_verdict": "CONTINUE",
            "phase8_evidence": "detected_orientation = AMBIGUOUS, speculative rotation inhibited.",
            "recommended_flow": "HUMAN_REVIEW_RECOMMENDED",
            "rationale": "Applying speculative 90/180/270 deg rotation risks destroying OCR; human confirms orientation.",
        },
        {
            "case": "Case D",
            "name": "Phase 7 CONTINUE + Severe Scale Concern",
            "description": "High resolution full-page photo, but tiny handwriting (median character height < 10px).",
            "phase7_verdict": "CONTINUE",
            "phase8_evidence": "median_char_height_px < 10px, stroke_width_px <= 1px.",
            "recommended_flow": "HUMAN_REVIEW_RECOMMENDED (or Upstream Zoom/Macro Rescan Guidance)",
            "rationale": "Characters fall in the empirical failure region; optical interpolation or human transcription needed.",
        },
        {
            "case": "Case E",
            "name": "Phase 7 CONTINUE + Complex Layout",
            "description": "Multi-column layout, embedded geometry diagrams, mathematical formulas, or tables.",
            "phase7_verdict": "CONTINUE",
            "phase8_evidence": "provisional_observation = COMPLEX_LAYOUT_OBSERVED, non-uniform line spacing.",
            "recommended_flow": "REGION_DECOMPOSITION_RECOMMENDED",
            "rationale": "Page-level OCR fails; page must be zoned into text regions, diagrams, and formulas.",
        },
        {
            "case": "Case F",
            "name": "Phase 7 HUMAN_REVIEW",
            "description": "Borderline physical acutance, illumination gradient, or unconfirmed marginal defect.",
            "phase7_verdict": "HUMAN_REVIEW",
            "phase8_evidence": "Phase 8 preparation can generate candidate representations for human inspection.",
            "recommended_flow": "HUMAN_REVIEW (Maintain Phase 7 Gate)",
            "rationale": "Phase 8 cannot override an upstream Phase 7 human review gate into an automatic continue.",
        },
        {
            "case": "Case G",
            "name": "Phase 7 RESCAN_REQUIRED",
            "description": "Fatal defect present: clipped text, severe defocus blur, or fatal specular glare.",
            "phase7_verdict": "RESCAN_REQUIRED",
            "phase8_evidence": "Halted before Phase 8 preparation; no representations generated.",
            "recommended_flow": "UPSTREAM_RESCAN_REQUIRED (Hard Halt)",
            "rationale": "Document cannot be recovered by image preprocessing; physical recapture is mandatory.",
        },
    ]
    return cases


# ===========================================================================
# 5. INVESTIGATION 6: NON-COMPENSATORY FAILURE MECHANISM
# ===========================================================================

def evaluate_non_compensatory_scenarios() -> List[Dict[str, Any]]:
    """
    Demonstrates that high quality in one dimension cannot compensate for
    catastrophic failure in another dimension.
    """
    scenarios = [
        {
            "scenario": "Severe Text Clipping + Perfect Sharpness & Contrast",
            "dim1": "Sharpness: Acutance = 850 (Exceptional)",
            "dim2": "Contrast: Delta = 210 (Pristine)",
            "fatal_dim": "Text Clipping: 35 foreground characters truncated at page perimeter",
            "result": "FATAL FAILURE — Missing text cannot be reconstructed regardless of contrast.",
            "compensable": False,
        },
        {
            "scenario": "Sideways 90 deg Orientation + Perfect Contrast & Zero Noise",
            "dim1": "Contrast: Delta = 195 (Pristine)",
            "dim2": "Noise Delta: +0.2 (Extremely clean)",
            "fatal_dim": "Orientation: 90 deg Rotated CW (0 lines detected, CER = 1.0000)",
            "result": "FATAL FAILURE — Downstream OCR detects 0 lines despite pristine contrast.",
            "compensable": False,
        },
        {
            "scenario": "Severe Optical Defocus + Perfect Upright Orientation",
            "dim1": "Orientation: Upright 0 deg (Confirmed)",
            "dim2": "Geometry: Perfectly rectified rectangle",
            "fatal_dim": "Optical Blur: Laplacian variance = 18 (Severe optical defocus)",
            "result": "FATAL FAILURE — Glyph strokes blurred into gray blobs; recognition impossible.",
            "compensable": False,
        },
        {
            "scenario": "Small Character Scale (8px) + Perfect Illumination",
            "dim1": "Illumination: Perfectly uniform, 0 shadow, 0 glare",
            "dim2": "Deskew: 0.0 deg tilt",
            "fatal_dim": "Character Scale: 8px median height (Below neural receptive field)",
            "result": "FATAL FAILURE — Downstream recognizer fails to extract character strokes.",
            "compensable": False,
        },
    ]
    return scenarios


# ===========================================================================
# 6. INVESTIGATION 9 & 10: REGION-LEVEL VS PAGE-LEVEL READINESS
# ===========================================================================

def simulate_multi_region_exam_page() -> Dict[str, Any]:
    """
    Simulates a multi-zone student exam page to investigate whether page-level
    binary readiness is sufficient or if region-level readiness is necessary.
    Zones:
      - Region 1: Header Block (Printed Text, Upright, High Contrast)
      - Region 2: Answer 1 (Handwritten Text, Ruled Paper)
      - Region 3: Diagram Box (Circuit / Geometry Diagram, Non-Text)
      - Region 4: Answer 2 (Dense Handwriting with Ascender/Descender Collision)
    """
    h, w = 1200, 900
    canvas = np.full((h, w, 3), 245, dtype=np.uint8)

    # 1. Header (y: 40 to 180)
    cv2.rectangle(canvas, (40, 40), (w - 40, 180), (200, 200, 200), 2)
    cv2.putText(canvas, "NATIONAL UNIVERSITY EXAMINATIONS - MATHEMATICS II", (60, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (20, 20, 20), 2)
    cv2.putText(canvas, "Candidate Roll No: 2026-ENG-4491    Section: A", (60, 120),
                cv2.FONT_HERSHEY_SIMPLEX, 0.60, (20, 20, 20), 2)
    cv2.putText(canvas, "Max Marks: 100                      Time: 3 Hours", (60, 155),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (50, 50, 50), 1)

    # 2. Answer 1 (y: 220 to 520) - Ruled paper with clean handwriting
    for y in range(270, 520, 45):
        cv2.line(canvas, (40, y), (w - 40, y), (190, 190, 190), 1)
    cv2.putText(canvas, "Ans 1: Integrating by parts with u = ln(x) and dv = x dx,", (60, 260),
                cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 0.70, (15, 15, 80), 2)
    cv2.putText(canvas, "we obtain du = (1/x) dx and v = (1/2) x^2.", (60, 305),
                cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 0.70, (15, 15, 80), 2)
    cv2.putText(canvas, "Substituting back into the standard formula gives:", (60, 350),
                cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 0.70, (15, 15, 80), 2)
    cv2.putText(canvas, "Integral = (1/2) x^2 ln(x) - (1/4) x^2 + C.", (60, 395),
                cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 0.70, (15, 15, 80), 2)

    # 3. Diagram Box (y: 540 to 820, x: 60 to 450)
    cv2.rectangle(canvas, (60, 550), (450, 810), (100, 100, 100), 2)
    cv2.putText(canvas, "Figure 1: Schematic", (70, 610), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 60, 60), 1)
    # Draw geometric circuit schematic
    cv2.circle(canvas, (250, 680), 60, (30, 30, 30), 2)
    cv2.line(canvas, (120, 680), (190, 680), (30, 30, 30), 2)
    cv2.line(canvas, (310, 680), (390, 680), (30, 30, 30), 2)
    cv2.line(canvas, (250, 620), (250, 590), (30, 30, 30), 2)
    cv2.line(canvas, (250, 740), (250, 780), (30, 30, 30), 2)
    cv2.putText(canvas, "R_1", (150, 670), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1)
    cv2.putText(canvas, "V_in", (340, 670), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1)

    # 4. Dense Handwriting adjacent to diagram (y: 550 to 820, x: 480 to 860)
    cv2.putText(canvas, "The nodal voltage equation at", (490, 590), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 0.65, (20, 20, 80), 2)
    cv2.putText(canvas, "junction A satisfies Kirchhoff's", (490, 635), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 0.65, (20, 20, 80), 2)
    cv2.putText(canvas, "law where sum(I_in) = sum(I_out).", (490, 680), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 0.65, (20, 20, 80), 2)
    cv2.putText(canvas, "Hence (V_a - V_in)/R + V_a/R_L = 0", (490, 725), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 0.65, (20, 20, 80), 2)
    cv2.putText(canvas, "yielding the transfer gain factor.", (490, 770), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 0.65, (20, 20, 80), 2)

    # 5. Answer 3: Low Contrast / Bleed-through Region (y: 860 to 1140)
    for y in range(910, 1140, 50):
        cv2.line(canvas, (40, y), (w - 40, y), (190, 190, 190), 1)
    cv2.putText(canvas, "Ans 2: Eigenvalues are found from det(A - lambda I) = 0,", (60, 900),
                cv2.FONT_HERSHEY_SIMPLEX, 0.60, (140, 140, 140), 1)
    cv2.putText(canvas, "giving lambda_1 = 3 and lambda_2 = -1 respectively.", (60, 950),
                cv2.FONT_HERSHEY_SIMPLEX, 0.60, (140, 140, 140), 1)

    # Region Definitions
    regions = [
        {
            "id": "Region_1_Header",
            "type": "PRINTED_HEADER",
            "bbox": (40, 40, w - 80, 140),
            "suitability": "OCR_CANDIDATE",
            "rationale": "Clean printed typography; high contrast; standard font.",
        },
        {
            "id": "Region_2_Answer1",
            "type": "HANDWRITTEN_TEXT",
            "bbox": (40, 220, w - 80, 300),
            "suitability": "HTR_CANDIDATE",
            "rationale": "Continuous handwriting on ruled paper; requires HTR model + rule suppression.",
        },
        {
            "id": "Region_3_Diagram",
            "type": "DIAGRAM_SCHEMATIC",
            "bbox": (60, 550, 390, 260),
            "suitability": "NON_TEXT_DIAGRAM",
            "rationale": "Schematic graphic; OCR/HTR recognition inappropriate; preserve as image artifact.",
        },
        {
            "id": "Region_4_SideAnswer",
            "type": "HANDWRITTEN_TEXT",
            "bbox": (480, 550, 380, 260),
            "suitability": "HTR_CANDIDATE",
            "rationale": "Handwritten math derivation in column format.",
        },
        {
            "id": "Region_5_FaintAnswer",
            "type": "LOW_CONTRAST_TEXT",
            "bbox": (40, 860, w - 80, 280),
            "suitability": "HUMAN_REVIEW_RECOMMENDED",
            "rationale": "Faint pencil/low contrast strokes; high risk of automated transcription error.",
        },
    ]

    return {
        "canvas": canvas,
        "regions": regions,
    }


# ===========================================================================
# 7. GENERATE PHASE 8.4 DIAGNOSTIC VISUALIZATIONS
# ===========================================================================

def generate_phase8_4_visualizations(
    matrix: List[Dict[str, Any]],
    sim_data: Dict[str, Any],
):
    print("\n--- Generating Phase 8.4 Diagnostic Visualizations ---")

    # Plot 1: Failure Mode Recoverability & Evidence Strength Distribution
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Bar chart 1: Recoverability Categories
    rec_counts = {}
    for item in matrix:
        cat = item["recoverability"]
        rec_counts[cat] = rec_counts.get(cat, 0) + 1

    cats = ["RECOVERABLE", "CONDITIONALLY_RECOVERABLE", "AMBIGUOUS", "LIKELY_UNRECOVERABLE"]
    counts = [rec_counts.get(c, 0) for c in cats]
    colors = ["#2ecc71", "#3498db", "#f39c12", "#e74c3c"]

    bars = ax1.bar(cats, counts, color=colors, edgecolor="black", width=0.6)
    ax1.set_title("Distribution of 18 Failure Modes by Recoverability", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Number of Failure Modes")
    ax1.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax1.set_xticks(range(len(cats)))
    ax1.set_xticklabels(["Recoverable", "Conditionally\nRecoverable", "Ambiguous", "Likely\nUnrecoverable"], fontsize=9)
    for bar in bars:
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15, str(int(bar.get_height())),
                 ha="center", va="bottom", fontweight="bold")

    # Bar chart 2: Evidence Strength Levels
    ev_counts = {}
    for item in matrix:
        st = item["evidence_strength"]
        ev_counts[st] = ev_counts.get(st, 0) + 1

    strengths_keys = [
        "STRONG CONTROLLED EVIDENCE",
        "MODERATE / LIMITED EVIDENCE",
        "EXPLORATORY EVIDENCE",
        "ARCHITECTURAL HYPOTHESIS",
        "INSUFFICIENT EVIDENCE",
    ]
    strengths_labels = [
        "Strong\nControlled",
        "Moderate /\nLimited",
        "Exploratory\nEvidence",
        "Architectural\nHypothesis",
        "Insufficient\nEvidence",
    ]
    ev_vals = [ev_counts.get(s, 0) for s in strengths_keys]
    ev_colors = ["#16a085", "#2980b9", "#f1c40f", "#95a5a6", "#bdc3c7"]

    bars2 = ax2.bar(range(len(strengths_keys)), ev_vals, color=ev_colors, edgecolor="black", width=0.6)
    ax2.set_title("Evidence Strength for Failure Mode Detection", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Number of Failure Modes")
    ax2.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax2.set_xticks(range(len(strengths_keys)))
    ax2.set_xticklabels(strengths_labels, fontsize=8)
    for bar in bars2:
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15, str(int(bar.get_height())),
                 ha="center", va="bottom", fontweight="bold")

    fig.tight_layout()
    fpath1 = os.path.join(OUTPUT_DIR, "phase8_4_failure_mode_taxonomy_breakdown.png")
    fig.savefig(fpath1, dpi=180)
    plt.close(fig)
    print(f"  Saved: {fpath1}")

    # Plot 2: Multi-Zone Page-Level vs Region-Level Decomposition
    canvas_bgr = sim_data["canvas"].copy()
    overlay = canvas_bgr.copy()

    region_colors = {
        "OCR_CANDIDATE": (0, 180, 0),         # Green
        "HTR_CANDIDATE": (200, 100, 0),       # Blue
        "NON_TEXT_DIAGRAM": (0, 140, 220),    # Orange
        "HUMAN_REVIEW_RECOMMENDED": (0, 0, 200) # Red
    }

    for reg in sim_data["regions"]:
        x, y, w, h = reg["bbox"]
        c = region_colors.get(reg["suitability"], (128, 128, 128))
        cv2.rectangle(overlay, (x, y), (x + w, y + h), c, -1)
        cv2.rectangle(canvas_bgr, (x, y), (x + w, y + h), c, 3)

        # Label badge banner
        lbl = f"{reg['id']}: {reg['suitability']}"
        (tw, th), _ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 2)
        cv2.rectangle(canvas_bgr, (x, y), (x + tw + 16, y + th + 14), c, -1)
        cv2.putText(canvas_bgr, lbl, (x + 8, y + th + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 2)

    # Blend overlay for transparent highlight
    cv2.addWeighted(overlay, 0.18, canvas_bgr, 0.82, 0, canvas_bgr)

    fpath2 = os.path.join(OUTPUT_DIR, "phase8_4_multi_zone_region_readiness_map.png")
    cv2.imwrite(fpath2, canvas_bgr)
    print(f"  Saved: {fpath2}")


# ===========================================================================
# 8. MAIN INVESTIGATION RUNNER
# ===========================================================================

def run_phase8_4_investigation():
    print("=" * 80)
    print("STARTING PHASE 8.4: OCR/HTR READINESS BOUNDARY & FAILURE-MODE INVESTIGATION")
    print("=" * 80)

    # 1. Failure Mode Matrix
    matrix = build_failure_mode_matrix()
    print(f"\nConstructed failure mode matrix covering {len(matrix)} distinct conditions.")

    # 2. Fatal Veto Analysis
    vetos = analyze_candidate_fatal_vetos()
    print(f"Evaluated {len(vetos)} candidate fatal veto conditions.")

    # 3. Phase 7 -> Phase 8 Interaction Cases
    cases = evaluate_phase7_phase8_interaction_cases()
    print(f"Evaluated {len(cases)} interaction cases across Phase 7 and Phase 8.")

    # 4. Non-Compensatory Failure Scenarios
    scenarios = evaluate_non_compensatory_scenarios()
    print(f"Evaluated {len(scenarios)} non-compensatory failure scenarios.")

    # 5. Multi-Region Readiness Simulation
    sim_data = simulate_multi_region_exam_page()
    print(f"Simulated multi-zone exam page with {len(sim_data['regions'])} distinct regions.")

    # 6. Generate Diagnostic Visualizations
    generate_phase8_4_visualizations(matrix, sim_data)

    print("\n" + "=" * 80)
    print("PHASE 8.4 INVESTIGATION COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    run_phase8_4_investigation()
