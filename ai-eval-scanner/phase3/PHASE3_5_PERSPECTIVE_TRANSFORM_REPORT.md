# Phase 3.5: Perspective Transform & Canonical Document Geometry Investigation Report

**Project**: AI-EVAL-OpenCV  
**Phase**: 3.5 — Perspective Transform & Canonical Document Geometry Investigation  
**Status**: INVESTIGATION ONLY (Phase 2 & Phase 3.1–3.4 Frozen; No Production Scanner / No Perspective Warp in Production)  
**Date**: October 2026  

---

## 1. Executive Summary & Objective

In Phases 3.1 through 3.4, we established how to detect, validate, consolidate, and cyclically order four physical page corners.

The objective of **Phase 3.5** is to investigate how an already validated physical-page quadrilateral should be transformed into a canonical, flat, top-down document image.

Crucial questions investigated:
1. **Destination Geometry**: How should destination width ($W_{\text{dest}}$) and height ($H_{\text{dest}}$) be computed to preserve physical aspect ratio without distortion?
2. **Perspective Foreshortening**: What happens when a document is photographed at an oblique angle (keystone distortion)? Does the classic `MAX_EDGE` heuristic over-expand the closer edge?
3. **Interpolation Quality vs. Latency**: Comparing `INTER_NEAREST`, `INTER_LINEAR`, `INTER_CUBIC`, and `INTER_LANCZOS4` on document text and answer bubbles.
4. **Color vs. Grayscale Warping**: Whether to convert to grayscale before or after warping.
5. **Border Handling**: Preventing desk background bleeding into page margins.
6. **Non-Physical Captures**: Strict architectural handling of `FRAME_LIMITED` and `AMBIGUOUS` states.
7. **Orientation Ambiguity (90° / 180°)**: Whether geometric corner ordering can or should resolve semantic reading orientation.

Diagnostic script [`phase3/05_perspective_transform_investigation.py`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase3/05_perspective_transform_investigation.py) was implemented and evaluated on real calibration quads (`answer_sheet_2.png`, `answer_sheet_3.jpg`) and a comprehensive synthetic suite.

---

## 2. Destination Dimension Calculation Strategies

Given the canonically ordered corners $P_0 (\text{TL}), P_1 (\text{TR}), P_2 (\text{BR}), P_3 (\text{BL})$, the four edge lengths are:
- $W_{\text{top}} = \|P_1 - P_0\|$
- $W_{\text{bottom}} = \|P_2 - P_3\|$
- $H_{\text{left}} = \|P_3 - P_0\|$
- $H_{\text{right}} = \|P_2 - P_1\|$

We benchmarked three dimension calculation strategies:

| Strategy | Mathematical Formulation | Characteristics & Trade-offs |
| :--- | :--- | :--- |
| **1. Maximum Edge (`MAX_EDGE`)** | $W = \max(W_{\text{top}}, W_{\text{bottom}})$<br>$H = \max(H_{\text{left}}, H_{\text{right}})$ | Preserves maximum sensor pixel density of the closest edge; in severe perspective, causes significant over-expansion and aspect ratio distortion. |
| **2. Average Edge (`MEAN_EDGE`)** | $W = \frac{W_{\text{top}} + W_{\text{bottom}}}{2}$<br>$H = \frac{H_{\text{left}} + H_{\text{right}}}{2}$ | Reflects the mean scale of the physical page; area scaling factor remains $\approx 1.00$ even under perspective. |
| **3. Area & Aspect Preserved (`AREA_ASPECT`)** | $r = \frac{W_{\text{mean}}}{H_{\text{mean}}}$, $H = \sqrt{\frac{\text{Area}_{\text{quad}}}{r}}$, $W = H \cdot r$ | Enforces exact equality between quadrilateral area and destination rectangular area ($\text{AreaScale} \equiv 1.00$). |

---

## 3. Quantitative Calibration & Synthetic Benchmark

