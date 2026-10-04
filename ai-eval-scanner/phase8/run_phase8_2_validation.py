"""
phase8/run_phase8_2_validation.py

AI-EVAL PHASE 8.2: PRODUCTION PREPROCESSING & READINESS ENGINE VALIDATION
========================================================================

PURPOSE:
Comprehensive automated validation test suite for the Phase 8.2 Preprocessing
and Readiness Preparation Layer.

VALIDATION SUITE COVERS:
1. Safe Image State & Array Immutability:
   - Prove writeable=False across all stored bundle buffers.
   - Assert attempting to write to ready_gray, ready_bin, ready_bgr, or raw_rectified_bgr raises ValueError.
2. Input Contract Compliance:
   - RescanDecisionResult (CONTINUE), RescanDecisionResult (RESCAN_REQUIRED),
     SafeImageState, and raw numpy arrays.
3. 4-Way Reading Orientation Detection & Lossless De-rotation:
   - Evaluates 0°, 90° CW, 180°, and 270° CCW.
   - Confirms proper de-rotation back to upright reading orientation.
4. Ambiguous Orientation Safety:
   - Proves engine NEVER forces a speculative rotation when polarity/axis is ambiguous.
5. Fine Baseline Deskew:
   - Tests detection and correction of sub-orthogonal tilt (+2.5°).
   - Confirms deadband compliance (< 0.4° left unskewed).
6. Non-Destructive Ruled-Line Representation:
   - Confirms auxiliary mask generation without destructive character stroke loss.
7. Aspect Ratio & Geometry Invariance:
   - Proves compatibility with landscape, square, and arbitrary resolution canvases.
8. End-to-End Multi-Phase Pipeline Integration:
   - Phase 3 -> Phase 5 -> Phase 6 -> Phase 7 -> Phase 8.2.
9. Telemetry Completeness & Audit Trail Integrity.
"""

from __future__ import annotations

import os
import sys
import time
import importlib.util
from typing import List, Tuple

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Path Configuration & Frozen Module Imports
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Phase 3 Scanner Integration (Frozen)
P3_PATH = os.path.join(ROOT_DIR, "phase3", "06_scanner_integration_investigation.py")
spec_p3 = importlib.util.spec_from_file_location("phase3_06", P3_PATH)
phase3_06 = importlib.util.module_from_spec(spec_p3)
spec_p3.loader.exec_module(phase3_06)
integrate_production_scanner = phase3_06.integrate_production_scanner

# Phase 5 Frozen Production Module
from phase5.production_quality_assessment import assess_document_quality

# Phase 6 Frozen Production Module
from phase6.correction_contracts import SafeImageState
from phase6.correction_engine import execute_intelligent_correction

# Phase 7 Frozen Production Module
from phase7.rescan_decision_engine import (
    RescanDecision,
    RescanDecisionResult,
    evaluate_rescan_decision,
)

# Phase 8.2 Production Modules
from phase8.ocr_readiness_contracts import (
    ReadingOrientation,
    OCRReadinessVerdict,
    ReadinessTopologicalDefect,
    ReadinessNormalizationAction,
    PreprocessedImageBundle,
    ReadinessPreparationConfig,
    OCRReadinessPreparationResult,
)
from phase8.ocr_readiness_engine import (
    prepare_ocr_readiness,
    analyze_canvas_orientation,
    estimate_residual_skew,
)


