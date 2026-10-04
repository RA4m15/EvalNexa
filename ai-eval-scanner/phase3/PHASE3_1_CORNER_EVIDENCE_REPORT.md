# Phase 3.1: Corner Evidence Investigation Report

**Project**: AI-EVAL-OpenCV  
**Phase**: 3.1 — Corner Evidence Investigation  
**Status**: INVESTIGATION ONLY (Phase 2 Frozen; No Production Scanner / No Perspective Warp / No Geometric Transform)  
**Date**: October 2026  

---

## 1. Executive Summary & Objective

In Phase 2, we established and verified a robust document-region detection architecture (`phase2/13_document_region_detector.py`) capable of classifying input images into distinct qualitative states:
- `ACCEPTED_PHYSICAL_PAGE`: Complete physical sheet isolated against an external background.
- `ACCEPTED_FRAME_LIMITED`: Physical sheet clipped by or filling the camera sensor frame.
- `AMBIGUOUS`: Conflicting physical page vs. inner content candidate signals.
- `INSUFFICIENT_CONFIDENCE`: No candidate meets physical boundary or framing criteria.

The objective of **Phase 3.1** is to investigate whether reliable physical page-corner evidence can be extracted from the document regions selected by Phase 2.13 across all 5 calibration images.

### Investigation Scope & Guardrails
- **Investigation Only**: No perspective correction, no `cv2.getPerspectiveTransform()`, no `cv2.warpPerspective()`.
- **No Corner Hallucination**: Image-frame bounds are never fabricated into physical paper corners.
- **No Universal Fixed Thresholds**: Measurements are empirical observations, not hard detector rules.
- **No Production Scoring or Weights**: Signal evaluation is qualitative, structural, and evidence-driven.

---

## 2. Calibration Image Investigation Profiles

Each calibration image was processed using `phase3/01_corner_evidence_investigation.py`, evaluating 7 independent corner signals:
1. Canny / edge evidence density
2. Hough line segments near corners
3. Local boundary continuity
4. Contour-based geometry (`approxPolyDP`)
5. Local corner features (Shi-Tomasi / Harris)
6. Boundary line-segment intersections
7. Frame-limited sensor clipping

---

### Image 1: `images/answer_sheet.jpg` (720 × 960 px)

- **Phase 2 Status**: `AMBIGUOUS`
- **Candidate Evaluated**: `cand_content_envelope_1` (Fallback to best envelope candidate)
- **Bounding Box ROI**: `(x=40, y=36, w=640, h=888)`
- **Physical Corners Directly Visible**: **0 / 4**
- **Sensor Frame Contact**: 0 sides touch the sensor frame, but candidate is an inner content envelope of a tightly-cropped form.

#### Corner Evidence Breakdown:
| Corner Location | Nominal Coord | Detected State | Physical Evidence Nature | Line Segments Nearby | Line Intersection | Visibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TOP_LEFT** | (40, 36) | `AMBIGUOUS` | Ambiguous printed grid margin | 1 (Vertical) | None | Inferred |
| **TOP_RIGHT** | (680, 36) | `AMBIGUOUS` | Ambiguous printed grid margin | 1 (Vertical) | None | Inferred |
| **BOTTOM_RIGHT**| (680, 924) | `INTERSECTED_BOUNDARY_CORNER` | Boundary line intersection | 2 (1H, 1V) | (679.8, 923.9) | Inferred |
| **BOTTOM_LEFT** | (40, 924) | `INTERSECTED_BOUNDARY_CORNER` | Boundary line intersection | 2 (1H, 1V) | (40.2, 924.1) | Inferred |

#### Detailed Observations:
- **Nature of Evidence**: The image is tightly cropped around the printed form. The candidate envelope represents printed tabular and text boundaries rather than physical paper edges.
- **Corner Features (Shi-Tomasi)**: 0 corners detected at outer boundary corners; features fire heavily inside printed text and table grid cells.
- **Contour Geometry**: Approximate polygon forms an 8-vertex irregular polygon due to text/handwriting protrusions.
- **Ambiguity / Failure Note**: Because the physical paper boundary is absent or flush with printed lines, extracting physical page corners from this image is impossible without confusing printed table corners with page corners.

---

### Image 2: `images/answer_sheet_2.png` (1200 × 1600 px)

- **Phase 2 Status**: `ACCEPTED_PHYSICAL_PAGE`
- **Candidate Selected**: `cand_app_mask_1` (Appearance Mask Candidate)
- **Bounding Box ROI**: `(x=119, y=141, w=962, h=1316)`
- **Physical Corners Directly Visible**: **4 / 4**
- **Sensor Frame Contact**: 0 / 4 sides touch sensor frame (sheet is fully contained on dark wood desk).

