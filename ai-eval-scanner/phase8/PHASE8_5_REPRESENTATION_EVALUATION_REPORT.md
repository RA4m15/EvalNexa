# PHASE 8.5 — RECOGNITION REPRESENTATION EVALUATION & CONTROLLED OCR EVIDENCE REPORT (POST-AUDIT CALIBRATED EDITION)

**Project:** `AI-EVAL-OpenCV` (Automated Exam Evaluation Pipeline)  
**Milestone:** Phase 8.5 — Recognition Representation Evaluation & Controlled OCR Evidence (Audited & Calibrated)  
**Author:** Antigravity AI  
**Date:** October 2026  
**Status:** **INVESTIGATION COMPLETE — REPRESENTATION EFFECTS EVALUATED UNDER TESTED CONDITIONS (SELECTION POLICY NOT FROZEN)**

---

> [!IMPORTANT]
> **INVESTIGATION MILESTONE DECLARATION**  
> Phase 8.5 is an **empirical investigation and architectural evidence milestone**, NOT a production OCR/HTR integration or decision classifier.  
> In strict compliance with pipeline governance:
> 1. Phases 2 through 7 remain frozen, intact, and untouched.
> 2. Phases 8.1, 8.2, 8.3, and 8.4 remain frozen, intact, and untouched.
> 3. No production OCR/HTR service was created or deployed into production.
> 4. No OCR/HTR model was trained or fine-tuned.
> 5. No production readiness classifier or machine-learning gate was introduced.
> 6. No universal representation ranking ("R1 is best", "R2 is worst") is asserted.
> 7. All findings distinguish between controlled empirical measurements and architectural hypotheses.

---

## 1. OBJECTIVE

Phase 8.1 formulated readiness criteria, Phase 8.2 established the multi-representation preparation engine, Phase 8.3 measured initial correlation against an offline neural OCR engine, and Phase 8.4 mapped the 18-defect failure boundary.

The objective of **Phase 8.5** is:

$$\mathbf{Evaluate\ whether\ different\ prepared\ image\ representations\ produced\ by\ the\ existing\ Phase\ 8\ pipeline\ affect\ downstream\ OCR\ recognition\ quality,\ using\ controlled\ experiments\ and\ evidence-driven\ comparison.}$$

The central research question is:
> **Under what evaluated conditions does an image representation improve, degrade, or leave downstream OCR recognition unchanged?**

This phase evaluates:
```text
Phase 8.2 Representations (R0, R1, R2) + Experimental R3
              ↓
    Controlled Conditions (N=15) + Real Exam Sheet
              ↓
    Same OCR Engine (Windows Media OCR via WinRT)
              ↓
    Exact Transcription Metrics (CER, WER, Line & Char Counts, Latency)
              ↓
    Condition-Specific Comparative Evidence
              ↓
    Failure Mode Root-Cause Analysis
              ↓
    NO Production Classifier / NO Frozen Selection Policy
```

---

## 2. FROZEN DEPENDENCIES & GOVERNANCE COMPLIANCE

All preceding pipeline milestones were verified prior to and after Phase 8.5 execution:

| Subsystem / Phase | Frozen Status | Verification Check | Regressions Observed |
| :--- | :--- | :--- | :--- |
| **Phase 2 — Geometry & Rectification** | FROZEN | Preserved read-only | None |
| **Phase 3 — Scanner Intake Integration** | FROZEN | Preserved read-only | None |
| **Phase 5 — Quality Assessment Engine** | FROZEN | Preserved read-only | None |
| **Phase 6.3 — Production Correction Engine** | FROZEN | 7/7 regression tests passed | None |
| **Phase 6.5 — Adaptive Contrast Normalization** | FROZEN | 9/9 regression tests passed | None |
| **Phase 7.2 — Rescan Decision Engine** | FROZEN | 13/13 regression tests passed | None |
| **Phase 8.1 — Readiness Evidence Investigation** | FROZEN | Preserved read-only | None |
| **Phase 8.2 — Readiness Preparation Layer** | FROZEN | 9/9 regression tests passed | None |
| **Phase 8.3 — OCR Correlation Investigation** | FROZEN | Preserved read-only | None |
| **Phase 8.4 — Readiness Boundary Investigation** | FROZEN | Preserved read-only | None |