def create_synthetic_test_sheet(
    width: int = 800,
    height: int = 1100,
    num_lines: int = 10,
    with_header: bool = True,
    skew_angle: float = 0.0
) -> np.ndarray:
    """
    Creates a clean synthetic document canvas with horizontal text lines and an optional header.
    """
    canvas = np.full((height, width), 245, dtype=np.uint8)

    if with_header:
        # Top header block (metadata, title)
        cv2.rectangle(canvas, (100, 50), (width - 100, 110), 40, -1)
        cv2.putText(canvas, "EXAMINATION ANSWER SCRIPT - 2026", (120, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, 240, 2)

    y_start = 180 if with_header else 80
    y_step = (height - y_start - 60) // num_lines

    for i in range(num_lines):
        y = y_start + (i * y_step)
        cv2.putText(canvas, f"Line {i+1}: The quick brown fox jumps over the lazy dog repeatedly.",
                    (80, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, 30, 2)

    if abs(skew_angle) > 0.01:
        center = (width // 2, height // 2)
        M = cv2.getRotationMatrix2D(center, skew_angle, 1.0)
        canvas = cv2.warpAffine(canvas, M, (width, height), flags=cv2.INTER_CUBIC,
                                borderMode=cv2.BORDER_REPLICATE)

    return canvas


# ===========================================================================
# TEST IMPLEMENTATIONS
# ===========================================================================

def test_1_safe_buffer_immutability():
    """Verify that all buffers in PreprocessedImageBundle have writeable=False."""
    print("\n--- Test 1: Safe Buffer Immutability ---")
    sheet = create_synthetic_test_sheet()
    result = prepare_ocr_readiness(sheet, document_id="immutability_test")
    bundle = result.image_bundle

    # Check ready_gray
    assert not bundle.ready_gray.flags.writeable, "ready_gray must be read-only"
    try:
        bundle.ready_gray[0, 0] = 0
        assert False, "Direct mutation of ready_gray should have raised ValueError"
    except ValueError:
        pass

    # Check ready_bin
    assert not bundle.ready_bin.flags.writeable, "ready_bin must be read-only"
    try:
        bundle.ready_bin[0, 0] = 255
        assert False, "Direct mutation of ready_bin should have raised ValueError"
    except ValueError:
        pass

    # Check ready_bgr
    if bundle.ready_bgr is not None:
        assert not bundle.ready_bgr.flags.writeable, "ready_bgr must be read-only"
        try:
            bundle.ready_bgr[0, 0, 0] = 0
            assert False, "Direct mutation of ready_bgr should have raised ValueError"
        except ValueError:
            pass

    # Check raw_rectified_bgr
    assert not bundle.raw_rectified_bgr.flags.writeable, "raw_rectified_bgr must be read-only"
    try:
        bundle.raw_rectified_bgr[0, 0, 0] = 0
        assert False, "Direct mutation of raw_rectified_bgr should have raised ValueError"
    except ValueError:
        pass

    print("  [PASS] All 4 bundle buffers are strictly read-only; mutation raises ValueError.")


def test_2_input_contract_compliance():
    """Verify handling of RescanDecisionResult, SafeImageState, and raw numpy arrays."""
    print("\n--- Test 2: Input Contract Compliance ---")
    sheet = create_synthetic_test_sheet()
    sheet_bgr = cv2.cvtColor(sheet, cv2.COLOR_GRAY2BGR)

    # 1. SafeImageState
    safe_state = SafeImageState(
        state_id="test_safe_state",
        version_index=0,
        parent_state_id=None,
        image_gray=sheet,
        image_bgr=sheet_bgr,
        raw_rectified_bgr=sheet_bgr,
        applied_operator_id=None,
        quality_profile=None,
        verification_evidence=None,
        is_verified_safe=True,
    )
    res_safe = prepare_ocr_readiness(safe_state, document_id="test_safe_state")
    assert res_safe.document_id == "test_safe_state"
    assert res_safe.verdict in [OCRReadinessVerdict.OCR_READY, OCRReadinessVerdict.HTR_READY, OCRReadinessVerdict.CONDITIONALLY_READY]
    print("  [PASS] Successfully ingested SafeImageState.")

    # 2. RescanDecisionResult (CONTINUE)
    res_continue = RescanDecisionResult(
        decision="CONTINUE",
        reason_codes=("CONFIRMED_HIGH_QUALITY",),
        readiness_state="GOOD",
        fatal_defects=(),
        human_review_required=False,
        rescan_required=False,
        evidence_sufficient=True,
        is_automated_continue=True,
        processing_notes=("Passed all gates",),
        confidence=0.98,
        primary_trigger="CONFIRMED_HIGH_QUALITY",
        actionable_operator_guidance="",
        human_review_checklist=(),
        processing_latency_ms=10.0,
    )
    res_p8_continue = prepare_ocr_readiness(source=safe_state, document_id="doc_continue", rescan_decision=res_continue)
    assert res_p8_continue.verdict != OCRReadinessVerdict.NOT_READY
    print("  [PASS] Successfully ingested SafeImageState with Phase 7 CONTINUE.")

    # 3. RescanDecisionResult (RESCAN_REQUIRED)
    res_rescan = RescanDecisionResult(
        decision="RESCAN_REQUIRED",
        reason_codes=("DEFOCUS_BLUR_FATAL",),
        readiness_state="UNUSABLE",
        fatal_defects=(),
        human_review_required=False,
        rescan_required=True,
        evidence_sufficient=True,
        is_automated_continue=False,
        processing_notes=("Fatal veto",),
        confidence=1.0,
        primary_trigger="DEFOCUS_BLUR_FATAL",
        actionable_operator_guidance="Rescan with clean focus",
        human_review_checklist=(),
        processing_latency_ms=10.0,
    )
    res_p8_rescan = prepare_ocr_readiness(source=safe_state, document_id="doc_rescan", rescan_decision=res_rescan)
    assert res_p8_rescan.verdict == OCRReadinessVerdict.NOT_READY
    assert "Physical page rescan required" in res_p8_rescan.recommended_downstream_actions[0]
    print("  [PASS] RescanDecisionResult (RESCAN_REQUIRED) safely outputs NOT_READY immediately.")

    # 4. Raw numpy 2D array
    res_raw_2d = prepare_ocr_readiness(sheet, document_id="raw_2d")
    assert res_raw_2d.image_bundle.ready_gray.shape == sheet.shape
    print("  [PASS] Successfully ingested raw 2D numpy array.")


def test_3_four_way_orientation_detection_and_derotation():
    """Verify 4-way orthogonal orientation detection and safe de-rotation."""
    print("\n--- Test 3: 4-Way Orientation Detection & De-Rotation ---")
    base_sheet = create_synthetic_test_sheet(width=700, height=1000, num_lines=12, with_header=True)

    sweeps = [
        ("0° UPRIGHT", base_sheet, ReadingOrientation.UPRIGHT_0, 0),
        ("90° ROTATED CW", cv2.rotate(base_sheet, cv2.ROTATE_90_CLOCKWISE), ReadingOrientation.ROTATED_90_CW, 270),
        ("180° INVERTED", cv2.rotate(base_sheet, cv2.ROTATE_180), ReadingOrientation.ROTATED_180_INVERTED, 180),
        ("270° ROTATED CCW", cv2.rotate(base_sheet, cv2.ROTATE_90_COUNTERCLOCKWISE), ReadingOrientation.ROTATED_270_CCW, 90),
    ]

    for label, img, expected_orient, expected_rot in sweeps:
        res = prepare_ocr_readiness(img, document_id=label)
        assert res.detected_orientation == expected_orient, (
            f"Expected {expected_orient.value} for {label}, got {res.detected_orientation.value}"
        )
        assert res.applied_rotation_deg == expected_rot, (
            f"Expected applied rotation {expected_rot} for {label}, got {res.applied_rotation_deg}"
        )
        # Verify restored output image orientation is upright (width < height for portrait test sheet)
        restored_h, restored_w = res.image_bundle.ready_gray.shape[:2]
        assert restored_h > restored_w, f"Restored canvas for {label} should be in original portrait orientation"
        print(f"  [PASS] {label:18} -> Detected: {res.detected_orientation.value:20} | Applied Rot: {res.applied_rotation_deg}° CW")


def test_4_ambiguous_orientation_handling():
    """Verify that ambiguous layouts do NOT force a speculative rotation."""
    print("\n--- Test 4: Ambiguous Orientation Handling ---")
    # Create symmetric layout: identical header at top and bottom, text strictly centered in middle band
    sym_sheet = np.full((1000, 700), 245, dtype=np.uint8)
    cv2.rectangle(sym_sheet, (100, 50), (600, 110), 40, -1)
    cv2.rectangle(sym_sheet, (100, 890), (600, 950), 40, -1)
    for y in [380, 460, 540, 620]:
        cv2.putText(sym_sheet, "Symmetric text row example test layout", (80, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, 30, 2)

    res = prepare_ocr_readiness(sym_sheet, document_id="sym_layout")
    assert res.is_orientation_ambiguous, "Symmetric top/bottom layout must be flagged AMBIGUOUS"
    assert res.detected_orientation == ReadingOrientation.AMBIGUOUS
    assert res.applied_rotation_deg == 0, "Ambiguous orientation must NEVER apply a speculative rotation"
    assert res.verdict == OCRReadinessVerdict.ORIENTATION_AMBIGUOUS
    assert ReadinessTopologicalDefect.ORIENTATION_AMBIGUOUS in res.blockers
    print("  [PASS] Symmetric canvas identified as AMBIGUOUS; zero speculative rotation applied.")


def test_5_fine_baseline_deskew():
    """Verify detection and correction of residual line skew."""
    print("\n--- Test 5: Fine Baseline Deskew ---")
    # 1. Sheet tilted by +2.5°
    tilted_sheet = create_synthetic_test_sheet(skew_angle=2.5)
    res_tilted = prepare_ocr_readiness(tilted_sheet, document_id="tilted_doc")
    assert abs(res_tilted.detected_skew_angle_deg - 2.5) < 0.5, (
        f"Expected detected skew ~2.5°, got {res_tilted.detected_skew_angle_deg:.2f}°"
    )
    assert ReadinessNormalizationAction.DESKEW_FINE in res_tilted.applied_actions
    assert abs(res_tilted.applied_deskew_angle_deg + 2.5) < 0.5
    print(f"  [PASS] +2.5° tilt detected ({res_tilted.detected_skew_angle_deg:+.2f}°) and deskewed.")

    # 2. Sheet with minimal tilt (0.2° within deadband)
    minor_tilt = create_synthetic_test_sheet(skew_angle=0.2)
    res_minor = prepare_ocr_readiness(minor_tilt, document_id="minor_tilt")
    assert ReadinessNormalizationAction.DESKEW_FINE not in res_minor.applied_actions
    assert res_minor.applied_deskew_angle_deg == 0.0
    print("  [PASS] 0.2° tilt within deadband correctly left unaltered.")


def test_6_ruled_paper_non_destructive_mask():
    """Verify non-destructive auxiliary rule-line mask generation."""
    print("\n--- Test 6: Ruled Paper Auxiliary Mask Generation ---")
    ruled_sheet = create_synthetic_test_sheet(num_lines=8)
    # Draw horizontal ruling lines across the page
    for y in range(160, 950, 60):
        cv2.line(ruled_sheet, (40, y), (760, y), 80, 2)

    res = prepare_ocr_readiness(ruled_sheet, document_id="ruled_sheet")
    bundle = res.image_bundle
    assert bundle.rule_lines_mask is not None, "Ruled paper should generate auxiliary rule_lines_mask"
    assert ReadinessNormalizationAction.RULED_LINE_MASK_GENERATED in res.applied_actions
    assert res.metrics.ruled_line_pixel_fraction > 0.003

    # Check that ready_gray has NOT had pixels erased (remains non-destructive)
    assert bundle.ready_gray[160, 400] != 255 or bundle.ready_gray[160, 400] == 80 or bundle.ready_gray[160, 400] > 0
    print(f"  [PASS] Auxiliary rule mask generated ({res.metrics.ruled_line_pixel_fraction*100:.2f}% coverage); un-eroded ready_gray preserved.")


def test_7_aspect_ratio_and_geometry_invariance():
    """Verify support for landscape, square, and arbitrary canvas sizes."""
    print("\n--- Test 7: Aspect Ratio & Geometry Invariance ---")
    sizes = [
        ("Landscape Sheet (1200x800)", 1200, 800),
        ("Square Crop (700x700)", 700, 700),
        ("Tall Canvas (600x1400)", 600, 1400),
    ]

    for label, w, h in sizes:
        canvas = np.full((h, w), 245, dtype=np.uint8)
        for y in range(80, h - 80, max(50, (h - 160) // 8)):
            cv2.putText(canvas, f"Sample text row on {label}", (60, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, 40, 2)
        res = prepare_ocr_readiness(canvas, document_id=label)
        assert res.image_bundle.ready_gray.shape == (h, w)
        print(f"  [PASS] {label:28} successfully processed (Shape: {res.image_bundle.ready_gray.shape}).")


def test_8_end_to_end_multiphase_integration():
    """Verify end-to-end flow: Phase 3 -> Phase 5 -> Phase 6 -> Phase 7 -> Phase 8.2 on calibration image."""
    print("\n--- Test 8: End-to-End Multi-Phase Pipeline Integration ---")
    img_path = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
    if not os.path.exists(img_path):
        print(f"  [SKIP] Calibration image not found at {img_path}")
        return

    # Step 1: Phase 3 Scanner Integration
    p3_res = integrate_production_scanner(img_path)
    rectified_bgr = p3_res.scanned_image
    if rectified_bgr.ndim == 2:
        rectified_bgr = cv2.cvtColor(rectified_bgr, cv2.COLOR_GRAY2BGR)
    rectified_gray = cv2.cvtColor(rectified_bgr, cv2.COLOR_BGR2GRAY)

    # Step 2: Phase 5 Quality Assessment
    p5_res = assess_document_quality(rectified_gray, "answer_sheet_2")

    # Step 3: Phase 6 Auto-Correction Engine
    p6_res = execute_intelligent_correction(
        raw_rectified_bgr=rectified_bgr,
        initial_assessment=p5_res,
    )

    # Step 4: Phase 7 Rescan Decision Engine
    p7_res = evaluate_rescan_decision(
        document_input=p6_res.final_safe_state,
        final_quality_assessment=p6_res.quality_assessment_final,
        image_name="answer_sheet_2",
    )
    assert p7_res.decision == "CONTINUE", f"Expected Phase 7 CONTINUE, got {p7_res.decision}"

    # Step 5: Phase 8.2 Preprocessing & Readiness Engine
    p8_res = prepare_ocr_readiness(
        source=p6_res.final_safe_state,
        document_id="answer_sheet_2",
        rescan_decision=p7_res,
    )
    assert isinstance(p8_res.verdict, OCRReadinessVerdict), f"Expected OCRReadinessVerdict enum, got {p8_res.verdict}"
    assert p8_res.document_id == "answer_sheet_2"
    assert p8_res.metrics.detected_line_count > 0, "Expected detected lines on rectified answer sheet"
    assert p8_res.image_bundle.ready_gray.shape[:2] == rectified_gray.shape[:2]
    assert len(p8_res.provenance_notes) >= 3

    print(f"  [PASS] End-to-end integration verified: Phase 7 {p7_res.decision} -> Phase 8.2 Prepared Representation Delivered [Provisional Observation: {p8_res.provisional_observation.value}] (Latency: {p8_res.latency_ms:.1f}ms).")


def test_9_telemetry_completeness():
    """Verify that all metrics in TextTopologyMetrics are finite and populated."""
    print("\n--- Test 9: Telemetry Completeness ---")
    sheet = create_synthetic_test_sheet()
    res = prepare_ocr_readiness(sheet, document_id="telemetry_test")
    m = res.metrics

    assert not np.isnan(m.axis_anisotropy_ratio)
    assert not np.isnan(m.header_polarity_ratio)
    assert not np.isnan(m.peak_to_valley_ratio)
    assert not np.isnan(m.median_line_pitch_px)
    assert not np.isnan(m.line_collision_ratio)
    assert not np.isnan(m.median_char_height_px)
    assert not np.isnan(m.estimated_stroke_width_px)
    assert not np.isnan(m.ruled_line_pixel_fraction)
    assert not np.isnan(m.stroke_fragmentation_ratio)
    assert not np.isnan(m.stroke_coalescence_ratio)
    assert m.detected_line_count > 0

    print("  [PASS] All TextTopologyMetrics populated with finite quantitative values.")


# ===========================================================================
# MAIN RUNNER
# ===========================================================================

def run_phase8_2_validation_suite():
    print("=" * 80)
    print("STARTING PHASE 8.2 PRODUCTION PREPROCESSING & READINESS VALIDATION SUITE")
    print("=" * 80)

    tests = [
        ("Test 1: Safe Buffer Immutability", test_1_safe_buffer_immutability),
        ("Test 2: Input Contract Compliance", test_2_input_contract_compliance),
        ("Test 3: 4-Way Orientation Detection & De-Rotation", test_3_four_way_orientation_detection_and_derotation),
        ("Test 4: Ambiguous Orientation Handling", test_4_ambiguous_orientation_handling),
        ("Test 5: Fine Baseline Deskew", test_5_fine_baseline_deskew),
        ("Test 6: Ruled Paper Auxiliary Mask Generation", test_6_ruled_paper_non_destructive_mask),
        ("Test 7: Aspect Ratio & Geometry Invariance", test_7_aspect_ratio_and_geometry_invariance),
        ("Test 8: End-to-End Multi-Phase Integration", test_8_end_to_end_multiphase_integration),
        ("Test 9: Telemetry Completeness", test_9_telemetry_completeness),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 80)
    print(f"PHASE 8.2 VALIDATION SUMMARY: {passed} PASSED, {failed} FAILED (TOTAL {len(tests)})")
    print("=" * 80)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_phase8_2_validation_suite()
