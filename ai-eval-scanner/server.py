"""
ai-eval-scanner/server.py

Lightweight HTTP microservice exposing the AI-EVAL computer vision pipeline
to Shiva's EvalNexa frontend Control Center and backend ingestion services.

Endpoints:
- GET  /health        -> Health check (fast status ping, < 50ms)
- POST /process-page  -> Page image analysis, deskew, quality assessment, and OCR readiness

Port: 8000 (configurable via PORT environment variable)
CORS: Fully enabled for cross-origin browser requests (localhost:5173, etc.)
"""

from __future__ import annotations

import os
import sys
import logging
from typing import Any, Dict

from flask import Flask, request, jsonify

# Ensure local scanner modules are importable
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from pipeline import process_image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ai_eval_scanner")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# CORS Configuration (Allows Browser Clients to Call http://localhost:8000)
# ---------------------------------------------------------------------------
@app.after_request
def apply_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-INGESTION-KEY, X-API-KEY"
    return response


# ---------------------------------------------------------------------------
# Health Check Endpoint: GET /health
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health_check():
    """
    Returns predictable JSON indicating scanner service availability.
    Consumed by apps/control-center/src/lib/scanningIntegration.ts:checkScanningServiceHealth()
    """
    return jsonify({
        "status": "ok",
        "service": "AI-EVAL-OpenCV Scanner Service",
        "version": "1.0.0",
    }), 200


# ---------------------------------------------------------------------------
# Page Processing Endpoint: POST /process-page
# ---------------------------------------------------------------------------
@app.route("/process-page", methods=["POST", "OPTIONS"])
def handle_process_page():
    """
    Accepts multipart/form-data with:
    - file: Binary image file (required)
    - pageNumber: String or int (required)
    - examId: String (optional)
    - answerBookCode: String (optional)

    Returns JSON conforming to EvalNexa's ProcessPageResult interface.
    """
    if request.method == "OPTIONS":
        return ("", 204)

    # 1. Validate 'file' presence
    if "file" not in request.files:
        logger.warning("Rejected /process-page: Missing 'file' form field")
        return jsonify({
            "status": "error",
            "message": "Missing required 'file' field in multipart payload",
        }), 400

    file_obj = request.files["file"]
    if not file_obj or file_obj.filename == "":
        logger.warning("Rejected /process-page: Empty filename or file object")
        return jsonify({
            "status": "error",
            "message": "Provided file is empty",
        }), 400

    # 2. Extract metadata fields
    page_num_str = request.form.get("pageNumber", "1")
    exam_id = request.form.get("examId", "default_exam")
    answer_book_code = request.form.get("answerBookCode", "PENDING")

    try:
        page_number = int(page_num_str)
    except (ValueError, TypeError):
        page_number = 1

    doc_id = f"{answer_book_code}_pg{page_number}"
    logger.info(f"Processing page: doc_id={doc_id}, exam_id={exam_id}, filename={file_obj.filename}")

    # 3. Read raw image bytes
    try:
        image_bytes = file_obj.read()
        if len(image_bytes) < 16:
            return jsonify({
                "status": "error",
                "message": "Image payload is empty or too small",
            }), 400
    except Exception as e:
        logger.error(f"Failed to read image stream: {e}")
        return jsonify({
            "status": "error",
            "message": "Failed to read image byte stream",
        }), 400

    # 4. Execute AI-EVAL Computer Vision Pipeline
    try:
        diagnostics = process_image(
            image_input=image_bytes,
            document_id=doc_id,
            page_number=page_number,
            exam_id=exam_id,
            answer_book_code=answer_book_code,
        )

        logger.info(
            f"Successfully processed {doc_id}: "
            f"status={diagnostics['qualityStatus']}, "
            f"sharpness={diagnostics['sharpness']}, "
            f"blur={diagnostics['blurDetected']}, "
            f"pageDetected={diagnostics['pageDetected']}"
        )

        # Return JSON directly compatible with ProcessPageResult in scanningIntegration.ts
        return jsonify(diagnostics), 200

    except ValueError as val_err:
        logger.warning(f"Validation error processing {doc_id}: {val_err}")
        return jsonify({
            "status": "error",
            "message": str(val_err),
        }), 400

    except Exception as err:
        logger.error(f"Internal error processing {doc_id}: {err}", exc_info=True)
        # Never expose Python stack traces or filesystem paths to client
        return jsonify({
            "status": "error",
            "message": "Image processing pipeline error occurred",
        }), 500


def main():
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    logger.info("=" * 70)
    logger.info(f"Starting AI-EVAL Scanner Service on http://{host}:{port}")
    logger.info("Endpoints: GET /health | POST /process-page")
    logger.info("=" * 70)
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