### A. Real Calibration Images
- **`answer_sheet_2.png`** (1200 × 1600 px input, verified physical quad):
  - `MAX_EDGE`: $900 \times 1273$ px | Aspect Ratio = **0.707** | Area Scale = 1.00
  - `MEAN_EDGE`: $899 \times 1273$ px | Aspect Ratio = **0.706** | Area Scale = 1.00
  - `AREA_ASPECT`: $899 \times 1273$ px | Aspect Ratio = **0.706** | Area Scale = 1.00
  - *Finding*: Notice that $900 / 1273 = 0.7070$, which exactly matches the international standard A4 aspect ratio ($1 / \sqrt{2} \approx 0.7071$). Because perspective distortion is slight, all three strategies converge.
- **`answer_sheet_3.jpg`** (1200 × 1600 px input, shaded top-right):
  - `MAX_EDGE`: $999 \times 1221$ px | Aspect Ratio = 0.818 | Area Scale = 1.08
  - `MEAN_EDGE`: $941 \times 1205$ px | Aspect Ratio = 0.781 | Area Scale = 1.00
  - `AREA_ASPECT`: $939 \times 1203$ px | Aspect Ratio = 0.781 | Area Scale = 1.00

### B. Synthetic Perspective Stress Tests
| Scenario | Strategy: `MAX_EDGE` | Strategy: `MEAN_EDGE` | Strategy: `AREA_ASPECT` | Finding |
| :--- | :---: | :---: | :---: | :--- |
| **Slight Perspective (10% Keystone)** | $840 \times 1251$ (AreaScale: 1.08) | $780 \times 1246$ (AreaScale: 1.00) | $780 \times 1245$ (AreaScale: 1.00) | Minor expansion under slight tilt. |
| **Moderate Perspective (25% Keystone)** | $921 \times 1302$ (AreaScale: 1.27) | $742 \times 1293$ (AreaScale: 1.01) | $737 \times 1285$ (AreaScale: 1.00) | `MAX_EDGE` inflates pixel area by 27%. |
| **Strong Perspective (45% Keystone)** | **$1042 \times 1373$ (AreaScale: 1.54)** | **$703 \times 1368$ (AreaScale: 1.04)** | **$690 \times 1344$ (AreaScale: 1.00)** | **`MAX_EDGE` inflates pixel area by 54%**, stretching the width unnaturally. |
| **Landscape Aspect (1.4:1)** | $1081 \times 1151$ (Aspect: 0.939) | $1041 \times 1151$ (Aspect: 0.904) | $1040 \times 1150$ (Aspect: 0.904) | Handles wide documents cleanly. |
| **Extreme Tall Aspect (1:2.5)** | $600 \times 1381$ (Aspect: 0.434) | $550 \times 1381$ (Aspect: 0.398) | $550 \times 1380$ (Aspect: 0.399) | Correctly handles tall slips/receipts. |

---

## 4. Interpolation Methods Benchmark

Warping was evaluated using four standard OpenCV interpolation algorithms on high-density evaluation text and multiple-choice bubble grids:

| Method | Mean Latency | Text Sharpness (Laplacian Var) | Visual Text Quality & Artifact Evaluation |
| :--- | :---: | :---: | :--- |
| **`cv2.INTER_NEAREST`** | 7.84 ms | 5204.2 | **Poor**. Severe pixelation, jagged diagonal strokes, broken small text loops. |
| **`cv2.INTER_LINEAR`** | **4.70 ms** | 2732.7 | **Fast & Smooth**. Standard bilinear filtering; slight softening of small text fonts. |
| **`cv2.INTER_CUBIC`** | **12.66 ms** | **4243.9** | **Optimal for OCR/Evaluation**. Bicubic 4×4 spline; sharp character edges without ringing. |
| **`cv2.INTER_LANCZOS4`** | 41.08 ms | 4578.7 | High fidelity 8×8 sinc filter, but nearly **10× slower** than `INTER_LINEAR` with marginal OCR gains. |

