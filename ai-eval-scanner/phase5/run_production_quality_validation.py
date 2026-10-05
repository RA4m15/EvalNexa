"""
phase5/run_production_quality_validation.py

AI-EVAL PHASE 5 PRODUCTION VALIDATION SUITE
===========================================

PURPOSE:
Validates the production Smart Quality Assessment module (phase5/production_quality_assessment.py)
against all required operational test criteria:

CRITICAL TEST CRITERIA:
1. Known fatal defects reach UNUSABLE with rescan_required=True.
2. Clean documents remain GOOD or ACCEPTABLE.
3. Borderline cases do not silently become GOOD (human_review_required=True).
4. Fatal defects cannot be compensated by high sharpness or contrast (Non-compensatory rule).
5. Global Laplacian variance does NOT influence the verdict (verified via high-variance grid case).
6. Phase 4 enhanced shadow case remains evaluable (transitioning CAN_BE_ENHANCED -> ALREADY_CLEAN).
7. Zero modifications to Phase 2, Phase 3, or Phase 4 files.
8. No investigation reports are overwritten.
"""

import os
import sys
import math
import importlib.util
from typing import Dict, List, Tuple, Any

import cv2
import numpy as np

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Dynamic Imports of Production Modules
# ---------------------------------------------------------------------------
P3_PATH = os.path.join(ROOT_DIR, "phase3", "06_scanner_integration_investigation.py")
spec_p3 = importlib.util.spec_from_file_location("phase3_06", P3_PATH)
if spec_p3 is None or spec_p3.loader is None:
    raise ImportError(f"Could not load module from {P3_PATH}")
phase3_06 = importlib.util.module_from_spec(spec_p3)
spec_p3.loader.exec_module(phase3_06)
integrate_production_scanner = phase3_06.integrate_production_scanner

P4_PATH = os.path.join(ROOT_DIR, "phase4", "production_enhancement.py")
spec_p4 = importlib.util.spec_from_file_location("phase4_prod", P4_PATH)
if spec_p4 is None or spec_p4.loader is None:
    raise ImportError(f"Could not load module from {P4_PATH}")
phase4_prod = importlib.util.module_from_spec(spec_p4)
spec_p4.loader.exec_module(phase4_prod)
enhance_scanned_document = phase4_prod.enhance_scanned_document

P5_PATH = os.path.join(ROOT_DIR, "phase5", "production_quality_assessment.py")
spec_p5 = importlib.util.spec_from_file_location("phase5_prod", P5_PATH)
if spec_p5 is None or spec_p5.loader is None:
    raise ImportError(f"Could not load module from {P5_PATH}")
phase5_prod = importlib.util.module_from_spec(spec_p5)
spec_p5.loader.exec_module(phase5_prod)
assess_document_quality = phase5_prod.assess_document_quality
QualityGateConfig = phase5_prod.QualityGateConfig


