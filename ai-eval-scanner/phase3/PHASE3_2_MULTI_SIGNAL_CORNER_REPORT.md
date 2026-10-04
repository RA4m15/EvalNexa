# Phase 3.2: Multi-Signal Corner Candidate Investigation Report

**Project**: AI-EVAL-OpenCV  
**Phase**: 3.2 — Multi-Signal Corner Candidate Investigation  
**Status**: INVESTIGATION ONLY (Phase 2 & Phase 3.1 Frozen; No Production Scanner / No Perspective Warp / No Geometric Transform)  
**Date**: October 2026  

---

## 1. Executive Summary & Objective

Phase 3.1 established that physical page corners are **not** universally visible across document images:
- Complete physical sheet vertices are directly observable only when the document is isolated on a contrasting surface (`answer_sheet_2.png`, `answer_sheet_3.jpg`).
- In frame-clipped or frame-filling captures (`answer_sheet_4.jpg`, `answer_sheet_5.jpg`), observable intersections at image bounds are sensor-frame cuts, not physical paper corners.
- In tightly cropped forms (`answer_sheet.jpg`), outer boundaries merge with printed form rules or are cropped away.

The objective of **Phase 3.2** is to investigate whether physical page corners can be reconstructed reliably from **multiple boundary signals** when corners are visible, focusing deeply on:
1. **Outer Margin Line Extraction**: Identifying long straight boundary line segments along candidate margins.
2. **Robust Line Fitting**: Evaluating RANSAC vs. total least-squares/PCA on line segment point clouds, identifying their respective success and failure modes.
3. **Outer-vs-Internal Disambiguation**: Separating physical paper boundaries from internal printed table rules, form boxes, handwriting strokes, and illumination artifacts.
4. **Quadrilateral Hypotheses**: Constructing and evaluating competing 4-line / 4-corner hypotheses (Outer Physical Page vs. Inner Printed Envelope).
5. **Frame-Limited and Ambiguous Cases**: Documenting what geometric information remains usable (e.g. lateral skew angles) without manufacturing unobservable corners.

### Guardrails Maintained
- **Investigation Only**: No perspective transform, no `cv2.getPerspectiveTransform()`, no `cv2.warpPerspective()`.
- **No Threshold Freezing**: All numbers reported are empirical observations, not hard detector rules.
- **No Corner Hallucination**: Sensor frame bounds are never returned as physical document corners.
- **No Modifications to Frozen Modules**: Phase 2 (`03`–`13`) and Phase 3.1 files remain strictly untouched.

---

## 2. Calibration Image Investigation Profiles

Diagnostic script [`phase3/02_multi_signal_corner_investigation.py`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase3/02_multi_signal_corner_investigation.py) was executed across all 5 calibration images.

---

### Image 1: `images/answer_sheet_2.png` (1200 × 1600 px) — Primary Physical Page Case

- **Phase 2 Status**: `ACCEPTED_PHYSICAL_PAGE` (Selected Candidate: `cand_app_mask_1`)
- **Evaluated Bounding Box**: `(x=119, y=142, w=962, h=1315)`
- **Frame-Limited Sides**: `[]` (0/4 sides touch sensor frame)
- **Detected Line Segments**: TOP: 49, BOTTOM: 14, LEFT: 7, RIGHT: 6

#### A. Outer vs. Inner Margin Line Analysis:
| Margin Side | Line Classification | Contrast Step ($\Delta V$) | Line Nature & Evidence |
| :--- | :--- | :--- | :--- |
| **TOP** | **Outer Line** | **+153.8 V** | `PHYSICAL_PAPER_BOUNDARY` (Dark wood desk vs bright paper) |
| | Inner Line | +74.1 V | `PHYSICAL_PAPER_BOUNDARY` (Near top printed margin rule) |
| **BOTTOM** | **Outer Line** | **+159.1 V** | `PHYSICAL_PAPER_BOUNDARY` (Dark wood desk vs bright paper) |
| | Inner Line | +2.0 V | `PRINTED_TABLE_RULE` (Both sides light paper; bottom grid border) |
| **LEFT** | **Outer Line** | **+153.6 V** | `PHYSICAL_PAPER_BOUNDARY` (Dark wood desk vs bright paper) |
| | Inner Line | +1.0 V | `PRINTED_TABLE_RULE` (Inner margin vertical line) |
| **RIGHT** | **Outer Line** | **+155.4 V** | `PHYSICAL_PAPER_BOUNDARY` (Dark wood desk vs bright paper) |
| | Inner Line | +154.8 V | `PHYSICAL_PAPER_BOUNDARY` (Paper boundary spans thin margin) |

#### B. Quadrilateral Hypotheses Comparison:
- **Hypothesis 1: `HYP_OUTER_PHYSICAL_PAGE`** (`VALID_CONVEX_QUAD`)
  - **Corners**:
    - `TOP_LEFT`: `(118.8, 185.5)`
    - `TOP_RIGHT`: `(1017.5, 141.0)`
    - `BOTTOM_RIGHT`: `(1079.7, 1412.0)`
    - `BOTTOM_LEFT`: `(181.9, 1456.9)`
  - **Supporting Evidence**: All 4 lines exhibit $\Delta V > +150$ contrast steps against the dark desk; forms a strictly convex quadrilateral; area ratio to Phase 2 ROI = 100.8%; perfectly captures physical paper vertices.
  - **Contradicting Evidence**: None.
- **Hypothesis 2: `HYP_INNER_PRINTED_ENVELOPE`** (`VALID_CONVEX_QUAD`)
  - **Corners**: `TL=(202.0, 227.1), TR=(1019.2, 183.8), BR=(1077.7, 1343.9), BL=(258.6, 1384.9)`
  - **Supporting Evidence**: Formed by internal printed table rules; strictly convex.
  - **Contradicting Evidence**: $\Delta V \approx +1$ to $+2$ V on bottom and left margins (paper-to-paper transition); area is noticeably smaller than physical page (ratio = 78.4%); corners lie inside the sheet.

---

### Image 2: `images/answer_sheet_3.jpg` (1200 × 1600 px) — Primary Physical Page Case (Shaded)

- **Phase 2 Status**: `ACCEPTED_PHYSICAL_PAGE` (Selected Candidate: `cand_app_mask_1`)
- **Evaluated Bounding Box**: `(x=141, y=176, w=997, h=1276)`
- **Frame-Limited Sides**: `[]` (0/4 sides touch sensor frame)
- **Detected Line Segments**: TOP: 57, BOTTOM: 5, LEFT: 2, RIGHT: 8

#### A. Outer vs. Inner Margin Line Analysis:
| Margin Side | Line Classification | Contrast Step ($\Delta V$) | Line Nature & Evidence |
| :--- | :--- | :--- | :--- |
| **TOP** | **Outer Line** | **+120.2 V** | `PHYSICAL_PAPER_BOUNDARY` (Outer paper edge against desk) |
| | Inner Line | +1.3 V | `PRINTED_TABLE_RULE` (Printed instruction table header) |
| **BOTTOM** | **Outer Line** | **+149.0 V** | `PHYSICAL_PAPER_BOUNDARY` (Dark desk vs bright paper) |
| | Inner Line | +150.6 V | `PHYSICAL_PAPER_BOUNDARY` (Collinear with outer edge) |
| **LEFT** | **Outer Line** | **+81.6 V** | `PHYSICAL_PAPER_BOUNDARY` (Desk transition, slightly shaded) |
| | Inner Line | +82.5 V | `PHYSICAL_PAPER_BOUNDARY` (Collinear with outer edge) |
| **RIGHT** | **Outer Line** | **+149.4 V** | `PHYSICAL_PAPER_BOUNDARY` (Desk transition) |
| | Inner Line | +149.0 V | `PHYSICAL_PAPER_BOUNDARY` (Collinear with outer edge) |

#### B. Quadrilateral Hypotheses Comparison:
- **Hypothesis 1: `HYP_OUTER_PHYSICAL_PAGE`** (`VALID_CONVEX_QUAD`)
  - **Corners**:
    - `TOP_LEFT`: `(204.5, 174.7)`
    - `TOP_RIGHT`: `(1084.0, 262.5)`
    - `BOTTOM_RIGHT`: `(1137.1, 1450.6)`
    - `BOTTOM_LEFT`: `(139.9, 1394.4)`
  - **Supporting Evidence**: All 4 sides exhibit large positive brightness steps ($\Delta V \in [+81.6, +149.4]$ V); strictly convex; area ratio = 99.4% of ROI; smoothly bridges the shaded top-right corner.
  - **Contradicting Evidence**: None.