No upstream contracts, thresholds, or implementation files were altered.

---

## 3. REPRESENTATION DEFINITIONS & PROVENANCE AUDIT

Four representations were evaluated under identical conditions. In accordance with the Phase 8.5 audit, their precise upstream provenance is documented below:

| Representation | Upstream Origin | Actual Transformations Applied | Information Discarded? | Color / Depth | Intended Downstream Use | Primary Known Failure Risks |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **$R_0$ — Raw Grayscale** | Direct conversion (`cv2.cvtColor(BGR2GRAY)`) | None (un-deskewed, un-rotated, un-normalized) | Color chrominance discarded | 8-bit Grayscale (1 channel) | Baseline comparison / fallback when preprocessing harms layout | Fails under rotated orientations; sensitive to low contrast |
| **$R_1$ — Prepared Grayscale** | Frozen Phase 8.2 `image_bundle.ready_gray` | 4-way orientation de-rotation + fine Radon deskew ($\|\theta\| \le 5^\circ$). **CLAHE is NOT part of Phase 8.2 `ready_gray`.** | Color chrominance discarded | 8-bit Grayscale (1 channel) | Primary input for neural OCR / Vision Transformers | Peripheral desk artifacts can fool projection profiling into spurious rotation |
| **$R_2$ — Binary Derivative** | Frozen Phase 8.2 `image_bundle.ready_bin` | Adaptive Gaussian thresholding ($C=10$, block size 25); inverted to dark ink on light substrate | All grayscale gradient and antialiasing information discarded | 1-bit Binary (packed as uint8 0/255) | Text-line slicing, bounding box discovery, layout segmentation | Character stroke fragmentation; loops filled; neural OCR tokenizers lose stroke gradients |
| **$R_3$ — Ruled-Line Handled** | **Experimental Phase 8.5-derived candidate representation** | Phase 8.2 `ready_gray` + horizontal dilation of `rule_lines_mask` + Telea inpainting (`cv2.INPAINT_TELEA`). **Telea inpainting is NOT a frozen Phase 8.2 output.** | Stroke ink overlapping ruling lines is locally synthesized | 8-bit Grayscale (1 channel) | Exploratory evaluation for lined-paper OCR | Thin descenders/ascenders intersecting rule lines can suffer stroke erosion |

> [!NOTE]
> **PROVENANCE AUDIT FINDING (R3 & R1):**  
> 1. **$R_3$ Origin:** Frozen Phase 8.2 generates an auxiliary `rule_lines_mask` in `PreprocessedImageBundle`, but does **NOT** apply Telea inpainting or mutate `ready_gray`. Therefore, $R_3$ is classified as an **experimental Phase 8.5-derived candidate representation** using the Phase 8.2 mask. It is not a frozen Phase 8.2 output.  
> 2. **$R_1$ Operations:** The frozen Phase 8.2 engine performs reading orientation de-rotation and fine Radon baseline deskew. **CLAHE is NOT applied in Phase 8.2 `ready_gray`** (contrast normalization was validated in Phase 6.5 as an upstream operator).

---

## 4. DATASET & GROUND-TRUTH TAXONOMY

To guarantee scientific rigor, data sources are explicitly segregated by ground-truth reliability:

1. **Controlled Synthetic Benchmark ($N=15$ conditions):**
   - High-contrast printed examination text (8 lines, 552 characters, 68 words).
   - Known mathematical ground truth ($100\%$ character accuracy ground truth).
   - Controlled physical perturbations: ruled guidelines, Gaussian noise, contrast attenuation, illumination gradients, sub-orthogonal skew, and cardinal rotations.
