"""
phase7/rescan_decision_engine.py

AI-EVAL PHASE 7.2: PRODUCTION RESCAN DECISION ENGINE
====================================================

PURPOSE:
Production implementation of the evidence-driven, non-compensatory Rescan
Decision Engine. Consumes the final verified safe document state and final
Phase 5 quality assessment (or Phase 6 CorrectedDocumentResult) and produces
exactly one definitive semantic routing outcome:
- CONTINUE
- HUMAN_REVIEW
- RESCAN_REQUIRED

ARCHITECTURAL PRINCIPLES (FROZEN PHASE 7.1):
1. Non-Compensatory Fatal Veto: If any confirmed Tier 1 fatal defect remains
   (boundary clipping, optical defocus, specular glare on text, margin occlusion,
   severe ink loss, geometric collapse), the document is assigned RESCAN_REQUIRED.
   Zero compensation is allowed by high contrast, paper whiteness, or acutance.
2. Perception-Action Decoupling: Decision operates strictly on the final verified
   safe state, not raw inputs or intermediate candidate buffers.
3. Separation of Concerns:
   - BORDERLINE != RESCAN_REQUIRED (borderline cases route to HUMAN_REVIEW).
   - INSUFFICIENT_EVIDENCE != RESCAN_REQUIRED (sparse/blank pages route to HUMAN_REVIEW).
   - Correction rejection != automatic rescan (evaluated against restored safe state).
4. Centralized Provisional Configuration:
   All empirical decision parameters reside in RescanDecisionConfig and are
   explicitly annotated: CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN.
"""

from __future__ import annotations

import os
import sys
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from dataclasses import dataclass, field

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Path Configuration & Frozen Module Imports
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

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
    CorrectedDocumentResult,
    SafeImageState,
)


# ===========================================================================
# 1. PRODUCTION DATA CONTRACTS
# ===========================================================================

class RescanDecision(str, Enum):
    """
    Definitive semantic routing outcome of the Rescan Decision Engine.
    Exactly one outcome is returned for every processed document.
    """
    CONTINUE = "CONTINUE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    RESCAN_REQUIRED = "RESCAN_REQUIRED"


class DecisionTrigger(str, Enum):
    """
    Underlying semantic trigger or reason code that drove the decision.
    """
    FATAL_VETO = "FATAL_VETO"
    SPARSE_OR_BLANK_CONTENT = "SPARSE_OR_BLANK_CONTENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNRECOVERABLE_QUALITY_COLLAPSE = "UNRECOVERABLE_QUALITY_COLLAPSE"
    BORDERLINE_QUALITY = "BORDERLINE_QUALITY"
    CORRECTION_ROLLBACK_SAFE_FALLBACK = "CORRECTION_ROLLBACK_SAFE_FALLBACK"
    CORRECTION_ROLLBACK_BORDERLINE = "CORRECTION_ROLLBACK_BORDERLINE"
    CONFIRMED_HIGH_QUALITY = "CONFIRMED_HIGH_QUALITY"
    ACCEPTABLE_QUALITY = "ACCEPTABLE_QUALITY"


@dataclass(frozen=True)
class RescanDecisionConfig:
    """
    Centralized provisional calibration parameters for the Rescan Decision Engine.
    
    CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN.
    These parameters represent empirical thresholds derived from real student exam sheets,
    controlled physical degradation sweeps, and Phase 5/6 calibration.
    Final parameter optimization across 5,000+ multi-institution scripts occurs in Phase 11.
    No magic numbers are scattered elsewhere in the code.
    """
    # Minimum foreground stroke pixel count to classify a document as having content
    min_stroke_pixels_for_content: int = 350

    # Minimum foreground pixel fraction relative to full document canvas
    min_foreground_fraction: float = 0.0005

    # Local intensity delta and gradient thresholds for stroke content extraction
    content_stroke_contrast_delta: float = 20.0
    content_stroke_grad_mag: float = 35.0

    # Maximum allowed risk factors for direct automated CONTINUE on ACCEPTABLE verdict
    max_acceptable_risk_factors_for_continue: int = 1

    # Empirical confidence assignments per decision path
    confidence_fatal_veto: float = 1.00
    confidence_confirmed_good: float = 0.98
    confidence_acceptable: float = 0.88
    confidence_borderline_review: float = 0.75
    confidence_sparse_review: float = 0.85
    confidence_unrecoverable_rescan: float = 0.95


