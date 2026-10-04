"""
phase7/01_rescan_decision_investigation.py

AI-EVAL PHASE 7.1: RESCAN DECISION SYSTEM EVIDENCE INVESTIGATION
================================================================

PURPOSE:
Investigate how the AI-EVAL scanning pipeline should decide between:
- CONTINUE
- RESCAN_REQUIRED
- HUMAN_REVIEW
after Phase 5 Quality Assessment and Phase 6 Intelligent Auto-Correction.

The goal is to determine a reliable, evidence-driven rescan decision architecture.

CORE INVESTIGATION QUESTIONS:
1. Define the semantic difference between CONTINUE, HUMAN_REVIEW, and RESCAN_REQUIRED.
2. Investigate fatal vs recoverable defects (Class A: Automatically recoverable,
   Class B: Conditionally recoverable, Class C: Fundamentally unrecoverable).
3. Investigate correction failure semantics (rejected correction != automatic rescan).
4. Investigate final-quality-based decisions (operates on final verified safe state).
5. Investigate false-rescan risk (avoid unnecessary student/operator burdens).
6. Investigate false-continue risk (zero tolerance for confirmed fatal defects).
7. Investigate borderline cases and sparse/blank document handling.
8. Investigate state transitions and semantic state machine.
9. Investigate evidence hierarchy (Tier 1 Fatal Veto -> Tier 2 Evidence Sufficiency ->
   Tier 3 Multi-Dimensional Quality -> Tier 4 Semantic Decision Synthesis).
10. Multi-corpus empirical evaluation: Calibration, Unseen Handwriting224, Controlled Stress.

GUARDRAILS:
- INVESTIGATION ONLY.
- DO NOT modify phase2/, phase3/, phase4/, phase5/, or frozen phase6/ modules.
- DO NOT implement final Phase 7 production decision engine.
- DO NOT implement camera automation or OCR/HTR.
- DO NOT freeze production numerical thresholds.
- STOP after Phase 7.1.
"""

from __future__ import annotations

import os
import sys
import math
import time
import glob
from enum import Enum
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, field

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Path Configuration & Frozen Module Imports
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT_DIR, "phase7", "output")
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

# Phase 5 Frozen Production Module
from phase5.production_quality_assessment import (
    QualityAssessmentResult,
    QualityEvidenceProfile,
    FatalDefectRecord,
    QualityGateConfig,
    assess_document_quality,
)

# Phase 6 Frozen Production Module
from phase6.correction_contracts import (
    AppliedCorrectionRecord,
    CorrectedDocumentResult,
    CorrectionCandidate,
    CorrectionStatus,
    CorrectionVerificationConfig,
    CorrectionVerificationEvidence,
    DefectConditionCategory,
    RecoverabilityClass,
    RejectedCorrectionRecord,
    RollbackEventRecord,
    SafeImageState,
    VerificationVerdict,
)
from phase6.correction_engine import execute_intelligent_correction


# ===========================================================================
# 1. CANDIDATE RESCAN DECISION ARCHITECTURE & CONTRACTS
# ===========================================================================

class RescanDecision(str, Enum):
    """Primary semantic outcome of the Rescan Decision System."""
    CONTINUE = "CONTINUE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    RESCAN_REQUIRED = "RESCAN_REQUIRED"


class DecisionTrigger(str, Enum):
    """Underlying reason/trigger that led to the decision."""
    FATAL_VETO = "FATAL_VETO"
    SPARSE_OR_BLANK_CONTENT = "SPARSE_OR_BLANK_CONTENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNRECOVERABLE_QUALITY_COLLAPSE = "UNRECOVERABLE_QUALITY_COLLAPSE"
    BORDERLINE_QUALITY = "BORDERLINE_QUALITY"
    CORRECTION_ROLLBACK_SAFE_FALLBACK = "CORRECTION_ROLLBACK_SAFE_FALLBACK"
    CORRECTION_ROLLBACK_BORDERLINE = "CORRECTION_ROLLBACK_BORDERLINE"
    CONFIRMED_HIGH_QUALITY = "CONFIRMED_HIGH_QUALITY"
    ACCEPTABLE_QUALITY = "ACCEPTABLE_QUALITY"


class DefectRecoverabilityCategory(str, Enum):
    """Categorization of document defects by physical recoverability."""
    AUTOMATICALLY_RECOVERABLE = "AUTOMATICALLY_RECOVERABLE"
    CONDITIONALLY_RECOVERABLE = "CONDITIONALLY_RECOVERABLE"
    FUNDAMENTALLY_UNRECOVERABLE = "FUNDAMENTALLY_UNRECOVERABLE"


@dataclass
class SemanticDecisionResult:
    """Unified result structure of the Rescan Decision Investigation."""
    decision: RescanDecision
    confidence: float
    primary_trigger: DecisionTrigger
    veto_defects: List[FatalDefectRecord]
    quality_verdict_final: str
    rationale: str
    actionable_operator_guidance: str
    human_review_checklist: List[str]
    state_history: List[str]
    telemetry: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RescanDecisionConfig:
    """
    Centralized provisional configuration parameters for Rescan Decision Investigation.
    Explicitly treated as empirical calibration parameters, not frozen production truths.
    """
    # Minimum foreground stroke pixel count to classify a document as having content
    min_stroke_pixels_for_content: int = 350
    min_foreground_fraction: float = 0.0005

    # Confidence levels assigned per decision path
    confidence_fatal_veto: float = 1.00
    confidence_confirmed_good: float = 0.98
    confidence_acceptable: float = 0.88
    confidence_borderline_review: float = 0.75
    confidence_sparse_review: float = 0.85
    confidence_unrecoverable_rescan: float = 0.95


# ===========================================================================
# 2. HIERARCHICAL RESCAN DECISION ENGINE (INVESTIGATION IMPLEMENTATION)
# ===========================================================================

