"""
phase4/run_production_enhancement_validation.py

Executes production validation of Phase 4 Automatic Image Enhancement across:
1. The 5 Calibration Images (Full scanner pipeline integration)
2. The 10 Unseen Validation Images (Diverse handwriting, math, lined paper, faint ink)
"""

import os
import sys
import time
import importlib.util
from typing import Dict, List, Any
import cv2
import numpy as np

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# Import production Phase 3 scanner & Phase 4 enhancement
from phase4.production_enhancement import (
    enhance_scanned_document,
    EnhancedDocumentResult,
    DocumentConditionProfile
)

P3_PATH = os.path.join(ROOT_DIR, "phase3", "06_scanner_integration_investigation.py")
spec_p3 = importlib.util.spec_from_file_location("phase3_06", P3_PATH)
phase3_06 = importlib.util.module_from_spec(spec_p3)
spec_p3.loader.exec_module(phase3_06)
integrate_production_scanner = phase3_06.integrate_production_scanner

CALIBRATION_COHORT = [
    ("answer_sheet.jpg", "images/answer_sheet.jpg", "Calibration: Ambiguous Grid Crop"),
    ("answer_sheet_2.png", "images/answer_sheet_2.png", "Calibration: Clean A4 Physical Page"),
    ("answer_sheet_3.jpg", "images/answer_sheet_3.jpg", "Calibration: Severe Diagonal Cast Shadow"),
    ("answer_sheet_4.jpg", "images/answer_sheet_4.jpg", "Calibration: High-Res Sensor Grain & Tables"),
    ("answer_sheet_5.jpg", "images/answer_sheet_5.jpg", "Calibration: Low-Contrast Blue Handwriting"),
]

UNSEEN_VALIDATION_COHORT = [
    ("Val_01_DenseDark", "images/dataset_samples/02_Y21AEC402_IMG20251016104816.jpg", "Unseen: Dense Dark Cursive Ink"),
    ("Val_02_FaintPencil", "images/dataset_samples/03_Y21AEC403_IMG_20251013_124038367_HDR.jpg", "Unseen: Faint Pencil on Textured Paper"),
    ("Val_03_SparseMath", "images/dataset_samples/05_Y21AEC407_IMG_20251016_105759.jpg", "Unseen: Sparse Mathematical Formulas"),
    ("Val_04_JPEGArtifacts", "images/dataset_samples/07_Y21AEC409_IMG-20251016-WA0063.jpg", "Unseen: Compressed JPEG Ringing"),
    ("Val_05_Overexposed", "images/dataset_samples/11_Y21AEC413_IMG_20251022_110128465_HDR.jpg", "Unseen: Overexposed Washed-out Blue Ink"),
    ("Val_06_LinedPaper", "images/dataset_samples/14_Y21AEC417_IMG_20251022_122722625_HDR.jpg", "Unseen: Dense Handwriting on Lined Paper"),
    ("Val_07_MixedPrinted", "images/dataset_samples/16_Y21AEC421_IMG20251022123543.jpg", "Unseen: Mixed Printed Form & Student Numbers"),
    ("Val_08_BleedThrough", "images/dataset_samples/19_Y21AEC427_IMG20251022122156.jpg", "Unseen: Reverse-Side Ink Bleed-Through"),
    ("Val_09_HeavyBlue", "images/dataset_samples/22_Y21AEC418_IMG20251023110034.jpg", "Unseen: Heavy Blue Ballpoint with Variable Pressure"),
    ("Val_10_PatchGradient", "images/dataset_samples/25_Y21AEC429_IMG20251022110708.jpg", "Unseen: Localized Lighting Gradient on Patch"),
]


