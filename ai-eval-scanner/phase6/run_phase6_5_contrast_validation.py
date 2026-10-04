"""
phase6/run_phase6_5_contrast_validation.py

AI-EVAL PHASE 6.5: CONTRAST NORMALIZATION OPERATOR VALIDATION SUITE
===================================================================

PURPOSE:
Comprehensive production validation of the ContrastNormalizationOperator,
safe-state lifecycle, dynamic planner ordering, multi-dimensional verification,
rollback behavior, operator depletion, buffer isolation, and Phase 6.3 regression safety.

TEST SUITE COVERAGE:
- Test A: Clean document -> Contrast operator NOT_APPLICABLE -> PRISTINE_PASS_THROUGH
- Test B: Low-contrast document -> Contrast operator APPLICABLE -> Verification PASS -> SafeState v1 committed
- Test C: Shadow + contrast ordering -> Shadow evaluated first -> Accepted shadow state input to contrast
          Contrast rejected on raw shadowed state (clamping) but accepted on leveled state
- Test D: Controlled candidate rejection -> Destructive contrast -> Verification FAIL -> Rollback to SafeState v0
- Test E: Insufficient evidence -> Sparse/blank canvas -> Verification INSUFFICIENT_EVIDENCE -> SafeState v0 retained
- Test F: Raw BGR preservation -> Pixel-for-pixel equality before/after correction revisions
- Test G: Buffer isolation & Immutability -> Verify read-only arrays and zero memory aliasing
- Test H: Operator depletion -> Rejected contrast operator marked depleted; no infinite loops
- Test I: Existing Phase 6.3 regression -> Full Phase 6.3 test suite executed (7/7 PASS)
"""

from __future__ import annotations

import os
import sys
import time
import importlib.util
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ---------------------------------------------------------------------------
# Import Frozen Phase 3 Scanner Integration & Phase 5 Quality Assessment
# ---------------------------------------------------------------------------
P3_PATH = os.path.join(ROOT_DIR, "phase3", "06_scanner_integration_investigation.py")
spec_p3 = importlib.util.spec_from_file_location("phase3_06", P3_PATH)
if spec_p3 is None or spec_p3.loader is None:
    raise ImportError(f"Could not load module from {P3_PATH}")
phase3_06 = importlib.util.module_from_spec(spec_p3)
spec_p3.loader.exec_module(phase3_06)
integrate_production_scanner = phase3_06.integrate_production_scanner

from phase5.production_quality_assessment import (
    QualityAssessmentResult,
    QualityGateConfig,
    assess_document_quality,
)

# ---------------------------------------------------------------------------
# Import Phase 6 Contracts & Production Implementation
# ---------------------------------------------------------------------------
from phase6.correction_contracts import (
    AppliedCorrectionRecord,
    CorrectedDocumentResult,
    CorrectionCandidate,
    CorrectionOperator,
    CorrectionPlanningConfig,
    CorrectionVerificationConfig,
    DefectConditionCategory,
    RecoverabilityClass,
    RejectedCorrectionRecord,
    RollbackEventRecord,
    SafeImageState,
    VerificationVerdict,
)
from phase6.operators.shadow_normalization import (
    ShadowNormalizationConfig,
    ShadowNormalizationOperator,
)
from phase6.operators.contrast_normalization import (
    ContrastNormalizationConfig,
    ContrastNormalizationOperator,
)
from phase6.correction_engine import (
    ProductionCorrectionPlanner,
    ProductionExecutionEngine,
    ProductionOperatorRegistry,
    ProductionVerificationGate,
    execute_intelligent_correction,
)
from phase6.run_phase6_3_engine_validation import run_engine_validation


