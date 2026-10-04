# AI-EVAL-OpenCV Scanner Integration Service for EvalNexa

This directory contains the production-integrated **AI-EVAL-OpenCV Scanner Service**, providing real-time computer vision processing, page detection, perspective rectification, quality assessment, auto-correction, and OCR readiness preparation for Shiva's **EvalNexa** platform.

---

## 1. Architectural Role

* **EvalNexa (Main Backend & Applications):** Owns MongoDB, authentication (JWT/RBAC), Cloudinary media persistence, examination rubrics, examiner evaluation workspaces, and realtime notifications (Socket.IO).
* **AI-EVAL Scanner Service (Port 8000):** A stateless Python/OpenCV microservice executing frozen Phases 2 through 9. It receives raw camera/scanner frames, performs geometric and quality verification, and returns diagnostic results conforming strictly to `apps/control-center/src/lib/scanningIntegration.ts`.

---

## 2. Frozen Computer Vision Pipeline Flow

```text
Incoming Image (Multipart Form-Data)
           │
           ▼
Phase 2: Document Region Boundary Detection
           │
           ▼
Phase 3: Perspective Transformation & Rectification
           │
           ▼
Phase 4: Illumination & Baseline Contrast Enhancement
           │
           ▼
Phase 5: Production Quality Assessment (Laplacian Variance, Glare, Stroke Delta)
           │
           ▼
Phase 6: Defect Remediation with Rejection Rollback
           │
           ▼
Phase 7: Rescan Decision Engine (Non-Compensatory Fatal Veto Gating)
           │
           ▼
Phase 8: OCR/HTR Readiness & Orientation Normalization
           │
           ▼
JSON Diagnostics Response (ProcessPageResult)
```

---

## 3. API Contract

### Health Check: `GET /health`
* **Response (HTTP 200):**
  ```json
  {
    "status": "ok",
    "service": "AI-EVAL-OpenCV Scanner Service",
    "version": "1.0.0"
  }
  ```

### Process Page: `POST /process-page`
* **Content-Type:** `multipart/form-data`
* **Form Fields:**
  * `file`: Binary image file (**Required**)
  * `pageNumber`: Page number string/int (**Required**)
  * `examId`: Target exam identifier (**Optional**)
  * `answerBookCode`: Docket code (**Optional**)
* **Response (HTTP 200 - PASSED):**
  ```json
  {
    "qualityStatus": "PASSED",
    "blurDetected": false,
    "sharpness": 99.5,
    "orientation": "NORMAL",
    "pageDetected": true,
    "cropReady": true,
    "ocrReadiness": "READY",
    "reason": null,
    "processedImageUrl": null,
    "ocrText": ""
  }
  ```
* **Response (HTTP 200 - RESCAN_REQUIRED):**
  ```json
  {
    "qualityStatus": "RESCAN_REQUIRED",
    "blurDetected": true,
    "sharpness": 24.3,
    "orientation": "NORMAL",
    "pageDetected": true,
    "cropReady": true,
    "ocrReadiness": "FAILED",
    "reason": "Optical defocus or severe motion blur detected. Recapture with steady focus.",
    "processedImageUrl": null,
    "ocrText": ""
  }
  ```
* **Error Responses:**
  * `HTTP 400`: Missing file or corrupt/unsupported image payload.
  * `HTTP 500`: Pipeline exception (internal details hidden from browser).

---

## 4. Setup & Running the Scanner

### Prerequisites
* Python 3.10+
* Virtual environment with required packages:
  ```bash
  pip install -r requirements.txt
  ```

### Starting the Service
From the repository root:
```bash
# Via pnpm
pnpm scanner

# Or directly with Python
python ai-eval-scanner/server.py
```
The service will start on `http://localhost:8000`.

### Running Integration Tests
```bash
python ai-eval-scanner/test_scanner_integration.py
```