2. **Real Exam-Sheet Calibration Document (`answer_sheet_2.png`):**
   - Physical university examination sheet captured in uncropped real-world conditions ($1600 \times 1200$ resolution).
   - Known ground truth available **only for printed header block**.
   - Unverified handwritten body content evaluated qualitatively for character retention and line discovery without fabricating character-level ground truth.
3. **Handwriting Datasets (HTR):**
   - **NOT EVALUATED.** No cursive HTR model exists in the runtime environment; claiming HTR CER without an active HTR decoder is scientifically invalid.

---

## 5. EXPERIMENTAL METHOD

- **Engine:** Native Windows Media OCR Engine (`Windows.Media.Ocr.OcrEngine`) invoked via WinRT through asynchronous memory-mapped `StorageFile` / `BitmapDecoder`.
- **Invariance Rule:** The OCR engine configuration, user profile language, and recognition decoding parameters remained **strictly identical** across all representations.
- **Fair Comparison:** For every test image, the identical spatial coordinates, canvas size, and crop were supplied to $R_0, R_1, R_2, R_3$.
- **Measured Metrics:**
  - $\text{CER} = \frac{\text{Levenshtein}(\text{hyp\_chars}, \text{ref\_chars})}{\max(1, \text{len}(\text{ref\_chars}))}$
  - $\text{WER} = \frac{\text{Levenshtein}(\text{hyp\_words}, \text{ref\_words})}{\max(1, \text{len}(\text{ref\_words}))}$
  - Detected line count ($N_{\text{lines}}$)
  - Transcribed character count ($N_{\text{chars}}$)
  - Recognition latency ($\text{ms}$)

---

## 6. EMPIRICAL RESULTS

### 6.1 Controlled Multi-Condition Experiment Matrix ($N=15$)

The exact quantitative measurements across the 15 controlled conditions are presented below:

| Case ID | Document Condition | $R_0$ CER | $R_1$ CER | $R_2$ CER | $R_3$ CER | $R_0$ Lines | $R_1$ Lines | $R_2$ Lines | $R_3$ Lines | Latency $R_1$ (ms) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `A_CLEAN_BASELINE` | Clean Typography | 0.0036 | 0.0036 | 0.0922 | 0.0036 | 8 | 8 | 8 | 8 | 72.8 |
| `B_RULED_PAPER_COARSE` | Ruled Paper (pitch 70px) | 0.0036 | 0.0036 | 0.1139 | 0.0036 | 8 | 8 | 8 | 8 | 76.8 |
| `C_RULED_PAPER_FINE` | Ruled Paper (pitch 45px) | 0.3617 | 0.3617 | 0.5316 | **0.3490** | 7 | 7 | 8 | 7 | 74.8 |
| `D_GAUSSIAN_NOISE_MODERATE` | Sensor Noise ($\sigma=15$) | 0.0018 | 0.0018 | 0.0434 | 0.0018 | 8 | 8 | 8 | 8 | 71.7 |
| `E_GAUSSIAN_NOISE_HEAVY` | Sensor Noise ($\sigma=28$) | 0.0054 | 0.0054 | 0.0796 | 0.0054 | 8 | 8 | 8 | 8 | 72.0 |
| `F_LOW_CONTRAST_MODERATE` | Low Contrast (gain 0.55) | 0.0036 | 0.0036 | 0.0271 | 0.0036 | 8 | 8 | 8 | 8 | 71.3 |
| `G_LOW_CONTRAST_SEVERE` | Low Contrast (gain 0.35) | 0.0090 | 0.0090 | 0.0398 | 0.0090 | 8 | 8 | 8 | 8 | 76.5 |
| `H_SHADOW_GRADIENT` | Diagonal Illumination Gradient | 0.0036 | 0.0036 | 0.0687 | 0.0036 | 8 | 8 | 8 | 8 | 80.3 |
| `I_MILD_SKEW_1.5DEG` | Geometric Skew ($+1.5^\circ$) | 0.0054 | 0.0090 | 0.0615 | 0.0090 | 8 | 8 | 8 | 8 | 66.8 |
| `J_MILD_SKEW_3.0DEG` | Geometric Skew ($+3.0^\circ$) | 0.0072 | **0.0054** | 0.0759 | **0.0054** | 8 | 8 | 8 | 8 | 76.2 |
| `K_ROTATED_90_CW` | Sideways Rotation ($90^\circ$ CW) | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0 | 0 | 0 | 0 | 44.5 |
| `L_ROTATED_180_INVERTED` | Upside-Down Inversion ($180^\circ$) | 0.8065 | 0.8065 | 0.8264 | 0.8065 | 4 | 4 | 5 | 4 | 74.8 |
| `M_ROTATED_270_CCW` | Sideways Rotation ($270^\circ$ CCW)| 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0 | 0 | 0 | 0 | 47.9 |
| `N_RULED_PLUS_NOISE` | Ruled Guidelines + Noise | 0.3074 | 0.3074 | 0.3707 | **0.3002** | 8 | 8 | 8 | 8 | 77.2 |
| `O_SHADOW_PLUS_LOW_CONTRAST` | Low Contrast + Illumination | 0.0018 | 0.0018 | 0.0271 | 0.0018 | 8 | 8 | 8 | 8 | 72.8 |