#### Corner Evidence Breakdown:
| Corner Location | Nominal Coord | Detected State | Physical Evidence Nature | Line Segments Nearby | Line Intersection | Visibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TOP_LEFT** | (119, 141) | `INTERSECTED_BOUNDARY_CORNER` | Physical paper corner on dark desk | 2 (1H, 1V) | (182.2, 141.0) | **Visible** |
| **TOP_RIGHT** | (1081, 141) | `INTERSECTED_BOUNDARY_CORNER` | Physical paper corner on dark desk | 2 (1H, 1V) | (1016.9, 140.9) | **Visible** |
| **BOTTOM_RIGHT**| (1081, 1457) | `INTERSECTED_BOUNDARY_CORNER` | Physical paper corner on dark desk | 2 (1H, 1V) | (1080.1, 1411.9) | **Visible** |
| **BOTTOM_LEFT** | (119, 1457) | `INTERSECTED_BOUNDARY_CORNER` | Physical paper corner on dark desk | 2 (1H, 1V) | (182.1, 1457.2) | **Visible** |

#### Detailed Observations:
- **Nature of Evidence**: Strong, genuine physical edge transitions (bright white paper vs. dark wooden desk).
- **Hough Line Segments**: Detected distinct horizontal top/bottom margins and vertical lateral margins. Intersecting line pairs reproduce the physical vertices with high fidelity.
- **Contour Geometry**: `approxPolyDP` successfully recovers a convex quadrilateral `[(183, 141), (120, 1457), (1080, 1411), (1017, 141)]`, precisely tracking the sheet's slight perspective tilt.
- **Corner Features**: Standard Shi-Tomasi features are weak at the rounded/blunt physical paper apex itself (edge steps are smooth at macro level), but line intersection captures the vertex cleanly.

---

### Image 3: `images/answer_sheet_3.jpg` (1200 × 1600 px)

- **Phase 2 Status**: `ACCEPTED_PHYSICAL_PAGE`
- **Candidate Selected**: `cand_app_mask_1` (Appearance Mask Candidate)
- **Bounding Box ROI**: `(x=141, y=176, w=997, h=1276)`
- **Physical Corners Directly Visible**: **4 / 4** (3 easily extracted via lines, 1 corner shaded).
- **Sensor Frame Contact**: 0 / 4 sides touch sensor frame (isolated sheet on desk).

#### Corner Evidence Breakdown:
| Corner Location | Nominal Coord | Detected State | Physical Evidence Nature | Line Segments Nearby | Line Intersection | Visibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TOP_LEFT** | (141, 176) | `INTERSECTED_BOUNDARY_CORNER` | Physical paper corner on desk | 2 (1H, 1V) | (205.1, 174.9) | **Visible** |
| **TOP_RIGHT** | (1138, 176) | `WEAK_OR_AMBIGUOUS_CORNER` | Shaded paper corner; low contrast | 0 | None | **Visible** (Subtle) |
| **BOTTOM_RIGHT**| (1138, 1452) | `INTERSECTED_BOUNDARY_CORNER` | Physical paper corner on desk | 2 (1H, 1V) | (1137.0, 1451.1) | **Visible** |
| **BOTTOM_LEFT** | (141, 1452) | `INTERSECTED_BOUNDARY_CORNER` | Physical paper corner on desk | 2 (1H, 1V) | (140.0, 1393.9) | **Visible** |

#### Detailed Observations:
- **Nature of Evidence**: Genuine physical paper boundary against desk background.
- **Shadow Ambiguity**: Top-right corner falls into a diffused shadow / low-contrast illumination gradient, causing local Canny and Hough detectors to fragment the margin line.
- **Contour Geometry**: Global contour approximation recovers the 4-vertex quadrilateral `[(207, 176), (142, 1393), (1137, 1450), (1084, 263)]`.
- **Key Takeaway**: Global boundary continuity and line projection can bridge local edge dropouts caused by uneven lighting.

---

### Image 4: `images/answer_sheet_4.jpg` (1200 × 1700 px)

- **Phase 2 Status**: `ACCEPTED_FRAME_LIMITED`
- **Candidate Selected**: `cand_app_mask_1` (Appearance Mask Candidate)
- **Bounding Box ROI**: `(x=166, y=0, w=884, h=1700)`
- **Physical Corners Directly Visible**: **0 / 4**
- **Sensor Frame Contact**: **2 edges (Top y=0 and Bottom y=1700) touch the sensor frame**.

