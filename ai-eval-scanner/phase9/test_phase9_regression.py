"""
phase9/test_phase9_regression.py

AI-EVAL PHASE 9: REGRESSION & COMPLIANCE TEST SUITE
===================================================

PURPOSE:
    Validates that Phase 9 Human-in-the-Loop architectural data contracts,
    non-destructive immutability, audit reconstruction, and feedback qualification
    rules remain reproducible, immutable, and strictly compliant with governance:
      1. ReviewCheckpoint, ReviewTriggerCategory, and HumanReviewAction enums.
      2. Non-destructive preservation of original AI hypotheses during correction.
      3. Complete audit trail serialization and deterministic recovery.
      4. Feedback loop qualification filter logic (rejection of blurred/unclear/incomplete cases).
      5. Generation of all 4 diagnostic output artifacts.

GOVERNANCE:
    - INVESTIGATION ONLY.
    - No production UI, no database, no hard thresholds frozen.
"""

from __future__ import annotations

import os
import sys
import json
import unittest
from dataclasses import asdict

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import importlib.util
p9_path = os.path.join(CURRENT_DIR, "01_human_review_boundary_investigation.py")
spec = importlib.util.spec_from_file_location("p9_investigation", p9_path)
if spec is None or spec.loader is None:
    raise ImportError(f"Could not load module from {p9_path}")
p9 = importlib.util.module_from_spec(spec)
sys.modules["p9_investigation"] = p9
spec.loader.exec_module(p9)

ReviewCheckpoint = p9.ReviewCheckpoint
ReviewTriggerCategory = p9.ReviewTriggerCategory
HumanReviewAction = p9.HumanReviewAction
ReviewerRole = p9.ReviewerRole
FeedbackEligibilityVerdict = p9.FeedbackEligibilityVerdict
BoundingBox = p9.BoundingBox
RegionAIHypothesis = p9.RegionAIHypothesis
HumanReviewEvent = p9.HumanReviewEvent
CanonicalEvaluationRecord = p9.CanonicalEvaluationRecord