def run_contrast_validation():
    print("=" * 80)
    print("PHASE 6.5 CONTRAST NORMALIZATION OPERATOR VALIDATION SUITE")
    print("=" * 80)

    all_passed = True
    test_results: List[Tuple[str, bool, str]] = []

    def record_test(test_id: str, name: str, passed: bool, details: str):
        nonlocal all_passed
        if not passed:
            all_passed = False
        status_str = "PASS" if passed else "FAIL"
        print(f"[{status_str}] Test {test_id}: {name:<48} | {details}")
        test_results.append((f"Test {test_id}: {name}", passed, details))

    # =======================================================================
    # TEST A: CLEAN DOCUMENT PASS-THROUGH (answer_sheet_2.png)
    # =======================================================================
    print("\n--- Test A: Clean Document Pass-Through (answer_sheet_2.png) ---")
    p_clean = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
    sc_clean_res = integrate_production_scanner(p_clean)
    assert sc_clean_res is not None, "Failed to rectify answer_sheet_2.png"
    sc_clean = sc_clean_res.scanned_image
    gray_clean = cv2.cvtColor(sc_clean, cv2.COLOR_BGR2GRAY)

    contrast_op = ContrastNormalizationOperator()
    state_a0 = SafeImageState(
        state_id="state_v0_raw",
        version_index=0,
        parent_state_id=None,
        image_gray=gray_clean.copy(),
        image_bgr=sc_clean.copy(),
        raw_rectified_bgr=sc_clean.copy(),
        applied_operator_id=None,
        quality_profile=None,
        verification_evidence=None,
        is_verified_safe=True
    )

    is_app_a, rat_a = contrast_op.estimate_applicability(state_a0)
    res_a = execute_intelligent_correction(sc_clean)

    test_a_pass = (
        not is_app_a and
        res_a.status == "PRISTINE_PASS_THROUGH" and
        len(res_a.applied_corrections) == 0 and
        res_a.final_safe_state.version_index == 0 and
        not res_a.rescan_required
    )
    record_test(
        "A", "Clean Document Pass-Through", test_a_pass,
        f"Applicable={is_app_a}, Status={res_a.status}, Version={res_a.final_safe_state.version_index}, "
        f"AppliedOps={len(res_a.applied_corrections)}"
    )

    # =======================================================================
    # TEST B: LOW-CONTRAST DOCUMENT REMEDIATION & COMMIT
    # =======================================================================
    print("\n--- Test B: Low-Contrast Calibration Document Remediation ---")
    # Construct a calibrated low-contrast document on clean uniform paper
    # Simulates faint 2H pencil or washed-out blue pen writing
    low_contrast_gray = np.clip(115.0 + (gray_clean.astype(np.float32) / 255.0) * (240.0 - 115.0), 0, 255).astype(np.uint8)
    low_contrast_bgr = cv2.cvtColor(low_contrast_gray, cv2.COLOR_GRAY2BGR)

    state_b0 = SafeImageState(
        state_id="state_v0_raw",
        version_index=0,
        parent_state_id=None,
        image_gray=low_contrast_gray.copy(),
        image_bgr=low_contrast_bgr.copy(),
        raw_rectified_bgr=low_contrast_bgr.copy(),
        applied_operator_id=None,
        quality_profile=None,
        verification_evidence=None,
        is_verified_safe=True
    )

    is_app_b, rat_b = contrast_op.estimate_applicability(state_b0)
    res_b = execute_intelligent_correction(low_contrast_bgr)

    test_b_pass = (
        is_app_b and
        res_b.status == "CORRECTED_VERIFIED" and
        len(res_b.applied_corrections) == 1 and
        res_b.applied_corrections[0].operator_id == "CONTRAST_NORMALIZATION" and
        res_b.final_safe_state.version_index == 1 and
        res_b.applied_corrections[0].verification_evidence.verdict == VerificationVerdict.PASS and
        res_b.applied_corrections[0].verification_evidence.stroke_intensity_delta_gain >= 15.0
    )
    b_ev = res_b.applied_corrections[0].verification_evidence if res_b.applied_corrections else None
    gain_b = f"+{b_ev.stroke_intensity_delta_gain:.1f}" if b_ev else "N/A"
    noise_b = f"{b_ev.substrate_noise_delta:+.1f}" if b_ev else "N/A"
    record_test(
        "B", "Low-Contrast Remediation & Commit", test_b_pass,
        f"Applicable={is_app_b}, Status={res_b.status}, Version={res_b.final_safe_state.version_index}, "
        f"ContrastGain={gain_b}, NoiseDelta={noise_b}, Latency={res_b.total_processing_latency_ms:.1f}ms"
    )

    # =======================================================================
    # TEST C: SHADOW + CONTRAST ORDERING DEPENDENCY (answer_sheet_3.jpg)
    # =======================================================================
    print("\n--- Test C: Shadow + Contrast Dependency & Ordering ---")
    p_shadow = os.path.join(ROOT_DIR, "images", "answer_sheet_3.jpg")
    sc_shadow_res = integrate_production_scanner(p_shadow)
    assert sc_shadow_res is not None, "Failed to rectify answer_sheet_3.jpg"
    sc_shadow = sc_shadow_res.scanned_image
    gray_shadow = cv2.cvtColor(sc_shadow, cv2.COLOR_BGR2GRAY)

    engine_c = ProductionExecutionEngine()
    verifier_c = ProductionVerificationGate()
    planner_c = ProductionCorrectionPlanner()
    registry_c = ProductionOperatorRegistry()
    registry_c.register_operator(ShadowNormalizationOperator())
    registry_c.register_operator(ContrastNormalizationOperator())

    state_c0 = SafeImageState(
        state_id="state_v0_raw",
        version_index=0,
        parent_state_id=None,
        image_gray=gray_shadow.copy(),
        image_bgr=sc_shadow.copy(),
        raw_rectified_bgr=sc_shadow.copy(),
        applied_operator_id=None,
        quality_profile=None,
        verification_evidence=None,
        is_verified_safe=True
    )

    # 1. Assert Sequence 1 (Direct contrast on RAW shadowed document) FAILS verification
    cand_contrast_raw = CorrectionCandidate(
        candidate_id="cand_contrast_raw",
        operator_id="CONTRAST_NORMALIZATION",
        condition_category=DefectConditionCategory.LOW_STROKE_CONTRAST,
        recoverability_class=RecoverabilityClass.CONDITIONALLY_RECOVERABLE,
        expected_benefit="Stretch raw contrast",
        risk_category="SUBSTRATE_NOISE_AMPLIFICATION"
    )
    raw_stretched = contrast_op.apply(gray_shadow)
    ev_raw_contrast = verifier_c.verify_candidate(state_c0, raw_stretched, cand_contrast_raw)
    seq1_rejected = (ev_raw_contrast.verdict == VerificationVerdict.FAIL)

    # 2. Assert Planner evaluates shadow normalization FIRST
    qa_c0 = assess_document_quality(sc_shadow, "shadow_doc")
    first_planned = planner_c.plan_next_candidate(state_c0, qa_c0, [], [], registry_c)
    shadow_planned_first = (first_planned is not None and first_planned.operator_id == "SHADOW_NORMALIZATION")

    # 3. Execute shadow normalization to produce SafeState 1
    shadow_op = registry_c.get_operator("SHADOW_NORMALIZATION")
    assert first_planned is not None
    assert shadow_op is not None
    state_c1, rec_shadow = engine_c.execute_and_verify(state_c0, first_planned, shadow_op, verifier_c)
    shadow_accepted = (rec_shadow.verification_evidence.verdict == VerificationVerdict.PASS and state_c1.version_index == 1)

    # 4. Assert Contrast Normalization operates on SafeState 1 (accepted shadow state), NOT raw shadowed state
    cand_contrast_c1 = CorrectionCandidate(
        candidate_id="cand_contrast_c1",
        operator_id="CONTRAST_NORMALIZATION",
        condition_category=DefectConditionCategory.LOW_STROKE_CONTRAST,
        recoverability_class=RecoverabilityClass.CONDITIONALLY_RECOVERABLE,
        expected_benefit="Enhance leveled handwriting contrast",
        risk_category="SUBSTRATE_NOISE_AMPLIFICATION"
    )
    c1_stretched = contrast_op.apply(state_c1.image_gray)
    ev_c1_contrast = verifier_c.verify_candidate(state_c1, c1_stretched, cand_contrast_c1)
    seq3_safe = (
        ev_c1_contrast.verdict == VerificationVerdict.PASS and
        ev_c1_contrast.substrate_noise_delta <= 3.0 and
        ev_c1_contrast.stroke_intensity_delta_gain >= 15.0
    )

    test_c_pass = seq1_rejected and shadow_planned_first and shadow_accepted and seq3_safe
    record_test(
        "C", "Shadow + Contrast Ordering Dependency", test_c_pass,
        f"Seq1RawRejected={seq1_rejected} (Noise={ev_raw_contrast.substrate_noise_delta:+.1f}), "
        f"ShadowFirst={shadow_planned_first}, ShadowAccepted={shadow_accepted}, "
        f"Seq3Safe={seq3_safe} (Noise={ev_c1_contrast.substrate_noise_delta:+.1f}, Gain={ev_c1_contrast.stroke_intensity_delta_gain:+.1f})"
    )

    # =======================================================================
    # TEST D: CONTROLLED CONTRAST REJECTION & AUTOMATIC ROLLBACK
    # =======================================================================
    print("\n--- Test D: Controlled Contrast Rejection & Rollback ---")

    class DestructiveContrastOperator(CorrectionOperator):
        @property
        def operator_id(self) -> str:
            return "DESTRUCTIVE_CONTRAST"
        @property
        def supported_condition(self) -> DefectConditionCategory:
            return DefectConditionCategory.LOW_STROKE_CONTRAST
        @property
        def recoverability_class(self) -> RecoverabilityClass:
            return RecoverabilityClass.CONDITIONALLY_RECOVERABLE
        @property
        def prerequisite_operators(self) -> List[str]:
            return []
        def estimate_applicability(self, current_state, quality_profile):
            return True, "Simulated destructive contrast operator"
        def apply(self, candidate_image, config=None):
            # Aggressive bi-level posterization causing severe threshold ringing & stroke fragmentation
            _, ruined = cv2.threshold(candidate_image, 128, 255, cv2.THRESH_BINARY)
            # Add synthetic substrate noise
            noise = np.random.normal(0, 30.0, candidate_image.shape).astype(np.float32)
            noisy_ruined = np.clip(ruined.astype(np.float32) + noise, 0, 255).astype(np.uint8)
            return noisy_ruined

    cand_d = CorrectionCandidate(
        candidate_id="cand_test_contrast_rejection",
        operator_id="DESTRUCTIVE_CONTRAST",
        condition_category=DefectConditionCategory.LOW_STROKE_CONTRAST,
        recoverability_class=RecoverabilityClass.CONDITIONALLY_RECOVERABLE,
        expected_benefit="Test destructive contrast candidate rejection",
        risk_category="SUBSTRATE_NOISE_AMPLIFICATION"
    )

    initial_gray_d = gray_clean.copy()
    state_d0 = SafeImageState(
        state_id="state_v0_raw",
        version_index=0,
        parent_state_id=None,
        image_gray=initial_gray_d.copy(),
        image_bgr=sc_clean.copy(),
        raw_rectified_bgr=sc_clean.copy(),
        applied_operator_id=None,
        quality_profile=None,
        verification_evidence=None,
        is_verified_safe=True
    )

    returned_state_d, record_d = engine_c.execute_and_verify(
        current_state=state_d0,
        candidate=cand_d,
        operator=DestructiveContrastOperator(),
        verifier=verifier_c
    )

    test_d_pass = (
        isinstance(record_d, RejectedCorrectionRecord) and
        record_d.verification_evidence.verdict == VerificationVerdict.FAIL and
        returned_state_d.version_index == 0 and
        returned_state_d.state_id == "state_v0_raw" and
        np.array_equal(returned_state_d.image_gray, initial_gray_d)
    )
    assert isinstance(record_d, RejectedCorrectionRecord)
    record_test(
        "D", "Controlled Contrast Rejection & Rollback", test_d_pass,
        f"Verdict={record_d.verification_evidence.verdict}, "
        f"RejectionReasons={record_d.rejection_reasons[:1]}, "
        f"StateRetained={returned_state_d.state_id}"
    )

    # =======================================================================
    # TEST E: INSUFFICIENT EVIDENCE PRESERVES SAFE STATE
    # =======================================================================
    print("\n--- Test E: Insufficient Evidence Handling ---")
    # Sparse document canvas: background gradient with zero stroke content (< 40 edge pixels)
    sparse_canvas = np.tile(np.linspace(210, 245, 600, dtype=np.uint8), (800, 1))
    state_e0 = SafeImageState(
        state_id="state_v0_sparse",
        version_index=0,
        parent_state_id=None,
        image_gray=sparse_canvas.copy(),
        image_bgr=None,
        raw_rectified_bgr=cv2.cvtColor(sparse_canvas, cv2.COLOR_GRAY2BGR),
        applied_operator_id=None,
        quality_profile=None,
        verification_evidence=None,
        is_verified_safe=True
    )

    cand_e = CorrectionCandidate(
        candidate_id="cand_test_insufficient_evidence",
        operator_id="CONTRAST_NORMALIZATION",
        condition_category=DefectConditionCategory.LOW_STROKE_CONTRAST,
        recoverability_class=RecoverabilityClass.CONDITIONALLY_RECOVERABLE,
        expected_benefit="Test sparse canvas safety evaluation",
        risk_category="SUBSTRATE_NOISE_AMPLIFICATION"
    )

    returned_state_e, record_e = engine_c.execute_and_verify(
        current_state=state_e0,
        candidate=cand_e,
        operator=contrast_op,
        verifier=verifier_c
    )

    test_e_pass = (
        record_e.verification_evidence.verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE and
        returned_state_e.version_index == 0 and
        returned_state_e.state_id == "state_v0_sparse" and
        np.array_equal(returned_state_e.image_gray, sparse_canvas)
    )
    record_test(
        "E", "Insufficient Evidence Retains Safe State", test_e_pass,
        f"Verdict={record_e.verification_evidence.verdict}, "
        f"Notes={record_e.verification_evidence.evidence_notes[:1]}, "
        f"SafeStateUnchanged={returned_state_e.state_id}"
    )

    # =======================================================================
    # TEST F: RAW BGR PRESERVATION ACROSS COMMITTED REVISIONS
    # =======================================================================
    print("\n--- Test F: Raw BGR Preservation Across Revisions ---")
    raw_match_b = np.array_equal(res_b.preserved_raw_bgr, low_contrast_bgr)
    raw_match_final_state = np.array_equal(res_b.final_safe_state.raw_rectified_bgr, low_contrast_bgr)
    raw_readonly = not res_b.final_safe_state.raw_rectified_bgr.flags.writeable

    test_f_pass = raw_match_b and raw_match_final_state and raw_readonly
    record_test(
        "F", "Raw BGR Preservation & Immutability", test_f_pass,
        f"RawBGR_ResultMatch={raw_match_b}, RawBGR_StateMatch={raw_match_final_state}, "
        f"RawBGR_ReadOnlyLocked={raw_readonly}"
    )

    # =======================================================================
    # TEST G: BUFFER ISOLATION & IMMUTABILITY GUARANTEES
    # =======================================================================
    print("\n--- Test G: Buffer Isolation & Memory Independence ---")
    gray_readonly = not res_b.final_safe_state.image_gray.flags.writeable

    # Verify mutating safe state raises ValueError
    mutation_raised = False
    try:
        res_b.final_safe_state.image_gray[0, 0] = 128
    except ValueError:
        mutation_raised = True

    # Verify operator working buffer does not share memory with safe state
    working_copy = res_b.final_safe_state.image_gray.copy()
    transformed_test = contrast_op.apply(working_copy)
    no_aliasing = not np.shares_memory(transformed_test, res_b.final_safe_state.image_gray)

    test_g_pass = gray_readonly and mutation_raised and no_aliasing
    record_test(
        "G", "Buffer Isolation & Immutability", test_g_pass,
        f"GrayReadOnlyLocked={gray_readonly}, MutationRaisesError={mutation_raised}, "
        f"BufferMemoryIndependent={no_aliasing}"
    )

    # =======================================================================
    # TEST H: OPERATOR DEPLETION & LOOP TERMINATION
    # =======================================================================
    print("\n--- Test H: Operator Depletion & Loop Termination ---")
    reg_h = ProductionOperatorRegistry()
    reg_h.register_operator(DestructiveContrastOperator())

    res_h = execute_intelligent_correction(
        raw_rectified_bgr=sc_clean,
        registry=reg_h
    )

    test_h_pass = (
        res_h.status == "PARTIAL_SAFE_FALLBACK" and
        len(res_h.applied_corrections) == 0 and
        len(res_h.rejected_corrections) == 1 and
        res_h.rejected_corrections[0].operator_id == "DESTRUCTIVE_CONTRAST" and
        res_h.final_safe_state.version_index == 0
    )
    record_test(
        "H", "Operator Depletion & Loop Prevention", test_h_pass,
        f"Status={res_h.status}, Applied={len(res_h.applied_corrections)}, "
        f"Rejected={len(res_h.rejected_corrections)}, Version={res_h.final_safe_state.version_index}"
    )

    # =======================================================================
    # TEST I: EXISTING PHASE 6.3 REGRESSION VALIDATION
    # =======================================================================
    print("\n--- Test I: Existing Phase 6.3 Regression Suite Execution ---")
    p63_start = time.perf_counter()
    p63_passed = run_engine_validation()
    p63_latency = (time.perf_counter() - p63_start) * 1000.0

    test_i_pass = p63_passed
    record_test(
        "I", "Phase 6.3 Complete Regression Suite", test_i_pass,
        f"Phase6.3SuitePassed={p63_passed} (7/7 tests), Latency={p63_latency:.1f}ms"
    )

    # =======================================================================
    # FINAL SUMMARY REPORT
    # =======================================================================
    print("\n" + "=" * 80)
    print("PHASE 6.5 CONTRAST VALIDATION SUMMARY")
    print("=" * 80)
    passed_count = sum(1 for _, p, _ in test_results if p)
    total_count = len(test_results)

    for name, p, details in test_results:
        status_str = "PASS" if p else "FAIL"
        print(f"[{status_str}] {name:<45} | {details}")

    print("-" * 80)
    print(f"FINAL RESULT: {passed_count}/{total_count} TESTS PASSED")
    if all_passed:
        print("ALL PHASE 6.5 CONTRAST NORMALIZATION CRITERIA SATISFIED SUCCESSFULLY!")
    else:
        print("VALIDATION FAILED: One or more test assertions failed.")
    print("=" * 80)

    return all_passed


if __name__ == "__main__":
    success = run_contrast_validation()
    sys.exit(0 if success else 1)