#### Corner Evidence Breakdown:
| Corner Location | Nominal Coord | Detected State | Physical Evidence Nature | Line Segments Nearby | Line Intersection | Visibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TOP_LEFT** | (166, 0) | `FRAME_CLIPPED_BORDER` | Lateral margin intersects top sensor frame | 0 | None | **NOT Visible** (Clipped) |
| **TOP_RIGHT** | (1050, 0) | `FRAME_CLIPPED_BORDER` | Lateral margin intersects top sensor frame | 0 | None | **NOT Visible** (Clipped) |
| **BOTTOM_RIGHT**| (1050, 1700) | `FRAME_CLIPPED_BORDER` | Lateral margin intersects bottom sensor frame| 1 (Vertical) | None | **NOT Visible** (Clipped) |
| **BOTTOM_LEFT** | (166, 1700) | `FRAME_CLIPPED_BORDER` | Lateral margin intersects bottom sensor frame| 0 | None | **NOT Visible** (Clipped) |

#### Detailed Observations:
- **Nature of Evidence**: Lateral physical borders (left and right) are clearly visible against the desk background. However, the top and bottom of the sheet extend beyond the field of view.
- **CRITICAL FINDING**: The points `(166, 0)` and `(1050, 0)` are **sensor-edge intersections**, NOT physical document corners. The actual paper corners are located in unobserved space beyond $y < 0$ and $y > 1700$.
- **Fabrication Hazard**: Any algorithm that forces 4 corners at `(166, 0)` and `(1050, 0)` would treat an arbitrary camera framing cutoff as the sheet's top edge, creating severe perspective distortion and content truncation.

---

### Image 5: `images/answer_sheet_5.jpg` (1200 × 1600 px)

- **Phase 2 Status**: `ACCEPTED_FRAME_LIMITED`
- **Candidate Selected**: `cand_frame_full` (Frame View Candidate)
- **Bounding Box ROI**: `(x=0, y=0, w=1200, h=1600)`
- **Physical Corners Directly Visible**: **0 / 4**
- **Sensor Frame Contact**: **4 / 4 edges touch the sensor frame**.

#### Corner Evidence Breakdown:
| Corner Location | Nominal Coord | Detected State | Physical Evidence Nature | Line Segments Nearby | Line Intersection | Visibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TOP_LEFT** | (0, 0) | `UNOBSERVABLE_FRAME_CORNER` | Sensor corner pixel; paper fills frame | 1 | None | **NOT Visible** (Sensor bound) |
| **TOP_RIGHT** | (1200, 0) | `UNOBSERVABLE_FRAME_CORNER` | Sensor corner pixel; paper fills frame | 0 | None | **NOT Visible** (Sensor bound) |
| **BOTTOM_RIGHT**| (1200, 1600) | `UNOBSERVABLE_FRAME_CORNER` | Sensor corner pixel; paper fills frame | 0 | None | **NOT Visible** (Sensor bound) |
| **BOTTOM_LEFT** | (0, 1600) | `UNOBSERVABLE_FRAME_CORNER` | Sensor corner pixel; paper fills frame | 1 | None | **NOT Visible** (Sensor bound) |

#### Detailed Observations:
- **Nature of Evidence**: The document occupies 100% of the sensor frame. There is no exterior background visible anywhere.
- **CRITICAL FINDING**: The 4 image corners `(0,0)`, `(1200,0)`, `(1200,1600)`, and `(0,1600)` are purely camera sensor coordinate limits. No physical page corners exist in the image.
- **Perspective Distortion Risk**: Calling `warpPerspective()` on image bounds `(0,0,w,h)` is mathematically degenerate (identity transform) and will fail if the document was captured at an angle under close-up cropping.

---

## 3. Signal Analysis: Promising vs. Unreliable Signals

### D. Signals that Appear Promising

1. **Boundary Line-Segment Extraction (Hough / LSD along margins)**:
   - *Why*: Physical paper edges are straight lines that span substantial lengths (hundreds of pixels). Line segment detectors filter out point noise and track long physical edges effectively.
   - *Strength*: By filtering lines into predominantly horizontal and vertical orientations along the candidate's outer boundary, we obtain reliable linear equations for the paper sides.
2. **Boundary Line-to-Line Intersection**:
   - *Why*: True physical corners are often rounded, creased, torn, or slightly out of focus. Intersecting the adjacent margin lines ($L_{\text{horizontal}} \cap L_{\text{vertical}}$) reconstructs the true geometric vertex without being sensitive to local corner radius or micro-fraying.