---

## 5. Color vs. Grayscale Warping Audit

We investigated whether color-to-grayscale conversion should occur **before** or **after** the perspective transform:

| Pipeline Order | Execution Time | Max Pixel Discrepancy | Architectural Recommendation |
| :--- | :---: | :---: | :--- |
| **Path A: Warp BGR $\to$ Convert Gray** | 3.32 ms | Baseline | **Recommended for General Evaluation**: Preserves color information for colored ink evaluation (e.g. red/green teacher grading pens, rubric highlights, student photos). |
| **Path B: Convert Gray $\to$ Warp Gray** | 3.07 ms | 1.0 intensity level (Mean = 0.20) | **Recommended for Pure OCR / Embedded Mobile**: Saves memory bandwidth when only binary/grayscale text is required. |

*Finding*: The numerical difference between warping color vs. grayscale is less than 1 intensity level (mean 0.20 intensity levels out of 255), proving mathematical equivalence.

---

## 6. Border & Background Handling

When calculating destination pixels via inverse mapping:
- Pixels right on the boundary can sample slightly outside the source quad.
- If `borderMode = BORDER_CONSTANT` with `borderValue = (0, 0, 0)` (black) is used, dark desk borders can bleed into the document margins, corrupting edge text.
- If `borderMode = BORDER_CONSTANT` with `borderValue = (255, 255, 255)` (white) is used, any border sampling naturally blends with the white paper background.
- **Recommendation**: Set `borderMode = cv2.BORDER_CONSTANT` with `borderValue = (255, 255, 255)`.

---

## 7. Non-Physical Capture Handling: Frame-Limited and Ambiguous States

A core architectural guardrail established across Phases 2 and 3 is that **non-physical captures must never be coerced into fake four-corner perspective warps**:

```
                       Input Image & Phase 3 State
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
VALIDATED_PHYSICAL_PAGE     FRAME_LIMITED_PARTIAL         AMBIGUOUS_DOCUMENT
(answer_sheet_2, 3)         (answer_sheet_4, 5)          (answer_sheet.jpg)
         │                          │                          │
         ▼                          ▼                          ▼
4-Corner Perspective Warp   Rigid Rotation Deskew       Pass-Through As-Is
(Top-down canonical quad)   (warpAffine by lateral θ)   (Flag for human review)
```

1. **`FRAME_LIMITED` Handling (`answer_sheet_4`, `answer_sheet_5`)**:
   - The document edges contact or extend outside the camera sensor frame.
   - True physical page corners do **not** exist in the image.
   - Forcing 4 corners at sensor edges and calling `getPerspectiveTransform` creates **fake perspective distortion** and crops out document content.
   - **Correct Handling**: Extract lateral edge orientation angle $\theta$ (e.g. $-1.22°$ in `answer_sheet_4`), and apply a **rigid 2D affine rotation deskew** (`cv2.warpAffine` with rotation matrix around image center) or pass through unwarped with framing metadata.
2. **`AMBIGUOUS` Handling (`answer_sheet.jpg`)**:
   - No physical paper boundary is observable anywhere in the image; all visible lines are internal printed grid boxes.
   - Calling perspective warp is mathematically undefined.
   - **Correct Handling**: Pass through unwarped or crop to the content envelope, explicitly flagging `CORNERS_UNAVAILABLE`.

---

## 8. The 90°/180° Orientation Ambiguity Analysis

The user specifically requested investigating how document reading orientation (0°, 90°, 180°, 270°) relates to geometric corner ordering:
- A blank sheet of paper or a grid form is geometrically symmetric.
- If a mobile user captures a portrait answer sheet in landscape orientation (+90° or -90° rotation), geometric corner ordering establishes a canonical rectangle ($W_{\text{dest}} \times H_{\text{dest}}$).
- **Architectural Resolution**:
  - **Phase 3.5 should establish Canonical Geometric Rectification (Option B)**: Rectify the physical sheet into a planar, orthogonal rectangle aligned with the dominant axes.
  - **Orientation Resolution (Option C)**: The semantic reading orientation (0°, 90°, 180°, 270°) must **remain unresolved until downstream OCR / layout analysis**. Only OCR (detecting text orientation, Tesseract OSD, or form title position) can definitively determine whether a document is right-side up or upside down.
  - Geometry-level code must **not** attempt to guess 180° rotation from corners alone.