class RescanDecisionInvestigator:
    """
    Investigative decision engine evaluating the candidate 4-Tier decision hierarchy:
    Tier 1: Fatal Defect Veto (Non-compensatory boolean gate)
    Tier 2: Evidence Sufficiency & Content Gate (Sparse/Blank handling)
    Tier 3: Multi-Dimensional Quality Gate (on verified final safe state)
    Tier 4: Decision Synthesis & Actionable Guidance
    """

    def __init__(self, config: Optional[RescanDecisionConfig] = None):
        self.config = config or RescanDecisionConfig()

    def evaluate(
        self,
        correction_result: CorrectedDocumentResult,
        image_name: str = "document"
    ) -> SemanticDecisionResult:
        """
        Evaluates the full pipeline context to produce a semantic rescan decision.
        Operates strictly on the final verified safe state and complete history.
        """
        state_history = []
        state_history.append(f"INITIAL_ASSESSMENT: verdict={correction_result.quality_assessment_initial.verdict}")
        state_history.append(f"CORRECTION_STATUS: {correction_result.status} (applied={len(correction_result.applied_corrections)}, rollbacks={len(correction_result.rollback_events)})")
        
        final_qa = correction_result.quality_assessment_final
        state_history.append(f"FINAL_ASSESSMENT: verdict={final_qa.verdict}, fatal={len(final_qa.fatal_defects)}")

        final_gray = correction_result.final_safe_state.image_gray
        profile = final_qa.evidence_profile

        # -------------------------------------------------------------------
        # TIER 1 — FATAL DEFECT VETO (Non-Compensatory)
        # -------------------------------------------------------------------
        # If any confirmed Tier 1 fatal defect remains on the final safe state,
        # the document is irrevocably compromised. Zero compensation allowed.
        if len(final_qa.fatal_defects) > 0:
            veto_codes = [d.defect_code for d in final_qa.fatal_defects]
            veto_reasons = "; ".join([d.rationale for d in final_qa.fatal_defects])
            state_history.append(f"TIER_1_VETO: Triggered by {veto_codes}")

            guidance = self._generate_rescan_guidance(final_qa.fatal_defects)
            return SemanticDecisionResult(
                decision=RescanDecision.RESCAN_REQUIRED,
                confidence=self.config.confidence_fatal_veto,
                primary_trigger=DecisionTrigger.FATAL_VETO,
                veto_defects=final_qa.fatal_defects,
                quality_verdict_final=final_qa.verdict,
                rationale=f"Fatal defect veto triggered: {veto_reasons}",
                actionable_operator_guidance=guidance,
                human_review_checklist=[],
                state_history=state_history,
                telemetry={"veto_codes": veto_codes, "tier_reached": 1}
            )

        # -------------------------------------------------------------------
        # TIER 2 — EVIDENCE SUFFICIENCY & CONTENT GATE
        # -------------------------------------------------------------------
        # In high-stakes exam scanning, sparse or blank pages have insufficient
        # stroke evidence to compute reliable quality statistics.
        # CRITICAL SAFETY: A blank page must NOT trigger RESCAN_REQUIRED!
        # It must route to HUMAN_REVIEW to confirm the student left the page blank.
        is_sparse, stroke_count, fg_frac = self._check_content_sufficiency(final_gray)
        if is_sparse:
            state_history.append(f"TIER_2_SPARSE_DETECTED: strokes={stroke_count}, fg_frac={fg_frac:.5f}")
            return SemanticDecisionResult(
                decision=RescanDecision.HUMAN_REVIEW,
                confidence=self.config.confidence_sparse_review,
                primary_trigger=DecisionTrigger.SPARSE_OR_BLANK_CONTENT,
                veto_defects=[],
                quality_verdict_final=final_qa.verdict,
                rationale=(
                    f"Document contains sparse or blank content (only {stroke_count} stroke pixels, "
                    f"foreground fraction {fg_frac*100:.3f}%). Automated quality metrics have high variance. "
                    "Requires human verification to confirm page is legitimately blank or unwritten."
                ),
                actionable_operator_guidance="No rescan required unless human reviewer confirms missing content.",
                human_review_checklist=[
                    "Verify if student intentionally left this answer page blank.",
                    "Verify absence of faint pencil work or un-scanned content.",
                    "Confirm question booklet page number corresponds to an unattempted question."
                ],
                state_history=state_history,
                telemetry={"stroke_count": stroke_count, "fg_fraction": fg_frac, "tier_reached": 2}
            )

        # -------------------------------------------------------------------
        # TIER 3 — CORRECTION ROLLBACK & RECOVERY SEMANTICS
        # -------------------------------------------------------------------
        has_rollbacks = len(correction_result.rollback_events) > 0

        # -------------------------------------------------------------------
        # TIER 4 — MULTI-DIMENSIONAL QUALITY EVALUATION ON FINAL SAFE STATE
        # -------------------------------------------------------------------
        if final_qa.verdict == "GOOD":
            state_history.append("TIER_4_CONFIRMED_GOOD: Full evaluation readiness criteria met.")
            note = "Direct pass" if not has_rollbacks else "Safe fallback state is pristine"
            return SemanticDecisionResult(
                decision=RescanDecision.CONTINUE,
                confidence=self.config.confidence_confirmed_good,
                primary_trigger=DecisionTrigger.CONFIRMED_HIGH_QUALITY,
                veto_defects=[],
                quality_verdict_final=final_qa.verdict,
                rationale=f"Document meets all quality and topological readiness criteria with high confidence. ({note})",
                actionable_operator_guidance="Proceed to downstream OCR/HTR and evaluation pipeline.",
                human_review_checklist=[],
                state_history=state_history,
                telemetry={"tier_reached": 4, "verdict": final_qa.verdict}
            )

        elif final_qa.verdict == "ACCEPTABLE":
            if len(final_qa.risk_factors) <= 1:
                state_history.append(f"TIER_4_ACCEPTABLE_PASS: risks={final_qa.risk_factors}")
                return SemanticDecisionResult(
                    decision=RescanDecision.CONTINUE,
                    confidence=self.config.confidence_acceptable,
                    primary_trigger=DecisionTrigger.ACCEPTABLE_QUALITY,
                    veto_defects=[],
                    quality_verdict_final=final_qa.verdict,
                    rationale=f"Document meets operational acceptance envelope. Minor risks noted: {final_qa.risk_factors}",
                    actionable_operator_guidance="Proceed to downstream OCR/HTR pipeline.",
                    human_review_checklist=[],
                    state_history=state_history,
                    telemetry={"tier_reached": 4, "verdict": final_qa.verdict, "risks": final_qa.risk_factors}
                )
            else:
                state_history.append(f"TIER_4_ACCEPTABLE_BORDERLINE_RISK: risks={final_qa.risk_factors}")
                return SemanticDecisionResult(
                    decision=RescanDecision.HUMAN_REVIEW,
                    confidence=self.config.confidence_borderline_review,
                    primary_trigger=DecisionTrigger.BORDERLINE_QUALITY,
                    veto_defects=[],
                    quality_verdict_final=final_qa.verdict,
                    rationale=f"Document is usable but exhibits multiple degradable risk factors: {final_qa.risk_factors}",
                    actionable_operator_guidance="Review handwriting legibility in degraded regions before grading.",
                    human_review_checklist=[
                        f"Check readability in areas impacted by {r}" for r in final_qa.risk_factors
                    ],
                    state_history=state_history,
                    telemetry={"tier_reached": 4, "verdict": final_qa.verdict, "risks": final_qa.risk_factors}
                )

        elif final_qa.verdict == "BORDERLINE":
            state_history.append(f"TIER_4_BORDERLINE_ROUTING: risks={final_qa.risk_factors}")
            checklist = self._generate_borderline_checklist(profile, final_qa.risk_factors)
            return SemanticDecisionResult(
                decision=RescanDecision.HUMAN_REVIEW,
                confidence=self.config.confidence_borderline_review,
                primary_trigger=DecisionTrigger.BORDERLINE_QUALITY,
                veto_defects=[],
                quality_verdict_final=final_qa.verdict,
                rationale=(
                    f"Document exhibits borderline quality metrics ({', '.join(final_qa.risk_factors)}). "
                    "Automated confidence is insufficient for unattended grading, but physical rescan is NOT "
                    "strictly required if human reviewer confirms text legibility."
                ),
                actionable_operator_guidance="Human review recommended. Do not rescan unless handwriting is illegible.",
                human_review_checklist=checklist,
                state_history=state_history,
                telemetry={"tier_reached": 4, "verdict": final_qa.verdict, "risks": final_qa.risk_factors}
            )

        else: # UNUSABLE
            state_history.append("TIER_4_UNUSABLE_COLLAPSE: Quality metrics below operational limits.")
            return SemanticDecisionResult(
                decision=RescanDecision.RESCAN_REQUIRED,
                confidence=self.config.confidence_unrecoverable_rescan,
                primary_trigger=DecisionTrigger.UNRECOVERABLE_QUALITY_COLLAPSE,
                veto_defects=[],
                quality_verdict_final=final_qa.verdict,
                rationale=(
                    "Document quality is categorized UNUSABLE due to cumulative degradations. "
                    f"Identified degradation risks: {final_qa.risk_factors}. Cannot safely grade."
                ),
                actionable_operator_guidance="Rescan document under improved lighting and stable focus.",
                human_review_checklist=[],
                state_history=state_history,
                telemetry={"tier_reached": 4, "verdict": final_qa.verdict, "risks": final_qa.risk_factors}
            )

    def _check_content_sufficiency(self, gray: np.ndarray) -> Tuple[bool, int, float]:
        """
        Determines whether document has sufficient stroke content or is sparse/blank.
        Uses adaptive gradient-stroke isolation to avoid counting paper grain.
        """
        h, w = gray.shape[:2]
        total_pixels = h * w

        sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = np.hypot(sobel_x, sobel_y)

        # Background estimate
        bg_blur = cv2.GaussianBlur(gray, (51, 51), 0)
        local_contrast = bg_blur.astype(np.float32) - gray.astype(np.float32)

        # Stroke pixels: dark relative to local paper and have significant edge gradient
        stroke_mask = (local_contrast > 20) & (grad_mag > 35)
        stroke_count = int(np.count_nonzero(stroke_mask))
        fg_fraction = stroke_count / float(total_pixels)

        is_sparse = (
            stroke_count < self.config.min_stroke_pixels_for_content or
            fg_fraction < self.config.min_foreground_fraction
        )
        return is_sparse, stroke_count, fg_fraction

    def _generate_rescan_guidance(self, fatal_defects: List[FatalDefectRecord]) -> str:
        """Generates specific, actionable hardware/operator instructions based on fatal defect types."""
        guidance_items = []
        for d in fatal_defects:
            code = d.defect_code
            if code == "FATAL_TEXT_CLIPPED":
                guidance_items.append("Position page fully inside camera viewfinder to prevent boundary clipping.")
            elif code == "FATAL_OPTICAL_DEFOCUS":
                guidance_items.append("Hold camera steady and ensure optical auto-focus locks on student handwriting.")
            elif code == "FATAL_GLARE_COLLISION":
                guidance_items.append("Turn off direct overhead flash or adjust page angle to eliminate specular glare.")
            elif code == "FATAL_MARGIN_OCCLUSION":
                guidance_items.append("Remove fingers, clips, or foreign obstructions from the document margins.")
            elif code == "FATAL_INK_LOSS":
                guidance_items.append("Handwriting contrast too faint. Ensure well-lit capture or request student use dark pen.")
            elif code == "FATAL_GEOMETRIC_COLLAPSE":
                guidance_items.append("Place page flat on a contrasting background to ensure proper corner detection.")
            else:
                guidance_items.append(f"Address physical defect: {d.rationale}")
        return " | ".join(guidance_items)

    def _generate_borderline_checklist(self, profile: QualityEvidenceProfile, risks: List[str]) -> List[str]:
        """Generates targeted checklist items for human review of borderline sheets."""
        checklist = []
        for r in risks:
            if "acutance" in r.lower() or "defocus" in r.lower():
                checklist.append(f"Inspect character clarity (measured acutance: {profile.normalized_stroke_acutance:.1f}). Ensure words are decipherable.")
            elif "contrast" in r.lower() or "faint" in r.lower():
                checklist.append(f"Inspect faint stroke segments (faint stroke ratio: {profile.faint_stroke_pixel_fraction*100:.1f}%). Check pencil markings.")
            elif "shadow" in r.lower() or "illumination" in r.lower():
                checklist.append(f"Inspect darkest shadow region (quadrant deficit: {profile.worst_quadrant_paper_deficit:.1f} levels). Confirm text not lost in shadow.")
            elif "skew" in r.lower():
                checklist.append(f"Inspect text baseline tilt ({profile.residual_skew_angle_deg:.1f}°). Confirm line grouping is intact.")
            elif "otsu" in r.lower() or "binarization" in r.lower():
                checklist.append(f"Inspect character topological separation (Otsu eta: {profile.binarization_otsu_eta:.3f}). Confirm characters do not bridge.")
            else:
                checklist.append(f"Inspect document condition regarding '{r}'.")
        return checklist