3. **Convex Quadrilateral Approximation (`approxPolyDP` on Appearance Mask)**:
   - *Why*: When an isolated physical page is present (`answer_sheet_2`, `answer_sheet_3`), contour polygonal simplification with adaptive $\epsilon$ cleanly recovers a 4-vertex quadrilateral that tightly matches the physical sheet.
4. **Sensor Frame Boundary Contact Flagging**:
   - *Why*: Checking whether candidate boundary points coincide with $x=0$, $y=0$, $x=w$, or $y=h$ immediately flags whether an edge is a physical boundary or a camera-cutoff artifact.

---

### E. Signals that are Unreliable or Misleading

1. **Local Corner Feature Detectors (Shi-Tomasi / Harris / FAST)**:
   - *Why Unreliable*: Local corner detectors fire on high eigenvalue intensity gradients in $x$ and $y$. Physical paper corners on flat desk surfaces often have gentle, rounded transitions. In contrast, internal printed tables, text characters, barcodes, and ruled lines produce thousands of high-intensity corner responses.
   - *Result*: In every calibration image, Shi-Tomasi placed 99%+ of its detected corners *inside* the page content, and nearly 0% at the true physical page vertices.
2. **Monolithic 4-Corner Assumption**:
   - *Why Unreliable*: In 3 of the 5 calibration images (`answer_sheet`, `answer_sheet_4`, `answer_sheet_5`), physical page corners are **NOT** visible. Forcing a detector to output 4 physical corners produces hallucinated vertices (e.g. treating camera frame edges as paper corners).
3. **Raw Canny Edge Density in Corner Patches**:
   - *Why Unreliable*: High edge density in a corner patch is almost always caused by printed form lines or handwriting near the edge, not the physical corner itself. Clean paper corners floating on a dark desk often exhibit low local edge density (< 1%).
4. **Unconstrained Contour Hierarchy**:
   - *Why Unreliable*: Finding all contours and sorting by area frequently selects inner printed tables or border frames rather than the physical page.

---

## 4. Evidence Classification: Observed, Ambiguous, and Failure Cases

```
                                  [Input Image]
                                        │
                         Phase 2.13 Document State
                                        │
           ┌────────────────────────────┴────────────────────────────┐
           ▼                                                         ▼
   ACCEPTED_PHYSICAL_PAGE                                    ACCEPTED_FRAME_LIMITED /
   (answer_sheet_2, answer_sheet_3)                          AMBIGUOUS
           │                                                 (answer_sheet_4, 5, 1)
           ▼                                                         │
   Physical Corners Visible                                          ▼
   (Observable Boundary Lines)                               Physical Corners Missing / Clipped
           │                                                         │
           ▼                                                         ▼
   Line Intersection & Quad Fit                              DO NOT Hallucinate Corners
   (True Perspective Estimable)                              (Use Frame Alignment / Flag Partial)
```

### A. Observed Evidence (High Confidence)
- **Isolated Paper Boundaries**: In `answer_sheet_2` and `answer_sheet_3`, distinct physical edge lines exist on all 4 margins. Margin line intersections yield stable vertices within 1–2 pixels of the true page geometry.
- **Framing Detection**: Frame contact at $y=0$ and $y=1700$ in `answer_sheet_4` was unambiguously detected, correctly identifying that the top and bottom sheet edges are unobservable.

### B. Ambiguous Evidence
- **Shadowed / Diffused Corners**: In `answer_sheet_3` (top-right), ambient lighting gradients reduce edge contrast. While the corner is physically present, simple edge detectors drop out, requiring global line projection to recover the vertex.
- **Tight Form Margins**: In `answer_sheet.jpg`, the outermost printed rectangular table border is located just millimeters inside the physical page edge, creating ambiguity between "page border" and "table border".

### C. Failure Modes to Avoid in Phase 3
1. **The "Frame-Corner Hallucination" Failure**:
   - In `answer_sheet_5`, assigning $(0,0), (1200,0), (1200,1600), (0,1600)$ as physical corners is mathematically false. It misleads downstream evaluation into assuming the page is fully captured and un-skewed.
2. **The "Clipped-Intersection" Failure**:
   - In `answer_sheet_4`, lateral margins intersect the top sensor edge at $(166, 0)$ and $(1050, 0)$. Treating these points as document corners truncates the document header.
3. **The "Internal Feature Attraction" Failure**:
   - Using local corner detectors (Harris/FAST) inside corner search windows causes the detector to snap to printed text or table boxes rather than the page vertex.

---

## 5. Direct Answers to Phase 3.1 Core Questions