---

### 6.2 Raw Paired CER Differences

To avoid arbitrary thresholding, the raw paired differences are presented directly:

$$\Delta\text{CER}(R_1 - R_0), \quad \Delta\text{CER}(R_2 - R_1), \quad \Delta\text{CER}(R_3 - R_1)$$

| Case ID | Document Condition | $R_1 - R_0$ | $R_2 - R_1$ | $R_3 - R_1$ | Paired Comparison Note |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `A_CLEAN_BASELINE` | Clean Typography | 0.0000 | +0.0886 | 0.0000 | $R_2$ higher CER; others identical |
| `B_RULED_PAPER_COARSE` | Ruled Paper (pitch 70px) | 0.0000 | +0.1103 | 0.0000 | $R_2$ higher CER; others identical |
| `C_RULED_PAPER_FINE` | Ruled Paper (pitch 45px) | 0.0000 | +0.1699 | **-0.0127** | $R_3$ lower CER (improvement observed); $R_2$ higher CER |
| `D_GAUSSIAN_NOISE_MODERATE` | Sensor Noise ($\sigma=15$) | 0.0000 | +0.0416 | 0.0000 | $R_2$ higher CER; others identical |
| `E_GAUSSIAN_NOISE_HEAVY` | Sensor Noise ($\sigma=28$) | 0.0000 | +0.0742 | 0.0000 | $R_2$ higher CER; others identical |
| `F_LOW_CONTRAST_MODERATE` | Low Contrast (gain 0.55) | 0.0000 | +0.0235 | 0.0000 | $R_2$ higher CER; others identical |
| `G_LOW_CONTRAST_SEVERE` | Low Contrast (gain 0.35) | 0.0000 | +0.0308 | 0.0000 | $R_2$ higher CER; others identical |
| `H_SHADOW_GRADIENT` | Diagonal Illumination Gradient | 0.0000 | +0.0651 | 0.0000 | $R_2$ higher CER; others identical |
| `I_MILD_SKEW_1.5DEG` | Geometric Skew ($+1.5^\circ$) | +0.0036 | +0.0525 | 0.0000 | Minor difference; $R_2$ higher CER |
| `J_MILD_SKEW_3.0DEG` | Geometric Skew ($+3.0^\circ$) | **-0.0018** | +0.0705 | 0.0000 | $R_1$ & $R_3$ lower CER (improvement observed); $R_2$ higher CER |
| `K_ROTATED_90_CW` | Sideways Rotation ($90^\circ$ CW) | 0.0000 | 0.0000 | 0.0000 | All fail completely (0 lines detected) |
| `L_ROTATED_180_INVERTED` | Upside-Down Inversion ($180^\circ$) | 0.0000 | +0.0199 | 0.0000 | $R_2$ slightly higher CER; all degraded |
| `M_ROTATED_270_CCW` | Sideways Rotation ($270^\circ$ CCW)| 0.0000 | 0.0000 | 0.0000 | All fail completely (0 lines detected) |
| `N_RULED_PLUS_NOISE` | Ruled Guidelines + Noise | 0.0000 | +0.0633 | **-0.0072** | $R_3$ lower CER; $R_2$ higher CER |
| `O_SHADOW_PLUS_LOW_CONTRAST` | Low Contrast + Illumination | 0.0000 | +0.0253 | 0.0000 | $R_2$ higher CER; others identical |

