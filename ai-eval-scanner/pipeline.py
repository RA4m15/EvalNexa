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
import base64
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
    corners_hint: Optional[List[List[float]]] = None,
    original_corners: Optional[List[List[float]]] = None,
    preview_width: Optional[int] = None,
    preview_height: Optional[int] = None,
    capture_width: Optional[int] = None,
    capture_height: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Executes the full end-to-end AI-EVAL scanning pipeline.
    Returns a dictionary strictly compatible with EvalNexa's ProcessPageResult:
    {
        "qualityStatus": "PASSED" | "HUMAN_REVIEW" | "RESCAN_REQUIRED",
        "blurDetected": bool,
        "sharpness": float,
        "orientation": str,
        "pageDetected": bool,
        "cropReady": bool,
        "ocrReadiness": "READY" | "UNCLEAR" | "FAILED",
        "reason": Optional[str],
        "processedImageUrl": Optional[str],
        "ocrText": str,
        "output_width": int,
        "output_height": int,
        "source_width": int,
        "source_height": int,
        "detected": bool,
        "corners": Optional[List[List[float]]],
    }
    """
    t_start = time.perf_counter()
    temp_file = None
    w_img, h_img = 0, 0

    try:
        # 1. Resolve image to a file path for Phase 2/3 intake
        if isinstance(image_input, (bytes, bytearray)):
            if len(image_input) < 16:
                raise ValueError("Uploaded image payload is empty or too small")
            nparr = np.frombuffer(image_input, np.uint8)
            img_test = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img_test is None:
                raise ValueError("Could not decode image from provided byte stream (corrupt or unsupported format)")
            h_img, w_img = img_test.shape[:2]

            fd, temp_file = tempfile.mkstemp(suffix=".jpg", prefix="evalnexa_scan_")
            os.close(fd)
            with open(temp_file, "wb") as f:
                f.write(image_input)
            input_path = temp_file

        elif isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Image file not found at: {image_input}")
            input_path = image_input
            test_read = cv2.imread(image_input)
            if test_read is not None:
                h_img, w_img = test_read.shape[:2]

        elif isinstance(image_input, np.ndarray):
            h_img, w_img = image_input.shape[:2]
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
            scanner_opts = {
                "corners_hint": corners_hint,
                "original_corners": original_corners,
                "preview_width": preview_width,
                "preview_height": preview_height,
                "capture_width": capture_width,
                "capture_height": capture_height,
            }
            p3_res = integrate_production_scanner(input_path, options=scanner_opts)

            if p3_res.status == "REJECTED_NON_DOCUMENT":
                reason = " ".join([n for n in (p3_res.processing_notes or []) if "Non-document" in n or "rejected" in n]) or "Non-document surface detected. Please place the answer sheet flat inside the camera frame."
                return {
                    "qualityStatus": "RESCAN_REQUIRED",
                    "blurDetected": False,
                    "sharpness": 0.0,
                    "sharpness_raw": 0.0,
                    "sharpness_score": 0.0,
                    "document_score": 0.0,
                    "detected": False,
                    "corners": None,
                    "warped_image": None,
                    "orientation": "NORMAL",
                    "pageDetected": False,
                    "cropReady": False,
                    "ocrReadiness": "FAILED",
                    "reason": reason,
                    "processedImageUrl": None,
                    "ocrText": "",
                    "output_width": 0,
                    "output_height": 0,
                    "source_width": int(w_img),
                    "source_height": int(h_img),
                }

            # Document / page validity gate (Step 2A): prevent unresolvable/non-document inputs from reaching Phase 5
            if p3_res.status == "AMBIGUOUS_UNWARPED":
                notes_text = " ".join(p3_res.processing_notes or [])
                has_credible_page = (
                    "Phase 2.13 arbitration result: AMBIGUOUS" in notes_text
                    or "Branch C entered: AMBIGUOUS" in notes_text
                )

                if has_credible_page:
                    preview_url = None
                    sharpness_score = 0.0
                    blur_flagged = False
                    if p3_res.scanned_image is not None and p3_res.scanned_image.size > 0:
                        img_bgr = p3_res.scanned_image
                        gray_img = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
                        lap_var = float(cv2.Laplacian(gray_img, cv2.CV_64F).var())
                        sharpness_score, blur_flagged = compute_sharpness_score(lap_var)

                        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                        success, encoded_buf = cv2.imencode(".jpg", img_bgr, encode_params)
                        if success:
                            b64_str = base64.b64encode(encoded_buf.tobytes()).decode("ascii")
                            preview_url = f"data:image/jpeg;base64,{b64_str}"

                    out_w = int(img_bgr.shape[1]) if p3_res.scanned_image is not None else 0
                    out_h = int(img_bgr.shape[0]) if p3_res.scanned_image is not None else 0
                    return {
                        "qualityStatus": "HUMAN_REVIEW",
                        "blurDetected": blur_flagged,
                        "sharpness": sharpness_score,
                        "sharpness_raw": lap_var,
                        "sharpness_score": sharpness_score,
                        "document_score": sharpness_score,
                        "detected": True,
                        "corners": p3_res.source_corners.tolist() if getattr(p3_res, "source_corners", None) is not None else None,
                        "warped_image": preview_url,
                        "orientation": "NORMAL",
                        "pageDetected": False,
                        "cropReady": False,
                        "ocrReadiness": "UNCLEAR",
                        "reason": "Document detected, but page boundaries could not be reliably resolved. Human verification required.",
                        "processedImageUrl": preview_url,
                        "ocrText": "",
                        "output_width": out_w,
                        "output_height": out_h,
                        "source_width": int(w_img),
                        "source_height": int(h_img),
                    }
                else:
                    return {
                        "qualityStatus": "RESCAN_REQUIRED",
                        "blurDetected": False,
                        "sharpness": 0.0,
                        "sharpness_raw": 0.0,
                        "sharpness_score": 0.0,
                        "document_score": 0.0,
                        "detected": False,
                        "corners": None,
                        "warped_image": None,
                        "orientation": "NORMAL",
                        "pageDetected": False,
                        "cropReady": False,
                        "ocrReadiness": "FAILED",
                        "reason": "No document detected. Please ensure the answer sheet is clearly visible within the camera viewfinder.",
                        "processedImageUrl": None,
                        "ocrText": "",
                        "output_width": 0,
                        "output_height": 0,
                        "source_width": int(w_img),
                        "source_height": int(h_img),
                    }

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
                "sharpness_raw": 0.0,
                "sharpness_score": 0.0,
                "document_score": 0.0,
                "detected": False,
                "corners": None,
                "warped_image": None,
                "orientation": "NORMAL",
                "pageDetected": False,
                "cropReady": False,
                "ocrReadiness": "FAILED",
                "reason": "Unable to detect page boundaries. Please place the answer sheet flat within the camera frame.",
                "processedImageUrl": None,
                "ocrText": "",
                "output_width": 0,
                "output_height": 0,
                "source_width": int(w_img),
                "source_height": int(h_img),
            }

        # -------------------------------------------------------------------
        # STEP 2: Quality Assessment (Phase 5)
        doc_box = None
        if p3_res.status == "DESKEWED_FRAME_LIMITED" and p3_res.framing_metadata:
            doc_box = p3_res.framing_metadata.get("selected_box")

        p5_res = assess_document_quality(
            rectified_gray,
            document_id,
            document_box=doc_box,
            scanner_status=p3_res.status,
        )
        laplacian_var = float(p5_res.evidence_profile.diagnostic_laplacian_variance)
        sharpness_score, blur_flagged = compute_sharpness_score(laplacian_var)

        # Fatal defect check for blur
        is_blur_fatal = any(d.defect_code in ("FATAL_OPTICAL_DEFOCUS", "OPTICAL_DEFOCUS", "MOTION_BLUR") for d in p5_res.fatal_defects)
        blur_detected = blur_flagged or is_blur_fatal

        # -------------------------------------------------------------------
        # STEP 3: Auto-Correction & Rollback (Phase 6)
        # -------------------------------------------------------------------
        p6_res = execute_intelligent_correction(
            raw_rectified_bgr=rectified_bgr,
            initial_assessment=p5_res,
        )

        # -------------------------------------------------------------------
        # -------------------------------------------------------------------
        # STEP 4: Rescan Decision Engine (Phase 7) & Usability Arbitration
        # -------------------------------------------------------------------
        p7_res = evaluate_rescan_decision(
            document_input=p6_res.final_safe_state,
            final_quality_assessment=p6_res.quality_assessment_final,
            image_name=document_id,
        )

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

        # Encode verified rectified color image as JPEG Base64 Data URI
        processed_image_url: Optional[str] = None
        color_candidate: Optional[np.ndarray] = None

        if p8_res is not None and hasattr(p8_res, "image_bundle") and p8_res.image_bundle is not None:
            ready_bgr = getattr(p8_res.image_bundle, "ready_bgr", None)
            if isinstance(ready_bgr, np.ndarray) and ready_bgr.size > 0:
                color_candidate = ready_bgr

        if color_candidate is None and p6_res is not None and hasattr(p6_res, "final_safe_state") and p6_res.final_safe_state is not None:
            raw_bgr = getattr(p6_res.final_safe_state, "raw_rectified_bgr", None)
            if isinstance(raw_bgr, np.ndarray) and raw_bgr.size > 0:
                color_candidate = raw_bgr
            else:
                image_bgr = getattr(p6_res.final_safe_state, "image_bgr", None)
                if isinstance(image_bgr, np.ndarray) and image_bgr.size > 0:
                    color_candidate = image_bgr

        if color_candidate is None:
            color_candidate = rectified_bgr

        # -------------------------------------------------------------------
        # HACKATHON USABILITY RULE:
        # A) Severely blurred & unreadable -> RESCAN_REQUIRED
        # B) Slightly imperfect but text readable -> light enhance -> ACCEPT (PASSED)
        # -------------------------------------------------------------------
        is_severely_blurred = laplacian_var < 35.0 or (sharpness_score < 40.0 and is_blur_fatal)
        is_severe_truncation = any(
            d.defect_code in ("FATAL_TEXT_CLIPPED", "SEVERE_TEXT_CLIPPING", "FATAL_BOUNDARY_CLIPPING")
            for d in getattr(p5_res, "fatal_defects", [])
        )

        if is_severely_blurred:
            quality_status = "RESCAN_REQUIRED"
            reason = "Document image is severely blurred and unreadable. Please hold steady and recapture."
            blur_detected = True
        elif is_severe_truncation:
            quality_status = "RESCAN_REQUIRED"
            reason = "Position page fully inside camera viewfinder to prevent boundary clipping."
        elif not crop_ready or not page_detected:
            quality_status = "RESCAN_REQUIRED"
            reason = "No valid document detected. Please place the answer sheet flat inside the camera viewfinder."
        else:
            # Usable document with readable text: apply light enhancement if slightly blurry or low-contrast
            if laplacian_var < 85.0 or sharpness_score < 70.0:
                try:
                    if color_candidate is not None and color_candidate.size > 0:
                        blurred_ref = cv2.GaussianBlur(color_candidate, (0, 0), 1.5)
                        color_candidate = cv2.addWeighted(color_candidate, 1.25, blurred_ref, -0.25, 0)
                except Exception:
                    pass

            quality_status = "PASSED"
            reason = None
            blur_detected = False

        if color_candidate is not None:
            encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
            success, encoded_buf = cv2.imencode(".jpg", color_candidate, encode_params)
            if success:
                b64_str = base64.b64encode(encoded_buf.tobytes()).decode("ascii")
                processed_image_url = f"data:image/jpeg;base64,{b64_str}"

        corners_list = (
            p3_res.source_corners.tolist()
            if getattr(p3_res, "source_corners", None) is not None
            else None
        )

        out_w = int(color_candidate.shape[1]) if color_candidate is not None else 0
        out_h = int(color_candidate.shape[0]) if color_candidate is not None else 0

        return {
            "qualityStatus": quality_status,
            "blurDetected": blur_detected,
            "sharpness": sharpness_score,
            "sharpness_raw": laplacian_var,
            "sharpness_score": sharpness_score,
            "document_score": sharpness_score if quality_status == "PASSED" else 0.0,
            "detected": page_detected,
            "corners": corners_list,
            "warped_image": processed_image_url,
            "orientation": orientation_str,
            "pageDetected": page_detected,
            "cropReady": crop_ready,
            "ocrReadiness": ocr_readiness,
            "reason": reason,
            "processedImageUrl": processed_image_url,
            "ocrText": "",
            "output_width": out_w,
            "output_height": out_h,
            "source_width": int(w_img),
            "source_height": int(h_img),
        }

    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass
