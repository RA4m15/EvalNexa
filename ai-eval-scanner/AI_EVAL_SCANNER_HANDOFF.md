# AI-EVAL OpenCV Scanner — Final Integration & Frontend Handoff Guide

**Target Audience:** Shiva Soni (EvalNexa Lead Engineer) & EvalNexa Integration Team  
**Repository:** `C:\Users\bunde\OneDrive\Desktop\EvalNexa`  
**Working Branch:** `ai-eval-opencv-integration`  
**Latest Verified Commit:** `beff158` (`fix: resolve fatal defect scanner integration`)  
**Service Location:** `ai-eval-scanner/`  
**Service Endpoint:** `http://localhost:8000`  

---

## 1. PURPOSE

The **AI-EVAL Scanner** is the dedicated, Python/OpenCV-based computer vision service integrated directly into the **EvalNexa** platform. Its primary purpose is to provide real-time, automated document preprocessing for handwritten examination answer sheets, including:

- Page boundary localization and contour isolation
- Four-corner ordering, perspective rectification, and deskewing
- Illumination balancing and shadow normalization
- Production quality verification (detecting defocus, blur, text clipping, and specular glare)
- Non-destructive image remediation with automated rollback guardrails
- Multi-tier rescan decision enforcement (`PASSED` vs. `RESCAN_REQUIRED`)
- OCR/HTR readiness profiling and reading orientation normalization

---

## 2. FINAL ARCHITECTURE

```text
EvalNexa (MAIN REPOSITORY & CORE PLATFORM)
│
├── Existing Frontend Applications
│   ├── apps/control-center      <-- Scan Center (Upload/Capture UI)
│   ├── apps/examiner            <-- Evaluation Workspace
│   └── apps/moderation          <-- Quality & Score Audit
│
├── Existing Node/Express Backend (Port 5000)
├── Existing MongoDB Database    (Exam, User, AnswerBook metadata)
├── Existing Cloudinary Media    (Permanent image storage)
├── Existing Auth / RBAC         (JWT, Permissions)
├── Existing Socket.IO Gateway   (Real-time notifications)
│
└── ai-eval-scanner/             <-- PYTHON / OPENCV SCANNER COMPONENT (Port 8000)
      ├── server.py              <-- Flask HTTP microservice
      ├── pipeline.py            <-- Lightweight pipeline wrapper
      └── phase2 → phase9        <-- Frozen computer vision engine
```

### Architectural Boundaries & Principles
1. **EvalNexa Remains the Master Application:** EvalNexa owns all database entities, examination rules, user permissions, grading rubrics, and cloud asset storage (Cloudinary).
2. **AI-EVAL is a Stateless Vision Service:** AI-EVAL does **not** create a second backend, database, auth system, or Cloudinary connection. It receives image frames, processes them in memory, and returns diagnostic results.
3. **No Architecture Duplication:** All permanent persistence and downstream evaluation remain with EvalNexa.

---

## 3. FOLDER STRUCTURE

The integrated `ai-eval-scanner/` directory inside `EvalNexa` contains:

```text
ai-eval-scanner/
├── server.py                     # Flask HTTP service exposing /health and /process-page (Port 8000)
├── pipeline.py                   # High-level pipeline controller connecting Phases 2–8 to EvalNexa
├── requirements.txt              # Python runtime dependencies (opencv, numpy, flask, matplotlib)
├── README.md                     # Technical service specification and quickstart instructions
├── test_scanner_integration.py   # Regression & integration test suite (6 verified tests)
│
├── phase2/                       # Phase 2: Page region boundary segmentation & contour isolation
├── phase3/                       # Phase 3: Corner ordering, deskewing & perspective rectification
├── phase4/                       # Phase 4: Contrast normalization & illumination compensation
├── phase5/                       # Phase 5: Production quality gate (Laplacian variance, glare, clipping)
├── phase6/                       # Phase 6: Intelligent auto-correction engine with rollback guardrails
├── phase7/                       # Phase 7: Multi-tier rescan decision engine (non-compensatory vetoes)
├── phase8/                       # Phase 8: OCR/HTR readiness verification & orientation normalization
├── phase9/                       # Phase 9: Multi-factor human-in-the-loop review routing framework
│
├── images/                       # Authentic evaluation documents
│   ├── answer_sheet.jpg          # Boundary-clipped form (triggers RESCAN_REQUIRED)
│   ├── answer_sheet_2.png        # Pristine examination sheet (PASSED baseline)
│   ├── answer_sheet_3.jpg        # Cast-shadow document (auto-normalized to PASSED)
│   ├── answer_sheet_4.jpg        # Severe defocus & clipped document (RESCAN_REQUIRED)
│   ├── answer_sheet_5.jpg        # Frame-filling boundary clipped sheet (RESCAN_REQUIRED)
│   └── dataset_samples/          # 30 authentic 224x224 student handwriting patches
│
├── phase10/                      # Phase 10 integration verification
│   └── PHASE10_BUGFIX_REPORT.md  # Audit report of line 175 fatal defect patch (Commit beff158)
│
└── phase11/                      # Phase 11 testing and reliability
    └── PHASE11_BASELINE_RELIABILITY_REPORT.md # 35-image end-to-end baseline audit report
```