def run_production_validation():
    print("=" * 80)
    print("AI-EVAL PRODUCTION ENHANCEMENT VALIDATION EXECUTION")
    print("=" * 80)

    all_results = []

    # 1. Evaluate Calibration Cohort (Full Phase 3 Integration)
    print("\n[PART 1: CALIBRATION COHORT (5 IMAGES) - INTEGRATED SCANNER INPUT]")
    print("-" * 80)

    for name, rel_path, desc in CALIBRATION_COHORT:
        full_path = os.path.join(ROOT_DIR, rel_path)
        scan_res = integrate_production_scanner(full_path)
        enh_res = enhance_scanned_document(scan_res)
        all_results.append((name, "CALIBRATION", desc, enh_res))

        p = enh_res.condition_profile
        accepted = [op.operator_name for op in enh_res.operator_audit_log if op.status == "ACCEPTED"]
        rejected = [f"{op.operator_name} ({op.rejection_reason})" for op in enh_res.operator_audit_log if op.status == "REJECTED_ROLLBACK"]
        bypassed = [op.operator_name for op in enh_res.operator_audit_log if op.status == "BYPASSED_NO_OP"]

        print(f"Target: {name:<18} [{desc}]")
        print(f"  Dims: {enh_res.dimensions[0]}x{enh_res.dimensions[1]} | Status: {enh_res.status} | Total Latency: {enh_res.total_latency_ms:.1f}ms")
        print(f"  Signals: BgRatio={p.spatial_bg_ratio:.2f}, NoiseSigma={p.paper_noise_sigma:.2f}, StrokeDynRange={p.stroke_center_dynamic_range:.1f}, Acutance={p.normalized_stroke_acutance:.1f}, ColorFrac={p.in_page_color_fraction*100:.1f}%")
        print(f"  Accepted Ops : {accepted if accepted else 'None'}")
        print(f"  Rejected Ops : {rejected if rejected else 'None (0 rollbacks)'}")
        print(f"  NO_OP Path   : {bypassed if bypassed else 'No'}")
        print(f"  Derivatives  : Binary Derivative {'OK' if enh_res.binary_derivative is not None else 'None'}, Color Mask {'OK' if enh_res.color_rubric_mask is not None else 'None'}")
        print()

    # 2. Evaluate Unseen Validation Cohort
    print("\n[PART 2: UNSEEN VALIDATION COHORT (10 IMAGES) - DIVERSE HANDWRITING]")
    print("-" * 80)

    for name, rel_path, desc in UNSEEN_VALIDATION_COHORT:
        full_path = os.path.join(ROOT_DIR, rel_path)
        bgr = cv2.imread(full_path)
        if bgr is None:
            continue
        enh_res = enhance_scanned_document(bgr)
        all_results.append((name, "UNSEEN_VALIDATION", desc, enh_res))

        p = enh_res.condition_profile
        accepted = [op.operator_name for op in enh_res.operator_audit_log if op.status == "ACCEPTED"]
        rejected = [f"{op.operator_name} ({op.rejection_reason})" for op in enh_res.operator_audit_log if op.status == "REJECTED_ROLLBACK"]
        bypassed = [op.operator_name for op in enh_res.operator_audit_log if op.status == "BYPASSED_NO_OP"]

        print(f"Target: {name:<22} [{desc}]")
        print(f"  Dims: {enh_res.dimensions[0]}x{enh_res.dimensions[1]} | Status: {enh_res.status} | Total Latency: {enh_res.total_latency_ms:.1f}ms")
        print(f"  Signals: BgRatio={p.spatial_bg_ratio:.2f}, NoiseSigma={p.paper_noise_sigma:.2f}, StrokeDynRange={p.stroke_center_dynamic_range:.1f}, Acutance={p.normalized_stroke_acutance:.1f}, ColorFrac={p.in_page_color_fraction*100:.1f}%")
        print(f"  Accepted Ops : {accepted if accepted else 'None'}")
        print(f"  Rejected Ops : {rejected if rejected else 'None (0 rollbacks)'}")
        print(f"  NO_OP Path   : {bypassed if bypassed else 'No'}")
        print(f"  Derivatives  : Binary Derivative {'OK' if enh_res.binary_derivative is not None else 'None'}, Color Mask {'OK' if enh_res.color_rubric_mask is not None else 'None'}")
        print()

    print("=" * 80)
    print("PRODUCTION VALIDATION COMPLETED SUCCESSFULLY.")
    print("=" * 80)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_production_validation()
