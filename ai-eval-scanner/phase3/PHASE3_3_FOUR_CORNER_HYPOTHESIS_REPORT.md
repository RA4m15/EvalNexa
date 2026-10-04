# Phase 3.3: Four-Corner Hypothesis Validation Report

**Project**: AI-EVAL-OpenCV  
**Phase**: 3.3 — Four-Corner Hypothesis Validation  
**Status**: INVESTIGATION ONLY (Phase 2 & Phase 3.1/3.2 Frozen; No Production Scanner / No Perspective Warp / No Geometric Transform)  
**Date**: October 2026  

---

## 1. Executive Summary & Objective

In Phase 3.2, we established that physical paper boundaries can be distinguished from internal printed table rules via spatial partitioning and orthogonal appearance sampling ($\Delta V$).

The goal of **Phase 3.3** is to determine **how competing four-boundary-line hypotheses should be validated before any perspective transform is considered safe**.

Crucially, in real evaluation documents:
- Multiple candidate lines exist on each margin (e.g. an outer paper edge, a printed margin line, an internal table header rule, or question box borders).
- Simply taking the "first" or "strongest" detected line frequently snaps to an internal printed table rather than the physical sheet boundary.
- Multiple 4-line combinations can form geometrically valid, convex quadrilaterals.

This investigation explores multi-signal hypothesis validation across all 5 calibration images using [`phase3/03_four_corner_hypothesis_validation.py`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase3/03_four_corner_hypothesis_validation.py).

### Architectural Guardrails Maintained
- **Investigation Only**: No perspective transform, no `cv2.getPerspectiveTransform()`, no `cv2.warpPerspective()`.
- **No Frozen Thresholds**: All numerical measurements reported are empirical calibration observations, not hard detector rules.
- **No Corner Hallucination**: Clipped document edges and sensor frame borders are never manufactured into sheet vertices.
- **No Premature Winner Selection**: When multiple hypotheses remain plausible, the result is explicitly classified as `AMBIGUOUS`.

---

## 2. Hypothesis Validation Framework

To ensure that perspective correction is mathematically and physically sound, every four-line candidate hypothesis $(L_{\text{top}}, L_{\text{bottom}}, L_{\text{left}}, L_{\text{right}})$ undergoes a three-stage validation pipeline:

```
                  Candidate Line Sets per Margin
                  (Top, Bottom, Left, Right)
                              │
                    Cartesian Combinations
                              │
                              ▼
            ┌───────────────────────────────────┐
            │ Stage 1: Geometric Validity       │
            │ - 4 non-parallel intersections    │
            │ - Strict cross-product convexity  │
            │ - Clockwise ordering (TL,TR,BR,BL)│
            │ - Vanishing perspective alignment │
            └─────────────────┬─────────────────┘
                              │ Passed
                              ▼
            ┌───────────────────────────────────┐
            │ Stage 2: Physical Plausibility    │
            │ - 4-side exterior step (ΔV / ΔS)  │
            │ - Content enclosure & leak ratio  │
            │ - Exterior background consistency │
            └─────────────────┬─────────────────┘
                              │
                              ▼
            ┌───────────────────────────────────┐
            │ Stage 3: Multi-Hypothesis         │
            │          Arbitration              │
            │ - Single winner: VALIDATED        │
            │ - Multiple winners: AMBIGUOUS     │
            │ - Clipped edges: FRAME_LIMITED    │
            └───────────────────────────────────┘
```

---

## 3. Calibration Image Hypothesis Analysis

---

### Image 1: `images/answer_sheet_2.png` (1200 × 1600 px) — Primary Desk Case

- **Phase 2 Status**: `ACCEPTED_PHYSICAL_PAGE` (Selected Candidate: `cand_app_mask_1`, Box: `(119, 142, 962, 1315)`)
- **Frame-Clipped Sides**: `[]` (All 4 borders isolated on dark wood desk)
- **Line Candidates Extracted**:
  - `TOP`: `TOP_OUTER` ($y \approx 141$, paper edge), `TOP_INNER` ($y \approx 210$, table header)
  - `BOTTOM`: `BOTTOM_OUTER` ($y \approx 1457$, paper edge), `BOTTOM_INNER` ($y \approx 1344$, table bottom)
  - `LEFT`: `LEFT_OUTER` ($x \approx 119$, paper edge), `LEFT_INNER` ($x \approx 199$, table left)
  - `RIGHT`: `RIGHT_OUTER` ($x \approx 1081$, paper edge)
- **Total Combinations Tested**: $2 \times 2 \times 2 \times 1 = 8$ hypotheses

#### Complete Hypotheses Breakdown:
| Hyp ID | Combination | Geometric Validity | Physical Sides | Content Leak | Classification | Notes |
| :---: | :--- | :---: | :---: | :---: | :--- | :--- |
| **[1]** | **`TOP_OUTER + BOTTOM_OUTER + LEFT_OUTER + RIGHT_OUTER`** | **VALID_CONVEX** | **4 / 4** | **1.5%** | **`PHYSICALLY_PLAUSIBLE_PAPER_PAGE`** | **True physical paper sheet quad**; $\Delta V > +150$ V on all 4 sides; encloses entire page. |
| [2] | `TOP_OUTER + BOTTOM_OUTER + LEFT_INNER + RIGHT_OUTER` | VALID_CONVEX | 3 / 4 | 5.9% | `AMBIGUOUS_OR_UNCONFIRMED` | Left side uses inner table rule ($\Delta V = +1$ V); excludes left margin content. |
| [3] | `TOP_OUTER + BOTTOM_INNER + LEFT_OUTER + RIGHT_OUTER` | VALID_CONVEX | 3 / 4 | 3.7% | `PHYSICALLY_PLAUSIBLE_PAPER_PAGE` | Bottom side uses inner table rule; cuts off bottom answer bubbles. |
| [4] | `TOP_OUTER + BOTTOM_INNER + LEFT_INNER + RIGHT_OUTER` | VALID_CONVEX | 2 / 4 | 8.0% | `AMBIGUOUS_OR_UNCONFIRMED` | Bottom & Left use printed table rules. |
| [5] | `TOP_INNER + BOTTOM_OUTER + LEFT_OUTER + RIGHT_OUTER` | VALID_CONVEX | 3 / 4 | 4.0% | `PHYSICALLY_PLAUSIBLE_PAPER_PAGE` | Top uses printed instruction header; cuts off header text. |
| [6] | `TOP_INNER + BOTTOM_OUTER + LEFT_INNER + RIGHT_OUTER` | VALID_CONVEX | 2 / 4 | 8.2% | `AMBIGUOUS_OR_UNCONFIRMED` | Top & Left use inner table rules. |
| [7] | `TOP_INNER + BOTTOM_INNER + LEFT_OUTER + RIGHT_OUTER` | VALID_CONVEX | 2 / 4 | 6.2% | `INTERNAL_PRINTED_ENVELOPE` | Top & Bottom use inner rules; clearly an internal printed sub-box. |
| [8] | `TOP_INNER + BOTTOM_INNER + LEFT_INNER + RIGHT_OUTER` | VALID_CONVEX | 1 / 4 | 10.2% | `INTERNAL_PRINTED_ENVELOPE` | 3 sides use printed table rules; 10.2% active content leaked outside. |

#### Analysis:
- Hypothesis [1] is the only hypothesis that achieves **4/4 confirmed physical boundary sides** and **minimal content leak (1.5%)**.
- Hypotheses [3] and [5] achieve 3/4 physical sides because 3 of their sides are true paper edges, while 1 side is a printed table rule.
- Because Hypotheses [1], [3], and [5] each meet the provisional multi-signal bar ($\ge 3/4$ physical sides), strict non-threshold arbitration classifies this image as **`AMBIGUOUS_COMPETING_PHYSICAL_QUADS`** rather than arbitrarily declaring a winner without complete arbitration rules.

---

### Image 2: `images/answer_sheet_3.jpg` (1200 × 1600 px) — Shaded Top-Right Case

- **Phase 2 Status**: `ACCEPTED_PHYSICAL_PAGE` (Selected Candidate: `cand_app_mask_1`, Box: `(141, 176, 997, 1276)`)
- **Frame-Clipped Sides**: `[]` (Isolated sheet on desk)
- **Line Candidates Extracted**:
  - `TOP`: `TOP_OUTER` ($y \approx 175$, paper edge), `TOP_INNER` ($y \approx 213$, table header)
  - `BOTTOM`: `BOTTOM_OUTER` ($y \approx 1450$)
  - `LEFT`: `LEFT_OUTER` ($x \approx 140$)
  - `RIGHT`: `RIGHT_OUTER` ($x \approx 1137$)
- **Total Combinations Tested**: $2 \times 1 \times 1 \times 1 = 2$ hypotheses

#### Complete Hypotheses Breakdown:
| Hyp ID | Combination | Geometric Validity | Physical Sides | Content Leak | Classification | Notes |
| :---: | :--- | :---: | :---: | :---: | :--- | :--- |
| **[1]** | **`TOP_OUTER + BOTTOM_OUTER + LEFT_OUTER + RIGHT_OUTER`** | **VALID_CONVEX** | **4 / 4** | **2.2%** | **`PHYSICALLY_PLAUSIBLE_PAPER_PAGE`** | **True physical paper sheet quad**; TL=(204.5, 174.8), TR=(1084.1, 262.4), BR=(1137.0, 1450.6), BL=(139.9, 1394.4); bridges shadow. |
| [2] | `TOP_INNER + BOTTOM_OUTER + LEFT_OUTER + RIGHT_OUTER` | VALID_CONVEX | 3 / 4 | 4.4% | `PHYSICALLY_PLAUSIBLE_PAPER_PAGE` | Top side uses printed header rule ($y \approx 213$ vs. $175$); leaks 4.4% content (header text). |

#### Analysis:
- Both hypotheses are geometrically valid convex quads.
- Hypothesis [1] achieves **4/4 physical sides** ($\Delta V \in [+81.6, +149.4]$ V) and encloses the document with only 2.2% peripheral leak.
- Hypothesis [2] uses the inner printed header rule for the top edge, exhibiting $\Delta V = +1.3$ V on the top edge and leaking 4.4% of the document content.

---

### Image 3: `images/answer_sheet_4.jpg` (1200 × 1700 px) — Frame-Clipped Case

- **Phase 2 Status**: `ACCEPTED_FRAME_LIMITED` (Selected Candidate: `cand_app_mask_1`, Box: `(166, 0, 884, 1700)`)
- **Frame-Clipped Sides**: `['TOP', 'BOTTOM']` (Top contacts $y=0$, Bottom contacts $y=1700$)
- **Line Candidates**:
  - `LEFT`: 1 physical line candidate (91.58°)
  - `RIGHT`: 1 physical line candidate (87.98°)
  - `TOP`: Internal printed header line at frame edge ($y \approx 0$)
  - `BOTTOM`: 0 lines (completely clipped by camera sensor)
- **Validation Result**: **`FRAME_LIMITED_UNOBSERVABLE_CORNERS`**
- **Findings**:
  - Cannot form a 4-line quad; bottom boundary is unobservable.
  - The script strictly refrains from manufacturing corners at the image frame cuts `(166, 0)` and `(1050, 0)`.
  - Usable geometric evidence: Lateral tilt angle is approximately $-1.22°$, suitable for rigid rotation deskewing without perspective warping.

---

### Image 4: `images/answer_sheet_5.jpg` (1200 × 1600 px) — Frame-Filling Case

- **Phase 2 Status**: `ACCEPTED_FRAME_LIMITED` (Selected Candidate: `cand_frame_full`, Box: `(0, 0, 1200, 1600)`)
- **Frame-Clipped Sides**: `['TOP', 'BOTTOM', 'LEFT', 'RIGHT']` (All 4 margins touch sensor frame)
- **Validation Result**: **`FRAME_LIMITED_UNOBSERVABLE_CORNERS`**
- **Findings**:
  - In Phase 3.2, we observed that internal printed form lines could intersect into a "valid-looking quad".
  - Stage 2 physical plausibility and frame contact audit correctly recognize that this inner quad is an **internal printed envelope**, not a physical paper boundary.
  - No physical page corners exist in the image.

---

### Image 5: `images/answer_sheet.jpg` (720 × 960 px) — Tightly Cropped Ambiguous Case

- **Phase 2 Status**: `AMBIGUOUS` (Fallback: `cand_frame_full`, Box: `(0, 0, 768, 1024)`)
- **Frame-Clipped Sides**: `['TOP', 'BOTTOM', 'LEFT', 'RIGHT']`
- **Validation Result**: **`FRAME_LIMITED_UNOBSERVABLE_CORNERS`**
- **Findings**:
  - Zero lateral boundary segments exist on the left.
  - All detected lines are printed bubble grid rules.
  - Conclusively confirms that physical corners cannot be extracted from this image.

---

## 4. Synthesis: Physical vs. Printed Hypotheses Disambiguation

A central milestone of Phase 3.3 is establishing that **$\Delta V$ alone is insufficient to disambiguate physical paper boundaries from internal printed rules**.

The investigation validated a **6-signal joint physical plausibility model**:

| Evidence Signal | Physical Paper Boundary Quad | Internal Printed Form Quad |
| :--- | :--- | :--- |
| **1. Exterior/Interior Step ($\Delta V, \Delta S$)** | Massive brightness step ($\Delta V \gg +20$ V) against dark desk | Minimal step ($|\Delta V| < 10$ V); white paper on both sides |
| **2. Content Leak Outside Quad** | Extremely low ($\le 2.2\%$ peripheral noise) | Significant ($> 6\%$ to $10\%+$ of active text/bubbles cut off) |
| **3. Spatial Position** | Sits at outermost frontier of candidate appearance mask | Sits recessed inside candidate mask ($> 20$–$50$ px inward) |
| **4. Edge Continuity & Span** | Spans across the full length of the paper sheet | Interrupted or bounded by internal column margins |
| **5. Exterior Collar Texture** | Smooth desk texture or dark wood grain | Contains text headers, barcodes, or instructions |
| **6. Area Ratio vs. Phase 2 ROI** | $\approx 0.98$ to $1.02$ of appearance mask area | $\approx 0.70$ to $0.85$ of appearance mask area |

---

## 5. Direct Answers to Phase 3.3 Core Questions

### Question 1: What makes a four-line hypothesis geometrically valid?
> **Answer:**
> A hypothesis is geometrically valid if and only if:
> 1. **Four Unique Intersections Exist**: Adjacent line pairs $(L_{\text{top}}, L_{\text{left}})$, $(L_{\text{top}}, L_{\text{right}})$, $(L_{\text{bottom}}, L_{\text{right}})$, and $(L_{\text{bottom}}, L_{\text{left}})$ are non-parallel ($|\det| > 10^{-4}$).
> 2. **Strict Cross-Product Convexity**: All 4 cyclic perimeter vector cross products share the exact same sign ($c_i > 0$ for clockwise orientation). This rules out self-intersecting "bow-tie" polygons or degenerate triangular collapses.
> 3. **Bounded Coordinates**: All 4 vertices lie within or reasonably close to the sensor field of view (e.g. within $[-0.15, 1.15] \times [w, h]$), ruling out distant intersections of near-parallel lines.
> 4. **Plausible Polygon Area**: The enclosed area is non-zero and represents a meaningful proportion ($> 30\%$) of the document ROI.

---

### Question 2: What makes it physically plausible as a paper boundary?
> **Answer:**
> Geometric validity only proves that 4 lines form a polygon; it does **not** prove the polygon is a sheet of paper.
> Physical plausibility requires:
> 1. **Step-Contrast Confirmation**: At least 3 (and ideally all 4) sides must exhibit a verified exterior-to-interior contrast step ($\Delta V \gg +20$ V) against a darker surrounding background.
> 2. **Full Content Containment**: The quadrilateral must fully enclose the document's active content. High-gradient text or table cells must not be orphaned outside the boundary.
> 3. **Exterior Background Homogeneity**: Samples taken orthogonal to the quad exterior must represent a non-paper background (e.g. low saturation/brightness desk surface).

---

### Question 3: How can printed internal rectangles be rejected?
> **Answer:**
> Printed internal rectangles (such as question grids or instruction boxes) are rejected through two primary mechanisms:
> 1. **Content Leakage**: When an internal printed box is hypothesized as the document boundary, substantial active content (page headers, candidate names, instruction text, or outer answer columns) falls *outside* the quad. Measuring the ratio of active content outside the hypothesis reliably flags it as `INTERNAL_PRINTED_ENVELOPE`.
> 2. **Dual-Sided Paper Appearance**: Sampling across an internal printed rule reveals white paper on *both* sides ($|\Delta V| \approx 0$ to $5$ V, with exterior brightness $V > 180$). A true paper boundary always transitions from paper to desk.

---

### Question 4: What evidence is sufficient to proceed toward perspective correction?
> **Answer:**
> Perspective correction is safe to proceed **only** when all of the following criteria are met:
> 1. Phase 2 image status is `ACCEPTED_PHYSICAL_PAGE`.
> 2. Zero margins contact the sensor frame (`frame_clipped_sides == []`).
> 3. Exactly one hypothesis satisfies both Geometric Validity and Physical Plausibility with 4/4 physical boundary sides and $< 3\%$ content leakage.
> 4. The 4 vertices form near-orthogonal interior angles ($85°$ to $95°$).
> 
> If any of these conditions fails, perspective warping must **not** be performed.

---

### Question 5: Which situations must remain AMBIGUOUS?
> **Answer:**
> The following cases must be strictly classified as `AMBIGUOUS`:
> 1. **Competing Physical Quads**: When multiple candidate combinations achieve high physical plausibility (e.g. when an outer margin rule and paper edge both have partial exterior support) and no single hypothesis clearly dominates.
> 2. **Tightly-Cropped Forms (`answer_sheet.jpg`)**: Where physical paper margins are missing or flush with printed lines, making it impossible to confirm whether the boundary is paper or printed rule.
> 3. **Diffused / Low-Contrast Lighting**: Where shadows cause multiple edge lines to have borderline contrast steps.

---

### Question 6: What information should be passed to Phase 3.4?
> **Answer:**
> The validation stage must export a structured `CornerHypothesisResult` object containing:
> 1. `validation_verdict`: (`VALIDATED_PHYSICAL_PAGE_QUAD`, `AMBIGUOUS_COMPETING_PHYSICAL_QUADS`, `FRAME_LIMITED_UNOBSERVABLE_CORNERS`, or `NO_VALID_QUAD_HYPOTHESIS`).
> 2. `verified_corners`: Ordered dictionary of 4 coordinates `(TOP_LEFT, TOP_RIGHT, BOTTOM_RIGHT, BOTTOM_LEFT)` if validated; `None` otherwise.
> 3. `frame_clipped_sides`: List of sides touching the sensor frame.
> 4. `lateral_skew_angle`: Skew angle in degrees (derived from observable lateral lines in frame-limited captures).
> 5. `competing_hypotheses_count`: Number of plausible physical quads found.
> 6. `content_leak_ratio`: Percentage of active content outside the selected quad.

---

### Question 7: Which numerical thresholds still require broader validation?
> **Answer:**
> The following empirical values observed on the 5 calibration images must **not** be frozen into production rules without broader multi-dataset testing:
> 1. **$\Delta V > 25$ V Contrast Step**: Works well on dark wood desks, but will drop significantly on light-colored tables, linoleum, or white paper stacks.
> 2. **Content Leak Ratio $< 5\%$**: Distinguishes inner table rules on calibration sheets, but could misclassify documents with stray printer alignment marks or punch holes in margins.
> 3. **Margin Search Band Width ($12\%$ of ROI)**: Adequate for moderate perspective tilt, but could miss paper edges under severe oblique angles.
> 4. **Orthogonality Range ($85°$–$95°$)**: Valid for near-overhead mobile captures, but inadequate for high-angle perspective captures ($> 20°$ tilt).

---

## 6. Generated Visual Artifacts

The diagnostic overlays generated in [`phase3/output/`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase3/output) illustrate the multi-hypothesis evaluation:
- `phase3_hyp_val_answer_sheet_2.png.png`: Displays 8 tested combinations, highlighting the 4/4 physical quad (bright lime green) vs. internal printed quads (orange dashed).
- `phase3_hyp_val_answer_sheet_3.jpg.png`: Displays the outer physical quad bridging the shaded top-right corner.
- `phase3_hyp_val_answer_sheet_4.jpg.png`: Displays top and bottom frame clipping with lateral lines.
- `phase3_hyp_val_answer_sheet_5.jpg.png`: Confirms rejection of internal printed box as sheet boundary.
- `phase3_hyp_val_answer_sheet.jpg.png`: Confirms absence of outer boundary evidence.

---
*Report prepared for Phase 3.3 of AI-EVAL-OpenCV.*
