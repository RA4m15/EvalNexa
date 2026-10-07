"""
ai-eval-scanner/test_scanner_integration.py

Integration test suite validating the AI-EVAL Scanner microservice contract
against EvalNexa Control Center's expected scanningIntegration.ts interface.
"""

import io
import os
import sys
import base64
import unittest
import cv2
import numpy as np

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from server import app


class TestScannerIntegration(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()
        self.sample_img_path = os.path.join(CURRENT_DIR, "images", "answer_sheet_2.png")

    def test_01_health_check(self):
        """Verify GET /health contract expected by checkScanningServiceHealth()."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("service", data)
        self.assertIn("Access-Control-Allow-Origin", res.headers)
        print("  [PASS] test_01_health_check: 200 OK, JSON valid, CORS present")

    def test_02_missing_file_payload(self):
        """Verify POST /process-page returns HTTP 400 when 'file' field is missing."""
        res = self.client.post("/process-page", data={"pageNumber": "1"})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data.get("status"), "error")
        print("  [PASS] test_02_missing_file_payload: 400 Bad Request on missing file")

    def test_03_invalid_image_payload(self):
        """Verify POST /process-page returns HTTP 400 when file content is not a valid image."""
        bad_file = (io.BytesIO(b"not an actual image file"), "test.jpg")
        res = self.client.post(
            "/process-page",
            data={"file": bad_file, "pageNumber": "1"},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data.get("status"), "error")
        print("  [PASS] test_03_invalid_image_payload: 400 Bad Request on corrupt stream")

    def test_04_valid_page_processing(self):
        """Verify POST /process-page returns expected ProcessPageResult fields on real answer sheet."""
        if not os.path.exists(self.sample_img_path):
            self.skipTest(f"Sample image not found at {self.sample_img_path}")

        with open(self.sample_img_path, "rb") as f:
            img_bytes = f.read()

        file_tuple = (io.BytesIO(img_bytes), "answer_sheet_2.png")
        res = self.client.post(
            "/process-page",
            data={
                "file": file_tuple,
                "pageNumber": "1",
                "examId": "exam_math_101",
                "answerBookCode": "AB-2026-MATH-001",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        # Assert all fields required by ProcessPageResult & PageQualityDiagnostics
        required_fields = [
            "qualityStatus",
            "blurDetected",
            "sharpness",
            "orientation",
            "pageDetected",
            "cropReady",
            "ocrReadiness",
            "reason",
            "processedImageUrl",
            "ocrText",
        ]
        for field in required_fields:
            self.assertIn(field, data, f"Missing required field: {field}")

        # Assert correct field types and values
        self.assertIn(data["qualityStatus"], ["PASSED", "RESCAN_REQUIRED"])
        self.assertIsInstance(data["blurDetected"], bool)
        self.assertIsInstance(data["sharpness"], (int, float))
        self.assertIsInstance(data["orientation"], str)
        self.assertIsInstance(data["pageDetected"], bool)
        self.assertIsInstance(data["cropReady"], bool)
        self.assertIn(data["ocrReadiness"], ["READY", "UNCLEAR", "FAILED"])

        # Clean answer sheet 2 should pass quality gates
        self.assertEqual(data["qualityStatus"], "PASSED")
        self.assertTrue(data["pageDetected"])
        self.assertTrue(data["cropReady"])
        self.assertFalse(data["blurDetected"])
        self.assertGreaterEqual(data["sharpness"], 55.0)

        # Assert diagnostic dimension telemetry
        self.assertIn("source_width", data)
        self.assertIn("source_height", data)
        self.assertIn("output_width", data)
        self.assertIn("output_height", data)
        self.assertEqual(data["source_width"], 1200)
        self.assertEqual(data["source_height"], 1600)
        self.assertGreater(data["output_width"], 0)
        self.assertGreater(data["output_height"], 0)
        # Verify that output is the cropped warped document, NOT the raw camera frame
        self.assertNotEqual((data["output_width"], data["output_height"]), (data["source_width"], data["source_height"]))

        # Decode processedImageUrl base64 and verify shape matches output_width and output_height
        self.assertIsNotNone(data.get("processedImageUrl"))
        b64_part = data["processedImageUrl"].split(",")[1]
        decoded_img = cv2.imdecode(np.frombuffer(base64.b64decode(b64_part), np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(decoded_img)
        self.assertEqual(decoded_img.shape[1], data["output_width"])
        self.assertEqual(decoded_img.shape[0], data["output_height"])

        print(f"  [PASS] test_04_valid_page_processing: 200 OK, qualityStatus={data['qualityStatus']}, sharpness={data['sharpness']}, output_dims={data['output_width']}x{data['output_height']}, pageDetected={data['pageDetected']}")

    def test_05_options_preflight(self):
        """Verify OPTIONS /process-page returns HTTP 204 with CORS headers for browser preflight."""
        res = self.client.open("/process-page", method="OPTIONS")
        self.assertEqual(res.status_code, 204)
        self.assertEqual(res.headers.get("Access-Control-Allow-Origin"), "*")
        print("  [PASS] test_05_options_preflight: 204 No Content with CORS preflight headers")

    def test_06_fatal_defect_rescan_required(self):
        """Verify POST /process-page returns RESCAN_REQUIRED with actionable reason on defective image without AttributeError."""
        defective_img_path = os.path.join(CURRENT_DIR, "images", "answer_sheet_4.jpg")
        if not os.path.exists(defective_img_path):
            self.skipTest(f"Defective test image not found at {defective_img_path}")

        with open(defective_img_path, "rb") as f:
            img_bytes = f.read()

        file_tuple = (io.BytesIO(img_bytes), "answer_sheet_4.jpg")
        res = self.client.post(
            "/process-page",
            data={
                "file": file_tuple,
                "pageNumber": "4",
                "examId": "exam_math_101",
                "answerBookCode": "AB-2026-MATH-001",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsNotNone(data)
        self.assertEqual(data.get("qualityStatus"), "RESCAN_REQUIRED")
        self.assertIsInstance(data.get("reason"), str)
        self.assertTrue(len(data.get("reason", "").strip()) > 0)
        self.assertIn(data.get("ocrReadiness"), ["READY", "UNCLEAR", "FAILED"])
        print(f"  [PASS] test_06_fatal_defect_rescan_required: 200 OK, qualityStatus=RESCAN_REQUIRED, reason='{data['reason'][:60]}...'")

    def test_07_detect_document_lightweight(self):
        """Verify POST /detect-document returns 4 corners and detected=True quickly without full pipeline."""
        if not os.path.exists(self.sample_img_path):
            self.skipTest(f"Sample image not found at {self.sample_img_path}")

        with open(self.sample_img_path, "rb") as f:
            img_bytes = f.read()

        file_tuple = (io.BytesIO(img_bytes), "answer_sheet_2.png")
        res = self.client.post(
            "/detect-document",
            data={"file": file_tuple},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("detected"))
        self.assertIsNotNone(data.get("corners"))
        self.assertEqual(len(data["corners"]), 4)
        self.assertGreater(data.get("document_score", 0), 50.0)
        self.assertIn("image_width", data)
        self.assertIn("image_height", data)

        # Preflight test
        opt_res = self.client.open("/detect-document", method="OPTIONS")
        self.assertEqual(opt_res.status_code, 204)
        self.assertEqual(opt_res.headers.get("Access-Control-Allow-Origin"), "*")

        print("  [PASS] test_07_detect_document_lightweight: 200 OK, 4 corners detected, CORS enabled")

    def test_08_corners_hint_fallback(self):
        """Verify POST /process-page accepts corners hint and uses it to warp document."""
        if not os.path.exists(self.sample_img_path):
            self.skipTest(f"Sample image not found at {self.sample_img_path}")

        with open(self.sample_img_path, "rb") as f:
            img_bytes = f.read()

        import json
        corners_hint = [[140, 160], [1050, 160], [1050, 1450], [140, 1450]]

        file_tuple = (io.BytesIO(img_bytes), "answer_sheet_2.png")
        res = self.client.post(
            "/process-page",
            data={
                "file": file_tuple,
                "pageNumber": "1",
                "examId": "exam_math_101",
                "answerBookCode": "AB-2026-MATH-001",
                "corners": json.dumps(corners_hint),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("pageDetected"))
        self.assertTrue(data.get("cropReady"))
        self.assertIsNotNone(data.get("processedImageUrl"))
        self.assertGreater(data.get("output_width", 0), 0)
        self.assertGreater(data.get("output_height", 0), 0)
        print(f"  [PASS] test_08_corners_hint_fallback: 200 OK, cropReady=True, output={data['output_width']}x{data['output_height']}")


if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING AI-EVAL SCANNER INTEGRATION TEST SUITE")
    print("=" * 70)
    unittest.main()