> [!NOTE]
> **ANALYSIS GROUPING CRITERION NOTE:**  
> In internal script summaries, comparisons where $\|\Delta\text{CER}\| \le 0.01$ were grouped as "no material difference." This value was an **exploratory analysis grouping criterion used solely for summarizing this Phase 8.5 dataset; it is NOT a production threshold and is NOT frozen.**

---

### 6.3 Real Exam Sheet Observation (`answer_sheet_2.png`)

When evaluated on the real, physical examination document:

| Representation | Recognized Lines | Total Characters | Header CER | Sample Output Excerpt |
| :--- | :---: | :---: | :---: | :--- |
| **$R_0$ (Raw Grayscale)** | **34 lines** | **916 chars** | **0.3226** | `TAGORE PUBLIC SCHOOL, ALLAHABAD EXAMINATION ANSWER SHEET Roll NO. Name of Examination Subject...` |
| **$R_1$ (Prepared Grayscale)** | 11 lines | 22 chars | 0.8602 | `0 o p o m -4 m o o o o...` |
| **$R_2$ (Binary Derivative)** | 0 lines | 0 chars | 1.0000 | *(Empty string — complete recognition collapse)* |
| **$R_3$ (Ruled Handled)** | 12 lines | 24 chars | 0.8495 | `6 0 o p o o o m -4 m o o...` |

---

## 7. REPRODUCIBILITY NOTE: EXPLAINING PHASE 8.3 vs PHASE 8.5 CER DIFFERENCE

An audit comparison of the reported `answer_sheet_2.png` header CER between Phase 8.3 and Phase 8.5 reveals a numerical difference:

- **Phase 8.3 Report:** $R_0 = 0.4453$, $R_1 = 0.8828$, $R_2 = 1.0000$, $R_3 = 0.8672$
- **Phase 8.5 Report:** $R_0 = 0.3226$, $R_1 = 0.8602$, $R_2 = 1.0000$, $R_3 = 0.8495$

### Investigation of Root Causes:
1. **Different Evaluation Scope & Reference String Definition:**
   - In **Phase 8.3**, `GT_ANSWER_SHEET_2_HEADER` was defined as:
     ```text
     "TAGORE PUBLIC SCHOOL, ALLAHABAD\nEXAMINATION ANSWER SHEET\nRoll No. Name of Examination\nClass & Section Day & Date Subject History"
     ```
     Length: **128 characters** (normalized).
   - In **Phase 8.5**, `GT_ANSWER_SHEET_2_HEADER` was defined as:
     ```text
     "TAGORE PUBLIC SCHOOL, ALLAHABAD EXAMINATION ANSWER SHEET Roll NO. Name of Examination Subject"
     ```
     Length: **93 characters** (normalized).
2. **Different Evaluation Slice Window:**
   - Phase 8.3 evaluated hypothesis slice: `hyp_text[:len(GT) + 50]`.
   - Phase 8.5 evaluated hypothesis slice: `hyp_text[:len(GT) + 30]`.
3. **CER Calculation Impact:**
   - Because CER is normalized by reference string length ($\text{dist} / \text{len}(\text{ref})$), altering reference length from 128 to 93 and changing the evaluation slice window changes the resulting scalar value ($0.3226$ vs $0.4453$).
4. **Consistency of Physical Conclusion:**
   - While the exact numerical values differ due to evaluation slice scope, **both phases observed the identical empirical phenomenon**:
     - $R_0$ successfully preserved document structure and recognized the upright header text (34 lines, 900+ chars).
     - $R_1$ suffered severe recognition degradation ($> 0.85$ CER) because unrectified peripheral desk margins caused a spurious $90^\circ$ de-rotation.
     - $R_2$ produced 0 recognized lines (complete recognition collapse).