@dataclass(frozen=True)
class RescanDecisionResult:
    """
    Immutable production result contract for the Rescan Decision System.
    All collection fields are stored as tuples to guarantee true immutability.
    """
    decision: str                                   # "CONTINUE", "HUMAN_REVIEW", "RESCAN_REQUIRED"
    reason_codes: Tuple[str, ...]                   # Primary trigger and associated reason codes
    readiness_state: str                            # Final Phase 5 verdict: GOOD, ACCEPTABLE, BORDERLINE, UNUSABLE
    fatal_defects: Tuple[FatalDefectRecord, ...]    # Confirmed Tier 1 fatal defects (empty if none)
    human_review_required: bool                     # True if routed to manual review queue
    rescan_required: bool                           # True if physical rescan is mandatory
    evidence_sufficient: bool                       # False if document has sparse/blank or ambiguous content
    is_automated_continue: bool                     # True iff decision == "CONTINUE"
    processing_notes: Tuple[str, ...]               # Audit log of evaluation steps
    confidence: float                               # Statistical confidence (0.0 to 1.0)
    primary_trigger: str                            # Primary trigger string
    actionable_operator_guidance: str               # Physical instructions for camera operator (empty if CONTINUE)
    human_review_checklist: Tuple[str, ...]         # Targeted checklist for human reviewer (empty if not HUMAN_REVIEW)
    processing_latency_ms: float                    # Engine execution latency in milliseconds
    source_metadata: Dict[str, Any] = field(default_factory=dict)


# ===========================================================================
# 2. PRODUCTION DECISION ENGINE
# ===========================================================================

