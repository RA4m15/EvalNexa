"""
ai-eval-scanner/pipeline.py

Production integration wrapper bridging EvalNexa's scanning contract
with the frozen AI-EVAL computer vision pipeline (Phases 2-9).

Responsibilities:
1. Accept image bytes, numpy array, or file path.
2. Step 1: Scanner intake (Phase 2 page boundary & Phase 3 perspective rectification).
3. Step 2: Quality assessment (Phase 5 acutance, illumination, defect detectors).
4. Step 3: Defect remediation & auto-correction (Phase 6 shadow/contrast correction & rollback).
5. Step 4: Rescan decision (Phase 7 non-compensatory 4-tier decision engine).
6. Step 5: OCR readiness representation (Phase 8 orientation & readiness telemetry).
7. Assemble and return predictable JSON matching EvalNexa's ProcessPageResult interface.
"""

from __future__ import annotations

import os
import sys
import time
import tempfile
import importlib.util
from typing import Any, Dict, Optional, Tuple, Union

import cv2
import numpy as np

# Ensure this directory is in Python path for intra-phase imports
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# ---------------------------------------------------------------------------
# Import Frozen Phase Modules
# ---------------------------------------------------------------------------

# Phase 3 Scanner Integration (Frozen)
P3_PATH = os.path.join(CURRENT_DIR, "phase3", "06_scanner_integration_investigation.py")
spec_p3 = importlib.util.spec_from_file_location("phase3_06", P3_PATH)
phase3_06 = importlib.util.module_from_spec(spec_p3)
spec_p3.loader.exec_module(phase3_06)
integrate_production_scanner = phase3_06.integrate_production_scanner

# Phase 5 Frozen Production Module
from phase5.production_quality_assessment import (
    assess_document_quality,
    QualityAssessmentResult,
)

# Phase 6 Frozen Production Module
from phase6.correction_engine import execute_intelligent_correction

# Phase 7 Frozen Production Module
from phase7.rescan_decision_engine import (
    evaluate_rescan_decision,
    RescanDecisionResult,
)

# Phase 8.2 Production Modules
from phase8.ocr_readiness_contracts import (
    ReadingOrientation,
    OCRReadinessVerdict,
)
from phase8.ocr_readiness_engine import prepare_ocr_readiness


def compute_sharpness_score(laplacian_variance: float) -> Tuple[float, bool]:
    """
    Converts raw Laplacian variance into a normalized 0-100 clarity score.
    Threshold for motion blur / defocus is 55.0.
    """
    if laplacian_variance < 55.0:
        blur_detected = True
        score = max(5.0, min(54.9, (laplacian_variance / 55.0) * 50.0))
    else:
        blur_detected = False
        progress = min(1.0, (laplacian_variance - 55.0) / 945.0)
        score = 55.0 + (progress * 44.5)
    return round(score, 1), blur_detected