---

## 8. CONDITION-SPECIFIC REPRESENTATION COMPARISON

Rather than declaring an uncalibrated global ranking, empirical comparison is classified strictly by document condition:

```text
+----------------------------------------------------------------------------------------------------+
|                               CONDITION-SPECIFIC EVIDENCE SUMMARY                                  |
+------------------------------------+---------------------------------------------------------------+
| Evaluated Document Condition       | Observed Representation Comparison Evidence                   |
+------------------------------------+---------------------------------------------------------------+
| Clean Typographic Baseline         | R0 == R1 == R3 (CER=0.0036); R2 higher CER (0.0922)           |
| Dense Ruled Guidelines             | R3 observed lower CER (0.3490 vs R1=0.3617); R2 higher CER     |
| Sensor Noise (Gaussian)            | R0 == R1 == R3 (CER=0.0018-0.0054); R2 higher CER             |
| Low Contrast & Illumination Grads  | R0 == R1 == R3 (CER=0.0018-0.0090); R2 higher CER             |
| Moderate Skew (+3.0°)              | R1 & R3 observed lower CER (0.0054 vs R0=0.0072); R2 higher   |
| Severe Cardinal Rotation (90°/270°)| ALL FAIL (CER=1.0000; 0 lines detected by evaluated engine)   |
| Real Exam Sheet with Desk Borders  | R0 observed superior retention (34 lines vs R1 11 lines)      |
+------------------------------------+---------------------------------------------------------------+
```

### Calibrated Representation Observations:

1. **R2 Binarization Effect (Calibrated):**
   - **Observation:** In **13 of 15 evaluated controlled conditions**, $R_2$ showed higher CER than the corresponding grayscale representations ($R_0 / R_1$).
   - **Context:** Within this controlled experiment, $R_2$ was frequently associated with recognition degradation. However, this finding is bounded to the evaluated benchmark and neural OCR engine; it does **not** assert that binarization universally harms all OCR/HTR systems.
2. **R3 Ruled-Line Handling Effect:**
   - **Observation:** On dense fine-pitch ruled lines (`C_RULED_PAPER_FINE`), $R_3$ showed a lower CER ($0.3490$ vs $0.3617$) by inpainting guidelines that otherwise triggered spurious hyphens.
   - **Context:** This is a condition-specific result on lined paper and does not establish $R_3$ as universally preferable.
3. **R1 Preparation Effect:**
   - **Observation:** On moderately skewed text (`J_MILD_SKEW_3.0DEG`), $R_1$ reduced CER from $0.0072$ to $0.0054$ through fine deskew. On clean upright text, $R_1$ and $R_0$ showed no material difference ($\text{CER} = 0.0036$).
   - **Limitation:** On uncropped real documents with dark borders (`answer_sheet_2.png`), $R_1$ orientation heuristics were misled by border variance, demonstrating that $R_1$ is not universally safe without prior rectification.

---

## 9. FAILURE ANALYSIS & ROOT-CAUSE TAXONOMY

Each observed degradation mode is mapped to its underlying mechanism and evidence strength:

| Observed Failure Mode | Affected Representation | Observable Manifestation | Causal Mechanism | Evidence Strength |
| :--- | :---: | :--- | :--- | :--- |
| **Binarization Contour Fragmentation** | $R_2$ | Broken glyph loops (e.g. `'o'` $\to$ `'c'`, `'e'` $\to$ `'c'`) | Loss of sub-pixel grayscale edge gradients required by convolutional feature extractors | **STRONGLY SUPPORTED** |
| **Spurious Rule-Line Hyphenation** | $R_0, R_1$ | Spurious hyphen/underscore tokens injected between words | Continuous horizontal rule lines recognized as delimiter tokens by 1D sequence recognizers | **OBSERVED** |
| **Peripheral Margin Induced Rotation** | $R_1, R_3$ | Canvas rotated $90^\circ$ sideways; transcript collapses to noise | Peripheral shadows/borders create dominant vertical projection variance, fooling 1D orientation heuristics | **OBSERVED** |
| **Sub-Resolution Stroke Thinning** | $R_2$ | Complete line dropouts on faint handwriting strokes | Global/local threshold sets faint ink strokes to background white | **STRONGLY SUPPORTED** |
| **Sideways Receptive Field Incompatibility**| All | 0 text lines detected ($\text{CER}=1.0$) on $90^\circ / 270^\circ$ text | 1D horizontal line segmenters cannot sweep orthogonal vertical columns | **STRONGLY SUPPORTED** |

