"""
phase6/run_phase6_3_engine_validation.py

AI-EVAL PHASE 6.3: PRODUCTION CORRECTION ENGINE VALIDATION SUITE
================================================================

PURPOSE:
Comprehensive validation of the Phase 6.3 production correction engine,
safe-state lifecycle, dynamic planner, verification gate, and rollback mechanism.

TEST SUITE COVERAGE:
- Test A: Clean document -> Shadow operator NOT_APPLICABLE -> PRISTINE_PASS_THROUGH
- Test B: Known shadow case -> Shadow operator APPLICABLE -> Verification PASS -> SafeState v1 committed
- Test C: Candidate rejection -> Artificial destructive operator -> Verification FAIL -> Rollback to SafeState v0
- Test D: Insufficient evidence -> Inconclusive sparse stroke case -> Verification INSUFFICIENT_EVIDENCE -> SafeState v0 retained
- Test E: Fatal quality state -> Phase 5 fatal defect -> Immediate halt, rescan_required=True, 0 ops executed
- Test F: Raw BGR preservation & State Immutability -> Verify raw BGR unchanged, no memory aliasing
- Test G: Operator depletion -> Verify planner does not loop on rejected operator
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
# Import Frozen Phase 3 & Phase 5 Modules (Read-Only)
# ---------------------------------------------------------------------------
P3_PATH = os.path.join(ROOT_DIR, "phase3", "06_scanner_integration_investigation.py")
spec_p3 = importlib.util.spec_from_file_location("phase3_06", P3_PATH)
if spec_p3 is None or spec_p3.loader is None:
    raise ImportError(f"Cannot load frozen phase3_06 module from {P3_PATH}")
phase3_06 = importlib.util.module_from_spec(spec_p3)
spec_p3.loader.exec_module(phase3_06)
integrate_production_scanner = phase3_06.integrate_production_scanner

from phase5.production_quality_assessment import (
    QualityAssessmentResult,
    QualityGateConfig,
    assess_document_quality,
)

# ---------------------------------------------------------------------------
# Import Phase 6 Production Implementation
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
from phase6.correction_engine import (
    ProductionCorrectionPlanner,
    ProductionExecutionEngine,
    ProductionOperatorRegistry,
    ProductionVerificationGate,
    execute_intelligent_correction,
)


def run_engine_validation():
    print("=" * 80)
    print("PHASE 6.3 PRODUCTION CORRECTION ENGINE VALIDATION SUITE")
    print("=" * 80)

    all_passed = True
    test_results: List[Tuple[str, bool, str]] = []

    def record_test(test_id: str, name: str, passed: bool, details: str):
        nonlocal all_passed
        if not passed:
            all_passed = False
        status_str = "PASS" if passed else "FAIL"
        print(f"[{status_str}] Test {test_id}: {name:<45} | {details}")
        test_results.append((f"Test {test_id}: {name}", passed, details))

    # =======================================================================
    # TEST A: CLEAN DOCUMENT AVOIDS UNNECESSARY CORRECTION
    # =======================================================================
    print("\n--- Test A: Clean Document (answer_sheet_2.png) ---")
    p_clean = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
    sc_clean_res = integrate_production_scanner(p_clean)
    assert sc_clean_res is not None, "Failed to rectify answer_sheet_2.png"
    sc_clean = sc_clean_res.scanned_image

    res_a = execute_intelligent_correction(sc_clean)
    test_a_pass = (
        res_a.status == "PRISTINE_PASS_THROUGH" and
        len(res_a.applied_corrections) == 0 and
        len(res_a.rejected_corrections) == 0 and
        res_a.final_safe_state.version_index == 0 and
        not res_a.rescan_required
    )
    record_test(
        "A", "Clean Document Pass-Through", test_a_pass,
        f"Status={res_a.status}, Version={res_a.final_safe_state.version_index}, "
        f"AppliedOps={len(res_a.applied_corrections)}, Latency={res_a.total_processing_latency_ms:.1f}ms"
    )

    # =======================================================================
    # TEST B: KNOWN SHADOW CASE REMEDIATION & VERIFIED COMMIT
    # =======================================================================
    print("\n--- Test B: Shadowed Calibration Document (answer_sheet_3.jpg) ---")
    p_shadow = os.path.join(ROOT_DIR, "images", "answer_sheet_3.jpg")
    sc_shadow_res = integrate_production_scanner(p_shadow)
    assert sc_shadow_res is not None, "Failed to rectify answer_sheet_3.jpg"
    sc_shadow = sc_shadow_res.scanned_image

    res_b = execute_intelligent_correction(sc_shadow)
    test_b_pass = (
        res_b.status == "CORRECTED_VERIFIED" and
        len(res_b.applied_corrections) == 1 and
        res_b.applied_corrections[0].operator_id == "SHADOW_NORMALIZATION" and
        res_b.final_safe_state.version_index == 1 and
        res_b.final_safe_state.parent_state_id == "state_v0_raw" and
        res_b.applied_corrections[0].verification_evidence.verdict == VerificationVerdict.PASS
    )
    v_ev = res_b.applied_corrections[0].verification_evidence if res_b.applied_corrections else None
    survival_str = f"{v_ev.thin_stroke_survival_ratio*100:.1f}%" if v_ev else "N/A"
    halo_str = f"+{v_ev.halo_overshoot_gain:.1f}" if v_ev else "N/A"
    record_test(
        "B", "Shadow Remediation & Commit", test_b_pass,
        f"Status={res_b.status}, Version={res_b.final_safe_state.version_index}, "
        f"ThinStrokeSurvival={survival_str}, HaloGain={halo_str}, "
        f"Latency={res_b.total_processing_latency_ms:.1f}ms"
    )

    # =======================================================================
    # TEST C: CANDIDATE REJECTION & AUTOMATIC ROLLBACK
    # =======================================================================
    print("\n--- Test C: Controlled Candidate Rejection & Rollback ---")

    # Define an artificial destructive operator that severely erodes thin strokes
    class DestructiveErosionOperator(CorrectionOperator):
        @property
        def operator_id(self) -> str:
            return "DESTRUCTIVE_EROSION"
        @property
        def supported_condition(self) -> DefectConditionCategory:
            return DefectConditionCategory.ILLUMINATION_SHADOW
        @property
        def recoverability_class(self) -> RecoverabilityClass:
            return RecoverabilityClass.CONDITIONALLY_RECOVERABLE
        @property
        def prerequisite_operators(self) -> List[str]:
            return []
        def estimate_applicability(self, current_state, quality_profile):
            return True, "Simulated destructive operator"
        def apply(self, candidate_image, config=None):
            # Aggressive thresholding that deletes thin strokes
            eroded = cv2.erode(candidate_image, np.ones((7, 7), np.uint8))
            return eroded

    reg_c = ProductionOperatorRegistry()
    reg_c.register_operator(DestructiveErosionOperator())

    # Create initial SafeImageState
    initial_gray_c = cv2.cvtColor(sc_clean, cv2.COLOR_BGR2GRAY)
    state_c0 = SafeImageState(
        state_id="state_v0_raw",
        version_index=0,
        parent_state_id=None,
        image_gray=initial_gray_c.copy(),
        image_bgr=sc_clean.copy(),
        raw_rectified_bgr=sc_clean.copy(),
        applied_operator_id=None,
        quality_profile=None,
        verification_evidence=None,
        is_verified_safe=True
    )

    cand_c = CorrectionCandidate(
        candidate_id="cand_test_rejection",
        operator_id="DESTRUCTIVE_EROSION",
        condition_category=DefectConditionCategory.ILLUMINATION_SHADOW,
        recoverability_class=RecoverabilityClass.CONDITIONALLY_RECOVERABLE,
        expected_benefit="Test candidate rejection",
        risk_category="STROKE_LOSS"
    )

    engine_c = ProductionExecutionEngine()
    verifier_c = ProductionVerificationGate()
    returned_state_c, record_c = engine_c.execute_and_verify(
        current_state=state_c0,
        candidate=cand_c,
        operator=DestructiveErosionOperator(),
        verifier=verifier_c
    )

    assert isinstance(record_c, RejectedCorrectionRecord)
    test_c_pass = (
        record_c.verification_evidence.verdict == VerificationVerdict.FAIL and
        returned_state_c.version_index == 0 and
        returned_state_c.state_id == "state_v0_raw" and
        np.array_equal(returned_state_c.image_gray, initial_gray_c)
    )
    record_test(
        "C", "Candidate Rejection & Rollback", test_c_pass,
        f"Verdict={record_c.verification_evidence.verdict}, "
        f"RejectionReasons={record_c.rejection_reasons[:1]}, "
        f"StateRetained={returned_state_c.state_id}"
    )

    # =======================================================================
    # TEST D: INSUFFICIENT EVIDENCE PRESERVES SAFE STATE
    # =======================================================================
    print("\n--- Test D: Insufficient Evidence Handling ---")
    # Blank canvas with almost zero stroke edges
    blank_canvas = np.full((800, 600), 240, dtype=np.uint8)
    state_d0 = SafeImageState(
        state_id="state_v0_blank",
        version_index=0,
        parent_state_id=None,
        image_gray=blank_canvas.copy(),
        image_bgr=None,
        raw_rectified_bgr=cv2.cvtColor(blank_canvas, cv2.COLOR_GRAY2BGR),
        applied_operator_id=None,
        quality_profile=None,
        verification_evidence=None,
        is_verified_safe=True
    )

    cand_d = CorrectionCandidate(
        candidate_id="cand_test_sparse",
        operator_id="SHADOW_NORMALIZATION",
        condition_category=DefectConditionCategory.ILLUMINATION_SHADOW,
        recoverability_class=RecoverabilityClass.RECOVERABLE
    )

    returned_state_d, record_d = engine_c.execute_and_verify(
        current_state=state_d0,
        candidate=cand_d,
        operator=ShadowNormalizationOperator(),
        verifier=verifier_c
    )

    test_d_pass = (
        isinstance(record_d, RejectedCorrectionRecord) and
        record_d.verification_evidence.verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE and
        returned_state_d.version_index == 0 and
        returned_state_d.state_id == "state_v0_blank" and
        np.array_equal(returned_state_d.image_gray, blank_canvas)
    )
    record_test(
        "D", "Insufficient Evidence Retains Safe State", test_d_pass,
        f"Verdict={record_d.verification_evidence.verdict}, "
        f"Notes={record_d.verification_evidence.evidence_notes[:1]}, "
        f"SafeStateUnchanged={returned_state_d.state_id}"
    )

    # =======================================================================
    # TEST E: FATAL QUALITY DEFECT VETOES ALL CORRECTIONS
    # =======================================================================
    print("\n--- Test E: Fatal Quality Defect Veto (answer_sheet_4.jpg) ---")
    p_fatal = os.path.join(ROOT_DIR, "images", "answer_sheet_4.jpg")
    sc_fatal_res = integrate_production_scanner(p_fatal)
    assert sc_fatal_res is not None, "Failed to rectify answer_sheet_4.jpg"
    sc_fatal = sc_fatal_res.scanned_image

    res_e = execute_intelligent_correction(sc_fatal)
    test_e_pass = (
        res_e.status == "UNRECOVERABLE_FATAL" and
        res_e.rescan_required is True and
        len(res_e.applied_corrections) == 0 and
        res_e.final_safe_state.version_index == 0 and
        len(res_e.quality_assessment_initial.fatal_defects) > 0
    )
    fatal_codes = [f.defect_code for f in res_e.quality_assessment_initial.fatal_defects]
    record_test(
        "E", "Fatal Defect Interception", test_e_pass,
        f"Status={res_e.status}, RescanRequired={res_e.rescan_required}, "
        f"FatalDefects={fatal_codes}, OpsExecuted={len(res_e.applied_corrections)}"
    )

    # =======================================================================
    # TEST F: RAW BGR PRESERVATION & STATE BUFFER IMMUTABILITY
    # =======================================================================
    print("\n--- Test F: Raw BGR Preservation & Buffer Immutability ---")
    # Verify that raw BGR matches original rectified BGR identically in accepted case
    bgr_accepted_intact = np.array_equal(res_b.preserved_raw_bgr, sc_shadow)
    bgr_clean_intact = np.array_equal(res_a.preserved_raw_bgr, sc_clean)

    test_state = res_b.final_safe_state

    # 1. Direct Mutation Test: Verify that SafeImageState arrays are hardware read-only
    gray_mutation_prevented = False
    try:
        test_state.image_gray[0, 0] = 123
    except ValueError as e:
        if "read-only" in str(e).lower():
            gray_mutation_prevented = True

    bgr_mutation_prevented = False
    try:
        test_state.raw_rectified_bgr[0, 0, 0] = 123
    except ValueError as e:
        if "read-only" in str(e).lower():
            bgr_mutation_prevented = True

    # 2. Working copy independence: Verify that copies are independently writable
    independent_copy = test_state.image_gray.copy()
    assert independent_copy.flags.writeable is True, "Copy should be writable"
    assert not np.shares_memory(independent_copy, test_state.image_gray), "Memory aliasing detected"

    independent_copy[0, 0] = 0 if test_state.image_gray[0, 0] != 0 else 255
    no_accidental_mutation = (test_state.image_gray[0, 0] != independent_copy[0, 0])

    test_f_pass = (
        bgr_accepted_intact and
        bgr_clean_intact and
        gray_mutation_prevented and
        bgr_mutation_prevented and
        no_accidental_mutation
    )
    record_test(
        "F", "Raw BGR Preservation & Buffer Immutability", test_f_pass,
        f"RawBGR_AcceptedMatch={bgr_accepted_intact}, "
        f"GrayReadOnlyLocked={gray_mutation_prevented}, "
        f"RawBGRReadOnlyLocked={bgr_mutation_prevented}, "
        f"BufferMemoryIndependent={no_accidental_mutation}"
    )

    # =======================================================================
    # TEST G: OPERATOR DEPLETION & LOOP TERMINATION
    # =======================================================================
    print("\n--- Test G: Operator Depletion & Loop Prevention ---")
    # Run pipeline with the rejected operator registered
    reg_g = ProductionOperatorRegistry()
    reg_g.register_operator(DestructiveErosionOperator())

    pln_g = ProductionCorrectionPlanner()
    eng_g = ProductionExecutionEngine()
    vrf_g = ProductionVerificationGate()

    res_g = execute_intelligent_correction(
        raw_rectified_bgr=sc_clean,
        registry=reg_g,
        planner=pln_g,
        engine=eng_g,
        verifier=vrf_g
    )

    # Operator was attempted once, rejected, marked depleted, and planner terminated cleanly
    test_g_pass = (
        len(res_g.applied_corrections) == 0 and
        len(res_g.rejected_corrections) == 1 and
        res_g.rejected_corrections[0].operator_id == "DESTRUCTIVE_EROSION" and
        res_g.status == "PARTIAL_SAFE_FALLBACK" and
        res_g.final_safe_state.version_index == 0
    )
    record_test(
        "G", "Operator Depletion & Loop Termination", test_g_pass,
        f"Status={res_g.status}, Applied={len(res_g.applied_corrections)}, "
        f"Rejected={len(res_g.rejected_corrections)}, Version={res_g.final_safe_state.version_index}"
    )

    # =======================================================================
    # SUMMARY REPORT
    # =======================================================================
    print("\n" + "=" * 80)
    print("PHASE 6.3 ENGINE VALIDATION SUMMARY")
    print("=" * 80)
    passed_count = sum(1 for _, p, _ in test_results if p)
    total_count = len(test_results)
    for name, p, det in test_results:
        s = "PASS" if p else "FAIL"
        print(f"[{s}] {name:<45} | {det}")

    print("-" * 80)
    print(f"FINAL RESULT: {passed_count}/{total_count} TESTS PASSED")
    if all_passed:
        print("ALL PHASE 6.3 PRODUCTION ENGINE CRITERIA SATISFIED SUCCESSFULLY!")
    else:
        print("WARNING: ONE OR MORE VALIDATION TESTS FAILED.")
    print("=" * 80)

    return all_passed


if __name__ == "__main__":
    success = run_engine_validation()
    sys.exit(0 if success else 1)