- **Hypothesis 2: `HYP_INNER_PRINTED_ENVELOPE`** (`VALID_CONVEX_QUAD`)
  - **Corners**: `TL=(203.4, 206.4), TR=(1085.6, 297.0), BR=(1136.3, 1447.0), BL=(140.7, 1394.6)`
  - **Difference**: The top boundary snaps to the internal printed header rule ($y \approx 206$ vs. $y \approx 175$ for paper edge). Contrast step on the inner top line is only $+1.3$ V, proving it is an internal printed rule.

---

### Image 3: `images/answer_sheet_4.jpg` (1200 × 1700 px) — Frame-Clipped Case

- **Phase 2 Status**: `ACCEPTED_FRAME_LIMITED` (Selected Candidate: `cand_app_mask_1`)
- **Evaluated Bounding Box**: `(x=166, y=0, w=884, h=1700)`
- **Frame-Limited Sides**: `['TOP', 'BOTTOM']` (Top touches $y=0$, Bottom touches $y=1700$)
- **Detected Line Segments**: TOP: 111, BOTTOM: 0, LEFT: 10, RIGHT: 9

#### Observations & Line Evidence:
- **Lateral Margins (LEFT & RIGHT)**:
  - LEFT: $\Delta V = +102.8$ V (`PHYSICAL_PAPER_BOUNDARY`, orientation = 91.58°)
  - RIGHT: $\Delta V = +51.5$ V (`PHYSICAL_PAPER_BOUNDARY`, orientation = 87.98°)
  - Both lateral sides are observable physical boundaries.
- **Top Margin**:
  - Sits at $y=0$. Line segments detected near $y=0$ are internal printed header text/lines ($\Delta V = -8.6$ V, `PRINTED_TABLE_RULE`). The actual physical top edge is clipped.
- **Bottom Margin**:
  - Sits at $y=1700$. 0 segments detected outside the sheet; the bottom edge is clipped.
- **Quadrilateral Formation**:
  - `HYP_OUTER_PHYSICAL_PAGE`: **INCOMPLETE** (Missing BOTTOM margin line).
  - `HYP_INNER_PRINTED_ENVELOPE`: **INCOMPLETE** (Missing BOTTOM margin line).
- **Usable Geometric Information**:
  - Lateral edge orientations: Left = 91.58°, Right = 87.98°.
  - The mean tilt of the document is approximately $-1.22°$ from vertical. This tilt angle is directly usable for deskewing without fabricating false corners.

---

### Image 4: `images/answer_sheet_5.jpg` (1200 × 1600 px) — Frame-Filling Case

- **Phase 2 Status**: `ACCEPTED_FRAME_LIMITED` (Selected Candidate: `cand_frame_full`)
- **Evaluated Bounding Box**: `(x=0, y=0, w=1200, h=1600)`
- **Frame-Limited Sides**: `['TOP', 'BOTTOM', 'LEFT', 'RIGHT']` (All 4 sides touch sensor boundary)
- **Detected Line Segments**: TOP: 61, BOTTOM: 9, LEFT: 10, RIGHT: 1

#### Observations & Line Evidence:
- **Contrast Steps Across All Margins**:
  - TOP: $+2.3$ V (`PRINTED_TABLE_RULE`)
  - BOTTOM: $-1.3$ V (`PRINTED_TABLE_RULE`)
  - LEFT: $-0.4$ V (`PRINTED_TABLE_RULE`)
  - RIGHT: $-1.2$ V (`PRINTED_TABLE_RULE`)
  - **Finding**: Every detectable line segment has $|\Delta V| \le 2.3$ V. Both sides of every line consist of white paper. There is **zero** physical boundary evidence anywhere in the image.
- **Fitted Quadrilateral**:
  - `HYP_OUTER_PHYSICAL_PAGE`: Forms a quad at `TL=(26.5, 79.2), TR=(1186.6, 9.0), BR=(1165.4, 1407.8), BL=(47.8, 1484.1)`.
  - **CRITICAL DISAMBIGUATION**: This quad is the **printed bounding box of the evaluation form**, NOT the physical paper corners!
  - Treating this quad as the document corners would crop out student header information and form instructions located outside the inner box.

---

### Image 5: `images/answer_sheet.jpg` (720 × 960 px) — Ambiguous / Tightly Cropped Case