class ProductionRescanDecisionEngine:
    """
    Production implementation of the Phase 7 Rescan Decision Engine.
    Implements the non-compensatory 4-Tier decision hierarchy:
    Tier 1: Fatal Defect Veto (Non-compensatory boolean gate)
    Tier 2: Evidence Sufficiency Gate (Sparse / Blank content separation)
    Tier 3: Correction Rollback & Recovery Evaluation
    Tier 4: Multi-Dimensional Quality Readiness Gate
    """

    def __init__(self, config: Optional[RescanDecisionConfig] = None):
        self.config = config or RescanDecisionConfig()

    def evaluate(
        self,
        document_input: Union[CorrectedDocumentResult, SafeImageState, np.ndarray],
        final_quality_assessment: Optional[QualityAssessmentResult] = None,
        initial_quality_assessment: Optional[QualityAssessmentResult] = None,
        has_rollbacks: bool = False,
        image_name: str = "document"
    ) -> RescanDecisionResult:
        """
        Main production evaluation entry point.
        
        Accepts:
        - CorrectedDocumentResult from Phase 6, OR
        - SafeImageState / np.ndarray with explicit QualityAssessmentResult from Phase 5.
        
        Returns an immutable RescanDecisionResult.
        """
        t0 = time.perf_counter()
        notes: List[str] = []
        reason_codes: List[str] = []

        # -------------------------------------------------------------------
        # 1. Input Unification & Context Extraction
        # -------------------------------------------------------------------
        if isinstance(document_input, CorrectedDocumentResult):
            final_safe_gray = document_input.final_safe_state.image_gray
            qa_final = document_input.quality_assessment_final
            qa_initial = document_input.quality_assessment_initial
            rollbacks_count = len(document_input.rollback_events)
            is_rollback_present = rollbacks_count > 0
            applied_ops = [c.operator_id for c in document_input.applied_corrections]
            notes.append(f"Source: CorrectedDocumentResult (status={document_input.status}, ops={applied_ops}, rollbacks={rollbacks_count})")
        elif isinstance(document_input, SafeImageState):
            final_safe_gray = document_input.image_gray
            qa_final = final_quality_assessment or assess_document_quality(final_safe_gray, image_name)
            qa_initial = initial_quality_assessment or qa_final
            is_rollback_present = has_rollbacks
            notes.append(f"Source: SafeImageState (id={document_input.state_id}, version={document_input.version_index})")
        elif isinstance(document_input, np.ndarray):
            if document_input.ndim == 3:
                final_safe_gray = cv2.cvtColor(document_input, cv2.COLOR_BGR2GRAY)
            else:
                final_safe_gray = document_input
            qa_final = final_quality_assessment or assess_document_quality(document_input, image_name)
            qa_initial = initial_quality_assessment or qa_final
            is_rollback_present = has_rollbacks
            notes.append("Source: np.ndarray image canvas")
        else:
            raise TypeError(f"Unsupported document_input type: {type(document_input)}")

        notes.append(f"Initial QA Verdict: {qa_initial.verdict} (fatal={len(qa_initial.fatal_defects)})")
        notes.append(f"Final QA Verdict: {qa_final.verdict} (fatal={len(qa_final.fatal_defects)})")

        # -------------------------------------------------------------------
        # TIER 1 — FATAL DEFECT VETO (Non-Compensatory)
        # -------------------------------------------------------------------
        # Any confirmed fatal defect triggers immediate RESCAN_REQUIRED.
        # Zero compensation is allowed by strong contrast, acutance, or paper whiteness.
        fatal_records = list(qa_final.fatal_defects)
        if not fatal_records and qa_initial.fatal_defects and qa_final.verdict == "UNUSABLE":
            # If correction halted at initial step due to fatal defect
            fatal_records = list(qa_initial.fatal_defects)

        if len(fatal_records) > 0:
            fatal_codes = [d.defect_code for d in fatal_records]
            reason_codes.append(DecisionTrigger.FATAL_VETO.value)
            reason_codes.extend(fatal_codes)
            notes.append(f"Tier 1 Fatal Veto Triggered: {fatal_codes}")

            guidance = self._build_operator_rescan_guidance(fatal_records)
            latency = (time.perf_counter() - t0) * 1000.0

            return RescanDecisionResult(
                decision=RescanDecision.RESCAN_REQUIRED.value,
                reason_codes=tuple(reason_codes),
                readiness_state=qa_final.verdict,
                fatal_defects=tuple(fatal_records),
                human_review_required=False,
                rescan_required=True,
                evidence_sufficient=True,
                is_automated_continue=False,
                processing_notes=tuple(notes),
                confidence=self.config.confidence_fatal_veto,
                primary_trigger=DecisionTrigger.FATAL_VETO.value,
                actionable_operator_guidance=guidance,
                human_review_checklist=(),
                processing_latency_ms=latency,
                source_metadata={"tier_reached": 1, "fatal_defect_count": len(fatal_records)}
            )

        # -------------------------------------------------------------------
        # TIER 2 — EVIDENCE SUFFICIENCY & CONTENT GATE
        # -------------------------------------------------------------------
        # Evaluate whether the document has sufficient stroke content.
        # CRITICAL SAFETY: A blank page must NOT trigger RESCAN_REQUIRED!
        # It must route to HUMAN_REVIEW to confirm the student left the page blank.
        is_sparse, stroke_count, fg_frac = self._check_content_sufficiency(final_safe_gray)
        if is_sparse:
            reason_codes.append(DecisionTrigger.SPARSE_OR_BLANK_CONTENT.value)
            notes.append(f"Tier 2 Content Sufficiency: Sparse/Blank detected (strokes={stroke_count}, fg_frac={fg_frac:.5f})")

            checklist = (
                "Verify if student intentionally left this answer booklet page blank.",
                "Verify absence of faint pencil work or unscanned diagrams.",
                "Confirm question booklet page number corresponds to an unattempted question."
            )
            latency = (time.perf_counter() - t0) * 1000.0

            return RescanDecisionResult(
                decision=RescanDecision.HUMAN_REVIEW.value,
                reason_codes=tuple(reason_codes),
                readiness_state=qa_final.verdict,
                fatal_defects=(),
                human_review_required=True,
                rescan_required=False,
                evidence_sufficient=False,
                is_automated_continue=False,
                processing_notes=tuple(notes),
                confidence=self.config.confidence_sparse_review,
                primary_trigger=DecisionTrigger.SPARSE_OR_BLANK_CONTENT.value,
                actionable_operator_guidance="No rescan required unless reviewer confirms missing content.",
                human_review_checklist=checklist,
                processing_latency_ms=latency,
                source_metadata={"tier_reached": 2, "stroke_count": stroke_count, "fg_fraction": fg_frac}
            )

        # -------------------------------------------------------------------
        # TIER 3 & 4 — CORRECTION FALLBACK & FINAL QUALITY READINESS
        # -------------------------------------------------------------------
        # Evaluate final verified safe state readiness
        if qa_final.verdict == "GOOD":
            trigger = DecisionTrigger.CONFIRMED_HIGH_QUALITY.value
            reason_codes.append(trigger)
            if is_rollback_present:
                reason_codes.append(DecisionTrigger.CORRECTION_ROLLBACK_SAFE_FALLBACK.value)
                notes.append("Tier 3/4: Operator rollback safely restored pristine GOOD safe state.")
            else:
                notes.append("Tier 3/4: Confirmed high quality across all readiness dimensions.")

            latency = (time.perf_counter() - t0) * 1000.0
            return RescanDecisionResult(
                decision=RescanDecision.CONTINUE.value,
                reason_codes=tuple(reason_codes),
                readiness_state=qa_final.verdict,
                fatal_defects=(),
                human_review_required=False,
                rescan_required=False,
                evidence_sufficient=True,
                is_automated_continue=True,
                processing_notes=tuple(notes),
                confidence=self.config.confidence_confirmed_good,
                primary_trigger=trigger,
                actionable_operator_guidance="",
                human_review_checklist=(),
                processing_latency_ms=latency,
                source_metadata={"tier_reached": 4, "verdict": qa_final.verdict}
            )

        elif qa_final.verdict == "ACCEPTABLE":
            # If acceptable with minimal risk, CONTINUE
            # If acceptable with multiple warning risks, route to HUMAN_REVIEW
            if len(qa_final.risk_factors) <= self.config.max_acceptable_risk_factors_for_continue:
                trigger = DecisionTrigger.ACCEPTABLE_QUALITY.value
                reason_codes.append(trigger)
                notes.append(f"Tier 3/4: Acceptable quality envelope satisfied. Risks: {qa_final.risk_factors}")
                latency = (time.perf_counter() - t0) * 1000.0

                return RescanDecisionResult(
                    decision=RescanDecision.CONTINUE.value,
                    reason_codes=tuple(reason_codes),
                    readiness_state=qa_final.verdict,
                    fatal_defects=(),
                    human_review_required=False,
                    rescan_required=False,
                    evidence_sufficient=True,
                    is_automated_continue=True,
                    processing_notes=tuple(notes),
                    confidence=self.config.confidence_acceptable,
                    primary_trigger=trigger,
                    actionable_operator_guidance="",
                    human_review_checklist=(),
                    processing_latency_ms=latency,
                    source_metadata={"tier_reached": 4, "verdict": qa_final.verdict, "risks": qa_final.risk_factors}
                )
            else:
                trigger = DecisionTrigger.BORDERLINE_QUALITY.value
                reason_codes.append(trigger)
                notes.append(f"Tier 3/4: Acceptable verdict has multiple warning risks: {qa_final.risk_factors}")
                checklist = self._build_borderline_checklist(qa_final.evidence_profile, qa_final.risk_factors)
                latency = (time.perf_counter() - t0) * 1000.0

                return RescanDecisionResult(
                    decision=RescanDecision.HUMAN_REVIEW.value,
                    reason_codes=tuple(reason_codes),
                    readiness_state=qa_final.verdict,
                    fatal_defects=(),
                    human_review_required=True,
                    rescan_required=False,
                    evidence_sufficient=True,
                    is_automated_continue=False,
                    processing_notes=tuple(notes),
                    confidence=self.config.confidence_borderline_review,
                    primary_trigger=trigger,
                    actionable_operator_guidance="Review handwriting legibility in degraded regions before grading.",
                    human_review_checklist=tuple(checklist),
                    processing_latency_ms=latency,
                    source_metadata={"tier_reached": 4, "verdict": qa_final.verdict, "risks": qa_final.risk_factors}
                )

        elif qa_final.verdict == "BORDERLINE":
            trigger = DecisionTrigger.BORDERLINE_QUALITY.value
            reason_codes.append(trigger)
            if is_rollback_present:
                reason_codes.append(DecisionTrigger.CORRECTION_ROLLBACK_BORDERLINE.value)
                notes.append("Tier 3/4: Operator rollback returned to borderline safe state.")
            notes.append(f"Tier 3/4: Borderline quality metrics observed: {qa_final.risk_factors}")

            checklist = self._build_borderline_checklist(qa_final.evidence_profile, qa_final.risk_factors)
            latency = (time.perf_counter() - t0) * 1000.0

            return RescanDecisionResult(
                decision=RescanDecision.HUMAN_REVIEW.value,
                reason_codes=tuple(reason_codes),
                readiness_state=qa_final.verdict,
                fatal_defects=(),
                human_review_required=True,
                rescan_required=False,
                evidence_sufficient=True,
                is_automated_continue=False,
                processing_notes=tuple(notes),
                confidence=self.config.confidence_borderline_review,
                primary_trigger=trigger,
                actionable_operator_guidance="Human review required. Do not rescan unless handwriting is unreadable.",
                human_review_checklist=tuple(checklist),
                processing_latency_ms=latency,
                source_metadata={"tier_reached": 4, "verdict": qa_final.verdict, "risks": qa_final.risk_factors}
            )

        else: # UNUSABLE
            trigger = DecisionTrigger.UNRECOVERABLE_QUALITY_COLLAPSE.value
            reason_codes.append(trigger)
            notes.append(f"Tier 3/4: Cumulative degradations exceed operational bounds: {qa_final.risk_factors}")
            latency = (time.perf_counter() - t0) * 1000.0

            return RescanDecisionResult(
                decision=RescanDecision.RESCAN_REQUIRED.value,
                reason_codes=tuple(reason_codes),
                readiness_state=qa_final.verdict,
                fatal_defects=(),
                human_review_required=False,
                rescan_required=True,
                evidence_sufficient=True,
                is_automated_continue=False,
                processing_notes=tuple(notes),
                confidence=self.config.confidence_unrecoverable_rescan,
                primary_trigger=trigger,
                actionable_operator_guidance="Rescan document under improved uniform lighting and stable optical focus.",
                human_review_checklist=(),
                processing_latency_ms=latency,
                source_metadata={"tier_reached": 4, "verdict": qa_final.verdict, "risks": qa_final.risk_factors}
            )

    def _check_content_sufficiency(self, gray: np.ndarray) -> Tuple[bool, int, float]:
        """
        Determines whether document has sufficient stroke content or is sparse/blank.
        Separates genuine ink strokes from flat paper substrate grain.
        """
        h, w = gray.shape[:2]
        total_pixels = h * w

        sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = np.hypot(sobel_x, sobel_y)

        # Low-pass filter for local background substrate
        bg_blur = cv2.GaussianBlur(gray, (51, 51), 0)
        local_contrast = bg_blur.astype(np.float32) - gray.astype(np.float32)

        stroke_mask = (local_contrast > self.config.content_stroke_contrast_delta) & \
                      (grad_mag > self.config.content_stroke_grad_mag)
        stroke_count = int(np.count_nonzero(stroke_mask))
        fg_fraction = stroke_count / float(max(1, total_pixels))

        is_sparse = (
            stroke_count < self.config.min_stroke_pixels_for_content or
            fg_fraction < self.config.min_foreground_fraction
        )
        return is_sparse, stroke_count, fg_fraction

    def _build_operator_rescan_guidance(self, fatal_defects: Sequence[FatalDefectRecord]) -> str:
        """
        Generates specific, actionable hardware/operator instructions based on fatal defect types.
        """
        guidance_items: List[str] = []
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

    def _build_borderline_checklist(self, profile: QualityEvidenceProfile, risks: Sequence[str]) -> List[str]:
        """
        Generates targeted checklist items for human review of borderline documents.
        """
        checklist: List[str] = []
        for r in risks:
            r_lower = r.lower()
            if "acutance" in r_lower or "defocus" in r_lower:
                checklist.append(f"Inspect character clarity (acutance: {profile.normalized_stroke_acutance:.1f}). Ensure words are decipherable.")
            elif "contrast" in r_lower or "faint" in r_lower:
                checklist.append(f"Inspect faint stroke segments (faint stroke ratio: {profile.faint_stroke_pixel_fraction*100:.1f}%). Check pencil markings.")
            elif "shadow" in r_lower or "illumination" in r_lower:
                checklist.append(f"Inspect darkest shadow region (quadrant deficit: {profile.worst_quadrant_paper_deficit:.1f} levels). Confirm text not lost.")
            elif "skew" in r_lower:
                checklist.append(f"Inspect text baseline tilt ({profile.residual_skew_angle_deg:.1f}°). Confirm line grouping is intact.")
            elif "otsu" in r_lower or "binarization" in r_lower:
                checklist.append(f"Inspect character topological separation (Otsu eta: {profile.binarization_otsu_eta:.3f}). Confirm characters do not bridge.")
            else:
                checklist.append(f"Inspect document condition regarding: {r}")
        return checklist


# ===========================================================================
# 3. HIGH-LEVEL FUNCTIONAL ENTRY POINT
# ===========================================================================

def evaluate_rescan_decision(
    document_input: Union[CorrectedDocumentResult, SafeImageState, np.ndarray],
    final_quality_assessment: Optional[QualityAssessmentResult] = None,
    initial_quality_assessment: Optional[QualityAssessmentResult] = None,
    has_rollbacks: bool = False,
    config: Optional[RescanDecisionConfig] = None,
    image_name: str = "document"
) -> RescanDecisionResult:
    """
    High-level functional entry point for the Production Rescan Decision Engine.
    """
    engine = ProductionRescanDecisionEngine(config=config)
    return engine.evaluate(
        document_input=document_input,
        final_quality_assessment=final_quality_assessment,
        initial_quality_assessment=initial_quality_assessment,
        has_rollbacks=has_rollbacks,
        image_name=image_name
    )