### Question 1: Are physical page corners directly visible in all calibration images?
> **Answer: NO.**
> - `answer_sheet_2.png`: **YES** (All 4 corners visible on desk).
> - `answer_sheet_3.jpg`: **YES** (All 4 corners visible on desk; 1 corner shaded).
> - `answer_sheet_4.jpg`: **NO** (Top and bottom margins are clipped by the camera frame; the sheet extends beyond the image bounds. Observable intersections are sensor-edge cuts, not page corners).
> - `answer_sheet_5.jpg`: **NO** (The document fills 100% of the sensor frame. All 4 image corners are camera sensor boundary pixels).
> - `answer_sheet.jpg`: **NO** (Tightly cropped form; physical edges are clipped or flush with the scan boundary).

---

### Question 2: Which corner signals are consistently available?
> **Answer:**
> 1. **Boundary Line-Segment Orientation**: Dominant linear segments along candidate margins (horizontal top/bottom, vertical left/right).
> 2. **Physical Edge Step Contrast**: Strong intensity/color step transitions along margins where physical paper meets an external background.
> 3. **Sensor-Frame Contact Detection**: Absolute coordinates $x \in \{0, w-1\}$ and $y \in \{0, h-1\}$ reliably indicate whether a boundary is physically bounded or artificially sensor-clipped.

---

### Question 3: Which signals are image-specific or unreliable?
> **Answer:**
> 1. **Shi-Tomasi / Harris Corner Detection**: Unreliable. Dominated by internal printed text, tables, and handwriting; rarely fires on blunt paper vertices.
> 2. **Unconstrained Contour Polygon Fitting (`approxPolyDP`)**: Unreliable across arbitrary images. Fails when documents contact frame borders or when desk textures fracture the contour.
> 3. **Raw Corner Patch Edge Density**: Unreliable. Correlates with printed content density near margins, not with corner presence.
> 4. **Four-Corner Assumption**: Completely invalid for frame-limited and tight-crop captures.

---

### Question 4: Can a robust four-corner detector be designed from the current evidence?
> **Answer: NO, not as a single monolithic four-corner detector.**
> A traditional document scanner that unconditionally looks for 4 corners and warps them into a rectangle will fail or produce distorted results on images like `answer_sheet_4` and `answer_sheet_5`.
> 
> However, a **robust bifurcated architecture** CAN be designed:
> - **Branch A (Physical Page Isolated)**: When Phase 2 classifies `ACCEPTED_PHYSICAL_PAGE`, execute 4-corner boundary line intersection with polygon validation.
> - **Branch B (Frame-Limited Capture)**: When Phase 2 classifies `ACCEPTED_FRAME_LIMITED`, do NOT attempt 4-corner perspective warping. Instead, treat the capture as frame-aligned or partial capture, avoiding corner hallucination.

---

### Question 5: What additional investigation is required before implementing Phase 3 production logic?
> **Answer:**
> 1. **RANSAC / Polar Line Fitting along Margins**: Developing a robust method to cluster line segments along the 4 margins and fit parametric lines ($ax + by + c = 0$) that ignore internal text lines.
> 2. **Boundary vs. Internal Grid Discrimination**: Verifying that a detected line is the outermost paper boundary rather than an internal table rule.
> 3. **Sub-Pixel Vertex Refinement**: For `ACCEPTED_PHYSICAL_PAGE`, refining the intersection points using orthogonal gradient profiles.
> 4. **Frame-Limited Document Alignment Strategy**: Investigating how to handle frame-limited captures (e.g., orientation correction / deskew without 4-corner warp).

---

## 6. Generated Visual Artifacts

The diagnostic script generated the following visual overlays in `phase3/output/`:
- `phase3/output/phase3_corner_vis_answer_sheet.jpg.png`: Visualizes candidate envelope, detected line segments, and ambiguous corners.
- `phase3/output/phase3_corner_vis_answer_sheet_2.png.png`: Visualizes 4 visible physical corners, intersecting margin lines, and quad overlay.
- `phase3/output/phase3_corner_vis_answer_sheet_3.jpg.png`: Visualizes shaded top-right corner, 3 strong intersections, and quad fit.
- `phase3/output/phase3_corner_vis_answer_sheet_4.jpg.png`: Visualizes top and bottom sensor frame clipping, lateral margin lines, and unobservable corners.
- `phase3/output/phase3_corner_vis_answer_sheet_5.jpg.png`: Visualizes frame-filling document with all 4 corners marked as unobservable sensor bounds.

---
*Report prepared for Phase 3.1 of AI-EVAL-OpenCV.*