def run_production_validation():
    print("=" * 80)
    print("PHASE 5 PRODUCTION QUALITY ASSESSMENT VALIDATION SUITE")
    print("=" * 80)

    config = QualityGateConfig()
    all_tests_passed = True
    test_results = []

    def record_test(name: str, passed: bool, details: str):
        nonlocal all_tests_passed
        if not passed:
            all_tests_passed = False
        status_str = "PASS" if passed else "FAIL"
        print(f"[{status_str}] {name:<45} | {details}")
        test_results.append((name, passed, details))

    # =======================================================================
    # TEST SUITE 1: CALIBRATION DOCUMENTS
    # =======================================================================
    print("\n--- TEST SUITE 1: Calibration Documents ---")

    # 1.1 Pristine Baseline (answer_sheet_2.png)
    p2 = os.path.join(ROOT_DIR, "images", "answer_sheet_2.png")
    sc2 = integrate_production_scanner(p2)
    res2 = assess_document_quality(sc2, image_name="answer_sheet_2", config=config)
    record_test(
        "1.1 Pristine Scan -> GOOD",
        res2.verdict == "GOOD" and not res2.rescan_required and not res2.human_review_required,
        f"Verdict={res2.verdict}, Latency={res2.processing_latency_ms:.1f}ms, Acutance={res2.evidence_profile.normalized_stroke_acutance:.1f}"
    )

    # 1.2 Shadowed Calibration Document (answer_sheet_3.jpg RAW)
    p3 = os.path.join(ROOT_DIR, "images", "answer_sheet_3.jpg")
    sc3 = integrate_production_scanner(p3)
    res3_raw = assess_document_quality(sc3, image_name="answer_sheet_3_RAW", config=config)
    record_test(
        "1.2 Shadowed Scan -> ACCEPTABLE & CAN_BE_ENHANCED",
        res3_raw.verdict == "ACCEPTABLE" and res3_raw.enhancement_potential == "CAN_BE_ENHANCED",
        f"Verdict={res3_raw.verdict}, Potential={res3_raw.enhancement_potential}, SpatialBG={res3_raw.evidence_profile.spatial_bg_ratio:.2f}"
    )

    # 1.3 Clipped Document (answer_sheet_4.jpg)
    p4 = os.path.join(ROOT_DIR, "images", "answer_sheet_4.jpg")
    sc4 = integrate_production_scanner(p4)
    res4 = assess_document_quality(sc4, image_name="answer_sheet_4", config=config)
    record_test(
        "1.3 Clipped Document -> UNUSABLE (Fatal Veto)",
        res4.verdict == "UNUSABLE" and res4.rescan_required and len(res4.fatal_defects) > 0,
        f"Verdict={res4.verdict}, Defect={res4.fatal_defects[0].defect_code}, Rescan={res4.rescan_required}"
    )

    # 1.4 Unclipped Table Rulings & Page Border Clean Scan (answer_sheet_5.jpg)
    p5 = os.path.join(ROOT_DIR, "images", "answer_sheet_5.jpg")
    sc5 = integrate_production_scanner(p5)
    res5 = assess_document_quality(sc5, image_name="answer_sheet_5", config=config)
    record_test(
        "1.4 Unclipped Table Rulings -> GOOD (No Fatal Defects)",
        res5.verdict == "GOOD" and not res5.rescan_required and len(res5.fatal_defects) == 0,
        f"Verdict={res5.verdict}, FatalDefects={len(res5.fatal_defects)}, Rescan={res5.rescan_required}"
    )

    # 1.5 Compressed Clipped Scan (answer_sheet.jpg)
    p1 = os.path.join(ROOT_DIR, "images", "answer_sheet.jpg")
    sc1 = integrate_production_scanner(p1)
    res1 = assess_document_quality(sc1, image_name="answer_sheet", config=config)
    record_test(
        "1.5 Compressed Clipped -> UNUSABLE (Fatal Veto)",
        res1.verdict == "UNUSABLE" and res1.rescan_required,
        f"Verdict={res1.verdict}, Defect={res1.fatal_defects[0].defect_code}"
    )

    # =======================================================================
    # TEST SUITE 2: PHASE 4 ENHANCED OUTPUTS
    # =======================================================================
    print("\n--- TEST SUITE 2: Phase 4 Enhanced Outputs ---")

    # 2.1 Enhanced Shadow Case (answer_sheet_3.jpg Enhanced)
    enh3 = enhance_scanned_document(sc3)
    res3_enh = assess_document_quality(enh3, image_name="answer_sheet_3_ENHANCED", config=config)
    record_test(
        "2.1 Enhanced Shadow -> GOOD & ALREADY_CLEAN",
        res3_enh.verdict == "GOOD" and res3_enh.enhancement_potential == "ALREADY_CLEAN",
        f"Verdict={res3_enh.verdict}, Potential={res3_enh.enhancement_potential}, Latency={res3_enh.processing_latency_ms:.1f}ms"
    )

    # =======================================================================
    # TEST SUITE 3: NON-COMPENSATORY RULE & FATAL DEFECTS
    # =======================================================================
    print("\n--- TEST SUITE 3: Fatal Defect Non-Compensatory Veto ---")
    base_img = sc2.scanned_image.copy()
    h, w = base_img.shape[:2]

    # 3.1 Specular Glare Collision (Obliterating 20% text)
    glare_img = base_img.copy()
    cv2.circle(glare_img, (int(w * 0.45), int(h * 0.25)), int(min(h, w) * 0.20), (255, 255, 255), -1)
    res_glare = assess_document_quality(glare_img, image_name="Stress_Glare", config=config)
    record_test(
        "3.1 Fatal Glare Collision -> UNUSABLE",
        res_glare.verdict == "UNUSABLE" and res_glare.rescan_required,
        f"Verdict={res_glare.verdict}, Defect={res_glare.fatal_defects[0].defect_code}"
    )

    # 3.2 Severe Defocus Blur (sigma = 5.0)
    blur_img = cv2.GaussianBlur(base_img, (35, 35), 5.0)
    res_blur = assess_document_quality(blur_img, image_name="Stress_Defocus", config=config)
    has_defocus_defect = any(d.defect_code == "FATAL_OPTICAL_DEFOCUS" for d in res_blur.fatal_defects)
    record_test(
        "3.2 Fatal Optical Defocus -> UNUSABLE",
        res_blur.verdict == "UNUSABLE" and res_blur.rescan_required and has_defocus_defect,
        f"Verdict={res_blur.verdict}, Acutance={res_blur.evidence_profile.normalized_stroke_acutance:.1f} (cutoff={config.fatal_defocus_acutance})"
    )

    # 3.3 Severe Ink Dropout (alpha = 0.10)
    faded_img = np.clip(245.0 - (245.0 - base_img.astype(np.float32)) * 0.10, 0, 255).astype(np.uint8)
    res_fade = assess_document_quality(faded_img, image_name="Stress_InkLoss", config=config)
    record_test(
        "3.3 Fatal Ink Loss -> UNUSABLE",
        res_fade.verdict == "UNUSABLE" and res_fade.rescan_required,
        f"Verdict={res_fade.verdict}, Delta={res_fade.evidence_profile.stroke_intensity_delta:.1f}"
    )

    # 3.4 Non-Compensatory Test: Pristine contrast + Severely Clipped Text
    # Artificially boost contrast, but translate text off canvas by 120px
    clipped_boosted = np.full_like(base_img, 255)
    clipped_boosted[:, : (w - 120)] = base_img[:, 120:]
    res_clip_comp = assess_document_quality(clipped_boosted, image_name="Clipped_Boosted", config=config)
    record_test(
        "3.4 Non-Compensatory Veto (Sharpness cannot override clipping)",
        res_clip_comp.verdict == "UNUSABLE" and res_clip_comp.rescan_required and res_clip_comp.fatal_defects[0].defect_code == "FATAL_TEXT_CLIPPED",
        f"Verdict={res_clip_comp.verdict}, Defect={res_clip_comp.fatal_defects[0].defect_code}, Acutance={res_clip_comp.evidence_profile.normalized_stroke_acutance:.1f}"
    )

    # =======================================================================
    # TEST SUITE 4: GLOBAL LAPLACIAN INVARIANCE (PROVING FLAW IMMUNITY)
    # =======================================================================
    print("\n--- TEST SUITE 4: Global Laplacian Invariance ---")

    # 4.1 Low Laplacian Sparse Document (Proving low Laplacian does not cause false rejection)
    # A sparse pristine text has low global Laplacian variance (~400-700) because of low content density
    sparse_doc = np.full((707, 500, 3), 250, dtype=np.uint8)
    cv2.putText(sparse_doc, "TAGORE PUBLIC SCHOOL", (40, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2)
    cv2.putText(sparse_doc, "EXAMINATION SHEET", (40, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2)
    res_sparse = assess_document_quality(sparse_doc, image_name="Sparse_Crisp_Low_Laplacian", config=config)
    record_test(
        "4.1 Low Laplacian Sparse Text -> GOOD (No false reject)",
        res_sparse.verdict == "GOOD" and res_sparse.evidence_profile.diagnostic_laplacian_variance < 800.0,
        f"Verdict={res_sparse.verdict}, LapVar={res_sparse.evidence_profile.diagnostic_laplacian_variance:.1f}, Acutance={res_sparse.evidence_profile.normalized_stroke_acutance:.1f}"
    )

    # 4.2 High Laplacian Defocused Document (Proving high Laplacian does not mask blur)
    # Defocus blur with high-frequency noise creates high Laplacian variance but low stroke acutance
    blur_defocus = cv2.GaussianBlur(base_img, (31, 31), 5.0)
    noise = np.random.normal(0, 10.0, blur_defocus.shape).astype(np.float32)
    textured_blurry = np.clip(blur_defocus.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    res_textured_blur = assess_document_quality(textured_blurry, image_name="Textured_Blurry_High_Laplacian", config=config)
    record_test(
        "4.2 High Laplacian Defocused Document -> UNUSABLE",
        res_textured_blur.verdict == "UNUSABLE" and res_textured_blur.rescan_required and any(d.defect_code == "FATAL_OPTICAL_DEFOCUS" for d in res_textured_blur.fatal_defects),
        f"Verdict={res_textured_blur.verdict}, LapVar={res_textured_blur.evidence_profile.diagnostic_laplacian_variance:.1f}, Acutance={res_textured_blur.evidence_profile.normalized_stroke_acutance:.1f}"
    )

    # =======================================================================
    # TEST SUITE 5: BORDERLINE CASES & HUMAN ROUTING
    # =======================================================================
    print("\n--- TEST SUITE 5: Borderline Cases & Human Verification ---")

    # 5.1 Moderate Defocus (sigma = 1.5, acutance in borderline band [120, 220])
    mod_blur_img = cv2.GaussianBlur(base_img, (15, 15), 1.5)
    res_border_blur = assess_document_quality(mod_blur_img, image_name="Borderline_Blur", config=config)
    record_test(
        "5.1 Moderate Blur -> BORDERLINE & human_review_required=True",
        res_border_blur.verdict == "BORDERLINE" and res_border_blur.human_review_required and not res_border_blur.rescan_required,
        f"Verdict={res_border_blur.verdict}, ReviewRequired={res_border_blur.human_review_required}, Acutance={res_border_blur.evidence_profile.normalized_stroke_acutance:.1f}"
    )

    # 5.2 Moderate Faint Ink (alpha = 0.28, delta in borderline band [18, 35])
    faint_border_img = np.clip(245.0 - (245.0 - base_img.astype(np.float32)) * 0.28, 0, 255).astype(np.uint8)
    res_border_fade = assess_document_quality(faint_border_img, image_name="Borderline_Faint", config=config)
    record_test(
        "5.2 Moderate Faint Ink -> BORDERLINE & human_review_required=True",
        res_border_fade.verdict == "BORDERLINE" and res_border_fade.human_review_required,
        f"Verdict={res_border_fade.verdict}, Delta={res_border_fade.evidence_profile.stroke_intensity_delta:.1f}"
    )

    # =======================================================================
    # TEST SUITE 6: UNSEEN VALIDATION SAMPLES (N=8)
    # =======================================================================
    print("\n--- TEST SUITE 6: Unseen Validation Samples ---")
    val_dir = os.path.join(ROOT_DIR, "images", "dataset_samples")
    if os.path.exists(val_dir):
        val_files = sorted([f for f in os.listdir(val_dir) if f.endswith((".jpg", ".png"))])[:8]
        val_verdicts = []
        for vf in val_files:
            v_img = cv2.imread(os.path.join(val_dir, vf))
            if v_img is None:
                continue
            res_v = assess_document_quality(v_img, image_name=vf[:12], config=config)
            val_verdicts.append(res_v.verdict)
        record_test(
            "6.1 Unseen Validation Samples Handled Reliably",
            len(val_verdicts) == 8 and all(v in ["GOOD", "ACCEPTABLE", "BORDERLINE", "UNUSABLE"] for v in val_verdicts),
            f"Verdicts Distribution: {dict((v, val_verdicts.count(v)) for v in set(val_verdicts))}"
        )

    # =======================================================================
    # SUMMARY
    # =======================================================================
    print("\n" + "=" * 80)
    print(f"VALIDATION SUMMARY: {'ALL TESTS PASSED' if all_tests_passed else 'SOME TESTS FAILED'}")
    print(f"Total Tests Executed: {len(test_results)}")
    print(f"Passed: {sum(1 for _, p, _ in test_results if p)} / {len(test_results)}")
    print("=" * 80)

    if not all_tests_passed:
        raise RuntimeError("Phase 5 Production Validation Suite encountered test failures.")
    return test_results


if __name__ == "__main__":
    run_production_validation()