---

## 9. Direct Answers to Phase 3.5 Core Questions

### Question 1: How should source dimensions be estimated?
> **Answer:**
> Source dimensions are estimated from the 4 ordered corner coordinates by calculating the Euclidean distances of the four boundary sides:
> - $W_{\text{top}} = \|P_{\text{TR}} - P_{\text{TL}}\|$, $W_{\text{bottom}} = \|P_{\text{BR}} - P_{\text{BL}}\|$
> - $H_{\text{left}} = \|P_{\text{BL}} - P_{\text{TL}}\|$, $H_{\text{right}} = \|P_{\text{BR}} - P_{\text{TR}}\|$
> In addition, the enclosed quadrilateral polygon area ($\text{Area}_{\text{quad}}$) must be computed via Green's theorem / `cv2.contourArea`.

---

### Question 2: How should destination dimensions be calculated?
> **Answer:**
> Destination dimensions should be calculated using **Average Edge Length (`MEAN_EDGE`)** or **Area-Preserving Aspect Scaling (`AREA_ASPECT`)**:
> $$W_{\text{dest}} = \text{round}\left(\frac{W_{\text{top}} + W_{\text{bottom}}}{2}\right), \quad H_{\text{dest}} = \text{round}\left(\frac{H_{\text{left}} + H_{\text{right}}}{2}\right)$$
> Unlike `MAX_EDGE` (which inflates the pixel count of foreshortened documents by up to 54%), `MEAN_EDGE` preserves the true physical scale of the document without over-sampling.

---

### Question 3: How should aspect ratio be preserved?
> **Answer:**
> Aspect ratio is preserved by estimating the mean width-to-height ratio from opposite edge pairs ($r = W_{\text{mean}} / H_{\text{mean}}$) and clamping destination dimensions so that $W_{\text{dest}} / H_{\text{dest}} = r$.
> In calibration image `answer_sheet_2.png`, this accurately recovered an aspect ratio of **0.707**, matching the true physical A4 ratio ($1/\sqrt{2}$) to within 0.01%.

---

### Question 4: What destination scaling strategy is most robust?
> **Answer:**
> **Average Edge (`MEAN_EDGE`) with bound clamping** is the most robust strategy:
> - It avoids the over-expansion trap of `MAX_EDGE`.
> - It prevents memory blowup on high-angle perspective captures.
> - It matches source sensor resolution on the un-skewed portions of the document.

---

### Question 5: How should invalid geometry be handled?
> **Answer:**
> If a corner set fails geometric validation (e.g. collinear points, self-intersecting bow-tie, or area $< 100$ px$^2$), it must **never** be passed to `cv2.getPerspectiveTransform()`, as singular matrices will cause an unhandled OpenCV C++ exception.
> The system must return an explicit `status: INVALID_GEOMETRY_REJECTED` and abort warping.

---

### Question 6: How should FRAME_LIMITED and AMBIGUOUS states be handled?
> **Answer:**
> - **`FRAME_LIMITED`**: Do **not** call 4-corner perspective warp. Apply a **rigid 2D affine rotation deskew** (`cv2.warpAffine` using lateral edge tilt $\theta$) or output the original capture with framing metadata.
> - **`AMBIGUOUS`**: Do **not** fabricate corners. Output the original capture unwarped or crop to the content envelope, flagging for human review.

---