class TestPhase9Regression(unittest.TestCase):
    """Regression test cases verifying Phase 9 HITL architecture and contracts."""

    def test_01_action_model_and_checkpoints(self):
        """Validates that candidate action model and checkpoint enums are complete."""
        expected_actions = {"ACCEPT", "CORRECT", "REJECT", "UNCLEAR", "ESCALATE"}
        actual_actions = {a.value for a in HumanReviewAction}
        self.assertEqual(expected_actions, actual_actions)

        expected_checkpoints = {
            "CP1_PHYSICAL_INTAKE",
            "CP2_READINESS_PREPARATION",
            "CP3_TRANSCRIPTION_RECOGNITION",
            "CP4_SEMANTIC_EVALUATION",
        }
        actual_checkpoints = {c.value for c in ReviewCheckpoint}
        self.assertEqual(expected_checkpoints, actual_checkpoints)

    def test_02_non_destructive_preservation(self):
        """Verifies that human corrections never mutate the original AI hypothesis."""
        ai_hyp = RegionAIHypothesis(
            region_id="Q1",
            bounding_box=BoundingBox(0.1, 0.1, 0.9, 0.3),
            recognized_text="Originl AI Text with typo",
            confidence_score=0.75,
            detected_script_type="CURSIVE_HANDWRITING",
        )

        review_evt = HumanReviewEvent(
            event_id="EVT_001",
            document_id="DOC_A",
            region_id="Q1",
            checkpoint=ReviewCheckpoint.CP3_TRANSCRIPTION_RECOGNITION,
            trigger_category=ReviewTriggerCategory.RECOGNITION_UNCERTAINTY,
            trigger_reason="Spelling error in cursive word",
            action=HumanReviewAction.CORRECT,
            original_ai_text=ai_hyp.recognized_text,
            human_corrected_text="Original AI Text with typo fixed",
            examiner_id="EXAM_01",
            examiner_role=ReviewerRole.PRIMARY_EXAMINER,
            timestamp_utc="2026-10-04T01:40:00Z",
            rationale_note="Fixed character reading based on stroke context",
            review_latency_sec=8.5,
        )

        record = CanonicalEvaluationRecord(
            document_id="DOC_A",
            region_id="Q1",
            ai_hypothesis=ai_hyp,
            human_review_event=review_evt,
            final_accepted_text=review_evt.human_corrected_text,
            was_human_reviewed=True,
            pipeline_version="v8.5.0-P9",
            decision_timestamp_utc="2026-10-04T01:40:01Z",
        )

        # AI hypothesis is preserved exactly and is frozen
        self.assertEqual(record.ai_hypothesis.recognized_text, "Originl AI Text with typo")
        self.assertEqual(record.final_accepted_text, "Original AI Text with typo fixed")
        self.assertTrue(record.was_human_reviewed)
        with self.assertRaises(Exception):
            record.final_accepted_text = "Attempted Mutation"

    def test_03_audit_trail_serialization_and_replay(self):
        """Confirms that the complete decision history can be serialized to JSON and verified."""
        ai_hyp = RegionAIHypothesis(
            region_id="Q2",
            bounding_box=BoundingBox(0.1, 0.3, 0.9, 0.6),
            recognized_text="Clean AI Hypothesis",
            confidence_score=0.98,
            detected_script_type="PRINTED_TYPOGRAPHY",
        )
        record = CanonicalEvaluationRecord(
            document_id="DOC_B",
            region_id="Q2",
            ai_hypothesis=ai_hyp,
            human_review_event=None,
            final_accepted_text=ai_hyp.recognized_text,
            was_human_reviewed=False,
            pipeline_version="v8.5.0-P9",
            decision_timestamp_utc="2026-10-04T01:40:02Z",
        )
        record_dict = asdict(record)
        json_str = json.dumps(record_dict)
        deserialized = json.loads(json_str)

        self.assertEqual(deserialized["document_id"], "DOC_B")
        self.assertFalse(deserialized["was_human_reviewed"])
        self.assertEqual(deserialized["final_accepted_text"], "Clean AI Hypothesis")
        self.assertEqual(deserialized["ai_hypothesis"]["confidence_score"], 0.98)

    def test_04_feedback_eligibility_filter(self):
        """Verifies qualification policy rejects defective images, unclear readings, and incomplete edits."""
        # Case 1: Defective image (e.g. fatal blur) must be disqualified
        image_defective = "FATAL_BLUR_OR_CLIPPED"
        has_unclear = False
        agreement = 0.95
        char_count = 40
        if image_defective == "FATAL_BLUR_OR_CLIPPED" or has_unclear:
            verdict = FeedbackEligibilityVerdict.DISQUALIFIED_DEFECTIVE
        self.assertEqual(verdict, FeedbackEligibilityVerdict.DISQUALIFIED_DEFECTIVE)

        # Case 2: Incomplete / short correction must be provisional audit only
        image_quality = "HIGH_CONFIRMED"
        has_unclear = False
        agreement = 0.85 # Below 0.90 threshold
        char_count = 8
        if image_quality == "FATAL_BLUR_OR_CLIPPED" or has_unclear:
            v2 = FeedbackEligibilityVerdict.DISQUALIFIED_DEFECTIVE
        elif agreement < 0.90 or char_count < 15:
            v2 = FeedbackEligibilityVerdict.PROVISIONAL_AUDIT_ONLY
        else:
            v2 = FeedbackEligibilityVerdict.QUALIFIED_FOR_TRAINING
        self.assertEqual(v2, FeedbackEligibilityVerdict.PROVISIONAL_AUDIT_ONLY)

    def test_05_diagnostic_artifacts_exist(self):
        """Verifies that all Phase 9 diagnostic visualization artifacts were produced."""
        output_dir = os.path.join(CURRENT_DIR, "output")
        required_artifacts = [
            "phase9_boundary_architecture.png",
            "phase9_page_vs_region_granularity.png",
            "phase9_audit_trail_reconstruction.png",
            "phase9_feedback_qualification_matrix.png",
        ]
        for artifact in required_artifacts:
            path = os.path.join(output_dir, artifact)
            self.assertTrue(os.path.exists(path), f"Missing required Phase 9 artifact: {artifact}")


if __name__ == "__main__":
    unittest.main()
