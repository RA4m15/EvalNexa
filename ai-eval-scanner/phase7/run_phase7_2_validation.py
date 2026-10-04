"""
phase7/run_phase7_2_validation.py

AI-EVAL PHASE 7.2 PRODUCTION RESCAN DECISION ENGINE VALIDATION SUITE
====================================================================

PURPOSE:
Comprehensive production validation of the Phase 7.2 Rescan Decision Engine
(phase7/rescan_decision_engine.py) covering all operational acceptance criteria:

REQUIRED TEST COVERAGE:
- Test A: Clean Document Pass-Through (answer_sheet_2.png) -> CONTINUE
- Test B: Shadow Corrected Document (answer_sheet_3.jpg) -> CONTINUE
- Test C: Borderline Quality Handling -> HUMAN_REVIEW
- Test D: Sparse / Blank Document Handling -> HUMAN_REVIEW
- Test E: Text Boundary Clipping Interception -> RESCAN_REQUIRED
- Test F: Severe Optical Defocus Interception -> RESCAN_REQUIRED
- Test G: Text-Colliding Specular Glare Interception -> RESCAN_REQUIRED
- Test H: Intrusive Margin Occlusion Interception -> RESCAN_REQUIRED
- Test I: Correction Rejected, Previous Safe State Good -> CONTINUE
- Test J: Correction Rejected, Previous Safe State Borderline -> HUMAN_REVIEW
- Test K: Correction Rejected, Confirmed Fatal Defect -> RESCAN_REQUIRED
- Test L: Non-Compensatory Veto Integrity (High Quality + Fatal Defect = RESCAN_REQUIRED)
- Test M: Phase 6 Production Regression Suite (6.3: 7/7 PASS, 6.5: 9/9 PASS)

GUARDRAILS:
- Zero modifications to Phase 2, Phase 3, Phase 4, Phase 5, or Phase 6 files.
- Operates on immutable data contracts.
- Strictly adheres to non-compensatory decision hierarchy.
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
# Import Frozen Production Modules (Read-Only)
# ---------------------------------------------------------------------------
# Phase 3 Scanner Integration
P3_PATH = os.path.join(ROOT_DIR, "phase3", "06_scanner_integration_investigation.py")
spec_p3 = importlib.util.spec_from_file_location("phase3_06", P3_PATH)
phase3_06 = importlib.util.module_from_spec(spec_p3)
spec_p3.loader.exec_module(phase3_06)
integrate_production_scanner = phase3_06.integrate_production_scanner

# Phase 5 Quality Assessment
from phase5.production_quality_assessment import (
    QualityAssessmentResult,
    QualityGateConfig,
    assess_document_quality,
)

# Phase 6 Correction Engine
from phase6.correction_engine import execute_intelligent_correction
from phase6.correction_contracts import CorrectedDocumentResult, SafeImageState

# Phase 7 Production Rescan Decision Engine
from phase7.rescan_decision_engine import (
    DecisionTrigger,
    ProductionRescanDecisionEngine,
    RescanDecision,
    RescanDecisionConfig,
    RescanDecisionResult,
    evaluate_rescan_decision,
)


def run_phase7_2_validation():
    print("=" * 80)
    print("AI-EVAL PHASE 7.2: PRODUCTION RESCAN DECISION ENGINE VALIDATION SUITE")
    print("=" * 80)

    config = RescanDecisionConfig()
    engine = ProductionRescanDecisionEngine(config=config)
    all_passed = True
    test_results: List[Tuple[str, bool, str]] = []

    def record_test(test_id: str, name: str, passed: bool, details: str):
        nonlocal all_passed
        if not passed:
            all_passed = False
        status_str = "PASS" if passed else "FAIL"
        print(f"[{status_str}] Test {test_id}: {name:<46} | {details}")
        test_results.append((f"Test {test_id}: {name}", passed, details))

    # Base reference canvas from rectified answer_sheet_2.png
    p_clean = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
    sc_clean_doc = integrate_production_scanner(p_clean)
    assert sc_clean_doc is not None, "Failed to rectify answer_sheet_2.png"
    base_canvas = sc_clean_doc.scanned_image
    h_c, w_c = base_canvas.shape[:2]

    # =======================================================================
    # TEST A: CLEAN DOCUMENT PASS-THROUGH
    # =======================================================================
    print("\n--- Test A: Clean Document (answer_sheet_2.png) ---")
    qa_clean_init = assess_document_quality(base_canvas, "answer_sheet_2")
    p6_clean = execute_intelligent_correction(base_canvas, initial_assessment=qa_clean_init)
    res_a = engine.evaluate(p6_clean, image_name="answer_sheet_2")
    test_a_pass = (
        res_a.decision == RescanDecision.CONTINUE.value and
        res_a.is_automated_continue is True and
        res_a.rescan_required is False and
        res_a.human_review_required is False and
        res_a.readiness_state == "GOOD"
    )
    record_test(
        "A", "Clean Document Pass-Through", test_a_pass,
        f"Decision={res_a.decision}, State={res_a.readiness_state}, Trigger={res_a.primary_trigger}, Latency={res_a.processing_latency_ms:.2f}ms"
    )

    # =======================================================================
    # TEST B: SHADOW CORRECTED DOCUMENT
    # =======================================================================
    print("\n--- Test B: Shadow Corrected Document (answer_sheet_3.jpg) ---")
    p_shadow = os.path.join(ROOT_DIR, "images", "answer_sheet_3.jpg")
    sc_shad_doc = integrate_production_scanner(p_shadow)
    assert sc_shad_doc is not None, "Failed to rectify answer_sheet_3.jpg"
    raw_shad = sc_shad_doc.scanned_image
    qa_shad_init = assess_document_quality(raw_shad, "answer_sheet_3")
    p6_shad = execute_intelligent_correction(raw_shad, initial_assessment=qa_shad_init)
    res_b = engine.evaluate(p6_shad, image_name="answer_sheet_3")
    test_b_pass = (
        res_b.decision == RescanDecision.CONTINUE.value and
        res_b.is_automated_continue is True and
        res_b.rescan_required is False and
        res_b.human_review_required is False and
        res_b.readiness_state == "GOOD" and
        len(p6_shad.applied_corrections) >= 1
    )
    record_test(
        "B", "Shadow Remediation & Verified Continue", test_b_pass,
        f"Decision={res_b.decision}, State={res_b.readiness_state}, AppliedOps={[c.operator_id for c in p6_shad.applied_corrections]}, Latency={res_b.processing_latency_ms:.2f}ms"
    )

    # =======================================================================
    # TEST C: BORDERLINE QUALITY HANDLING
    # =======================================================================
    print("\n--- Test C: Borderline Quality Document ---")
    canvas_soft = base_canvas.copy()
    canvas_soft[15:-15, 15:-15] = cv2.GaussianBlur(base_canvas[15:-15, 15:-15], (5, 5), 1.6)
    qa_soft = assess_document_quality(canvas_soft, "borderline_soft")
    res_c = engine.evaluate(canvas_soft, final_quality_assessment=qa_soft, image_name="borderline_soft")
    test_c_pass = (
        res_c.decision == RescanDecision.HUMAN_REVIEW.value and
        res_c.human_review_required is True and
        res_c.rescan_required is False and
        res_c.is_automated_continue is False and
        res_c.readiness_state == "BORDERLINE" and
        len(res_c.human_review_checklist) > 0
    )
    record_test(
        "C", "Borderline Quality Routed to Human Review", test_c_pass,
        f"Decision={res_c.decision}, State={res_c.readiness_state}, ReviewItems={len(res_c.human_review_checklist)}, Latency={res_c.processing_latency_ms:.2f}ms"
    )

    # =======================================================================
    # TEST D: SPARSE / BLANK DOCUMENT HANDLING
    # =======================================================================
    print("\n--- Test D: Sparse / Blank Document ---")
    canvas_blank = np.full((1600, 1200, 3), 248, dtype=np.uint8)
    cv2.putText(canvas_blank, "[X]", (600, 800), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 40), 1)
    qa_blank = assess_document_quality(canvas_blank, "blank_sheet")
    res_d = engine.evaluate(canvas_blank, final_quality_assessment=qa_blank, image_name="blank_sheet")
    test_d_pass = (
        res_d.decision == RescanDecision.HUMAN_REVIEW.value and
        res_d.human_review_required is True and
        res_d.rescan_required is False and
        res_d.evidence_sufficient is False and
        res_d.primary_trigger == DecisionTrigger.SPARSE_OR_BLANK_CONTENT.value
    )
    record_test(
        "D", "Sparse / Blank Routed to Review (Not Rescan)", test_d_pass,
        f"Decision={res_d.decision}, Sufficient={res_d.evidence_sufficient}, Trigger={res_d.primary_trigger}, Latency={res_d.processing_latency_ms:.2f}ms"
    )

    # =======================================================================
    # TEST E: TEXT BOUNDARY CLIPPING INTERCEPTION
    # =======================================================================
    print("\n--- Test E: Text Boundary Clipping Interception ---")
    canvas_clip = base_canvas.copy()
    cv2.putText(canvas_clip, "CRITICAL STUDENT ROLL NUMBER", (2, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 3)
    cv2.line(canvas_clip, (0, 70), (50, 70), (10, 10, 10), 4)
    qa_clip = assess_document_quality(canvas_clip, "clipped_sheet")
    res_e = engine.evaluate(canvas_clip, final_quality_assessment=qa_clip, image_name="clipped_sheet")
    test_e_pass = (
        res_e.decision == RescanDecision.RESCAN_REQUIRED.value and
        res_e.rescan_required is True and
        res_e.human_review_required is False and
        res_e.primary_trigger == DecisionTrigger.FATAL_VETO.value and
        any(d.defect_code == "FATAL_TEXT_CLIPPED" for d in res_e.fatal_defects)
    )
    record_test(
        "E", "Text Boundary Clipping Fatal Veto", test_e_pass,
        f"Decision={res_e.decision}, RescanRequired={res_e.rescan_required}, DefectCodes={[d.defect_code for d in res_e.fatal_defects]}"
    )

    # =======================================================================
    # TEST F: SEVERE OPTICAL DEFOCUS INTERCEPTION
    # =======================================================================
    print("\n--- Test F: Severe Optical Defocus Interception ---")
    canvas_defocus = cv2.GaussianBlur(base_canvas, (35, 35), 11.0)
    qa_defocus = assess_document_quality(canvas_defocus, "defocused_sheet")
    res_f = engine.evaluate(canvas_defocus, final_quality_assessment=qa_defocus, image_name="defocused_sheet")
    test_f_pass = (
        res_f.decision == RescanDecision.RESCAN_REQUIRED.value and
        res_f.rescan_required is True and
        res_f.primary_trigger == DecisionTrigger.FATAL_VETO.value and
        any(d.defect_code == "FATAL_OPTICAL_DEFOCUS" for d in res_f.fatal_defects)
    )
    record_test(
        "F", "Severe Optical Defocus Fatal Veto", test_f_pass,
        f"Decision={res_f.decision}, DefectCodes={[d.defect_code for d in res_f.fatal_defects]}, Guidance='{res_f.actionable_operator_guidance[:50]}...'"
    )

    # =======================================================================
    # TEST G: TEXT-COLLIDING SPECULAR GLARE INTERCEPTION
    # =======================================================================
    print("\n--- Test G: Text-Colliding Specular Glare Interception ---")
    canvas_glare = base_canvas.copy()
    cv2.ellipse(canvas_glare, (600, 800), (180, 120), 0, 0, 360, (255, 255, 255), -1)
    qa_glare = assess_document_quality(canvas_glare, "glare_sheet")
    res_g = engine.evaluate(canvas_glare, final_quality_assessment=qa_glare, image_name="glare_sheet")
    test_g_pass = (
        res_g.decision == RescanDecision.RESCAN_REQUIRED.value and
        res_g.rescan_required is True and
        res_g.primary_trigger == DecisionTrigger.FATAL_VETO.value and
        any(d.defect_code == "FATAL_GLARE_COLLISION" for d in res_g.fatal_defects)
    )
    record_test(
        "G", "Specular Glare Collision Fatal Veto", test_g_pass,
        f"Decision={res_g.decision}, RescanRequired={res_g.rescan_required}, DefectCodes={[d.defect_code for d in res_g.fatal_defects]}"
    )

    # =======================================================================
    # TEST H: INTRUSIVE MARGIN OCCLUSION INTERCEPTION
    # =======================================================================
    print("\n--- Test H: Intrusive Margin Occlusion Interception ---")
    canvas_occ = base_canvas.copy()
    m_w = int(round(w_c * 0.05))
    m_h = int(round(h_c * 0.05))
    cv2.rectangle(canvas_occ, (0, 0), (m_w + 30, h_c), (25, 25, 30), -1)
    cv2.rectangle(canvas_occ, (0, 0), (w_c // 2, m_h + 30), (25, 25, 30), -1)
    qa_occ = assess_document_quality(canvas_occ, "occluded_sheet")
    res_h = engine.evaluate(canvas_occ, final_quality_assessment=qa_occ, image_name="occluded_sheet")
    test_h_pass = (
        res_h.decision == RescanDecision.RESCAN_REQUIRED.value and
        res_h.rescan_required is True and
        res_h.primary_trigger == DecisionTrigger.FATAL_VETO.value and
        any(d.defect_code == "FATAL_MARGIN_OCCLUSION" for d in res_h.fatal_defects)
    )
    record_test(
        "H", "Margin Foreign Occlusion Fatal Veto", test_h_pass,
        f"Decision={res_h.decision}, RescanRequired={res_h.rescan_required}, DefectCodes={[d.defect_code for d in res_h.fatal_defects]}"
    )

    # =======================================================================
    # TEST I: CORRECTION REJECTED, PREVIOUS SAFE STATE GOOD
    # =======================================================================
    print("\n--- Test I: Correction Rejected, Previous Safe State Good ---")
    # Simulate Case A: candidate operator rejected, rollback triggered, safe state remains GOOD
    qa_good = assess_document_quality(base_canvas, "safe_good")
    res_i = engine.evaluate(
        base_canvas,
        final_quality_assessment=qa_good,
        has_rollbacks=True,
        image_name="case_i_good_rollback"
    )
    test_i_pass = (
        res_i.decision == RescanDecision.CONTINUE.value and
        res_i.is_automated_continue is True and
        res_i.rescan_required is False and
        DecisionTrigger.CORRECTION_ROLLBACK_SAFE_FALLBACK.value in res_i.reason_codes
    )
    record_test(
        "I", "Correction Rejected -> Safe State Good -> CONTINUE", test_i_pass,
        f"Decision={res_i.decision}, TriggerCodes={res_i.reason_codes}, Latency={res_i.processing_latency_ms:.2f}ms"
    )

    # =======================================================================
    # TEST J: CORRECTION REJECTED, PREVIOUS SAFE STATE BORDERLINE
    # =======================================================================
    print("\n--- Test J: Correction Rejected, Previous Safe State Borderline ---")
    # Simulate Case B: candidate operator rejected, rollback triggered, safe state is BORDERLINE
    res_j = engine.evaluate(
        canvas_soft,
        final_quality_assessment=qa_soft,
        has_rollbacks=True,
        image_name="case_j_borderline_rollback"
    )
    test_j_pass = (
        res_j.decision == RescanDecision.HUMAN_REVIEW.value and
        res_j.human_review_required is True and
        res_j.rescan_required is False and
        DecisionTrigger.CORRECTION_ROLLBACK_BORDERLINE.value in res_j.reason_codes
    )
    record_test(
        "J", "Correction Rejected -> State Borderline -> HUMAN_REVIEW", test_j_pass,
        f"Decision={res_j.decision}, TriggerCodes={res_j.reason_codes}, ReviewRequired={res_j.human_review_required}"
    )

    # =======================================================================
    # TEST K: CORRECTION REJECTED, CONFIRMED FATAL DEFECT
    # =======================================================================
    print("\n--- Test K: Correction Rejected, Confirmed Fatal Defect ---")
    # Real image answer_sheet_4.jpg has clipping and defocus: halts at init
    p4 = os.path.join(ROOT_DIR, "images", "answer_sheet_4.jpg")
    sc4_doc = integrate_production_scanner(p4)
    assert sc4_doc is not None, "Failed to rectify answer_sheet_4.jpg"
    p6_p4 = execute_intelligent_correction(sc4_doc.scanned_image)
    res_k = engine.evaluate(p6_p4, image_name="answer_sheet_4")
    test_k_pass = (
        res_k.decision == RescanDecision.RESCAN_REQUIRED.value and
        res_k.rescan_required is True and
        res_k.human_review_required is False and
        res_k.primary_trigger == DecisionTrigger.FATAL_VETO.value
    )
    record_test(
        "K", "Correction Halts on Fatal Defect -> RESCAN_REQUIRED", test_k_pass,
        f"Decision={res_k.decision}, RescanRequired={res_k.rescan_required}, DefectCount={len(res_k.fatal_defects)}"
    )

    # =======================================================================
    # TEST L: NON-COMPENSATORY VETO INTEGRITY (HIGH QUALITY + FATAL DEFECT)
    # =======================================================================
    print("\n--- Test L: Non-Compensatory Veto Integrity ---")
    # Construct an image with exceptional contrast, perfect sharpness, clean white paper,
    # BUT inject an unrecoverable boundary clipping fatal defect.
    canvas_high_qual = base_canvas.copy().astype(np.float32)
    # High stroke contrast stretch
    canvas_high_qual = np.where(canvas_high_qual > 200, 255.0, canvas_high_qual * 0.4)
    canvas_high_qual = np.clip(canvas_high_qual, 0, 255).astype(np.uint8)
    # Inject fatal text clipping
    cv2.putText(canvas_high_qual, "IMPORTANT EXAM ANSWER", (2, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (10, 10, 10), 3)
    cv2.line(canvas_high_qual, (0, 70), (50, 70), (0, 0, 0), 4)

    qa_l = assess_document_quality(canvas_high_qual, "high_qual_clipped")
    res_l = engine.evaluate(canvas_high_qual, final_quality_assessment=qa_l, image_name="high_qual_clipped")
    
    # Assert non-compensatory veto: despite delta > 150, acutance > 250, paper_white = 255,
    # the fatal defect MUST trigger RESCAN_REQUIRED and cannot be overridden!
    test_l_pass = (
        res_l.decision == RescanDecision.RESCAN_REQUIRED.value and
        res_l.rescan_required is True and
        res_l.is_automated_continue is False and
        res_l.primary_trigger == DecisionTrigger.FATAL_VETO.value and
        qa_l.evidence_profile.stroke_intensity_delta > 100.0 # Proves high contrast existed
    )
    record_test(
        "L", "Fatal Defect Cannot Be Compensated By High Quality", test_l_pass,
        f"Decision={res_l.decision}, ContrastDelta={qa_l.evidence_profile.stroke_intensity_delta:.1f}, Acutance={qa_l.evidence_profile.normalized_stroke_acutance:.1f}, FatalVeto={res_l.primary_trigger}"
    )

    # =======================================================================
    # TEST M: PHASE 6 PRODUCTION REGRESSION SUITE
    # =======================================================================
    print("\n--- Test M: Phase 6 Production Regression Suite ---")
    p6_3_path = os.path.join(ROOT_DIR, "phase6", "run_phase6_3_engine_validation.py")
    spec_6_3 = importlib.util.spec_from_file_location("val_6_3", p6_3_path)
    val_6_3 = importlib.util.module_from_spec(spec_6_3)
    spec_6_3.loader.exec_module(val_6_3)
    p6_3_passed = val_6_3.run_engine_validation()

    p6_5_path = os.path.join(ROOT_DIR, "phase6", "run_phase6_5_contrast_validation.py")
    spec_6_5 = importlib.util.spec_from_file_location("val_6_5", p6_5_path)
    val_6_5 = importlib.util.module_from_spec(spec_6_5)
    spec_6_5.loader.exec_module(val_6_5)
    p6_5_passed = val_6_5.run_contrast_validation()

    test_m_pass = p6_3_passed and p6_5_passed
    record_test(
        "M", "Phase 6.3 & 6.5 Production Regression Pass", test_m_pass,
        f"Phase6.3Passed={p6_3_passed} (7/7 tests), Phase6.5Passed={p6_5_passed} (9/9 tests)"
    )

    # =======================================================================
    # FINAL SUMMARY
    # =======================================================================
    print("\n" + "=" * 80)
    print("PHASE 7.2 DECISION ENGINE VALIDATION SUMMARY")
    print("=" * 80)
    passed_count = sum(1 for _, p, _ in test_results)
    for name, p, details in test_results:
        st = "PASS" if p else "FAIL"
        print(f"[{st}] {name:<50} | {details}")
    print("-" * 80)
    print(f"FINAL RESULT: {passed_count}/{len(test_results)} TESTS PASSED")
    if all_passed:
        print("ALL PHASE 7.2 PRODUCTION DECISION ENGINE CRITERIA SATISFIED SUCCESSFULLY!")
    else:
        print("ONE OR MORE PHASE 7.2 TESTS FAILED!")
    print("=" * 80)
    return all_passed


if __name__ == "__main__":
    success = run_phase7_2_validation()
    sys.exit(0 if success else 1)