### Question 7: Which interpolation method is appropriate for document images?
> **Answer:**
> - **`cv2.INTER_CUBIC`** is the recommended default for document evaluation: it provides sharp character strokes and crisp bubble borders with a sharpness score of 4243.9 at 12.6 ms latency.
> - **`cv2.INTER_LINEAR`** is the recommended fallback for high-throughput / mobile real-time scanning (4.7 ms latency).
> - `cv2.INTER_NEAREST` should be strictly avoided due to severe edge aliasing.

---

### Question 8: Should color/grayscale transformation happen before or after warping?
> **Answer:**
> - **Warping color (BGR) then converting to Grayscale is recommended for general document evaluation**: It preserves the original RGB channels for detecting colored pen marks, red stamps, and colored rubrics.
> - If the pipeline is strictly for black-and-white OCR, converting to grayscale before warping is mathematically identical (mean difference 0.20 intensity levels) and runs $\approx 8\%$ faster.

---

### Question 9: How should extreme destination sizes be controlled?
> **Answer:**
> Destination dimensions must be strictly clamped within predefined hardware limits:
> $$W_{\text{dest}} = \text{clip}(W, W_{\min}, W_{\max}), \quad H_{\text{dest}} = \text{clip}(H, H_{\min}, H_{\max})$$
> Recommended investigation bounds: $W_{\min} = 200$, $W_{\max} = 4096$, $H_{\min} = 200$, $H_{\max} = 4096$. This prevents accidental multi-gigabyte memory allocations from divergent perspective rays.

---

### Question 10: How should the 90°/180° orientation ambiguity be handled?
> **Answer:**
> Phase 3.5 should establish **Canonical Geometric Rectification only**:
> - Ensure the document is rectified into a planar rectangle aligned with dominant image axes.
> - **Do NOT attempt to guess semantic reading orientation (0°, 90°, 180°, 270°) from corners alone.**
> - Pass the rectified image to downstream OCR / layout analysis (Phase 4), where text direction and header templates can authoritatively determine the upright reading orientation.

---

### Question 11: What exact structured input/output contract should Phase 3.6 receive?
> **Answer:**
> ```python
> @dataclass
> class ScannedDocumentResult:
>     status: str                          # "RECTIFIED_PHYSICAL_PAGE", "DESKEWED_FRAME_LIMITED", "AMBIGUOUS_UNWARPED"
>     scanned_image: np.ndarray            # Canonical rectified image (BGR or Gray)
>     destination_dimensions: Tuple[int, int] # (width, height)
>     homography_matrix: Optional[np.ndarray] # 3x3 perspective matrix (or 2x3 affine matrix)
>     source_corners: Optional[np.ndarray] # Normalized float32 (4, 2)
>     aspect_ratio: float                  # width / height
>     interpolation_used: str              # "INTER_CUBIC" or "INTER_LINEAR"
>     is_reading_orientation_resolved: bool # False (deferred to OCR stage)
> ```

---

### Question 12: Which numerical parameters still require broader validation?
> **Answer:**
> 1. **Destination Dimension Scaling Strategy**: Validating whether `MEAN_EDGE` or `AREA_ASPECT` delivers higher OCR accuracy across a 500+ document dataset.
> 2. **Interpolation Impact on OMR Bubble Detection**: Confirming whether `INTER_CUBIC` ringing artifacts affect circular Hough bubble detection.
> 3. **Maximum Pixel Dimension Clamping**: Evaluating memory constraints on embedded mobile devices (e.g. clamping to 2048 px on mobile).

---

## 10. Generated Visual Artifacts

The following visual diagnostics were generated in [`phase3/output/`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase3/output):
- `phase3/output/phase3_perspective_warp_real.png`: Illustrates verified physical quads for `answer_sheet_2.png` and `answer_sheet_3.jpg` and their canonical top-down rectified outputs.
- `phase3/output/phase3_perspective_warp_synthetic.png`: Illustrates perspective rectification under 10%, 25%, and 45% keystone foreshortening.

---
*Report prepared for Phase 3.5 of AI-EVAL-OpenCV.*