---

## 4. SETUP & STARTUP COMMANDS

### Prerequisites
- Python 3.10+ (tested on Python 3.14.6)
- Node.js & pnpm (standard EvalNexa development toolchain)

### 1. Install Scanner Dependencies
From the root of the `EvalNexa` repository:
```bash
pip install -r ai-eval-scanner/requirements.txt
```

### 2. Start the Scanner Service
You can start the scanner using either `pnpm` or `python` directly:

**Option A — Via pnpm (Recommended):**
```bash
pnpm scanner
```

**Option B — Directly with Python:**
```bash
python ai-eval-scanner/server.py
```

The service binds to `http://0.0.0.0:8000` (configurable via `PORT` environment variable).

### 3. Verify Integration Tests
Before connecting the frontend, verify the scanner test suite passes:
```bash
python ai-eval-scanner/test_scanner_integration.py
```
Expected output:
```text
ALL 6 TESTS PASSED SUCCESSFULLY!
```

---

## 5. HEALTH API CONTRACT

### `GET /health`
A lightweight endpoint consumed by the frontend to confirm service availability before uploading pages.

- **Request:** `GET http://localhost:8000/health`
- **Response Headers:** `Content-Type: application/json`, `Access-Control-Allow-Origin: *`
- **Status:** `200 OK`
- **Response Body:**
  ```json
  {
    "status": "ok",
    "service": "AI-EVAL-OpenCV Scanner Service",
    "version": "1.0.0"
  }
  ```

---

## 6. PROCESS PAGE API CONTRACT

### `POST /process-page`
Processes an uploaded or captured answer sheet frame through the full computer vision pipeline.

- **URL:** `http://localhost:8000/process-page`
- **Method:** `POST` (supports `OPTIONS` for browser CORS preflight)
- **Content-Type:** `multipart/form-data`

#### Multipart Form Fields
| Field Name | Type | Requirement | Description |
|:---|:---|:---:|:---|
| `file` | Binary File | **Required** | The raw image file (`image/jpeg`, `image/png`, `image/webp`). |
| `pageNumber` | String / Int | **Required** | Page sequence number (e.g. `1`, `"1"`). |
| `examId` | String | *Optional* | Exam identifier (defaults to `"default_exam"`). |
| `answerBookCode` | String | *Optional* | Answer booklet / docket code (defaults to `"PENDING"`). |

#### Verified Response Fields (JSON)
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

| Field Name | Type | Value Range | Meaning |
|:---|:---|:---|:---|
| `qualityStatus` | string | `"PASSED"` \| `"RESCAN_REQUIRED"` | Overall quality decision. |
| `blurDetected` | boolean | `true` \| `false` | True if optical defocus, motion blur, or low variance detected. |
| `sharpness` | number | `0.0` – `100.0` | Normalized acutance / clarity score based on Laplacian variance. |
| `orientation` | string | `"NORMAL"`, `"ROTATED_90_CW"`, `"INVERTED_180"`, `"ROTATED_270_CCW"`, `"AMBIGUOUS"` | Detected text reading orientation. |
| `pageDetected` | boolean | `true` \| `false` | True if document boundaries were successfully localized. |
| `cropReady` | boolean | `true` \| `false` | True if perspective transform produced a clean rectified document. |
| `ocrReadiness` | string | `"READY"`, `"UNCLEAR"`, `"FAILED"` | Downstream OCR/HTR readability readiness assessment. |
| `reason` | string \| null | Actionable text or `null` | Operator guidance if rescan is required; `null` if passed. |
| `processedImageUrl` | null | `null` | Currently `null`. The scanner does not upload to Cloudinary. |
| `ocrText` | string | `""` | Currently empty string. OCR extraction is not executed here. |

