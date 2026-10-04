# Phase 3.3-C: Hypothesis Consolidation & Arbitration Investigation Report

**Project**: AI-EVAL-OpenCV  
**Phase**: 3.3-C — Hypothesis Consolidation & Arbitration Investigation  
**Status**: INVESTIGATION ONLY (Phase 2, Phase 3.1, 3.2, 3.3 Frozen; No Production Scanner / No Perspective Warp / No Geometric Transform)  
**Date**: October 2026  

---

## 1. Executive Summary & Objective

Phase 3.3 revealed that for isolated physical pages (`answer_sheet_2.png`, `answer_sheet_3.jpg`), evaluating multiple 4-line combinations generated multiple candidate quadrilaterals with high contrast steps ($\ge 3/4$ physical sides).

The objective of **Phase 3.3-C** is to answer a crucial architectural question:
> **Do multiple plausible four-corner hypotheses represent genuinely different physical-page interpretations (e.g. ambiguity), or are they merely small fitting variations of the exact same physical boundary?**

Additionally, this investigation explicitly enforces the architectural correction regarding **`images/answer_sheet.jpg`**:
- In Phase 2.13, `answer_sheet.jpg` was classified as `AMBIGUOUS`.
- In Phase 3.3, it was temporarily grouped under `FRAME_LIMITED`.
- **Phase 3.3-C definitively restores and clarifies the boundary between `AMBIGUOUS` (content-level ambiguity without observable paper edges) and `FRAME_LIMITED` (physical sheet confirmed to be cut off by camera frame bounds).**

Diagnostic script [`phase3/03c_hypothesis_consolidation_investigation.py`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase3/03c_hypothesis_consolidation_investigation.py) was executed across all 5 calibration images.

---

## 2. Hypothesis Clustering & Consolidation Framework

To determine whether candidate hypotheses represent distinct physical entities or minor mathematical fitting variants, we measure:
1. **Intra-Hypothesis Polygon Overlap (IoU)**: $\frac{\text{Area}(H_A \cap H_B)}{\text{Area}(H_A \cup H_B)}$.
2. **Mean & Max Corner Displacement ($\Delta d_{\text{corners}}$)**: Euclidean shift of corresponding vertices $(P_{\text{TL}}, P_{\text{TR}}, P_{\text{BR}}, P_{\text{BL}})$.
3. **Normal Side Displacement ($\Delta d_{\text{sides}}$)**: Perpendicular distance between corresponding boundary lines.
4. **Structural Line Identity**: Distinguishing small fitting variants (e.g. RANSAC inlier fit vs. PCA least-squares fit on the *same* margin edge) from structural line swaps (e.g. replacing the top paper edge with an internal printed table header rule).

```
                      Candidate Four-Line Hypotheses
                                    │
                        Pairwise Metric Evaluation
                        - Polygon IoU
                        - Corner Displacement
                        - Structural Line Identity
                                    │
           ┌────────────────────────┴────────────────────────┐
           ▼                                                 ▼
High IoU (IoU ≥ 0.95)                             Lower IoU (IoU < 0.90)
Small Shift (Δd ≤ 15 px)                          Large Shift (Δd ≥ 30–80 px)
Same Structural Margin Edge                       Swapped Internal Printed Rule
           │                                                 │
           ▼                                                 ▼
[FITTING VARIANTS]                                [STRUCTURAL SWAPS]
Consolidate into single                           Separate distinct clusters:
physical boundary cluster                         - Physical Paper Outer Boundary
                                                  - Partially Swapped Hybrid
                                                  - Internal Printed Envelope
```

---

## 3. Calibration Image Consolidation Audit

---

### Image 1: `images/answer_sheet_2.png` (1200 × 1600 px) — Isolated Physical Page

- **Phase 2 Status**: `ACCEPTED_PHYSICAL_PAGE` (Appearance Mask Candidate `cand_app_mask_1`)
- **Total Hypotheses Formulated**: **18 combinations** (evaluating RANSAC vs. PCA fitting variants and outer vs. inner margin lines).
- **Valid Convex Quadrilaterals**: **18 / 18**.
- **Natural Clusters Formed**: **6 distinct clusters**.

#### Cluster Analysis Breakdown:
| Cluster ID | Size (N) | Structural Composition | Physical Interpretation | Mean Intra-Cluster IoU | Mean Corner Shift | Content Leakage |
| :---: | :---: | :--- | :--- | :---: | :---: | :---: |
| **`CLUSTER_1`** | **5** | **`TOP_OUTER (RANSAC/PCA) + BOTTOM_OUTER (RANSAC/PCA) + LEFT_OUTER + RIGHT_OUTER`** | **`PHYSICAL_PAPER_OUTER_BOUNDARY`** | **0.987** | **9.6 px** | **1.5%** |
| `CLUSTER_2` | 5 | `TOP_OUTER + BOTTOM_OUTER + LEFT_INNER + RIGHT_OUTER` | `PARTIALLY_SWAPPED_HYBRID` (Left Rule) | 0.987 | 9.2 px | 5.9% |
| `CLUSTER_3` | 3 | `TOP_OUTER + BOTTOM_INNER + LEFT_OUTER + RIGHT_OUTER` | `PARTIALLY_SWAPPED_HYBRID` (Bottom Rule) | 0.985 | 9.3 px | 3.7% |
| `CLUSTER_4` | 3 | `TOP_INNER + BOTTOM_INNER + LEFT_INNER + RIGHT_OUTER` | `INTERNAL_PRINTED_TABLE_ENVELOPE` | 0.985 | 9.3 px | 10.2% |
| `CLUSTER_5` | 1 | `TOP_INNER + BOTTOM_OUTER + LEFT_OUTER + RIGHT_OUTER` | `PARTIALLY_SWAPPED_HYBRID` (Top Rule) | 1.000 | 0.0 px | 4.0% |
| `CLUSTER_6` | 1 | `TOP_INNER + BOTTOM_OUTER + LEFT_INNER + RIGHT_OUTER` | `PARTIALLY_SWAPPED_HYBRID` (Top+Left) | 1.000 | 0.0 px | 8.2% |

#### Key Consolidation Findings:
1. **Fitting Variants Confirmed**:
   - The 5 hypotheses in `CLUSTER_1` differ *only* by whether RANSAC or PCA was used to fit the outer line segments.
   - They exhibit **98.7% polygon overlap (IoU = 0.987)** and an average corner vertex shift of only **9.6 pixels** (at 1200×1600 resolution, $< 0.6\%$ of image diagonal).
   - They represent **one single physical boundary entity**, not 5 competing physical pages.
2. **Structural Swaps Confirmed**:
   - Clusters 2, 3, 5, and 6 are formed by swapping 1 physical boundary edge with an internal printed table rule (e.g. swapping the top paper edge at $y \approx 141$ for the printed instruction header rule at $y \approx 217$).
   - This shifts the boundary by $\sim 76$ pixels inward and leaks active header text outside the quad (leakage jumps from $1.5\%$ to $4.0\%$–$10.2\%$).
3. **Consolidated Image Verdict**:
   - **`SINGLE_CONSOLIDATED_PHYSICAL_PAGE_HYPOTHESIS`**
   - There is **exactly ONE** outer physical paper boundary cluster (`CLUSTER_1`). The apparent ambiguity in Phase 3.3 was an artifact of counting line fitting variants as competing hypotheses.

---

### Image 2: `images/answer_sheet_3.jpg` (1200 × 1600 px) — Isolated Physical Page (Shaded)

- **Phase 2 Status**: `ACCEPTED_PHYSICAL_PAGE` (Appearance Mask Candidate `cand_app_mask_1`)
- **Total Hypotheses Formulated**: **2 combinations**.
- **Valid Convex Quadrilaterals**: **2 / 2**.
- **Natural Clusters Formed**: **1 cluster**.

#### Cluster Analysis Breakdown:
| Cluster ID | Size (N) | Structural Composition | Physical Interpretation | Mean Intra-Cluster IoU | Mean Corner Shift | Content Leakage |
| :---: | :---: | :--- | :--- | :---: | :---: | :---: |
| **`CLUSTER_1`** | **2** | **`TOP_OUTER/INNER + BOTTOM_OUTER + LEFT_OUTER + RIGHT_OUTER`** | **`PHYSICAL_PAPER_OUTER_BOUNDARY`** | **0.987** | **8.0 px** | **2.2%** |

#### Key Consolidation Findings:
1. The 2 hypotheses consolidate into **1 single physical cluster** with an IoU of **0.987** and a mean corner shift of **8.0 pixels**.
2. Both hypotheses capture the true physical geometry of the page on desk background while bridging the diffused shadow across the top-right corner.
3. **Consolidated Image Verdict**:
   - **`SINGLE_CONSOLIDATED_PHYSICAL_PAGE_HYPOTHESIS`**

---

### Image 3: `images/answer_sheet_4.jpg` (1200 × 1700 px) — Frame-Clipped Capture

- **Phase 2 Status**: `ACCEPTED_FRAME_LIMITED`
- **Frame-Clipped Margins**: `['TOP', 'BOTTOM']` (Top touches $y=0$, Bottom touches $y=1700$)
- **Valid 4-Corner Quads**: **0**.
- **Consolidated State**: **`FRAME_LIMITED_UNOBSERVABLE_CORNERS`**
- **Findings**:
  - The lateral physical paper borders are clearly visible against the desk background, but they exit the top and bottom sensor frame.
  - No 4-corner hypothesis can be constructed without hallucinating corners at image edges.
  - The script refrains from corner fabrication; usable lateral edge tilt is preserved for affine deskewing.

---

### Image 4: `images/answer_sheet_5.jpg` (1200 × 1600 px) — Frame-Filling Capture

- **Phase 2 Status**: `ACCEPTED_FRAME_LIMITED`
- **Frame-Clipped Margins**: `['TOP', 'BOTTOM', 'LEFT', 'RIGHT']` (All 4 margins touch sensor frame)
- **Valid 4-Corner Quads**: **0** (Internal printed table rules rejected).
- **Consolidated State**: **`FRAME_LIMITED_UNOBSERVABLE_CORNERS`**
- **Findings**:
  - The document fills 100% of the image frame.
  - While internal printed form rules exist, physical paper boundaries are completely absent.
  - Correctly prevented from treating internal form rules as physical page corners.

---

### Image 5: `images/answer_sheet.jpg` (720 × 960 px) — Ambiguous Tightly-Cropped Form

- **Phase 2 Status**: **`AMBIGUOUS`**
- **Frame-Clipped Margins**: None confirmed as physical paper exits.
- **Valid 4-Corner Quads**: **0**.
- **Consolidated State**: **`AMBIGUOUS_NO_VERIFIED_PHYSICAL_CORNERS`**
- **CRITICAL ARCHITECTURAL DISTINCTION**:
  - In `answer_sheet_4.jpg`, physical paper edges are *directly observable* running into and exiting the camera frame ($y=0$ and $y=1700$). This is **physical frame clipping** (`FRAME_LIMITED`).
  - In `answer_sheet.jpg`, **no physical paper edges are visible anywhere in the image**. The image is a pre-cropped digital scan of a printed evaluation form. The edges of the image simply truncate whitespace; there is no desk background, no physical boundary step, and no paper margin line.
  - Relabeling `answer_sheet.jpg` as `FRAME_LIMITED` would falsely imply that a physical sheet was photographed extending beyond the camera frame.
  - **Preserved Phase 2 State**: `AMBIGUOUS_NO_VERIFIED_PHYSICAL_CORNERS`. The system correctly reports that boundary evidence is missing/ambiguous.

---

## 4. Synthesis of Calibration Findings

| Image | Phase 2 State | Total Quads Formed | Distinct Physical Clusters | Intra-Cluster IoU | Final Phase 3.3-C Consolidated State |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`answer_sheet_2.png`** | `ACCEPTED_PHYSICAL_PAGE` | 18 | **1** (`CLUSTER_1`, N=5) | **0.987** | **`SINGLE_CONSOLIDATED_PHYSICAL_PAGE_HYPOTHESIS`** |
| **`answer_sheet_3.jpg`** | `ACCEPTED_PHYSICAL_PAGE` | 2 | **1** (`CLUSTER_1`, N=2) | **0.987** | **`SINGLE_CONSOLIDATED_PHYSICAL_PAGE_HYPOTHESIS`** |
| **`answer_sheet_4.jpg`** | `ACCEPTED_FRAME_LIMITED` | 0 | **0** | — | **`FRAME_LIMITED_UNOBSERVABLE_CORNERS`** |
| **`answer_sheet_5.jpg`** | `ACCEPTED_FRAME_LIMITED` | 0 | **0** | — | **`FRAME_LIMITED_UNOBSERVABLE_CORNERS`** |
| **`answer_sheet.jpg`** | `AMBIGUOUS` | 0 | **0** | — | **`AMBIGUOUS_NO_VERIFIED_PHYSICAL_CORNERS`** |

---

## 5. Direct Answers to Phase 3.3-C Core Questions

### Question 1: How many DISTINCT physical-page hypotheses exist per calibration image?
> **Answer:**
> - `answer_sheet_2.png`: **Exactly ONE** distinct physical paper boundary cluster (`CLUSTER_1`). All 5 constituent hypotheses are small fitting variants of the same physical edges.
> - `answer_sheet_3.jpg`: **Exactly ONE** distinct physical paper boundary cluster (`CLUSTER_1`).
> - `answer_sheet_4.jpg`: **ZERO**. Physical sheet vertices are cut off by the top and bottom sensor frame.
> - `answer_sheet_5.jpg`: **ZERO**. Physical paper boundaries are unobservable (frame-filling capture).
> - `answer_sheet.jpg`: **ZERO**. No physical paper boundary evidence exists.

---

### Question 2: Which hypotheses are merely fitting variants of the same boundary?
> **Answer:**
> Hypotheses that use the **same underlying margin edge segments** but vary only by the numerical fitting estimator (e.g. RANSAC inlier consensus vs. PCA total least-squares) are merely fitting variants.
> In our calibration audit, these variants consistently exhibit:
> - Polygon overlap IoU $\ge 0.985$
> - Corner displacement $\Delta d \le 10$ pixels
> - Zero structural line swaps
> These should be consolidated into a single hypothesis cluster rather than treated as competing physical pages.

---

### Question 3: Can competing hypotheses be consolidated safely?
> **Answer: YES.**
> By grouping hypotheses using geometric similarity (high IoU, low vertex displacement) and structural line identity, minor fitting variations can be averaged or represented by an exemplar.
> However, hypotheses that represent **structural swaps** (e.g. swapping an outer paper line for an internal table rule, causing IoU $< 0.90$ and corner shift $> 50$ px) must **never** be merged; they must remain distinct and be arbitrated using physical evidence (content leakage and exterior appearance step).

---

### Question 4: What evidence distinguishes an outer physical boundary from an internal printed rectangle?
> **Answer:**
> 1. **Content Leakage Ratio**: Internal printed rectangles orphan substantial document content (instruction text, headers, outer bubble columns) outside their boundary ($> 4\%$ to $10\%+$ leak). True outer paper boundaries enclose all active content ($\le 2\%$ peripheral noise).
> 2. **Exterior Contrast Step ($\Delta V$)**: True outer paper boundaries exhibit a massive step ($\Delta V > +80$ to $+160$ V) transitioning from paper to dark desk. Internal printed rules have white paper on both sides ($|\Delta V| \le 5$ V).
> 3. **Spatial Margin Offset**: Internal table rules sit $> 20$ to $70$ pixels recessed inside the candidate appearance envelope.

---

### Question 5: What should the correct semantic state of `answer_sheet.jpg` be?
> **Answer: `AMBIGUOUS_NO_VERIFIED_PHYSICAL_CORNERS`.**
> `answer_sheet.jpg` must **not** be relabeled as `FRAME_LIMITED`.
> - In `FRAME_LIMITED` captures (`answer_sheet_4`, `answer_sheet_5`), physical paper is confirmed to contact or exit the sensor frame.
> - In `answer_sheet.jpg`, **no physical paper boundary was ever photographed**. It is a tight digital scan of a printed form where paper edges are absent or flush with whitespace.
> Preserving `AMBIGUOUS_NO_VERIFIED_PHYSICAL_CORNERS` maintains strict architectural consistency with Phase 2.13.

---

### Question 6: What information should Phase 3.4 receive?
> **Answer:**
> Phase 3.4 (Perspective Transformation & Scanning Architecture) should receive a structured record containing:
> 1. `semantic_state`: One of:
>    - `VALIDATED_PHYSICAL_PAGE` (for `answer_sheet_2`, `answer_sheet_3`)
>    - `FRAME_LIMITED_PARTIAL` (for `answer_sheet_4`, `answer_sheet_5`)
>    - `AMBIGUOUS_DOCUMENT` (for `answer_sheet`)
> 2. `consolidated_corners`: The 4 validated coordinates $(P_{\text{TL}}, P_{\text{TR}}, P_{\text{BR}}, P_{\text{BL}})$ for `VALIDATED_PHYSICAL_PAGE`; `None` otherwise.
> 3. `lateral_skew_angle`: Skew angle in degrees for frame-limited documents (enabling affine deskewing without warping).
> 4. `framing_metadata`: Observable vs. unobservable sides.

---

### Question 7: Which production decisions still require broader validation?
> **Answer:**
> 1. **Clustering IoU Threshold**: While IoU $\ge 0.95$ cleanly separated fitting variants from table swaps on calibration sheets, documents with very narrow margins (e.g. $< 10$ px margin) may exhibit higher IoU between table rules and paper edges.
> 2. **Sub-Pixel Vertex Averaging**: Investigating whether the centroid of cluster vertices or the RANSAC exemplar provides superior perspective accuracy.
> 3. **Non-Overhead Capture Geometry**: Evaluating cluster behavior on extreme perspective tilts ($> 30°$) where opposite sides converge significantly.

---

## 6. Generated Visual Artifacts

The diagnostic overlays generated in [`phase3/output/`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase3/output) illustrate the consolidation audit:
- `phase3_consolidation_answer_sheet_2.png.png`: Displays the 6 hypothesis clusters, showing that `CLUSTER_1` (lime green) consolidates 5 fitting variants into 1 physical page interpretation, while orange/magenta clusters represent inner table swaps.
- `phase3_consolidation_answer_sheet_3.jpg.png`: Displays consolidation of outer boundary variants bridging the shaded corner.
- `phase3_consolidation_answer_sheet_4.jpg.png`: Displays frame-limited lateral edges with clipped top and bottom.
- `phase3_consolidation_answer_sheet_5.jpg.png`: Displays frame-filling document with rejected inner printed quad.
- `phase3_consolidation_answer_sheet.jpg.png`: Displays ambiguous form scan confirming absence of physical paper edges.

---
*Report prepared for Phase 3.3-C of AI-EVAL-OpenCV.*