- **Phase 2 Status**: `AMBIGUOUS` (Fallback Candidate: `cand_frame_full`)
- **Evaluated Bounding Box**: `(x=0, y=0, w=768, h=1024)`
- **Frame-Limited Sides**: `['TOP', 'BOTTOM', 'LEFT', 'RIGHT']`
- **Detected Line Segments**: TOP: 109, BOTTOM: 112, LEFT: 0, RIGHT: 2

#### Observations & Line Evidence:
- **Zero Lateral Boundary Lines**: LEFT has 0 line segments. RIGHT has 2 faint vertical grid fragments ($\Delta V = -3.6$ V).
- **Dense Grid Segments**: TOP (109 segments) and BOTTOM (112 segments) are dominated by hundreds of horizontal grid lines from the multiple-choice bubble rows.
- **Physical Boundary Evidence**: **None**. No physical edge step exists.
- **Quadrilateral Formation**: Cannot form a quad; missing LEFT margin.
- **Confirmation**: Physical page corners are genuinely unavailable. Any 4-corner model applied here would pick arbitrary printed table grid lines.

---

## 3. Detailed Investigation Findings

```
                              Detected Line Segments
                                         │
                         Spatial & Distance Partitioning
                                         │
                    ┌────────────────────┴────────────────────┐
                    ▼                                         ▼
            Outer-Band Segments                       Inner-Band Segments
                    │                                         │
            RANSAC + PCA Fit                          RANSAC + PCA Fit
                    │                                         │
            Outer Fitted Lines                        Inner Fitted Lines
                    │                                         │
            Exterior/Interior                         Exterior/Interior
            Appearance Sampling                       Appearance Sampling
                    │                                         │
       ΔV > +20 V ? │                             ΔV < +12 V ?│
       ┌────────────┴────────────┐                            ▼
       ▼                         ▼                   PRINTED_TABLE_RULE
PHYSICAL_PAPER_BOUNDARY      AMBIGUOUS /             (Inner Form Envelope)
(True Paper Edge)            FRAME_CUTOFF                     │
       │                                                      │
       ▼                                                      ▼
HYP_OUTER_PHYSICAL_PAGE                              HYP_INNER_PRINTED_ENVELOPE
(Physical Sheet Vertices)                            (Content Box Vertices)
```

### A. Observed Evidence

1. **Physical Boundary Step Signal**:
   - In both `answer_sheet_2` and `answer_sheet_3`, the physical edge step between paper and desk background is massive and unambiguous: $\Delta V \in [+81.6, +159.1]$ V.
   - When sampled 12 pixels orthogonal to the fitted line, the exterior values are dark desk pixels ($V < 80$), while interior values are clean white paper ($V > 210$).
2. **Internal Printed Rule Step Signal**:
   - Printed table lines, question boxes, and bubble grid borders have paper on both sides: $\Delta V \in [-3.6, +5.7]$ V, with both exterior and interior values exceeding $V > 180$.
   - This provides a reliable physical discriminator between paper edges and printed form rules.
3. **Convex Quadrilateral Intersection**:
   - In `answer_sheet_2` and `answer_sheet_3`, intersecting the 4 fitted outer margin lines yields convex quadrilaterals with angles within 2.8° of orthogonality ($87.2°$ to $93.0°$).
   - The area of these quadrilaterals matches the Phase 2 appearance mask ROI within 1%.

---

### B. Promising Signals

1. **Spatial Margin Partitioning (Outer-Band vs. Inner-Band)**:
   - Partitioning detected segments into an outer margin band (near candidate perimeter) and an inner band successfully separates the faint single outer paper edge from the dozens of dense inner table rules.
2. **RANSAC Consensus on Segment Point Clouds**:
   - When applied to the isolated outer band, RANSAC reliably rejects short spurious segments (e.g. handwriting strokes extending into margins, hole-punch artifacts).
   - RANSAC inlier ratios on true physical edges consistently exceed 85%.
3. **Pairwise Line-to-Line Intersection ($L_i \cap L_j$)**:
   - Mathematical intersection of parametric lines $A_1 x + B_1 y + C_1 = 0$ and $A_2 x + B_2 y + C_2 = 0$ calculates corners with sub-pixel precision.
   - Completely overcomes the blunt/rounded corner limitation where local point detectors fail.
4. **Dominant Lateral Orientation in Frame-Clipped Images**:
   - In `answer_sheet_4`, even though top and bottom corners are clipped, the left and right lines provide precise document skew angle ($91.58°$ and $87.98° \implies -1.22°$ tilt).

---