def process_image(
    image_input: Union[bytes, str, np.ndarray],
    document_id: str = "page_1",
    page_number: int = 1,
    exam_id: Optional[str] = None,
    answer_book_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes the full end-to-end AI-EVAL scanning pipeline.
    Returns a dictionary strictly compatible with EvalNexa's ProcessPageResult:
    {
        "qualityStatus": "PASSED" | "RESCAN_REQUIRED",
        "blurDetected": bool,
        "sharpness": float,
        "orientation": str,
        "pageDetected": bool,
        "cropReady": bool,
        "ocrReadiness": "READY" | "UNCLEAR" | "FAILED",
        "reason": Optional[str],
        "processedImageUrl": Optional[str],
        "ocrText": str
    }
    """
    t_start = time.perf_counter()
    temp_file = None

    try:
        # 1. Resolve image to a file path for Phase 2/3 intake
        if isinstance(image_input, (bytes, bytearray)):
            if len(image_input) < 16:
                raise ValueError("Uploaded image payload is empty or too small")
            nparr = np.frombuffer(image_input, np.uint8)
            img_test = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img_test is None:
                raise ValueError("Could not decode image from provided byte stream (corrupt or unsupported format)")

            fd, temp_file = tempfile.mkstemp(suffix=".jpg", prefix="evalnexa_scan_")
            os.close(fd)
            with open(temp_file, "wb") as f:
                f.write(image_input)
            input_path = temp_file

        elif isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Image file not found at: {image_input}")
            input_path = image_input

        elif isinstance(image_input, np.ndarray):
            fd, temp_file = tempfile.mkstemp(suffix=".jpg", prefix="evalnexa_scan_")
            os.close(fd)
            cv2.imwrite(temp_file, image_input)
            input_path = temp_file

        else:
            raise TypeError(f"Unsupported image input type: {type(image_input)}")

        # -------------------------------------------------------------------
        # STEP 1: Scanner Intake (Phase 2 Detection + Phase 3 Rectification)
        # -------------------------------------------------------------------
        try:
            p3_res = integrate_production_scanner(input_path)
            rectified_bgr = p3_res.scanned_image
            if rectified_bgr is None or rectified_bgr.size == 0:
                raise ValueError("Phase 3 returned an empty scanned image")
            if rectified_bgr.ndim == 2:
                rectified_bgr = cv2.cvtColor(rectified_bgr, cv2.COLOR_GRAY2BGR)
            rectified_gray = cv2.cvtColor(rectified_bgr, cv2.COLOR_BGR2GRAY)
            page_detected = True
            crop_ready = (p3_res.status == "RECTIFIED_PHYSICAL_PAGE")
        except Exception:
            # Fallback if document boundary detection cannot locate the sheet
            return {
                "qualityStatus": "RESCAN_REQUIRED",
                "blurDetected": True,
                "sharpness": 0.0,
                "orientation": "NORMAL",
                "pageDetected": False,
                "cropReady": False,
                "ocrReadiness": "FAILED",
                "reason": "Unable to detect page boundaries. Please place the answer sheet flat within the camera frame.",
                "processedImageUrl": None,
                "ocrText": "",
            }

        # -------------------------------------------------------------------
        # STEP 2: Quality Assessment (Phase 5)
        # -------------------------------------------------------------------
        p5_res = assess_document_quality(rectified_gray, document_id)
        laplacian_var = float(p5_res.evidence_profile.diagnostic_laplacian_variance)
        sharpness_score, blur_flagged = compute_sharpness_score(laplacian_var)

        # Fatal defect check for blur
        is_blur_fatal = any(d.defect_type in ("OPTICAL_DEFOCUS", "MOTION_BLUR") for d in p5_res.fatal_defects)
        blur_detected = blur_flagged or is_blur_fatal

        # -------------------------------------------------------------------
        # STEP 3: Auto-Correction & Rollback (Phase 6)
        # -------------------------------------------------------------------
        p6_res = execute_intelligent_correction(
            raw_rectified_bgr=rectified_bgr,
            initial_assessment=p5_res,
        )

        # -------------------------------------------------------------------
        # STEP 4: Rescan Decision Engine (Phase 7)
        # -------------------------------------------------------------------
        p7_res = evaluate_rescan_decision(
            document_input=p6_res.final_safe_state,
            final_quality_assessment=p6_res.quality_assessment_final,
            image_name=document_id,
        )

        if p7_res.decision == "CONTINUE":
            quality_status = "PASSED"
            reason = None
        else:
            quality_status = "RESCAN_REQUIRED"
            reason = p7_res.actionable_operator_guidance or f"Defect flagged: {p7_res.primary_trigger}"

        # -------------------------------------------------------------------
        # STEP 5: OCR Readiness & Representations (Phase 8)
        # -------------------------------------------------------------------
        p8_res = prepare_ocr_readiness(
            source=p6_res.final_safe_state,
            document_id=document_id,
            rescan_decision=p7_res,
        )

        orient_map = {
            ReadingOrientation.UPRIGHT_0: "NORMAL",
            ReadingOrientation.ROTATED_90_CW: "ROTATED_90_CW",
            ReadingOrientation.ROTATED_180_INVERTED: "INVERTED_180",
            ReadingOrientation.ROTATED_270_CCW: "ROTATED_270_CCW",
            ReadingOrientation.AMBIGUOUS: "AMBIGUOUS",
        }
        orientation_str = orient_map.get(p8_res.detected_orientation, "NORMAL")

        if p8_res.verdict in (OCRReadinessVerdict.OCR_READY, OCRReadinessVerdict.HTR_READY):
            ocr_readiness = "READY"
        elif p8_res.verdict == OCRReadinessVerdict.CONDITIONALLY_READY:
            ocr_readiness = "UNCLEAR"
        else:
            ocr_readiness = "FAILED"

        total_latency = (time.perf_counter() - t_start) * 1000.0

        return {
            "qualityStatus": quality_status,
            "blurDetected": blur_detected,
            "sharpness": sharpness_score,
            "orientation": orientation_str,
            "pageDetected": page_detected,
            "cropReady": crop_ready,
            "ocrReadiness": ocr_readiness,
            "reason": reason,
            "processedImageUrl": None,
            "ocrText": "",
        }

    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass
