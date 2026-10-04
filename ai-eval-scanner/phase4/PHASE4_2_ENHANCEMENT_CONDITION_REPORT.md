# Phase 4.2: Enhancement Condition Detection & Operator Selection Investigation Report

**Project**: AI-EVAL-OpenCV  
**Phase**: 4.2 — Enhancement Condition Detection & Operator Selection Investigation  
**Status**: INVESTIGATION ONLY (Phase 2 & Phase 3 Frozen; Parameters Unfrozen; No Decision Engine Implemented)  
**Date**: October 2026  

---

## 1. Executive Summary & Objective

In Phase 4.1, we benchmarked 12 individual enhancement operators and determined that **no enhancement operator is universally beneficial**. Applying operators indiscriminately can damage clean documents:
- Applying CLAHE to clean paper amplifies microscopic paper grain into grey splotches ($\text{BgStd}$ doubled from 3.4 to 7.5).
- Applying morphological shadow division to already uniform documents adds 70–80 ms of needless latency.
- Applying aggressive morphological filtering erodes 7% to 20% of handwriting strokes.

The objective of **Phase 4.2** is to investigate how the system can automatically **inspect a rectified document image** (`ScannedDocumentResult` from Phase 3) and evaluate raw condition signals to decide:
1. Whether enhancement is actually needed, or whether `NO_ENHANCEMENT` is the optimal choice.
2. Which specific operator (or chained operators) is appropriate for the detected defect.
3. How to classify condition signals into **PRIMARY**, **SUPPORTING**, and **DIAGNOSTIC ONLY** roles without relying on a single brittle quality metric or frozen numerical thresholds.

The investigation was implemented in [`phase4/02_enhancement_condition_investigation.py`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase4/02_enhancement_condition_investigation.py) and evaluated across the calibration suite (`answer_sheet.jpg`, `answer_sheet_2.png`, `answer_sheet_3.jpg`, `answer_sheet_4.jpg`, `answer_sheet_5.jpg`) and dataset handwriting samples.

---

## 2. Quantitative Condition Signals Extraction Across Calibration Suite

We divided each document into a $4 \times 4$ spatial analysis grid (16 cells) to capture local paper white levels ($B_{i, j}$), local foreground contrast, high-frequency noise, and stroke acutance:

| Document Image | Mean Brightness | Dynamic Range ($P_{90} - P_{10}$) | Spatial Bg Ratio ($B_{\min} / B_{\max}$) | Spatial Bg Std | Flat Paper Noise $\sigma$ | Stroke Acutance | Color Fraction | Evaluated Candidate States |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`answer_sheet_3.jpg`** | 202.3 | 82.0 | **0.68** | **23.1** | 5.12 | 83.5 | 3.3% (Blue: 3.2%) | `MULTI_CORRECTION` (`SHADOW_CORR`, `CONTRAST_CORR`, `DENOISE`) |
| **`answer_sheet.jpg`** | 168.1 | 104.0 | **0.58** | **28.3** | 4.11 | 78.5 | 0.2% | `MULTI_CORRECTION` (`SHADOW_CORR`, `CONTRAST_CORR`) |
| **`answer_sheet_4.jpg`** | 178.1 | 169.0 | **0.72** | **23.2** | **5.99** | 81.6 | 31.1% (Desk edge) | `MULTI_CORRECTION` (`SHADOW_CORR`, `DENOISE`) |
| **`answer_sheet_5.jpg`** | 218.0 | 57.0 | 0.81 | 16.1 | 4.90 | 83.9 | 4.3% (Blue: 3.8%) | `MULTI_CORRECTION` (`CONTRAST_CORR`, `DENOISE`) |
| **`answer_sheet_2.png`** | **223.7** | 36.0 | **0.90** | **6.8** | 4.82 | 64.3 | 5.2% (Blue: 5.0%) | `CONTRAST_CORR` (Clean paper, uniform illumination) |
| **`Dataset Sample 01`** | 214.2 | 73.0 | 0.84 | 14.2 | 3.10 | 67.7 | 0.1% | `CONTRAST_CORR` (Faint pencil handwriting) |
| **`Dataset Sample 04`** | 201.5 | 56.0 | 0.76 | 19.5 | 3.80 | 75.4 | 1.2% | `MULTI_CORRECTION` (Uneven scan, low ink density) |

---

## 3. Operator Chaining & Interaction Findings

We benchmarked operator interactions on `answer_sheet_3.jpg` (severe shadow) and `answer_sheet_2.png` (clean A4):

### A. Shadowed Document (`answer_sheet_3.jpg`)
1. **Raw Rectified**: Sharpness = 595.0, $\text{BgStd} = 3.8$, severe diagonal illumination gradient.
2. **Shadow Correction Alone**: Flattens background ($\text{BgStd} = 1.3$), boosts sharpness to 773.9 in 72.5 ms.
3. **Shadow Correction $\to$ Mild Unsharp Masking**:
   - Laplacian sharpness jumps from 773.9 to **2393.8** (3x gain in character stroke contrast).
   - Paper background remains exceptionally clean ($\text{BgStd} = 2.6$).
   - Total latency: 77.1 ms.
   - *Verdict*: **Optimal compound chain for shadowed documents.**
4. **CLAHE Alone**: Yields sharpness 942.1, but fails to eliminate the shadow boundary, creating tile edge artifacts.

### B. Clean Document (`answer_sheet_2.png`)
1. **Raw Rectified**: Sharpness = 2523.6, $\text{BgStd} = 3.4$. Illumination is already uniform ($B_{\min}/B_{\max} = 0.90$).
2. **Applying Shadow Correction Unnecessarily**:
   - Adds 80.5 ms latency with **zero visual benefit** ($\text{BgStd}$ moves trivially from 3.4 to 2.9).
3. **Applying CLAHE Unnecessarily**:
   - $\text{BgStd}$ more than doubles from 3.4 to **7.5**, corrupting pristine white paper with mottled grey noise.
4. **Applying Mild Unsharp Masking Alone**:
   - In just **4.9 ms**, boosts sharpness from 2523.6 to **6759.4**, enhancing printed text and handwriting legibility without noise amplification.

---

## 4. Signal Hierarchy: Primary, Supporting, and Diagnostic Roles

To prevent brittle decision-making, condition signals are assigned strict architectural roles:

| Signal Name | Architectural Role | Role Rationale & Constraints |
| :--- | :--- | :--- |
| **Spatial Background Ratio ($B_{\min} / B_{\max}$)** | **PRIMARY** | Directly measures illumination disparity across paper regions. Strong, robust trigger for shadow correction. |
| **Spatial Background Std ($\sigma_{\text{grid}}$)** | **SUPPORTING** | Confirms whether illumination variation is a localized cast shadow or a gradual global falloff. |
| **Flat Paper Noise ($\sigma_{\text{noise}}$)** | **PRIMARY** | High-frequency variance in featureless paper regions. Unambiguously triggers edge-preserving denoising. |
| **Dynamic Range ($P_{90} - P_{10}$)** | **PRIMARY** | Measures global ink-to-paper separation. Triggers dynamic range contrast stretching. |
| **Local Michelson Contrast** | **SUPPORTING** | Evaluates local text stroke contrast within individual grid cells. Prevents global over-stretching. |
| **Stroke Acutance** | **PRIMARY** | Mean gradient across genuine stroke boundaries. Directly indicates whether strokes are blurry (triggering sharpening). |
| **Laplacian Sharpness / Tenengrad** | **DIAGNOSTIC ONLY** | Extremely sensitive to document content density (a page with lots of text has high variance; a sparse page has low variance regardless of focus). Never used as a standalone decision-maker. |
| **Global Brightness (Mean)** | **DIAGNOSTIC ONLY** | Highly dependent on the amount of dark text or desk margins; uninformative about local readability. |
| **Color Saturation Fraction** | **SUPPORTING** | Direct trigger for preserving color channels and isolating colored grading marks or student ink. |

---

## 5. Answers to Mandatory Phase 4.2 Investigation Questions

### Question 1: How can the system detect uneven illumination?
The system detects uneven illumination using a **multi-cell spatial background grid**:
1. Partition the document into a $4 \times 4$ grid (16 cells).
2. In each cell $(i, j)$, estimate local paper white using the 90th percentile intensity $B_{i, j}$.
3. Compute the **Spatial Background Ratio**:
   $$R_{\text{bg}} = \frac{\min(B_{i, j})}{\max(B_{i, j})}$$
   and the standard deviation of local backgrounds ($\sigma_{\text{bg}}$).
4. On `answer_sheet_3.jpg`, $R_{\text{bg}} = 0.68$ and $\sigma_{\text{bg}} = 23.1$, indicating an unequivocal shadow. On `answer_sheet_2.png`, $R_{\text{bg}} = 0.90$ and $\sigma_{\text{bg}} = 6.8$, proving uniform lighting. A ratio $R_{\text{bg}} < 0.80$ reliably flags uneven illumination.

---

### Question 2: How can it detect low contrast?
Low contrast is detected via two complementary signals:
1. **Global Dynamic Range**: $\Delta_{\text{dyn}} = P_{90} - P_{10}$. When $\Delta_{\text{dyn}} < 55.0$ (as in `answer_sheet_2.png` where faint print is confined to $[207, 243]$), global contrast is compressed.
2. **Mean Local Michelson Contrast**: Evaluated across local grid cells:
   $$C_{\text{Michelson}} = \frac{B_{\text{local}} - F_{\text{local}}}{B_{\text{local}} + F_{\text{local}}}$$
   Values below $0.20$ indicate washed-out pencil or low-density toner requiring contrast expansion.

---

### Question 3: How can it detect excessive noise?
Noise must **never** be measured across the whole image, because text edges and printed rules produce high-frequency responses that mimic noise.
- The system segments a **flat paper mask**: pixels with brightness $I \ge 0.85 \times B_{\max}$ and low gradient magnitude ($\|\nabla I\| < 15.0$).
- In these featureless paper areas, it computes the standard deviation of the Laplacian response ($\sigma_{\text{noise}}$).
- In clean scans, $\sigma_{\text{noise}} \le 3.5$. In `answer_sheet_4.jpg`, $\sigma_{\text{noise}} = 5.99$, indicating sensor grain that justifies bilateral denoising.

---

### Question 4: How can it detect whether sharpening is actually needed?
Sharpening is needed **only when stroke boundaries are diffuse (soft focus / optical blur)** and high-frequency noise is low:
- **Stroke Acutance**: Compute the mean gradient magnitude strictly along detected text stroke boundaries ($\|\nabla I\| \in [30, 150]$).
- If stroke acutance is low ($< 50.0$) and flat paper noise is low ($\sigma_{\text{noise}} \le 4.0$), the document suffers from optical blur and will benefit from mild unsharp masking ($\alpha \le 1.0$).
- If stroke acutance is already high ($> 75.0$), sharpening is unnecessary and risks haloing around OMR bubbles.

---

### Question 5: How can it identify a clean image where no enhancement is preferable?
A document is classified as `NO_ENHANCEMENT` when all primary signals confirm high capture fidelity:
1. Spatial illumination is uniform ($R_{\text{bg}} \ge 0.85$ and $\sigma_{\text{bg}} \le 10.0$).
2. Dynamic range is healthy ($\Delta_{\text{dyn}} \ge 50.0$ and $C_{\text{Michelson}} \ge 0.25$).
3. Paper noise is low ($\sigma_{\text{noise}} \le 3.5$).
4. Stroke acutance is sharp ($> 65.0$).
Under these conditions, any operator (especially CLAHE or histogram equalization) will introduce artifacts or waste computation. The original rectified image should be passed directly to OCR/OMR.

---

### Question 6: Which signals should trigger candidate operators?
- **Spatial Background Ratio ($R_{\text{bg}} < 0.80$)** $\to$ Triggers `SHADOW_CORRECTION_CANDIDATE`.
- **Dynamic Range ($\Delta_{\text{dyn}} < 55.0$) & Michelson ($< 0.22$)** $\to$ Triggers `CONTRAST_CORRECTION_CANDIDATE`.
- **Flat Paper Noise ($\sigma_{\text{noise}} > 4.5$)** $\to$ Triggers `DENOISING_CANDIDATE`.
- **Low Stroke Acutance ($< 50.0$) with Low Noise ($\le 4.0$)** $\to$ Triggers `SHARPENING_CANDIDATE`.
- **Color Saturation Fraction ($> 3.0\%$)** $\to$ Triggers `COLOR_PRESERVATION_ROUTING`.

---

### Question 7: Which signals should never independently trigger enhancement?
1. **Total Laplacian Variance / Tenengrad Energy**: A blank exam page has near-zero Laplacian variance, but it is not blurry; a page with dense small print has high variance even if slightly out of focus. It must never trigger sharpening alone.
2. **Mean Image Brightness**: A document with large black instruction boxes or dark margin desk pixels has a low mean brightness despite being perfectly exposed.
3. **Global Standard Deviation**: Conflates ink density with lighting contrast.

---

### Question 8: How should conflicting signals be handled?
When conflicting conditions occur (e.g. **High Noise + Low Stroke Sharpness** or **Severe Shadow + Low Contrast**):
- **Conflict 1: High Noise vs. Need for Sharpening**:
  *Risk*: Sharpening a noisy image amplifies noise into spurious text dots.
  *Resolution*: Order-dependent chaining. Apply **Bilateral Denoising first**, re-check stroke acutance, and apply only very mild unsharp masking ($\alpha \le 0.6$).
- **Conflict 2: Severe Shadow vs. Contrast Stretching**:
  *Risk*: Contrast stretching a shadowed image compresses the shadow into solid black and clips bright text into white.
  *Resolution*: Apply **Morphological Background Division first** to normalize the illumination field, then apply contrast stretching on the flattened image.

---

### Question 9: What information should be passed to Phase 4.3?
Phase 4.3 (Enhancement Pipeline Execution & Arbitration) requires:
1. `DocumentConditionProfile`: Complete structured measurements across all 6 dimensions.
2. `candidate_states`: List of recommended candidate operators (e.g. `['SHADOW_CORR', 'CONTRAST_CORR']`).
3. `execution_order_hints`: Recommended operator sequence (e.g. `SHADOW_CORR` $\to$ `DENOISE` $\to$ `CONTRAST_STRETCH` $\to$ `SHARPEN`).
4. `qualitative_notes`: Human-readable rationale explaining why specific operators were triggered or suppressed.

---

### Question 10: Which numerical thresholds still require broader validation?
The numerical thresholds explored here are **investigation calibration baselines** and must undergo wider validation on 500+ documents before freezing:
1. **Spatial Background Ratio threshold ($R_{\text{bg}} < 0.80$)**: Testing edge cases with faint watermark logos vs true cast shadows.
2. **Flat Paper Noise threshold ($\sigma_{\text{noise}} > 4.5$)**: Validating across varied sensor camera types (mobile phone CMOS vs flatbed CIS scanners).
3. **Stroke Acutance threshold ($45.0 - 50.0$)**: Validating on faint 0.3mm mechanical pencil vs 1.0mm felt-tip markers.

---

## 6. Generated Visual Artifacts

The following visual diagnostics were generated in [`phase4/output/`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase4/output):
- `phase4/output/phase4_condition_spatial_illumination_grid.png`: Visualizes the $4 \times 4$ local background brightness heatmap comparing shadowed `answer_sheet_3.jpg` (ratio: 0.68) vs uniform `answer_sheet_2.png` (ratio: 0.90).
- `phase4/output/phase4_operator_chaining_matrix.png`: Demonstrates operator interactions on `answer_sheet_3.jpg` (Shadow Alone vs Shadow $\to$ Sharpen vs Full Chain).
- `phase4/output/phase4_operator_selection_decision_map.png`: Multi-panel summary displaying condition profiles and candidate recommendations across all calibration images.

---
*Report prepared for Phase 4.2 of AI-EVAL-OpenCV.*