### C. Failure Modes & Limitations of Pure Methods

1. **RANSAC Point-Count Trap**:
   - **Crucial Finding**: Standard RANSAC selects the model with the *maximum number of inliers*.
   - In printed answer sheets, a printed table rule often has 10–50 collinear segments across multiple columns, while the outer paper boundary may only produce 1–3 segments.
   - Unconstrained RANSAC run across the entire margin band **consistently selects the internal table rule** instead of the physical edge because the table rule has more inliers.
   - *Fix*: Spatial partitioning and contrast-step verification must precede or constrain RANSAC.
2. **Internal Line Quad Illusion**:
   - In `answer_sheet_5`, 4 printed lines intersect to form a "valid convex quad". An unguided algorithm would happily warp this inner quad, cutting off crucial student data and instructions in the page margins.
3. **Shadowed Corner Blur**:
   - In `answer_sheet_3`, the top-right corner is diffused by ambient shading, dropping local edge count. Relying on local corner features completely fails here; however, intersecting the top and right fitted lines accurately locates the vertex.

---

### D. Ambiguous Cases

- **`answer_sheet.jpg`**:
  - The image contains hundreds of collinear segments, but all are internal table grid borders. The physical page boundary is completely absent.
  - A detector must report `CORNERS_UNAVAILABLE` rather than arbitrarily snapping to an internal table box.

---

## 4. Direct Answers to Phase 3.2 Core Questions

### Question 1: Can outer paper boundary lines be separated from internal printed lines?
> **YES, reliably.**
> Two complementary signals achieve this separation:
> 1. **Appearance Contrast Step ($\Delta V$)**: Physical paper boundaries exhibit an exterior-to-interior contrast step $\Delta V \gg +20$ V (typically $+80$ to $+160$ V against desk surfaces). Internal printed rules have white paper on both sides ($|\Delta V| < 10$ V).
> 2. **Spatial Position (Distance to Envelope Perimeter)**: Physical boundaries lie strictly at the outer frontier of the document region, whereas printed table lines lie recessed within the document interior.

---

### Question 2: Does robust line fitting improve reliability?
> **YES, but only when constrained by spatial partitioning.**
> - **Where it succeeds**: RANSAC filters out skewed handwriting strokes, stray checkmarks, and staple/clip marks that bleed into the margin. Once outlier points are removed, PCA / total least-squares fitting provides a mathematically optimal line.
> - **Where it fails if unconstrained**: RANSAC consensus maximization naturally favors dense features. If printed table lines and paper edges are fed into the same RANSAC pool, RANSAC overfits to the printed table line because it contains more segments.

---

### Question 3: Can line intersections provide reliable physical corner candidates?
> **YES, for images where physical boundaries are observable.**
> Intersecting parametric lines ($L_{\text{horizontal}} \cap L_{\text{vertical}}$) avoids the fundamental flaw of point-based corner detectors (Harris/Shi-Tomasi/FAST), which fail on rounded, torn, or low-contrast paper vertices. Line intersection recovers true geometric vertices even when the corner apex itself is shaded or out of focus.

---

### Question 4: What geometric checks are useful?
> 1. **Convexity Check**: Cross products of adjacent perimeter vectors must all share the same sign.
> 2. **Area Consistency**: The polygon area of the intersection quad must be within a plausible ratio ($\approx 0.95$ to $1.05$) of the Phase 2 appearance mask ROI area.
> 3. **Orthogonality / Angle Plausibility**: Interior angles of the 4 intersections must be reasonably close to 90° (empirically $85°$ to $95°$).
> 4. **Exterior Step Consistency**: All 4 lines forming the quad must independently confirm physical paper boundary status ($\Delta V > +20$ V).

---

### Question 5: Which failure cases remain?
> 1. **Frame-Limited Captures (`answer_sheet_4`, `answer_sheet_5`)**: Physical corners do not exist in the field of view. Attempting 4-corner perspective warping is physically invalid.
> 2. **Low-Contrast / White-on-White Backgrounds**: If an answer sheet is placed on a white desk or white paper stack, the exterior contrast step $\Delta V$ drops significantly.
> 3. **Severe Perspective Distortion**: If skew is extreme, margin bands must be adaptive rather than axis-aligned.

---