> **Important Implementation Fact:** `processedImageUrl` is currently returned as `null` by the scanner. Cloudinary media storage is handled by the EvalNexa Node.js backend when finalizing a docket, NOT by this microservice.

---

## 7. RESPONSE BEHAVIOR & DECISION SEMANTICS

### When `qualityStatus == "PASSED"`
- The document satisfies all geometric, contrast, and sharpness gates.
- Zero fatal defects were triggered.
- If shadow was present (like `answer_sheet_3.jpg`), Phase 6 auto-correction safely normalized it.
- **Frontend Action:** The page can be accepted into the booklet docket and proceed to the next page or finalization.

### When `qualityStatus == "RESCAN_REQUIRED"`
- The scanner intercepted a critical defect that would corrupt evaluation (e.g. optical defocus, text clipped by sensor boundary, finger/border occlusion, or severe specular glare).
- Or the page exhibits borderline stroke contrast requiring human review.
- **Frontend Action:** The page is rejected from automated acceptance. The UI alerts the operator with the specific guidance provided in `reason`.

### The `reason` Field
The scanner delivers context-specific operator instructions derived directly from Phase 7 triggers:
- **Boundary Clipping:** *"Position page fully inside camera viewfinder to prevent boundary clipping."*
- **Optical Defocus:** *"Optical defocus or severe motion blur detected. Recapture with steady focus."*
- **Specular Glare:** *"Turn off direct overhead flash or adjust page angle to eliminate specular glare."*
- **Margin Occlusion:** *"Remove fingers, clips, or foreign obstructions from the document margins."*
- **Human Review / Faint Ink:** *"Human review required. Do not rescan unless handwriting is unreadable."*

> **Enum Alignment Note:** Internally, AI-EVAL Phase 7 has three routing outcomes: `CONTINUE`, `RESCAN_REQUIRED`, and `HUMAN_REVIEW`. Because the current EvalNexa frontend contract (`@evalnexa/types`) supports `PASSED`, `RESCAN_REQUIRED`, and `PENDING`, the scanner safely maps `CONTINUE` $ightarrow$ `PASSED` and all non-CONTINUE outcomes $ightarrow$ `RESCAN_REQUIRED`. Do not add `HUMAN_REVIEW` to the frontend until Phase 12.

---

## 8. EXISTING EVALNEXA FRONTEND INTEGRATION

