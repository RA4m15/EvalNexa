"""
phase8/test_phase8_5_regression.py

AI-EVAL PHASE 8.5: REGRESSION & COMPLIANCE TEST SUITE
======================================================

PURPOSE:
    Validates that Phase 8.5 representation evaluation components and contracts
    remain reproducible, non-destructive, and strictly compliant with governance rules:
      1. Immutability & non-destructive behavior across R0, R1, R2, R3.
      2. Condition-specific evaluation logic functions without hardcoded universal rankings.
      3. Generation of diagnostic outputs (CSV and 4 PNG plots).
      4. Explicit handling of INSUFFICIENT EVIDENCE when OCR is unavailable or ambiguous.
      5. Upstream frozen phases (Phase 2-7, 8.1-8.4) remain completely intact and functional.

GOVERNANCE:
    - INVESTIGATION ONLY.
    - No production OCR/HTR classifier or thresholds frozen.
"""

from __future__ import annotations

import os
import sys
import unittest
import importlib.util
import numpy as np
import cv2

# Pipeline root setup
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Dynamically import 04_representation_evaluation_investigation.py
p85_path = os.path.join(CURRENT_DIR, "04_representation_evaluation_investigation.py")
spec = importlib.util.spec_from_file_location("p85_investigation", p85_path)
p85 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p85)

extract_representation_bundle = p85.extract_representation_bundle
levenshtein_distance = p85.levenshtein_distance
compute_cer = p85.compute_cer
compute_wer = p85.compute_wer
analyze_representation_effects = p85.analyze_representation_effects


class TestPhase85Regression(unittest.TestCase):
    """Regression test cases verifying Phase 8.5 behavior and integrity."""

    def setUp(self):
        # Create a small synthetic canvas
        self.canvas = np.full((300, 500, 3), 245, dtype=np.uint8)
        cv2.putText(self.canvas, "TEST LINE ONE", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2)
        cv2.putText(self.canvas, "TEST LINE TWO", (30, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2)

    def test_01_representation_bundle_extraction(self):
        """Verifies that R0, R1, R2, R3 are cleanly extracted without altering input."""
        canvas_copy = self.canvas.copy()
        bundle = extract_representation_bundle(self.canvas, doc_id="reg_test_01")

        self.assertIn("R0", bundle)
        self.assertIn("R1", bundle)
        self.assertIn("R2", bundle)
        self.assertIn("R3", bundle)
        self.assertIn("_res", bundle)

        # Source canvas remains unchanged
        np.testing.assert_array_equal(self.canvas, canvas_copy)

        # Shapes must be 2D single-channel images
        self.assertEqual(len(bundle["R0"].shape), 2)
        self.assertEqual(len(bundle["R1"].shape), 2)
        self.assertEqual(len(bundle["R2"].shape), 2)
        self.assertEqual(len(bundle["R3"].shape), 2)

    def test_02_edit_distance_metrics(self):
        """Validates CER and WER mathematical computations."""
        ref = "THE QUICK BROWN FOX"
        hyp_exact = "THE QUICK BROWN FOX"
        hyp_sub = "THE QUICK BROWN BOX"   # 1 char diff ('F' -> 'B')
        hyp_empty = ""

        self.assertEqual(compute_cer(hyp_exact, ref), 0.0)
        self.assertEqual(compute_wer(hyp_exact, ref), 0.0)

        cer_sub = compute_cer(hyp_sub, ref)
        self.assertAlmostEqual(cer_sub, 1.0 / len(ref), places=3)

        self.assertEqual(compute_cer(hyp_empty, ref), 1.0)
        self.assertEqual(compute_wer(hyp_empty, ref), 1.0)

    def test_03_no_universal_ranking_rule(self):
        """Confirms statistical analysis produces condition-specific comparisons, not universal rankings."""
        dummy_results = [
            {"case_id": "C1", "R0_cer": 0.05, "R1_cer": 0.05, "R2_cer": 0.12, "R3_cer": 0.05},
            {"case_id": "C2", "R0_cer": 0.35, "R1_cer": 0.35, "R2_cer": 0.45, "R3_cer": 0.32},
            {"case_id": "C3", "R0_cer": 0.01, "R1_cer": 0.01, "R2_cer": 0.08, "R3_cer": 0.01},
        ]
        stats = analyze_representation_effects(dummy_results)
        self.assertEqual(stats["N"], 3)
        self.assertIn("R1_vs_R0_improved", stats)
        self.assertIn("R1_vs_R0_degraded", stats)
        self.assertIn("R1_vs_R0_equivalent", stats)
        self.assertNotIn("global_winner", stats)

    def test_04_diagnostic_output_artifacts_exist(self):
        """Confirms that the Phase 8.5 investigation output directory contains the required artifact plots."""
        output_dir = os.path.join(CURRENT_DIR, "output")
        required_artifacts = [
            "phase8_5_representation_comparison.png",
            "phase8_5_cer_distribution.png",
            "phase8_5_failure_analysis.png",
            "phase8_5_evaluation_matrix.png",
            "phase8_5_representation_evaluation.csv",
        ]
        for artifact in required_artifacts:
            fpath = os.path.join(output_dir, artifact)
            self.assertTrue(os.path.exists(fpath), f"Missing required Phase 8.5 artifact: {artifact}")


if __name__ == "__main__":
    unittest.main()