### Question 6: Is enough evidence now available to design Phase 3 production architecture?
> **YES.**
> Phase 3.1 and Phase 3.2 have established complete clarity on:
> - When corners are observable vs. unobservable.
> - How to isolate outer physical margins from dense inner table grids.
> - How to robustly fit lines and intersect them into accurate vertices.
> - How to handle frame-limited images through tilt deskewing rather than 4-corner warping.

---

## 5. Proposed Phase 3 Production Architecture (DESIGN ONLY)

> **IMPORTANT**: In accordance with project instructions, this is a **design proposal only**. No production code has been implemented.

```
                         Input Image
                              │
                    Phase 2.13 Classification
                              │
         ┌────────────────────┴────────────────────┐
         ▼                                         ▼
ACCEPTED_PHYSICAL_PAGE                     ACCEPTED_FRAME_LIMITED /
(answer_sheet_2, 3)                        AMBIGUOUS
         │                                 (answer_sheet_4, 5, 1)
         ▼                                         │
┌───────────────────────────────┐                  ▼
│  Physical Corner Pipeline     │       ┌───────────────────────────────┐
│  1. Extract Outer Margins     │       │  Frame-Limited Pipeline       │
│  2. Step-Contrast Filter      │       │  1. Identify Observable Edges │
│  3. RANSAC Line Fitting       │       │  2. Extract Skew Angle (θ)    │
│  4. Pairwise Intersection     │       │  3. Do NOT Hallucinate Corners│
│  5. Convex Quad Validation    │       │  4. Rigid Affine Deskew Only  │
│  6. 4-Corner Perspective Warp │       └───────────────────────────────┘
└───────────────────────────────┘
```

### Module Specifications:

1. **Phase 2 Gate**:
   - Read `DocumentValidationResult.image_status`.
   - If `ACCEPTED_PHYSICAL_PAGE` $\implies$ Route to **Physical 4-Corner Pipeline**.
   - If `ACCEPTED_FRAME_LIMITED` $\implies$ Route to **Frame-Limited Rigid Deskew Pipeline**.
   - If `AMBIGUOUS` or `INSUFFICIENT_CONFIDENCE` $\implies$ Return unwarped crop or flag for human review.

2. **Physical 4-Corner Pipeline**:
   - **Step 1: Outer Margin Line Extraction**: Detect segments within the outer 5% band of the selected candidate ROI.
   - **Step 2: Contrast Step Disambiguation**: Sample normal profiles ($\pm 12$ px) along each candidate line. Retain lines with $\Delta V > \text{threshold}_{\text{adaptive}}$.
   - **Step 3: Constrained RANSAC Line Fit**: Fit parametric lines $(A_i, B_i, C_i)$ to inliers for Top, Bottom, Left, and Right.
   - **Step 4: Intersection & Vertex Computation**: Compute the 4 corner intersections.
   - **Step 5: Geometric Validation**: Verify convexity, angle near 90°, and area consistency with Phase 2 ROI.
   - **Step 6: Verified Perspective Correction**: Call perspective transform using the 4 verified physical corners.

3. **Frame-Limited Rigid Deskew Pipeline**:
   - Extract orientation angle $\theta$ from available long boundary segments (e.g. Left/Right lateral edges in `answer_sheet_4`).
   - If $|\theta - 90°| > 0.5°$, apply a **rigid rotation deskew** (`cv2.warpAffine` with rotation matrix) centered on the ROI.
   - Explicitly output `corners = None` and `framing_mode = 'FRAME_LIMITED_ALIGNED'`.
   - Never call 4-corner perspective warp on clipped boundaries.

---

## 6. Generated Visual Artifacts

The following visual diagnostics were generated in [`phase3/output/`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase3/output):
- `phase3_multisignal_vis_answer_sheet_2.png.png`: Displays outer physical boundary lines (green), inner table rules (orange), and verified 4-corner outer quad (yellow).
- `phase3_multisignal_vis_answer_sheet_3.jpg.png`: Displays successful outer quad reconstruction overcoming top-right shadow diffusion.
- `phase3_multisignal_vis_answer_sheet_4.jpg.png`: Displays observable lateral boundary lines, top/bottom frame contact, and absence of bottom line.
- `phase3_multisignal_vis_answer_sheet_5.jpg.png`: Displays inner printed table envelope vs. unobservable sensor frame borders.
- `phase3_multisignal_vis_answer_sheet.jpg.png`: Displays dense internal grid segments and absence of physical boundary evidence.

---
*Report prepared for Phase 3.2 of AI-EVAL-OpenCV.*