The frontend integration code already exists inside the repository at:  
[`apps/control-center/src/lib/scanningIntegration.ts`](file:///C:/Users/bunde/OneDrive/Desktop/EvalNexa/apps/control-center/src/lib/scanningIntegration.ts)

### How It Works

1. **Default Service URL:**
   ```typescript
   const DEFAULT_SCANNING_SERVICE_URL =
     (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_SCANNING_SERVICE_URL) ||
     'http://localhost:8000';
   ```
2. **Health Check Function (`checkScanningServiceHealth`):**
   - Calls `GET http://localhost:8000/health` with a 1,800 ms timeout.
   - Used by `ScanCenterPage.tsx` on mount to display service status badge:
     - `OPENCV SERVICE: CONNECTED (PORT 8000)` if available.
     - `STANDALONE ADAPTER` if offline.
3. **Capture Processing Function (`processPageWithOpenCVService`):**
   - Packages image `Blob`, `pageNumber`, `examId`, and `answerBookCode` into `FormData`.
   - Sends `POST http://localhost:8000/process-page` with an 8,000 ms timeout (`AbortController`).
   - Parses the JSON response into `PageQualityDiagnostics`.
4. **Fallback Mechanism:**
   - If the scanner service is offline or unreachable, `processPageWithOpenCVService` returns `serviceAvailable: false`.
   - `ScanCenterPage.tsx` automatically falls back to client-side HTML5 Canvas Laplacian blur analysis (`analyzePageWithCanvas`) so scanning is never completely blocked.

---

## 9. STEP-BY-STEP FRONTEND CONNECTION GUIDE FOR SHIVA

Follow this practical sequence to test end-to-end scanning:

### Step 1: Start the Backend & Database
In Terminal 1 (EvalNexa repository root):
```bash
pnpm dev:backend
```
Ensure MongoDB is running and connected.

### Step 2: Start the AI-EVAL Scanner
In Terminal 2 (EvalNexa repository root):
```bash
pnpm scanner
```
Confirm the console output:
```text
Starting AI-EVAL Scanner Service on http://0.0.0.0:8000
Endpoints: GET /health | POST /process-page
```

### Step 3: Start the Control Center Frontend
In Terminal 3 (EvalNexa repository root):
```bash
pnpm dev:control-center
```
The frontend will open on `http://localhost:5173` (or configured Vite port).

### Step 4: Open the Scan Center
1. Navigate to `/scanning` (or click **Scan Center** in the navigation bar).
2. Look at the top status bar: verify the green badge displays:
   `OPENCV SERVICE: CONNECTED (PORT 8000)`.

### Step 5: Test a Clean Page (Expect `PASSED`)
1. In Step 1 of Scan Center, select an exam and enter an answer booklet code.
2. In Step 2 (Capture/Upload), upload `ai-eval-scanner/images/answer_sheet_2.png` or `answer_sheet_3.jpg`.
3. Check Terminal 2: Confirm `server.py` logs `POST /process-page` with HTTP 200.
4. Check Step 3 (Quality & Blur) in the UI:
   - Status badge shows green `PASSED`.
   - Sharpness score displays (e.g. `99.5`).
   - Click **Accept Page & Continue** $ightarrow$ Advances to next page.

### Step 6: Test a Defective Page (Expect `RESCAN_REQUIRED`)
1. Upload `ai-eval-scanner/images/answer_sheet_4.jpg` (defocused) or `answer_sheet.jpg` (boundary clipped).
2. Check Step 3 (Quality & Blur) in the UI:
   - Status badge shows red `RESCAN REQUIRED`.
   - Blur warning is flagged.
   - Operator guidance alert displays the specific reason message.
   - The UI prevents acceptance of the unreadable page.

---

## 10. COMPUTER VISION PIPELINE (PHASES 2–9)

All core image processing logic resides in frozen Python modules:

- **Phase 2 (`phase2/`):** Document region boundary detection, morphological contour tracking, and page isolation.
- **Phase 3 (`phase3/`):** Multi-signal corner detection (Harris + Shi-Tomasi), corner ordering, homography perspective transform, and deskewing.
- **Phase 4 (`phase4/`):** Illumination balancing, shadow gradient compensation, and contrast enhancement.
- **Phase 5 (`phase5/`):** Multi-dimensional production quality assessment (Laplacian sharpness variance, stroke darkness delta, margin clipping, specular glare collision).
- **Phase 6 (`phase6/`):** Intelligent auto-correction engine with non-destructive candidate state rollback.
- **Phase 7 (`phase7/`):** Production rescan decision engine enforcing non-compensatory fatal defect vetoes.
- **Phase 8 (`phase8/`):** OCR/HTR readiness classification, reading orientation detection (0°, 90°, 180°, 270°), and standardized image representations.
- **Phase 9 (`phase9/`):** Multi-factor human-in-the-loop review routing and ambiguity scoring.

> **CRITICAL RULE:** Phases 2 through 9 are **FROZEN**. Do NOT alter any algorithms, thresholds, weights, or decision trees inside these directories during frontend integration.

---

## 11. SUMMARY OF PHASE 10 INTEGRATION WORK

The following milestones were completed and verified in commit `beff158`:
1. **Integrated Copy Created:** All AI-EVAL modules, images, and tests were integrated directly into `EvalNexa/ai-eval-scanner/`.
2. **Standard API Wrapper Built:** `pipeline.py` and `server.py` were implemented to directly satisfy `apps/control-center/src/lib/scanningIntegration.ts`.
3. **No Redundant Services:** Kept EvalNexa's single-backend architecture intact.
4. **Fatal Defect Field Bugfix:** Corrected attribute reference on line 175 of `pipeline.py` (`d.defect_type` $ightarrow$ `d.defect_code`), resolving an unhandled `AttributeError` on defective documents.
5. **Git Commit:** Committed and pushed to remote branch `origin/ai-eval-opencv-integration` under commit hash `beff158`.

---

## 12. PHASE 11 BASELINE PERFORMANCE SUMMARY

A rigorous end-to-end reliability baseline was established across all 35 project images through the live HTTP service:

| Metric | Verified Baseline Result |
|:---|:---|
| **Total Images Tested** | **35** (5 primary full pages + 30 handwriting patches) |
| **HTTP Success Rate** | **35 / 35 (100.0% HTTP 200 OK)** |
| **HTTP Failures / Timeouts** | **0** |
| **Runtime Exceptions / Crashes** | **0** |
| **Decision Distribution** | **16 `CONTINUE` (PASSED)**, **7 `RESCAN_REQUIRED`**, **12 `HUMAN_REVIEW`** |
| **Unexpected Decisions** | **0** (100% compliant with Phase 2–9 contracts) |
| **Overall Average Latency** | **774.7 ms** |
| **Primary Full-Page Average Latency** | **4,211.5 ms** (high-resolution full document processing) |
| **Handwriting Patch Average Latency** | **99.8 ms** (224x224 patch analysis) |

> **Context Note:** These latency figures represent baseline measurements under local development environments, not production SLA guarantees. The 30 dataset samples are 224x224 handwriting crops; they validate stroke quality and glare detection, but do not validate physical page boundary segmentation.

---

## 13. KNOWN LIMITATIONS & SCOPE CONSTRAINTS

1. **High-Resolution Latency:** Processing full-resolution pages (e.g. 1600x1200 uncompressed PNGs) requires 4–9 seconds due to multi-stage pixel convolutions and connected-component analysis. Set frontend fetch timeouts to $\ge 10	ext{ seconds}$ for production scans.
2. **Sub-Page Patches:** The 224x224 dataset crops lack external page borders on a background surface. In intake, Phase 2 falls back to full-frame intake (`cropReady=False`). This is expected for patch crops.
3. **No In-Service OCR:** The scanner verifies OCR *readiness* (`READY`, `UNCLEAR`, `FAILED`), but does not perform character recognition. The `ocrText` field is returned empty.
4. **`processedImageUrl` is Null:** The microservice does not upload images to Cloudinary. EvalNexa's Node.js backend handles Cloudinary uploads when saving the answer book.
5. **No Legal / Regulatory Certification:** This is an engineering computer vision pipeline, not a certified biometric or legal scanning appliance.

---

## 14. TROUBLESHOOTING GUIDE

| Issue | Root Cause | Solution |
|:---|:---|:---|
| **Status badge shows `STANDALONE ADAPTER`** | `server.py` is not running or port 8000 is occupied. | Run `pnpm scanner` in a separate terminal. Check if another process uses port 8000 (`netstat -ano \| findstr :8000`). |
| **`GET /health` Connection Refused** | Scanner service stopped or crashed. | Check the terminal running `server.py` for Python startup errors. Run `python ai-eval-scanner/test_scanner_integration.py` to diagnose. |
| **`POST /process-page` returns HTTP 400** | Missing `file` field in `FormData`, or file size $< 16	ext{ bytes}$. | Ensure the frontend appends `formData.append('file', blob, filename)`. Check that the camera capture produced a valid JPEG/PNG blob. |
| **Unexpected `RESCAN_REQUIRED` on capture** | Document border touches camera frame or severe glare is present. | Ensure the answer sheet is placed flat with all 4 corners visible against a contrasting desk background, and eliminate overhead reflections. |
| **Frontend Fetch Timeout (AbortError)** | High-resolution image processing exceeded the 8-second fetch timeout. | Increase the timeout in `scanningIntegration.ts` (e.g. from `8000` to `15000` ms) for high-resolution mobile camera captures. |

---

## 15. FINAL HANDOFF CHECKLIST FOR SHIVA

- [ ] **EvalNexa Node.js backend running** (`pnpm dev:backend` on port 5000)
- [ ] **EvalNexa Control Center running** (`pnpm dev:control-center` on port 5173)
- [ ] **AI-EVAL Scanner Service running** (`pnpm scanner` on port 8000)
- [ ] **Health endpoint verified** (`http://localhost:8000/health` returns `{"status":"ok", ...}`)
- [ ] **Scan Center displays connected status** (`OPENCV SERVICE: CONNECTED (PORT 8000)`)
- [ ] **Clean page upload (`answer_sheet_2.png`) returns `PASSED`** with green checkmark
- [ ] **Shadowed page upload (`answer_sheet_3.jpg`) returns `PASSED`** via auto-correction
- [ ] **Defective page upload (`answer_sheet_4.jpg`) returns `RESCAN_REQUIRED`** with operator guidance
- [ ] **Existing frontend allows accepted pages to advance into the booklet docket**

---

**AI-EVAL scanner integration is complete from the scanner/API side; remaining work is consumption of the existing scanner contract by the EvalNexa frontend.**