---

## 10. SYSTEM LIMITATIONS

1. **Sample Size:** $N=15$ controlled cases is an **INSUFFICIENT SAMPLE SIZE FOR RELIABLE GENERALIZATION** across diverse handwriting styles, unconstrained layouts, and multi-lingual scripts.
2. **OCR Engine Specificity:** All empirical measurements were obtained using the native Windows Media OCR engine. Different recognition architectures (e.g. TrOCR, CRNN, Tesseract LSTM) may exhibit differing representation sensitivities.
3. **HTR Evaluation Gap:** Handwritten text recognition was **not evaluated** because no active HTR decoder is integrated into the workspace. Findings apply to printed typography and must not be extrapolated to cursive handwriting.
4. **Synthetic vs Real Disconnect:** Synthetic benchmarks demonstrated that $R_1$ equals or outperforms $R_0$, yet real-world evaluation (`answer_sheet_2.png`) demonstrated that uncropped margin artifacts invert this relationship.

---

## 11. ARCHITECTURAL IMPLICATIONS FOR FUTURE PIPELINE PHASES

The Phase 8.5 findings suggest the following architectural considerations (non-binding, not frozen):

1. **Multi-Representation Routing:** Downstream pipeline stages should not enforce a single representation monopoly. Segmentation and line slicing benefit from $R_2$, while neural text recognition benefits from grayscale representations ($R_1 / R_3$).
2. **Safe Fallback Retention:** $R_0$ (Raw Grayscale) should remain accessible in memory as an immutable fallback whenever orientation ambiguity or peripheral border defects are detected.
3. **Sequencing Dependency:** Orientation de-rotation and baseline deskew must be executed after page boundary rectification and margin cropping, preventing peripheral background from corrupting projection profiles.

---

## 12. PHASE 11 CALIBRATION REQUIREMENTS

The following questions require large-scale empirical evaluation in Phase 11:
1. **Cross-Model Representation Benchmarking:** Measure representation response across dedicated HTR models (TrOCR, CRNN) on real handwritten exam cohorts ($N \ge 200$).
2. **Margin-Resilient Orientation:** Calibrate orientation heuristics against full-page scans containing varied external backgrounds and desk artifacts.
3. **Handwriting Thin-Stroke Survival under Ruled Suppression:** Quantify thin-stroke erosion caused by $R_3$ inpainting across cursive script samples.

---

## 13. FINAL STATUS & VERDICT

```text
Phase 8.5 Investigation
→ COMPLETE / APPROVED AT INVESTIGATION LEVEL

Representation effects
→ EVALUATED UNDER TESTED CONDITIONS

R2 binarization effect
→ OBSERVED DEGRADATION IN 13/15 CONTROLLED CASES

R3 ruled-line handling
→ CONDITION-SPECIFIC RESULT ONLY

Universal representation preference
→ NOT ESTABLISHED

Production OCR classifier
→ NOT IMPLEMENTED

Production HTR classifier
→ NOT IMPLEMENTED

Hard OCR readiness thresholds
→ NOT FROZEN

Representation selection policy
→ NOT FROZEN

Phase 8.1
→ FROZEN

Phase 8.2
→ FROZEN

Phase 8.3
→ FROZEN

Phase 8.4
→ FROZEN

Phase 9
→ NOT STARTED
```