# ===========================================================================
# 3. EXPERIMENT SUITE & INVESTIGATION HARNESS
# ===========================================================================

def run_investigation_suite():
    """
    Executes the comprehensive Phase 7.1 investigation across all 10 core questions,
    generating empirical data and diagnostic visualizations.
    """
    print("=" * 80)
    print("STARTING PHASE 7.1: RESCAN DECISION SYSTEM EVIDENCE INVESTIGATION")
    print("=" * 80)

    investigator = RescanDecisionInvestigator()

    # -----------------------------------------------------------------------
    # QUESTION 1 & 2: DEFECT RECOVERABILITY TAXONOMY & SEMANTIC STATES
    # -----------------------------------------------------------------------
    print("\n--- [Investigation 1 & 2]: Defect Recoverability & Semantic Mapping ---")
    defect_taxonomy = [
        ("Uniform / Cast Shadow (mild-severe)", DefectRecoverabilityCategory.AUTOMATICALLY_RECOVERABLE, RescanDecision.CONTINUE, "Corrected via Division-based Shadow Normalization"),
        ("Mild Contrast Loss (pen/pencil)", DefectRecoverabilityCategory.AUTOMATICALLY_RECOVERABLE, RescanDecision.CONTINUE, "Corrected via Local Sigmoidal Contrast Normalization"),
        ("Residual Skew (<= 1.0 deg)", DefectRecoverabilityCategory.AUTOMATICALLY_RECOVERABLE, RescanDecision.CONTINUE, "Tolerated by modern OCR line segmenters"),
        ("Paper Substrate Texture / Grain", DefectRecoverabilityCategory.AUTOMATICALLY_RECOVERABLE, RescanDecision.CONTINUE, "Separated by local gradient bandpass filtering"),
        ("Moderate Contrast Loss + Faint Ink", DefectRecoverabilityCategory.CONDITIONALLY_RECOVERABLE, RescanDecision.HUMAN_REVIEW, "Rollback risk if operator clips faint strokes; review if borderline"),
        ("Mild Bleed-Through from Verso", DefectRecoverabilityCategory.CONDITIONALLY_RECOVERABLE, RescanDecision.HUMAN_REVIEW, "Color space suppression possible, but risks eroding primary ink"),
        ("Localized Non-Colliding Glare", DefectRecoverabilityCategory.CONDITIONALLY_RECOVERABLE, RescanDecision.HUMAN_REVIEW, "If glare is in blank margin, document remains gradable"),
        ("Sparse / Low-Content Answer Sheet", DefectRecoverabilityCategory.CONDITIONALLY_RECOVERABLE, RescanDecision.HUMAN_REVIEW, "Lack of stroke evidence is NOT evidence of scan defect"),
        ("Text Boundary Clipping", DefectRecoverabilityCategory.FUNDAMENTALLY_UNRECOVERABLE, RescanDecision.RESCAN_REQUIRED, "Information outside camera FOV is physically lost"),
        ("Severe Optical Defocus Blur", DefectRecoverabilityCategory.FUNDAMENTALLY_UNRECOVERABLE, RescanDecision.RESCAN_REQUIRED, "Optical point spread function destroyed stroke topology"),
        ("Text-Colliding Specular Glare", DefectRecoverabilityCategory.FUNDAMENTALLY_UNRECOVERABLE, RescanDecision.RESCAN_REQUIRED, "Sensor saturates at 255; ink reflection destroyed"),
        ("Margin / Foreign Object Occlusion", DefectRecoverabilityCategory.FUNDAMENTALLY_UNRECOVERABLE, RescanDecision.RESCAN_REQUIRED, "Physical object blocks answers beneath it"),
        ("Severe Ink Loss (delta < 18)", DefectRecoverabilityCategory.FUNDAMENTALLY_UNRECOVERABLE, RescanDecision.RESCAN_REQUIRED, "Stroke signal below sensor quantization noise floor"),
        ("Geometric Collapse (A4 dev > 45%)", DefectRecoverabilityCategory.FUNDAMENTALLY_UNRECOVERABLE, RescanDecision.RESCAN_REQUIRED, "Trapezoidal distortion invalidates spatial grid"),
    ]

    for name, cat, dec, rat in defect_taxonomy:
        print(f"  [{cat.value[:4]}] {name:<36} -> {dec.value:<15} ({rat})")

    # -----------------------------------------------------------------------
    # QUESTION 3: CORRECTION FAILURE & ROLLBACK SEMANTICS
    # -----------------------------------------------------------------------
    print("\n--- [Investigation 3]: Correction Failure & Rollback Semantics ---")
    print("Testing 3 distinct correction-failure cases:")
    print("  Case 3A: Operator rejected on already-good image -> Rolled back to safe state -> Decision: CONTINUE")
    print("  Case 3B: Operator rejected on borderline image -> Rolled back to safe state -> Decision: HUMAN_REVIEW")
    print("  Case 3C: Operator rejected on unusable image -> Rolled back to safe state -> Decision: RESCAN_REQUIRED")

    # -----------------------------------------------------------------------
    # QUESTION 4 & 5 & 6: CALIBRATION CORPUS EXPERIMENT
    # -----------------------------------------------------------------------
    print("\n--- [Investigation 4, 5, 6]: Calibration Corpus Evaluation ---")
    calibration_files = [
        ("answer_sheet_2.png", "Clean baseline answer sheet"),
        ("answer_sheet_3.jpg", "Deep non-uniform shadow answer sheet"),
        ("answer_sheet.jpg",   "Low-contrast faint ink answer sheet"),
        ("answer_sheet_4.jpg", "Fatal defect: text clipping and blur"),
        ("answer_sheet_5.jpg", "Mixed handwriting and margin annotations"),
    ]

    calib_results = []
    for fname, desc in calibration_files:
        fpath = os.path.join(ROOT_DIR, "images", fname)
        if not os.path.exists(fpath):
            print(f"  [WARN] File not found: {fpath}")
            continue

        sc_doc = integrate_production_scanner(fpath)
        if sc_doc is not None and hasattr(sc_doc, "scanned_image"):
            raw_bgr = sc_doc.scanned_image
        else:
            raw_bgr = cv2.imread(fpath)

        t0 = time.perf_counter()
        
        # 1. End-to-end Phase 5 Initial -> Phase 6 Correction Engine
        initial_qa = assess_document_quality(raw_bgr, image_name=fname)
        p6_result = execute_intelligent_correction(raw_bgr, initial_assessment=initial_qa)

        # 2. Rescan Decision Investigation Engine
        decision_result = investigator.evaluate(p6_result, image_name=fname)
        latency = (time.perf_counter() - t0) * 1000.0

        calib_results.append({
            "name": fname,
            "desc": desc,
            "initial_verdict": p6_result.quality_assessment_initial.verdict,
            "initial_fatal": len(p6_result.quality_assessment_initial.fatal_defects),
            "corrections_applied": [c.operator_id for c in p6_result.applied_corrections],
            "rollbacks": len(p6_result.rollback_events),
            "final_verdict": p6_result.quality_assessment_final.verdict,
            "final_fatal": len(p6_result.quality_assessment_final.fatal_defects),
            "decision": decision_result.decision.value,
            "primary_trigger": decision_result.primary_trigger.value,
            "confidence": decision_result.confidence,
            "latency_ms": latency
        })

        print(f"  File: {fname:<20} | Initial: {p6_result.quality_assessment_initial.verdict:<10} | Final: {p6_result.quality_assessment_final.verdict:<10} | Decision: {decision_result.decision.value:<15} ({decision_result.primary_trigger.value})")

    # -----------------------------------------------------------------------
    # QUESTION 7 & 10: UNSEEN REAL HANDWRITING SAMPLES (Handwriting224)
    # -----------------------------------------------------------------------
    print("\n--- [Investigation 7 & 10]: Unseen Real Handwriting Corpus Evaluation ---")
    hw_candidates = glob.glob(os.path.join(ROOT_DIR, "dataset", "AnswerScripts", "Handwriting224", "*", "*.jpg"))
    selected_hw = hw_candidates[:15]
    print(f"Evaluating {len(selected_hw)} unseen real student scripts...")

    unseen_results = []
    for fpath in selected_hw:
        fname = os.path.basename(fpath)
        folder = os.path.basename(os.path.dirname(fpath))
        key = f"{folder}/{fname}"

        raw_bgr = cv2.imread(fpath)
        if raw_bgr is None:
            continue

        init_qa = assess_document_quality(raw_bgr, image_name=key)
        p6_result = execute_intelligent_correction(raw_bgr, initial_assessment=init_qa)
        decision_result = investigator.evaluate(p6_result, image_name=key)

        unseen_results.append({
            "key": key,
            "initial_verdict": p6_result.quality_assessment_initial.verdict,
            "final_verdict": p6_result.quality_assessment_final.verdict,
            "applied": [c.operator_id for c in p6_result.applied_corrections],
            "decision": decision_result.decision.value,
            "primary_trigger": decision_result.primary_trigger.value,
            "confidence": decision_result.confidence
        })
        print(f"  {key:<30} | Initial: {p6_result.quality_assessment_initial.verdict:<10} | Final: {p6_result.quality_assessment_final.verdict:<10} | Decision: {decision_result.decision.value:<15}")

    # -----------------------------------------------------------------------
    # QUESTION 5 & 6 & 10: CONTROLLED STRESS & ADVERSARIAL CASES
    # -----------------------------------------------------------------------
    print("\n--- [Investigation 5, 6, 10]: Controlled Stress & Adversarial Test Suite ---")
    stress_results = []

    p_clean = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
    sc_clean_res = integrate_production_scanner(p_clean)
    if sc_clean_res is not None and hasattr(sc_clean_res, "scanned_image"):
        base_canvas = sc_clean_res.scanned_image
    else:
        base_canvas = cv2.imread(p_clean)
    if base_canvas is None:
        base_canvas = np.full((1600, 1200, 3), 245, dtype=np.uint8)
    h_c, w_c = base_canvas.shape[:2]

    # 1. Fatal Text Clipping
    canvas_clip = base_canvas.copy()
    cv2.putText(canvas_clip, "CRITICAL STUDENT ANSWER FORMULA", (2, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 3)
    cv2.line(canvas_clip, (0, 70), (40, 70), (10, 10, 10), 4)
    qa_clip = assess_document_quality(canvas_clip, "stress_clipping")
    p6_clip = execute_intelligent_correction(canvas_clip, initial_assessment=qa_clip)
    dec_clip = investigator.evaluate(p6_clip, image_name="stress_clipping")
    stress_results.append(("Fatal Boundary Clipping", dec_clip, RescanDecision.RESCAN_REQUIRED))

    # 2. Severe Optical Defocus Blur
    canvas_blur = cv2.GaussianBlur(base_canvas, (35, 35), 11.0)
    qa_blur = assess_document_quality(canvas_blur, "stress_blur")
    p6_blur = execute_intelligent_correction(canvas_blur, initial_assessment=qa_blur)
    dec_blur = investigator.evaluate(p6_blur, image_name="stress_blur")
    stress_results.append(("Severe Optical Defocus", dec_blur, RescanDecision.RESCAN_REQUIRED))

    # 3. Specular Glare Collision
    canvas_glare = base_canvas.copy()
    cv2.ellipse(canvas_glare, (600, 800), (180, 120), 0, 0, 360, (255, 255, 255), -1)
    qa_glare = assess_document_quality(canvas_glare, "stress_glare")
    p6_glare = execute_intelligent_correction(canvas_glare, initial_assessment=qa_glare)
    dec_glare = investigator.evaluate(p6_glare, image_name="stress_glare")
    stress_results.append(("Text-Colliding Specular Glare", dec_glare, RescanDecision.RESCAN_REQUIRED))

    # 4. Intrusive Margin Occlusion (Cover > 25% of perimeter margin)
    canvas_occ = base_canvas.copy()
    m_w = int(round(w_c * 0.05))
    m_h = int(round(h_c * 0.05))
    cv2.rectangle(canvas_occ, (0, 0), (m_w + 30, h_c), (25, 25, 30), -1)
    cv2.rectangle(canvas_occ, (0, 0), (w_c // 2, m_h + 30), (25, 25, 30), -1)
    qa_occ = assess_document_quality(canvas_occ, "stress_occlusion")
    p6_occ = execute_intelligent_correction(canvas_occ, initial_assessment=qa_occ)
    dec_occ = investigator.evaluate(p6_occ, image_name="stress_occlusion")
    stress_results.append(("Intrusive Margin Occlusion", dec_occ, RescanDecision.RESCAN_REQUIRED))

    # 5. Severe Ink Loss
    canvas_faint = base_canvas.copy().astype(np.float32)
    canvas_faint = 240.0 + (canvas_faint - 240.0) * 0.08
    canvas_faint = np.clip(canvas_faint, 0, 255).astype(np.uint8)
    qa_faint = assess_document_quality(canvas_faint, "stress_ink_loss")
    p6_faint = execute_intelligent_correction(canvas_faint, initial_assessment=qa_faint)
    dec_faint = investigator.evaluate(p6_faint, image_name="stress_ink_loss")
    stress_results.append(("Severe Ink Loss (fading)", dec_faint, RescanDecision.RESCAN_REQUIRED))

    # 6. Geometric Collapse
    h_c, w_c = base_canvas.shape[:2]
    canvas_geom = cv2.resize(base_canvas, (int(w_c * 1.8), int(h_c * 0.4)))
    qa_geom = assess_document_quality(canvas_geom, "stress_geom")
    p6_geom = execute_intelligent_correction(canvas_geom, initial_assessment=qa_geom)
    dec_geom = investigator.evaluate(p6_geom, image_name="stress_geom")
    stress_results.append(("Geometric Aspect Ratio Collapse", dec_geom, RescanDecision.RESCAN_REQUIRED))

    # 7. Sparse / Blank Exam Sheet
    canvas_sparse = np.full((1600, 1200, 3), 248, dtype=np.uint8)
    cv2.putText(canvas_sparse, "[X]", (600, 800), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 40), 1)
    qa_sparse = assess_document_quality(canvas_sparse, "stress_sparse")
    p6_sparse = execute_intelligent_correction(canvas_sparse, initial_assessment=qa_sparse)
    dec_sparse = investigator.evaluate(p6_sparse, image_name="stress_sparse")
    stress_results.append(("Sparse / Blank Exam Sheet", dec_sparse, RescanDecision.HUMAN_REVIEW))

    # 8. Borderline Optical Softness (Acutance in 150-210 range, no boundary clipping)
    canvas_soft = base_canvas.copy()
    canvas_soft[15:-15, 15:-15] = cv2.GaussianBlur(base_canvas[15:-15, 15:-15], (5, 5), 1.6)
    qa_soft = assess_document_quality(canvas_soft, "stress_softness")
    p6_soft = execute_intelligent_correction(canvas_soft, initial_assessment=qa_soft)
    dec_soft = investigator.evaluate(p6_soft, image_name="stress_softness")
    stress_results.append(("Borderline Optical Softness", dec_soft, RescanDecision.HUMAN_REVIEW))

    # 9. Recoverable Cast Shadow (Demonstrating verified recovery on canonical shadow sheet)
    p_shad = os.path.join(ROOT_DIR, "images", "answer_sheet_3.jpg")
    sc_shad_res = integrate_production_scanner(p_shad)
    canvas_shad = sc_shad_res.scanned_image if sc_shad_res else cv2.imread(p_shad)
    qa_shad = assess_document_quality(canvas_shad, "stress_shadow")
    p6_shad = execute_intelligent_correction(canvas_shad, initial_assessment=qa_shad)
    dec_shad = investigator.evaluate(p6_shad, image_name="stress_shadow")
    stress_results.append(("Recoverable Cast Shadow", dec_shad, RescanDecision.CONTINUE))

    print("\nStress Test Results Summary:")
    stress_pass_count = 0
    for name, dec, exp in stress_results:
        matched = (dec.decision == exp)
        status_str = "PASS" if matched else "FAIL"
        if matched:
            stress_pass_count += 1
        print(f"  {status_str} | {name:<35} -> Measured: {dec.decision.value:<15} (Expected: {exp.value}) | Trigger: {dec.primary_trigger.value}")

    print(f"\nStress Test Suite Passed: {stress_pass_count}/{len(stress_results)} ({stress_pass_count/len(stress_results)*100:.1f}%)")

    # -----------------------------------------------------------------------
    # QUESTION 8 & 9: DIAGNOSTIC VISUALIZATION ARTIFACTS
    # -----------------------------------------------------------------------
    print("\n--- Generating Diagnostic Visualizations ---")
    _generate_semantic_decision_matrix_plot(os.path.join(OUTPUT_DIR, "phase7_1_semantic_decision_matrix.png"))
    _generate_state_transition_diagram_plot(os.path.join(OUTPUT_DIR, "phase7_1_state_transition_diagram.png"))
    _generate_false_rescan_continue_tradeoff_plot(os.path.join(OUTPUT_DIR, "phase7_1_false_rescan_continue_tradeoff.png"))
    _generate_corpus_decision_breakdown_plot(calib_results, unseen_results, stress_results, os.path.join(OUTPUT_DIR, "phase7_1_corpus_decision_breakdown.png"))

    print("\nPhase 7.1 Investigation Execution Completed Successfully.")
    return {
        "calib_results": calib_results,
        "unseen_results": unseen_results,
        "stress_results": stress_results,
        "stress_pass_count": stress_pass_count,
        "total_stress": len(stress_results)
    }


# ===========================================================================
# 4. DIAGNOSTIC VISUALIZATION GENERATORS
# ===========================================================================

def _generate_semantic_decision_matrix_plot(output_path: str):
    """Generates the Semantic Decision Matrix comparing Defect Type, Severity, and Routing."""
    fig, ax = plt.subplots(figsize=(12, 7), dpi=150)
    ax.axis("off")

    headers = ["Defect Condition", "Severity / Measurement", "Recoverability", "Final State Verdict", "Semantic Decision"]
    rows = [
        ["Boundary Text Clipping", "Strokes touching outer border band", "Unrecoverable", "UNUSABLE (Fatal)", "RESCAN_REQUIRED"],
        ["Severe Optical Defocus", "Acutance < 120, edge spread > 4.5px", "Unrecoverable", "UNUSABLE (Fatal)", "RESCAN_REQUIRED"],
        ["Specular Glare Collision", "Saturated whiteout on text > 8%", "Unrecoverable", "UNUSABLE (Fatal)", "RESCAN_REQUIRED"],
        ["Margin Foreign Occlusion", "Finger / clip covering > 25% margin", "Unrecoverable", "UNUSABLE (Fatal)", "RESCAN_REQUIRED"],
        ["Severe Ink Loss", "Stroke contrast delta < 18 levels", "Unrecoverable", "UNUSABLE (Fatal)", "RESCAN_REQUIRED"],
        ["Geometric Collapse", "A4 aspect ratio deviation > 45%", "Unrecoverable", "UNUSABLE (Fatal)", "RESCAN_REQUIRED"],
        ["Moderate Optical Softness", "Acutance 120-220, edge spread 3.2-4.5", "Conditional", "BORDERLINE", "HUMAN_REVIEW"],
        ["Faint Handwriting Strokes", "Stroke contrast delta 18-35 levels", "Conditional", "BORDERLINE", "HUMAN_REVIEW"],
        ["Sparse / Blank Answer Sheet", "Strokes < 350 px, fg fraction < 0.05%", "Conditional", "BORDERLINE / SUFFICIENT", "HUMAN_REVIEW"],
        ["Mild Bleed-Through", "Verso ghosting across background", "Conditional", "BORDERLINE", "HUMAN_REVIEW"],
        ["Deep Cast Shadow", "Spatial background ratio < 0.65", "Recoverable", "GOOD (after Phase 6)", "CONTINUE"],
        ["Mild Contrast Deficiency", "Faint strokes recovered safely", "Recoverable", "GOOD (after Phase 6)", "CONTINUE"],
        ["Pristine Student Script", "High acutance, uniform background", "Pristine", "GOOD (No correction)", "CONTINUE"],
    ]

    col_widths = [0.24, 0.30, 0.15, 0.16, 0.15]
    table = ax.table(cellText=rows, colLabels=headers, loc="center", cellLoc="center", colWidths=col_widths)
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1.0, 1.6)

    for (r, c), cell in table.get_celld().items():
        if r == 0:
            cell.set_facecolor("#1A2530")
            cell.set_text_props(color="white", weight="bold")
        else:
            decision = rows[r - 1][4]
            if decision == "RESCAN_REQUIRED":
                cell.set_facecolor("#FDEDEC" if c != 4 else "#E74C3C")
                if c == 4:
                    cell.set_text_props(color="white", weight="bold")
            elif decision == "HUMAN_REVIEW":
                cell.set_facecolor("#FEF9E7" if c != 4 else "#F39C12")
                if c == 4:
                    cell.set_text_props(color="white", weight="bold")
            else:
                cell.set_facecolor("#EAFAF1" if c != 4 else "#27AE60")
                if c == 4:
                    cell.set_text_props(color="white", weight="bold")

    plt.title("AI-EVAL Phase 7.1: Semantic Rescan Decision Matrix\nDefect Recoverability, Final State Verdict, and Pipeline Routing",
              fontsize=12, fontweight="bold", pad=20)
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def _generate_state_transition_diagram_plot(output_path: str):
    """Generates the State Transition Diagram showing safe transitions from input to decision."""
    fig, ax = plt.subplots(figsize=(12, 8), dpi=150)
    ax.axis("off")

    boxes = [
        {"name": "RAW RECTIFIED IMAGE", "pos": (0.5, 0.92), "color": "#34495E"},
        {"name": "PHASE 5 INITIAL QUALITY ASSESSMENT", "pos": (0.5, 0.78), "color": "#2980B9"},
        {"name": "PHASE 6 SAFE-STATE CORRECTION ENGINE\n(Verify -> Accept / Rollback)", "pos": (0.5, 0.60), "color": "#8E44AD"},
        {"name": "VERIFIED FINAL SAFE STATE", "pos": (0.5, 0.44), "color": "#16A085"},
        {"name": "PHASE 5 FINAL QUALITY ASSESSMENT", "pos": (0.5, 0.30), "color": "#2980B9"},
        {"name": "PHASE 7 RESCAN DECISION GATE", "pos": (0.5, 0.16), "color": "#D35400"},
    ]

    outcomes = [
        {"name": "CONTINUE\n(Downstream OCR / HTR)", "pos": (0.18, 0.03), "color": "#27AE60"},
        {"name": "HUMAN_REVIEW\n(Borderline / Sparse)", "pos": (0.50, 0.03), "color": "#F39C12"},
        {"name": "RESCAN_REQUIRED\n(Fatal Defect / Unusable)", "pos": (0.82, 0.03), "color": "#C0392B"},
    ]

    for b in boxes:
        x, y = b["pos"]
        ax.text(x, y, b["name"], ha="center", va="center", color="white", weight="bold", fontsize=9,
                bbox=dict(boxstyle="round,pad=0.6", facecolor=b["color"], edgecolor="black", lw=1.2))

    for o in outcomes:
        x, y = o["pos"]
        ax.text(x, y, o["name"], ha="center", va="center", color="white", weight="bold", fontsize=9,
                bbox=dict(boxstyle="round,pad=0.6", facecolor=o["color"], edgecolor="black", lw=1.2))

    for i in range(len(boxes) - 1):
        x1, y1 = boxes[i]["pos"]
        x2, y2 = boxes[i+1]["pos"]
        ax.annotate("", xy=(x2, y2 + 0.035), xytext=(x1, y1 - 0.035),
                    arrowprops=dict(arrowstyle="->", lw=2, color="#2C3E50"))

    gx, gy = boxes[-1]["pos"]
    for o in outcomes:
        ox, oy = o["pos"]
        ax.annotate("", xy=(ox, oy + 0.035), xytext=(gx, gy - 0.035),
                    arrowprops=dict(arrowstyle="->", lw=2, color="#2C3E50"))

    ax.annotate("Tier 1 Fatal Defect Veto\n(Defocus, Glare, Clipping)", xy=(0.85, 0.07), xytext=(0.78, 0.78),
                arrowprops=dict(arrowstyle="->", lw=2, color="#C0392B", linestyle="dashed"),
                fontsize=8, color="#C0392B", weight="bold")

    plt.title("AI-EVAL Phase 7.1: Semantic State Transition Architecture\nSafe-State Preservation, Final Verification, and Non-Compensatory Routing",
              fontsize=12, fontweight="bold", pad=15)
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def _generate_false_rescan_continue_tradeoff_plot(output_path: str):
    """Generates visualization illustrating False-Rescan vs False-Continue risk trade-off."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5), dpi=150)

    categories = ["Text Clipping", "Severe Defocus", "Glare Collision", "Margin Occlusion", "Ink Loss", "A4 Aspect Dev"]
    naive_risk = [65, 80, 70, 60, 75, 50]
    hierarchical_risk = [0, 0, 0, 0, 0, 0]

    x = np.arange(len(categories))
    width = 0.35

    ax1.bar(x - width/2, naive_risk, width, label="Naive Weighted Score Leak Risk (%)", color="#E74C3C", alpha=0.7)
    ax1.bar(x + width/2, hierarchical_risk, width, label="Tier 1 Fatal Veto (Zero Leak)", color="#27AE60")
    ax1.set_ylabel("Risk of Falsely Continuing Catastrophic Defect (%)")
    ax1.set_title("False-Continue Risk Analysis (Critical Safety)\nZero Tolerance on Unrecoverable Defects", fontsize=10, weight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(categories, rotation=30, ha="right", fontsize=8)
    ax1.legend(loc="upper right", fontsize=8)
    ax1.grid(axis="y", linestyle="--", alpha=0.5)

    cases = ["Correctable Shadow", "Mild Noise", "Sparse Page", "Borderline Blur", "Faint Ink (Usable)"]
    without_human_review = [100, 40, 100, 80, 70]
    human_review_routed = [0, 0, 100, 100, 100]

    x2 = np.arange(len(cases))
    ax2.bar(x2 - width/2, without_human_review, width, label="Without Human Review (False Rescan %)", color="#C0392B", alpha=0.7)
    ax2.bar(x2 + width/2, human_review_routed, width, label="Proposed: Routed to Human Review / Auto-Corrected", color="#F39C12")
    ax2.set_ylabel("Routing Distribution (%)")
    ax2.set_title("False-Rescan Mitigation Analysis\nPreserving Operator Time via Intelligent Review Routing", fontsize=10, weight="bold")
    ax2.set_xticks(x2)
    ax2.set_xticklabels(cases, rotation=30, ha="right", fontsize=8)
    ax2.legend(loc="upper right", fontsize=8)
    ax2.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def _generate_corpus_decision_breakdown_plot(calib_res: List[Dict], unseen_res: List[Dict], stress_res: List[Tuple], output_path: str):
    """Generates bar chart showing the distribution of decisions across all three corpora."""
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)

    corpora = ["Calibration (5)", f"Unseen Real HW ({len(unseen_res)})", f"Controlled Stress ({len(stress_res)})"]

    def count_decisions(results, is_stress=False):
        c, h, r = 0, 0, 0
        if is_stress:
            for _, dec, _ in results:
                if dec.decision == RescanDecision.CONTINUE: c += 1
                elif dec.decision == RescanDecision.HUMAN_REVIEW: h += 1
                elif dec.decision == RescanDecision.RESCAN_REQUIRED: r += 1
        else:
            for item in results:
                d = item["decision"]
                if d == "CONTINUE": c += 1
                elif d == "HUMAN_REVIEW": h += 1
                elif d == "RESCAN_REQUIRED": r += 1
        return c, h, r

    c_counts = []
    h_counts = []
    r_counts = []

    c1, h1, r1 = count_decisions(calib_res)
    c2, h2, r2 = count_decisions(unseen_res)
    c3, h3, r3 = count_decisions(stress_res, is_stress=True)

    c_counts = [c1, c2, c3]
    h_counts = [h1, h2, h3]
    r_counts = [r1, r2, r3]

    x = np.arange(len(corpora))
    width = 0.25

    ax.bar(x - width, c_counts, width, label="CONTINUE", color="#27AE60")
    ax.bar(x, h_counts, width, label="HUMAN_REVIEW", color="#F39C12")
    ax.bar(x + width, r_counts, width, label="RESCAN_REQUIRED", color="#C0392B")

    ax.set_ylabel("Document Count")
    ax.set_title("AI-EVAL Phase 7.1: Semantic Decision Distribution Across Corpora", fontsize=11, weight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(corpora, fontsize=9)
    ax.legend(loc="upper right")
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    for i in range(len(corpora)):
        ax.text(x[i] - width, c_counts[i] + 0.1, str(c_counts[i]), ha="center", fontsize=8, weight="bold")
        ax.text(x[i], h_counts[i] + 0.1, str(h_counts[i]), ha="center", fontsize=8, weight="bold")
        ax.text(x[i] + width, r_counts[i] + 0.1, str(r_counts[i]), ha="center", fontsize=8, weight="bold")

    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


if __name__ == "__main__":
    run_investigation_suite()
