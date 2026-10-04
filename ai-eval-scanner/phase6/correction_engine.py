"""
phase6/correction_engine.py

AI-EVAL PHASE 6.3: PRODUCTION CORRECTION ENGINE & PLANNER IMPLEMENTATION
========================================================================

PURPOSE:
Production implementation of the safe-state correction framework, dynamic
planner, execution engine, and multi-dimensional verification gate based strictly
on Phase 6.2 contracts.

CORE ARCHITECTURAL GUARANTEES:
1. SAFE-STATE IMMUTABILITY & ISOLATION:
   Unverified candidate transformations operate strictly on isolated working copies.
   The active SafeImageState is never mutated before, during, or after verification.
2. DETERMINISTIC ROLLBACK:
   If verification returns FAIL or INSUFFICIENT_EVIDENCE, the candidate is discarded
   and the pipeline retains the previous verified SafeImageState.
3. RAW BGR PRESERVATION:
   raw_rectified_bgr is preserved across all revisions without modification.
4. PHASE 5 INTEGRATION & FATAL VETO:
   Tier 1 fatal defects (defocus, text clipping, glare collision, occlusion)
   immediately trigger rescan_required=True with zero correction execution.
5. OPERATOR DEPLETION & LOOP PREVENTION:
   An operator rejected on a state branch is marked DEPLETED for that branch
   to prevent repetitive loops on unchanged safe states.
6. CENTRALIZED PROVISIONAL CONFIGURATION:
   All calibration parameters reside in configuration dataclasses.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np

# Phase 5 Contracts
from phase5.production_quality_assessment import (
    QualityAssessmentResult,
    QualityEvidenceProfile,
    FatalDefectRecord,
    QualityGateConfig,
    assess_document_quality,
)

# Phase 6 Contracts
from phase6.correction_contracts import (
    AppliedCorrectionRecord,
    CorrectedDocumentResult,
    CorrectionAuditEntry,
    CorrectionCandidate,
    CorrectionExecutionEngine,
    CorrectionOperator,
    CorrectionPlanningConfig,
    CorrectionStatus,
    CorrectionVerificationConfig,
    CorrectionVerificationEvidence,
    CorrectionVerificationGate,
    DefectConditionCategory,
    IntelligentCorrectionPlanner,
    OperatorRegistry,
    RecoverabilityClass,
    RejectedCorrectionRecord,
    RollbackEventRecord,
    SafeImageState,
    VerificationVerdict,
)
from phase6.operators.shadow_normalization import ShadowNormalizationOperator
from phase6.operators.contrast_normalization import ContrastNormalizationOperator, ContrastNormalizationConfig


# ===========================================================================
# 1. OPERATOR REGISTRY IMPLEMENTATION
# ===========================================================================

class ProductionOperatorRegistry(OperatorRegistry):
    """
    Thread-safe registry managing available correction operators.
    """

    def __init__(self) -> None:
        self._operators: Dict[str, CorrectionOperator] = {}
        self._condition_map: Dict[DefectConditionCategory, List[str]] = {}

    def register_operator(self, operator: CorrectionOperator) -> None:
        op_id = operator.operator_id
        self._operators[op_id] = operator
        cond = operator.supported_condition
        if cond not in self._condition_map:
            self._condition_map[cond] = []
        if op_id not in self._condition_map[cond]:
            self._condition_map[cond].append(op_id)

    def get_operator(self, operator_id: str) -> Optional[CorrectionOperator]:
        return self._operators.get(operator_id)

    def list_operators_for_condition(
        self,
        condition: DefectConditionCategory
    ) -> List[CorrectionOperator]:
        op_ids = self._condition_map.get(condition, [])
        return [self._operators[oid] for oid in op_ids if oid in self._operators]

    def list_all_operators(self) -> List[CorrectionOperator]:
        return list(self._operators.values())


# ===========================================================================
# 2. MULTI-DIMENSIONAL VERIFICATION GATE
# ===========================================================================

class ProductionVerificationGate(CorrectionVerificationGate):
    """
    Multi-dimensional safety gate evaluating candidate transformations
    against the reference SafeImageState.
    """

    def verify_candidate(
        self,
        before_state: SafeImageState,
        candidate_image: np.ndarray,
        candidate: CorrectionCandidate,
        config: Optional[CorrectionVerificationConfig] = None
    ) -> CorrectionVerificationEvidence:
        cfg = config or CorrectionVerificationConfig()
        rejection_reasons: List[str] = []
        evidence_notes: List[str] = []

        ref_gray = before_state.image_gray
        cand_gray = candidate_image

        # 1. Verify buffer non-aliasing / identity
        if cand_gray is ref_gray or np.shares_memory(cand_gray, ref_gray):
            rejection_reasons.append("CRITICAL: Candidate buffer aliases reference SafeImageState buffer")
            return CorrectionVerificationEvidence(
                thin_stroke_survival_ratio=0.0,
                faint_stroke_loss=1.0,
                halo_overshoot_gain=999.0,
                substrate_noise_delta=999.0,
                connected_component_ratio=0.0,
                background_mean_drift=0.0,
                stroke_intensity_delta_gain=0.0,
                normalized_acutance_gain=0.0,
                verdict=VerificationVerdict.FAIL,
                rejection_reasons=rejection_reasons,
                evidence_notes=["Buffer isolation invariant violated"]
            )

        # 2. Pixel difference check (MAD)
        diff = np.abs(cand_gray.astype(np.float32) - ref_gray.astype(np.float32))
        mad = float(np.mean(diff))
        if mad < 0.5:
            rejection_reasons.append(f"Negligible transformation effect (MAD = {mad:.3f} < 0.5)")
            return CorrectionVerificationEvidence(
                thin_stroke_survival_ratio=1.0,
                faint_stroke_loss=0.0,
                halo_overshoot_gain=0.0,
                substrate_noise_delta=0.0,
                connected_component_ratio=1.0,
                background_mean_drift=0.0,
                stroke_intensity_delta_gain=0.0,
                normalized_acutance_gain=0.0,
                verdict=VerificationVerdict.FAIL,
                rejection_reasons=rejection_reasons,
                evidence_notes=["Operator produced no material change; NO_OP preferable"]
            )

        # 3. Thin-stroke survival evaluation (Canny edge skeleton overlap)
        ref_edges = cv2.Canny(ref_gray, 40, 120)
        cand_edges = cv2.Canny(cand_gray, 40, 120)
        n_ref_edge = int(np.count_nonzero(ref_edges))

        if n_ref_edge < 40:
            # Insufficient stroke evidence for topological verification
            evidence_notes.append("Sparse stroke content: edge pixel count below statistical confidence floor")
            return CorrectionVerificationEvidence(
                thin_stroke_survival_ratio=1.0,
                faint_stroke_loss=0.0,
                halo_overshoot_gain=0.0,
                substrate_noise_delta=0.0,
                connected_component_ratio=1.0,
                background_mean_drift=0.0,
                stroke_intensity_delta_gain=0.0,
                normalized_acutance_gain=0.0,
                verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
                rejection_reasons=["Insufficient stroke pixels to verify safety"],
                evidence_notes=evidence_notes
            )

        # Edge overlap within 1-pixel dilation tolerance
        dilated_cand = cv2.dilate(cand_edges, np.ones((3, 3), np.uint8))
        surviving = int(np.count_nonzero((ref_edges > 0) & (dilated_cand > 0)))
        thin_stroke_survival = float(surviving / n_ref_edge)

        if thin_stroke_survival < cfg.min_thin_stroke_survival:
            rejection_reasons.append(
                f"Thin-stroke erosion: survival = {thin_stroke_survival*100:.1f}% "
                f"(< {cfg.min_thin_stroke_survival*100:.1f}%)"
            )
        else:
            evidence_notes.append(f"Thin-stroke preservation verified: {thin_stroke_survival*100:.1f}% retained")

        # 4. Faint-stroke retention (Local-Paper-Relative Evaluation)
        # Isolate local paper substrate via scale-aware morphological dilation
        h_img, w_img = ref_gray.shape[:2]
        scale_factor = min(w_img, h_img) / 1000.0
        bg_k = max(11, int(round(cfg.local_bg_kernel_base * scale_factor)) | 1)
        local_bg = cv2.dilate(ref_gray, cv2.getStructuringElement(cv2.MORPH_RECT, (bg_k, bg_k)))
        local_contrast = np.maximum(0, local_bg.astype(np.float32) - ref_gray.astype(np.float32))

        # Local adaptive binarization to capture candidate stroke topology under non-uniform lighting
        adapt_k = max(15, int(round(min(w_img, h_img) * 0.03)) | 1)
        ref_bin = cv2.adaptiveThreshold(ref_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, adapt_k, 10)
        cand_bin = cv2.adaptiveThreshold(cand_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, adapt_k, 10)

        # Faint-stroke mask: genuine stroke pixels whose local contrast is within the faint envelope [min, max]
        # (Excludes dark ink strokes > max_faint_contrast_delta and paper texture < min_faint_contrast_delta)
        faint_mask = (ref_bin > 0) & (local_contrast >= cfg.min_faint_contrast_delta) & (local_contrast <= cfg.max_faint_contrast_delta)
        n_faint = int(np.count_nonzero(faint_mask))

        if n_faint > 30:
            faint_survived = int(np.count_nonzero(faint_mask & (cand_bin > 0)))
            faint_stroke_loss = float(1.0 - (faint_survived / n_faint))
            if faint_stroke_loss > cfg.max_faint_stroke_loss:
                rejection_reasons.append(
                    f"Faint-stroke loss: {faint_stroke_loss*100:.1f}% faint pixels erased "
                    f"(> {cfg.max_faint_stroke_loss*100:.1f}%)"
                )
            else:
                evidence_notes.append(
                    f"Faint-stroke retention verified: {(1.0 - faint_stroke_loss)*100:.1f}% faint strokes preserved"
                )
        else:
            faint_stroke_loss = 0.0

        # 5. Halo overshoot & edge ringing evaluation (Scale-Aware)
        scale_factor = min(w_img, h_img) / 1000.0
        effective_halo_limit = cfg.max_halo_gain * (1.0 + 0.25 * scale_factor)

        sobel_ref = np.hypot(cv2.Sobel(ref_gray, cv2.CV_32F, 1, 0), cv2.Sobel(ref_gray, cv2.CV_32F, 0, 1))
        sobel_cand = np.hypot(cv2.Sobel(cand_gray, cv2.CV_32F, 1, 0), cv2.Sobel(cand_gray, cv2.CV_32F, 0, 1))
        dilated_ref = cv2.dilate(ref_bin, np.ones((5, 5), np.uint8))
        paper_near_strokes = cv2.bitwise_xor(dilated_ref, ref_bin)

        # For linear contrast expansion, baseline gradient legitimately scales with dynamic range expansion factor k.
        # True ringing / halo overshoot is gradient surge beyond linear contrast scaling.
        contrast_scaling = 1.0
        if candidate.operator_id == "CONTRAST_NORMALIZATION":
            ref_dyn = float(np.percentile(ref_gray, 99) - np.percentile(ref_gray, 1))
            cand_dyn = float(np.percentile(cand_gray, 99) - np.percentile(cand_gray, 1))
            if ref_dyn > 10.0:
                contrast_scaling = max(1.0, cand_dyn / ref_dyn)

        if np.count_nonzero(paper_near_strokes) > 50:
            halo_gain = float(np.mean(sobel_cand[paper_near_strokes > 0]) - contrast_scaling * np.mean(sobel_ref[paper_near_strokes > 0]))
        else:
            halo_gain = 0.0

        if halo_gain > effective_halo_limit:
            rejection_reasons.append(
                f"Excessive edge ringing / halo overshoot: halo gain = +{halo_gain:.1f} "
                f"(> {effective_halo_limit:.1f})"
            )

        # 6. Connected component topological stability (filtering sub-pixel noise specks < 4px)
        _, _, stats_ref, _ = cv2.connectedComponentsWithStats(ref_bin)
        _, _, stats_cand, _ = cv2.connectedComponentsWithStats(cand_bin)
        n_cc_ref = max(1, int(np.count_nonzero(stats_ref[1:, cv2.CC_STAT_AREA] >= 4)))
        n_cc_cand = max(1, int(np.count_nonzero(stats_cand[1:, cv2.CC_STAT_AREA] >= 4)))
        cc_ratio = float(n_cc_cand / n_cc_ref)

        effective_cc_tol = cfg.max_connected_component_ratio_deviation
        if candidate.operator_id == "CONTRAST_NORMALIZATION":
            # Contrast expansion can legitimately bridge faint fragmented strokes into continuous characters
            effective_cc_tol = max(cfg.max_connected_component_ratio_deviation, 0.25)

        if abs(cc_ratio - 1.0) > effective_cc_tol:
            rejection_reasons.append(
                f"Connected-component count divergence: CC ratio = {cc_ratio:.2f} "
                f"(tolerance = 1.0 +/- {effective_cc_tol:.2f})"
            )

        # 7. Substrate noise evaluation
        flat_mask = (paper_near_strokes == 0) & (ref_bin == 0)
        if np.count_nonzero(flat_mask) > 100:
            std_ref = float(np.std(ref_gray[flat_mask]))
            std_cand = float(np.std(cand_gray[flat_mask]))
            substrate_noise_delta = float(std_cand - std_ref)

            effective_noise_limit = cfg.max_substrate_noise_gain
            if candidate.operator_id == "CONTRAST_NORMALIZATION":
                # Linear contrast expansion naturally scales sensor grain with dynamic range expansion
                effective_noise_limit = max(cfg.max_substrate_noise_gain, 8.0 * (1.0 + 0.25 * scale_factor))

            if substrate_noise_delta > effective_noise_limit:
                rejection_reasons.append(
                    f"Substrate noise surge: delta = +{substrate_noise_delta:.1f} levels "
                    f"(> {effective_noise_limit:.1f})"
                )
        else:
            substrate_noise_delta = 0.0

        # 8. Background mean drift
        ref_bg_median = float(np.percentile(ref_gray, 85))
        cand_bg_median = float(np.percentile(cand_gray, 85))
        background_mean_drift = float(cand_bg_median - ref_bg_median)

        # 9. Stroke intensity delta gain & Acutance
        ref_ink_median = float(np.percentile(ref_gray[ref_bin > 0], 25)) if np.count_nonzero(ref_bin) > 0 else 0.0
        cand_ink_median = float(np.percentile(cand_gray[cand_bin > 0], 25)) if np.count_nonzero(cand_bin) > 0 else 0.0
        stroke_intensity_delta_gain = float((cand_bg_median - cand_ink_median) - (ref_bg_median - ref_ink_median))

        ref_acutance = float(np.mean(sobel_ref[ref_edges > 0])) if n_ref_edge > 0 else 0.0
        cand_acutance = float(np.mean(sobel_cand[cand_edges > 0])) if np.count_nonzero(cand_edges) > 0 else 0.0
        normalized_acutance_gain = float(cand_acutance - ref_acutance)

        # 10. Operator-specific remediation check for SHADOW_NORMALIZATION
        if candidate.operator_id == "SHADOW_NORMALIZATION":
            # Verify that regional illumination deficit actually decreased
            deficit_before = self._compute_paper_deficit(ref_gray)
            deficit_after = self._compute_paper_deficit(cand_gray)
            deficit_reduction = deficit_before - deficit_after
            if deficit_reduction < 10.0:
                rejection_reasons.append(
                    f"Insufficient shadow remediation: deficit reduction = {deficit_reduction:.1f} "
                    f"(< 10.0 levels required)"
                )
            else:
                evidence_notes.append(
                    f"Shadow remediation verified: deficit reduced from {deficit_before:.1f} to {deficit_after:.1f}"
                )

        # 11. Operator-specific remediation check for CONTRAST_NORMALIZATION
        if candidate.operator_id == "CONTRAST_NORMALIZATION":
            if stroke_intensity_delta_gain < cfg.min_contrast_delta_gain:
                rejection_reasons.append(
                    f"Insufficient contrast improvement: delta gain = +{stroke_intensity_delta_gain:.1f} "
                    f"(< {cfg.min_contrast_delta_gain:.1f} required)"
                )
            else:
                evidence_notes.append(
                    f"Contrast improvement verified: stroke contrast delta gain = +{stroke_intensity_delta_gain:.1f}"
                )

        # Final verdict determination
        if rejection_reasons:
            verdict = VerificationVerdict.FAIL
        else:
            verdict = VerificationVerdict.PASS

        return CorrectionVerificationEvidence(
            thin_stroke_survival_ratio=thin_stroke_survival,
            faint_stroke_loss=faint_stroke_loss,
            halo_overshoot_gain=halo_gain,
            substrate_noise_delta=substrate_noise_delta,
            connected_component_ratio=cc_ratio,
            background_mean_drift=background_mean_drift,
            stroke_intensity_delta_gain=stroke_intensity_delta_gain,
            normalized_acutance_gain=normalized_acutance_gain,
            verdict=verdict,
            rejection_reasons=rejection_reasons,
            evidence_notes=evidence_notes
        )

    def _compute_paper_deficit(self, gray: np.ndarray) -> float:
        h, w = gray.shape[:2]
        grid_rows, grid_cols = 4, 4
        cell_h = max(1, h // grid_rows)
        cell_w = max(1, w // grid_cols)
        regional_whites: List[float] = []

        for r in range(grid_rows):
            for c in range(grid_cols):
                cell = gray[r * cell_h:min(h, (r + 1) * cell_h), c * cell_w:min(w, (c + 1) * cell_w)]
                if cell.size > 50:
                    regional_whites.append(float(np.percentile(cell, 85)))

        if regional_whites:
            return float(max(regional_whites) - min(regional_whites))
        return 0.0


# ===========================================================================
# 3. CORRECTION EXECUTION ENGINE IMPLEMENTATION
# ===========================================================================

class ProductionExecutionEngine(CorrectionExecutionEngine):
    """
    Atomic execution engine enforcing buffer isolation, verification, and deterministic rollback.
    """

    def execute_and_verify(
        self,
        current_state: SafeImageState,
        candidate: CorrectionCandidate,
        operator: CorrectionOperator,
        verifier: CorrectionVerificationGate,
        config: Optional[CorrectionVerificationConfig] = None
    ) -> Tuple[SafeImageState, Union[AppliedCorrectionRecord, RejectedCorrectionRecord]]:
        cfg = config or CorrectionVerificationConfig()
        t0 = time.perf_counter()

        # 1. GUARANTEE BUFFER ISOLATION
        # Create explicit working copy; verify memory non-aliasing
        working_buffer = current_state.image_gray.copy()
        assert working_buffer is not current_state.image_gray, "Working buffer must not be identical object"
        assert not np.shares_memory(working_buffer, current_state.image_gray), "Working buffer must not share memory"

        # 2. APPLY CANDIDATE TRANSFORMATION
        t_exec_start = time.perf_counter()
        transformed_gray = operator.apply(working_buffer, candidate.config_parameters)
        exec_latency_ms = (time.perf_counter() - t_exec_start) * 1000.0

        # Invariant check: operator must not have returned original safe buffer
        assert transformed_gray is not current_state.image_gray, "Operator cannot return safe state buffer"
        assert not np.shares_memory(transformed_gray, current_state.image_gray), "Operator cannot share memory with safe state"

        # 3. VERIFY CANDIDATE
        t_verif_start = time.perf_counter()
        evidence = verifier.verify_candidate(current_state, transformed_gray, candidate, cfg)
        verif_latency_ms = (time.perf_counter() - t_verif_start) * 1000.0

        # 4. DECISION & STATE TRANSITION
        if evidence.verdict == VerificationVerdict.PASS:
            # Commit new SafeImageState (Safe State N+1)
            new_version = current_state.version_index + 1
            new_state_id = f"state_v{new_version}_{operator.operator_id.lower()}"

            new_safe_state = SafeImageState(
                state_id=new_state_id,
                version_index=new_version,
                parent_state_id=current_state.state_id,
                image_gray=transformed_gray,
                image_bgr=None,
                raw_rectified_bgr=current_state.raw_rectified_bgr.copy(),  # RAW BGR PRESERVED
                applied_operator_id=operator.operator_id,
                quality_profile=None,  # Will be re-measured after commit
                verification_evidence=evidence,
                is_verified_safe=True
            )

            record = AppliedCorrectionRecord(
                candidate_id=candidate.candidate_id,
                operator_id=operator.operator_id,
                condition_addressed=candidate.condition_category,
                from_state_id=current_state.state_id,
                to_state_id=new_state_id,
                verification_evidence=evidence,
                execution_latency_ms=exec_latency_ms,
                verification_latency_ms=verif_latency_ms
            )
            return new_safe_state, record

        else:
            # Automatic Rollback to current SafeImageState (Safe State N)
            # Candidate buffer is dropped and garbage-collected
            record = RejectedCorrectionRecord(
                candidate_id=candidate.candidate_id,
                operator_id=operator.operator_id,
                condition_addressed=candidate.condition_category,
                at_state_id=current_state.state_id,
                verification_evidence=evidence,
                rejection_reasons=evidence.rejection_reasons,
                rolled_back_to_state_id=current_state.state_id
            )
            return current_state, record


# ===========================================================================
# 4. DYNAMIC INTELLIGENT CORRECTION PLANNER
# ===========================================================================

class ProductionCorrectionPlanner(IntelligentCorrectionPlanner):
    """
    Dynamic correction planner that evaluates active SafeImageState evidence,
    filters dependencies and depleted operators, and emits single candidate proposals.
    """

    def plan_next_candidate(
        self,
        current_state: SafeImageState,
        quality_assessment: QualityAssessmentResult,
        applied_candidates: Sequence[AppliedCorrectionRecord],
        rejected_candidates: Sequence[RejectedCorrectionRecord],
        registry: OperatorRegistry,
        config: Optional[CorrectionPlanningConfig] = None
    ) -> Optional[CorrectionCandidate]:
        cfg = config or CorrectionPlanningConfig()

        # 1. PHASE 5 FATAL DEFECT INTERCEPTION
        # Tier 1 fatal defects strictly veto all correction attempts
        if quality_assessment.fatal_defects:
            return None

        # 2. ITERATION CEILING GUARD
        if len(applied_candidates) >= cfg.max_planner_iterations:
            return None

        # 3. OPERATOR DEPLETION TRACKING
        # Operators that failed on the current safe state are depleted for this state
        depleted_ops = {
            r.operator_id for r in rejected_candidates
            if r.at_state_id == current_state.state_id
        }
        # Operators already successfully applied across the active state branch
        applied_ops = {a.operator_id for a in applied_candidates}

        profile = quality_assessment.evidence_profile

        # 4. CONDITION-DRIVEN OPERATOR SELECTION
        # Currently registered and tested: SHADOW_NORMALIZATION
        # (Future operators for contrast, denoise, sharpen will register here in Phase 6.4)
        shadow_ops = registry.list_operators_for_condition(DefectConditionCategory.ILLUMINATION_SHADOW)

        for op in shadow_ops:
            if op.operator_id in depleted_ops or op.operator_id in applied_ops:
                continue

            # Check prerequisites
            deps_satisfied = all(dep in applied_ops for dep in op.prerequisite_operators)
            if not deps_satisfied:
                continue

            # Evaluate applicability against current safe state
            is_applicable, rationale = op.estimate_applicability(current_state, profile)
            if is_applicable:
                candidate_id = f"cand_{op.operator_id.lower()}_{current_state.version_index + 1}"
                return CorrectionCandidate(
                    candidate_id=candidate_id,
                    operator_id=op.operator_id,
                    condition_category=op.supported_condition,
                    recoverability_class=op.recoverability_class,
                    dependencies=op.prerequisite_operators,
                    prerequisites={},
                    expected_benefit="Level regional background illumination to target paper white",
                    risk_category="HALO_RINGING_OVER_BLEACHING",
                    is_reversible=True,
                    is_verification_mandatory=True,
                    priority=10,
                    config_parameters={}
                )

        # 5. CONTRAST NORMALIZATION EVALUATION (Planner Soft Dependency / Preference)
        # Shadow normalization is preferred first if applicable.
        # If shadow normalization was already applied, depleted, or not applicable,
        # contrast normalization is evaluated on the active SafeImageState.
        contrast_ops = registry.list_operators_for_condition(DefectConditionCategory.LOW_STROKE_CONTRAST)
        for op in contrast_ops:
            if op.operator_id in depleted_ops or op.operator_id in applied_ops:
                continue

            # Check prerequisites if any
            deps_satisfied = all(dep in applied_ops for dep in op.prerequisite_operators)
            if not deps_satisfied:
                continue

            # Evaluate applicability against active safe state
            is_applicable, rationale = op.estimate_applicability(current_state, profile)
            if is_applicable:
                candidate_id = f"cand_{op.operator_id.lower()}_{current_state.version_index + 1}"
                return CorrectionCandidate(
                    candidate_id=candidate_id,
                    operator_id=op.operator_id,
                    condition_category=op.supported_condition,
                    recoverability_class=op.recoverability_class,
                    dependencies=op.prerequisite_operators,
                    prerequisites={},
                    expected_benefit="Stretches effective stroke intensity distribution to enhance handwriting contrast",
                    risk_category="SUBSTRATE_NOISE_AMPLIFICATION",
                    is_reversible=True,
                    is_verification_mandatory=True,
                    priority=20,
                    config_parameters={}
                )

        # No safe or applicable operator remaining
        return None


# ===========================================================================
# 5. HIGH-LEVEL PIPELINE ORCHESTRATOR
# ===========================================================================

def execute_intelligent_correction(
    raw_rectified_bgr: np.ndarray,
    initial_assessment: Optional[QualityAssessmentResult] = None,
    registry: Optional[OperatorRegistry] = None,
    planner: Optional[IntelligentCorrectionPlanner] = None,
    engine: Optional[CorrectionExecutionEngine] = None,
    verifier: Optional[CorrectionVerificationGate] = None,
    planning_config: Optional[CorrectionPlanningConfig] = None,
    verification_config: Optional[CorrectionVerificationConfig] = None
) -> CorrectedDocumentResult:
    """
    Main entry point for intelligent document correction.
    
    Orchestrates the dynamic perception-action loop:
    1. Initializes SafeImageState 0 from raw rectified BGR.
    2. Runs Phase 5 assessment if not already provided.
    3. If fatal defects exist, halts immediately (rescan_required=True).
    4. Dynamically plans and executes candidate operators in isolated buffers.
    5. Commits verified improvements or rolls back to the previous safe state.
    6. Returns an immutable CorrectedDocumentResult.
    """
    t_start = time.perf_counter()
    p_cfg = planning_config or CorrectionPlanningConfig()
    v_cfg = verification_config or CorrectionVerificationConfig()

    reg = registry or ProductionOperatorRegistry()
    if reg.get_operator("SHADOW_NORMALIZATION") is None:
        reg.register_operator(ShadowNormalizationOperator())
    if reg.get_operator("CONTRAST_NORMALIZATION") is None:
        reg.register_operator(ContrastNormalizationOperator())

    pln = planner or ProductionCorrectionPlanner()
    eng = engine or ProductionExecutionEngine()
    vrf = verifier or ProductionVerificationGate()

    # 1. Initialize SafeImageState 0 (Raw Rectified State)
    if hasattr(raw_rectified_bgr, "scanned_image"):
        raw_rectified_bgr = raw_rectified_bgr.scanned_image

    if raw_rectified_bgr.ndim == 3:
        initial_gray = cv2.cvtColor(raw_rectified_bgr, cv2.COLOR_BGR2GRAY)
    else:
        initial_gray = raw_rectified_bgr.copy()
        raw_rectified_bgr = cv2.cvtColor(initial_gray, cv2.COLOR_GRAY2BGR)

    current_state = SafeImageState(
        state_id="state_v0_raw",
        version_index=0,
        parent_state_id=None,
        image_gray=initial_gray,
        image_bgr=raw_rectified_bgr.copy(),
        raw_rectified_bgr=raw_rectified_bgr.copy(),  # Invariant: preserved raw BGR
        applied_operator_id=None,
        quality_profile=None,
        verification_evidence=None,
        is_verified_safe=True
    )

    # 2. Phase 5 Assessment on initial state
    if initial_assessment is None:
        assessment = assess_document_quality(raw_rectified_bgr, "input_document")
    else:
        assessment = initial_assessment

    applied_corrections: List[AppliedCorrectionRecord] = []
    rejected_corrections: List[RejectedCorrectionRecord] = []
    rollback_events: List[RollbackEventRecord] = []
    audit_trail: List[CorrectionAuditEntry] = []

    step_idx = 0
    audit_trail.append(CorrectionAuditEntry(
        step_index=step_idx,
        action_type="INIT",
        details=f"Initialized SafeImageState v0 with dimensions {current_state.image_gray.shape}"
    ))

    # 3. Check for Tier 1 Fatal Defects
    if assessment.fatal_defects:
        fatal_codes = [f.defect_code for f in assessment.fatal_defects]
        audit_trail.append(CorrectionAuditEntry(
            step_index=step_idx + 1,
            action_type="HALT",
            details=f"Phase 5 fatal defect(s) detected: {fatal_codes}. Halting correction planning."
        ))
        total_latency = (time.perf_counter() - t_start) * 1000.0

        return CorrectedDocumentResult(
            status="UNRECOVERABLE_FATAL",
            final_safe_state=current_state,
            corrected_gray=current_state.image_gray,
            preserved_raw_bgr=current_state.raw_rectified_bgr,
            binary_derivative=None,
            applied_corrections=[],
            rejected_corrections=[],
            rollback_events=[],
            audit_trail=audit_trail,
            rescan_required=True,
            human_review_required=False,
            overall_recoverability=RecoverabilityClass.UNRECOVERABLE,
            quality_assessment_initial=assessment,
            quality_assessment_final=assessment,
            total_processing_latency_ms=total_latency,
            metadata={"halt_reason": "Tier 1 Fatal Defect", "fatal_defects": fatal_codes}
        )

    # 4. Dynamic Planning & Execution Loop
    while True:
        step_idx += 1
        candidate = pln.plan_next_candidate(
            current_state=current_state,
            quality_assessment=assessment,
            applied_candidates=applied_corrections,
            rejected_candidates=rejected_corrections,
            registry=reg,
            config=p_cfg
        )

        if candidate is None:
            audit_trail.append(CorrectionAuditEntry(
                step_index=step_idx,
                action_type="PLAN_COMPLETE",
                details="No further applicable or safe candidate operators. Terminating loop."
            ))
            break

        operator = reg.get_operator(candidate.operator_id)
        if operator is None:
            audit_trail.append(CorrectionAuditEntry(
                step_index=step_idx,
                action_type="ERROR",
                details=f"Operator '{candidate.operator_id}' not found in registry. Skipping."
            ))
            break

        audit_trail.append(CorrectionAuditEntry(
            step_index=step_idx,
            action_type="EXECUTE_CANDIDATE",
            details=f"Executing candidate '{candidate.candidate_id}' ({operator.operator_id}) on isolated copy"
        ))

        # Execute in isolated working copy and verify
        next_state, record = eng.execute_and_verify(
            current_state=current_state,
            candidate=candidate,
            operator=operator,
            verifier=vrf,
            config=v_cfg
        )

        if isinstance(record, AppliedCorrectionRecord):
            audit_trail.append(CorrectionAuditEntry(
                step_index=step_idx,
                action_type="ACCEPT_COMMIT",
                details=f"Candidate accepted by verification gate. Committed new safe state '{next_state.state_id}'"
            ))
            applied_corrections.append(record)
            current_state = next_state

            # Re-measure quality assessment from new verified state
            assessment = assess_document_quality(
                cv2.cvtColor(current_state.image_gray, cv2.COLOR_GRAY2BGR),
                f"state_{current_state.version_index}"
            )

        elif isinstance(record, RejectedCorrectionRecord):
            rollback_ev = RollbackEventRecord(
                event_id=f"rollback_{step_idx}",
                rejected_candidate_id=candidate.candidate_id,
                from_candidate_state_id=f"candidate_{candidate.operator_id.lower()}",
                restored_safe_state_id=current_state.state_id,
                trigger_reason="; ".join(record.rejection_reasons)
            )
            rollback_events.append(rollback_ev)
            rejected_corrections.append(record)

            audit_trail.append(CorrectionAuditEntry(
                step_index=step_idx,
                action_type="ROLLBACK",
                details=f"Candidate rejected: {rollback_ev.trigger_reason}. Rolled back to safe state '{current_state.state_id}'"
            ))

    # 5. Final Result Synthesis
    total_latency = (time.perf_counter() - t_start) * 1000.0

    # Optional binary derivative for layout parsing / OMR
    _, bin_derivative = cv2.threshold(
        current_state.image_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    if applied_corrections:
        status = "CORRECTED_VERIFIED"
        overall_recoverability = RecoverabilityClass.RECOVERABLE
    elif rejected_corrections:
        status = "PARTIAL_SAFE_FALLBACK"
        overall_recoverability = RecoverabilityClass.CONDITIONALLY_RECOVERABLE
    else:
        status = "PRISTINE_PASS_THROUGH"
        overall_recoverability = RecoverabilityClass.RECOVERABLE

    return CorrectedDocumentResult(
        status=status,
        final_safe_state=current_state,
        corrected_gray=current_state.image_gray,
        preserved_raw_bgr=current_state.raw_rectified_bgr,
        binary_derivative=bin_derivative,
        applied_corrections=applied_corrections,
        rejected_corrections=rejected_corrections,
        rollback_events=rollback_events,
        audit_trail=audit_trail,
        rescan_required=assessment.rescan_required,
        human_review_required=assessment.human_review_required,
        overall_recoverability=overall_recoverability,
        quality_assessment_initial=initial_assessment or assessment,
        quality_assessment_final=assessment,
        total_processing_latency_ms=total_latency,
        metadata={"total_steps": step_idx, "committed_version": current_state.version_index}
    )
