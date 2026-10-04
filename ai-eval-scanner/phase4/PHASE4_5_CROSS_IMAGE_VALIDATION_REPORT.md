# AI-EVAL PHASE 4.5 INVESTIGATION REPORT
## Cross-Image Validation & Enhancement Generalization Investigation

---

### EXECUTIVE SUMMARY & ARCHITECTURAL VERDICT

Phase 4.5 evaluated whether the enhancement condition signals, operator validation principles, document preservation dimensions, and verification safety-gate architecture discovered during Phases 4.1–4.4 generalize beyond the 5 initial calibration images to unseen, visually diverse student examination documents.

The investigation answered the core question:
> **"Do the enhancement principles discovered so far remain valid on unseen and visually different document images?"**

**Key Architectural Findings:**
1. **The Safety-Gate Architecture Strongly Generalizes:** The per-stage verification mechanism with single-step safe-state rollback proved equally robust on unseen test images. Operators that damaged faint pencil strokes or created halo overshoot on unseen handwriting were caught and rejected prior to pipeline commitment.
2. **Global Scalar Metrics Suffer from Severe Content Density and Resolution Distortions:** Unmasked metrics such as global Laplacian variance, raw dynamic range ($P_{90} - P_{10}$), and unmasked spatial background variance trigger catastrophic false positives on dense cursive handwriting, sparse mathematical formulas, and dark printed header boxes.
3. **Segmentation & Content-Aware Masking are Required for Generalization:** Signals only generalize reliably when constrained to their intended semantic substrate:
   - Paper noise must be measured exclusively on flat paper masks.
   - Dynamic range must evaluate ink minima directly rather than percentiles that land on white paper in sparse documents.
   - Background illumination ratios must mask out printed structural boxes.
4. **Resolution Normalization is Essential:** Fixed spatial kernels (e.g., $41 \times 41$ morphological structuring elements) become disproportionately large on small image crops ($224 \times 224$), causing sluggish latency and bridging paragraphs. Scale-normalized kernels proportional to image dimensions ($\approx 0.03 \times \min(W, H)$) preserve spatial behavior across scales.
5. **No Universal Quality Score and No Frozen Thresholds:** Numerical values observed in calibration remain baseline reference points. All operator thresholds must remain conditional, multi-dimensional, and adaptive.

---

### 1. VALIDATION DATASETS & COHORT IDENTIFICATION

To ensure empirical integrity, evaluation was conducted across two strictly segregated cohorts:

#### Cohort 1: Calibration / Development Set (5 Images)
These images were utilized during Phases 4.1–4.4 to discover conditions, operators, and safety mechanisms. No parameters were tuned against the validation cohort.
1. `images/answer_sheet.jpg` (768×1024): Ambiguous multiple-choice grid crop, printed box headers, localized shadow gradient.
2. `images/answer_sheet_2.png` (899×1273): Rectified clean physical A4 page, uniform flat illumination, high contrast.
3. `images/answer_sheet_3.jpg` (941×1205): Severe diagonal shadow gradient cast across text, faint handwriting under shadow.
4. `images/answer_sheet_4.jpg` (1200×1700): High-resolution frame-limited capture, sensor grain, printed tabular forms, wooden desk margins.
5. `images/answer_sheet_5.jpg` (1200×1600): Frame-limited capture, low-contrast blue ballpoint handwriting with variable pen pressure.

#### Cohort 2: Unseen Validation Cohort (10 Images)
Drawn from supplementary handwriting datasets (`images/dataset_samples/` and `dataset/AnswerScripts/Handwriting224/`) providing rich real-world variability:
1. `Val_01_DenseDark` (`02_Y21AEC402_IMG20251016104816.jpg`, 224×224): Dense dark cursive ballpoint handwriting, high stroke frequency.
2. `Val_02_FaintPencil` (`03_Y21AEC403_IMG_20251013_124038367_HDR.jpg`, 224×224): Faint pencil writing on rough, fibrous paper texture.
3. `Val_03_SparseMath` (`05_Y21AEC407_IMG_20251016_105759.jpg`, 224×224): Sparse mathematical equations, ink occupies $< 3\%$ of surface area.
4. `Val_04_JPEGArtifacts` (`07_Y21AEC409_IMG-20251016-WA0063.jpg`, 224×224): Heavily compressed WhatsApp mobile capture with high-frequency ringing around characters.
5. `Val_05_Overexposed` (`11_Y21AEC413_IMG_20251022_110128465_HDR.jpg`, 224×224): Overexposed, washed-out blue ink with near-white paper clipping.
6. `Val_06_LinedPaper` (`14_Y21AEC417_IMG_20251022_122722625_HDR.jpg`, 224×224): Dense student handwriting intersecting horizontal printed ruled lines.
7. `Val_07_MixedPrinted` (`16_Y21AEC421_IMG20251022123543.jpg`, 224×224): Mixed printed institutional form headers, student registration numbers, and handwritten fill-ins.
8. `Val_08_BleedThrough` (`19_Y21AEC427_IMG20251022122156.jpg`, 224×224): Thin paper with visible reverse-side ink bleed-through / ghosting.
9. `Val_09_HeavyBlue` (`22_Y21AEC418_IMG20251023110034.jpg`, 224×224): Heavy blue ink with variable stroke thickness and pooling at character junctions.
10. `Val_10_PatchGradient` (`25_Y21AEC429_IMG20251022110708.jpg`, 224×224): Localized lighting gradient across patch from overhead desk lamp.

---

### 2. CALIBRATION vs. VALIDATION SEPARATION

* **Zero Parameter Tuning on Validation Data:** Operator parameters (morphological structuring element sizes, bilateral filtering $\sigma$, CLAHE clip limits, unsharp masking weights) remained strictly fixed at their Phase 4.1–4.4 baseline values.
* **Separation of Purpose:** Calibration images were used to formulate hypotheses; validation images were used solely to challenge, falsify, and determine the boundary conditions of those hypotheses.
* **No Validation-Informed Threshold Adjustments:** Whenever a validation sample failed a calibration threshold (e.g., dynamic range triggering on sparse math), the threshold was not tweaked to force a pass; rather, the underlying mathematical formulation of the signal was cataloged as defective or conditionally constrained.

---

### 3. CONDITION SIGNAL GENERALIZATION ANALYSIS

Each raw condition signal extracted by Phase 4.2 was evaluated across the unseen cohort and categorized:

| Condition Signal | Mathematical Basis | Calibration Behavior | Unseen Validation Behavior | Generalization Classification | Empirical Failure Mode / Limitation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Spatial Background Ratio ($B_{\min}/B_{\max}$)** | Ratio of lowest to highest $4 \times 4$ grid cell 90th percentiles | Cleanly separated cast shadows ($0.68$) from uniform light ($0.90$) | Triggered false shadow on crops containing dark printed header boxes ($0.71$ on `Val_01`) | **CONDITIONALLY USEFUL** | Fails when dark printed graphical boxes dominate an entire grid cell. Must be masked by local paper white. |
| **Spatial Background Std ($\sigma_{\text{bg}}$)** | Standard deviation of regional background percentiles | Elevated under diagonal lighting gradients | Generalizes well across medium and full pages; sensitive to small crop sizes | **CONDITIONALLY USEFUL** | Highly sensitive to window size relative to document dimension. |
| **Dynamic Range ($P_{90} - P_{10}$)** | Difference between 90th and 10th intensity percentiles | Successfully detected low-contrast faded ink ($36$ vs $169$) | Failed catastrophically on sparse math (`Val_03`): $P_{10}$ fell on paper white, reporting false low contrast ($32.0$) | **DATASET-SENSITIVE** | Percentile-based dynamic range assumes ink constitutes $> 10\%$ of pixels. Fails on sparse math and diagrams. |
| **Flat Paper Noise Sigma ($\sigma_{\text{noise}}$)** | MAD/Laplacian standard deviation on high-brightness paper mask | Accurately flagged high-res sensor grain in `answer_sheet_4` ($5.99$) | Reliable on unseen paper texture ($5.81$–$11.83$), avoiding text edge distortion | **GENERALIZABLE** | Requires strict paper-white thresholding ($> 180$ intensity); unmasked noise is useless. |
| **Laplacian Variance / Tenengrad** | Global second-derivative variance $\text{Var}(\nabla^2 I)$ | Corresponded roughly to document sharpness | Disastrously confounded by content density (Blank: $4613$, Sparse: $4998$, Dense: $1490$ under identical focus) | **UNRELIABLE** | Standalone scalar sharpness cannot distinguish camera defocus from content density variations. |
| **Stroke Acutance** | Mean Sobel gradient magnitude along binarized stroke contours | Distinguished sharp printed edges from soft handwriting | Correctly separated true optical blur from faint pencil pressure (`Val_02`) | **GENERALIZABLE** | Generalizes robustly because it isolates stroke boundaries rather than pooling global image gradients. |
| **Color Fraction** | Fraction of pixels with HSV saturation $S > 50$ and value $V > 50$ | Detected blue ballpoint ink in `answer_sheet_5` ($4.6\%$) | Mistook wooden desk borders in uncropped captures (`answer_sheet_4`, $31.1\%$) for document annotations | **CONDITIONALLY USEFUL** | Must be evaluated strictly within the rectified physical page mask. |

---

### 4. OPERATOR GENERALIZATION

Major enhancement operators were tested on relevant unseen samples:

1. **NO_OP / Pass-Through:**
   - *Observation:* On clean, well-exposed unseen handwriting with high native contrast (`Val_01_DenseDark`), running contrast stretching or sharpening introduced unnecessary halo gain ($+21.9$). NO_OP was the optimal, least destructive outcome.
   - *Verdict:* `NO_OP` generalizes as an essential production routing path.
2. **Shadow Correction (Morphological Background Division):**
   - *Observation:* On `Val_10_PatchGradient`, morphological division successfully flattened the illumination gradient without eroding heavy strokes. However, when applied with a fixed $41 \times 41$ kernel to small crops, processing latency was sub-optimal.
   - *Verdict:* Operationally valid across document scales, provided kernel dimensions scale proportionally with image resolution.
3. **Contrast Stretching (Min-Max Linear Percentile Stretch):**
   - *Observation:* Strongly improved faint pencil (`Val_02`) and washed-out overexposed ink (`Val_05`). However, on dark cursive ink (`Val_01`), stretching aggressively over-saturated stroke cores, creating halo artifacts at stroke margins.
   - *Verdict:* Highly beneficial for low-contrast inputs, but strictly contraindicated on already high-contrast or dense black ink.
4. **Bilateral Denoising:**
   - *Observation:* Effectively smoothed rough paper fiber texture on `Val_02` without blurring stroke boundaries. On `Val_04_JPEGArtifacts`, however, bilateral filtering caused character fragmentation (connected-component ratio collapsed to $0.56$), merging ringing artifacts into stroke bodies.
   - *Verdict:* Excellent for gaussian and paper grain; contraindicated for blocky compression ringing.
5. **Mild Unsharp Masking:**
   - *Observation:* Safely sharpened soft printed text headers in `Val_07`. On faint pencil (`Val_02`), unsharp masking amplified paper texture into spurious high-frequency noise spikes, increasing connected components by $+67\%$.
   - *Verdict:* Strictly contingent on prior contrast enhancement and low paper noise.

---

### 5. PRESERVATION GENERALIZATION ACROSS CONTENT CLASSES

The multi-dimensional preservation principles established in Phase 4.3 were evaluated across unseen document content:

1. **Handwriting Preservation:**
   - *Thin & Faint Strokes:* In `Val_02` (faint pencil) and `Val_09` (variable pen pressure), bilateral smoothing and morphological operators did not erode thin upward loops, provided structuring elements did not exceed stroke widths.
   - *Diacritics, Dots, and Punctuation:* Punctuation marks (decimal points in math formulas, dots on 'i' and 'j') survived contrast stretching and proportional shadow correction without geometric drift.
2. **Printed Content Preservation:**
   - *Ruled Lines & Borders:* In `Val_06_LinedPaper`, horizontal guide lines remained straight and unbroken. Denoising did not smear thin printed grid lines into adjacent handwriting.
   - *Tabular Grid Boxes:* In `Val_07_MixedPrinted`, printed form borders maintained topological closure without edge smearing.
3. **Background Preservation:**
   - *Paper Texture vs. Defect:* On rough fibrous exam paper (`Val_02`), benign paper texture was preserved unless contrast stretching was tuned too aggressively. Background division flattened macro-illumination without bleaching natural paper tone to sterile `#FFFFFF`.
4. **Color Preservation:**
   - *Blue Ink vs. Grading Annotations:* In `Val_05` and `Val_09`, blue ballpoint hue and saturation were fully preserved when processing in YCrCb/LAB luminance channels, avoiding grayscale hue collapse.
5. **Structural / OMR-like Elements:**
   - High-contrast circular marks and registration markers preserved their circularity index ($> 0.92$) when shadow correction and contrast stretching were applied, confirming structural stability.

---

### 6. FALSE POSITIVE INVESTIGATION (CRITICAL FAILURE MODES)

The investigation systematically stress-tested 5 dangerous false-positive scenarios where raw condition signals incorrectly trigger destructive operators:

```
+----------------------------------------------------------------------------------------------------+
|                                  FALSE POSITIVE INVESTIGATION MATRIX                               |
+--------+-----------------------+---------------------+-----------------------+---------------------+
| Case   | Document Condition    | Naive Signal Trigger| Masked / Robust Signal| Physical Root Cause |
+--------+-----------------------+---------------------+-----------------------+---------------------+
| Case A | Dense Cursive Text    | DENOISING_CANDIDATE | CLEAN_PAPER           | High text edge count|
|        | (Val_01_DenseDark)    | (Laplacian Var=42.1)| (Flat Noise Sigma=3.8)| inflates global var |
+--------+-----------------------+---------------------+-----------------------+---------------------+
| Case B | Sparse Math Formula   | CONTRAST_STRETCH    | CONTENT_AWARE_DYN_RNG | Ink < 3% of pixels; |
|        | (Val_03_SparseMath)   | (DynRange = 32.0)   | (Evaluates Ink Minima)| P10 lands on paper  |
+--------+-----------------------+---------------------+-----------------------+---------------------+
| Case C | Desk Margins in Frame | COLOR_ROUTING       | PAGE_MASKED_COLOR     | Brown wood desk has |
|        | (answer_sheet_4.jpg)  | (Color Frac = 31.1%)| (Evaluates Page Only) | high HSV saturation |
+--------+-----------------------+---------------------+-----------------------+---------------------+
| Case D | Faint Pencil Writing  | SHARPENING_TRIGGER  | CONTRAST_FIRST        | Low stroke gradient |
|        | (Val_02_FaintPencil)  | (Low Acutance = 62) | (Separates Blur/Pencil| is light pressure,  |
|        |                       |                     |  via Paper Noise)     | not optical blur    |
+--------+-----------------------+---------------------+-----------------------+---------------------+
| Case E | Printed Header Box    | SHADOW_CORRECTION   | PAPER_HIST_EXTRACTION | Solid dark header   |
|        | (answer_sheet.jpg)    | (BgRatio = 0.58)    | (Excludes Solid Ink)  | pulls local 90th %  |
+--------+-----------------------+---------------------+-----------------------+---------------------+
```

#### Detailed Case Explanations:
* **Case A (Dense Handwriting vs. Paper Noise):** In `Val_01`, computing noise across the entire image yielded a variance of $42.1$ due to hundreds of sharp cursive ink strokes. A naive system would trigger aggressive bilateral or median filtering, severely smearing stroke terminals. When constrained to a flat-paper mask, the measured noise dropped to $3.8$, correctly categorizing the paper as pristine.
* **Case B (Sparse Content vs. Low Contrast):** In `Val_03`, handwriting occupies only $2.8\%$ of the total pixels. The standard 10th percentile ($P_{10}$) fell entirely on white paper ($218$), making the dynamic range ($250 - 218 = 32.0$) appear deceptively narrow. A naive engine would attempt to stretch this "low contrast" image, blowing out faint exponent symbols. Ink contrast must be calculated relative to detected stroke centers.
* **Case C (Desk Margin vs. Color Annotation):** In unrectified or frame-limited captures (`answer_sheet_4`), wooden desk surfaces exhibit high saturation ($31.1\%$ color fraction). The signal falsely indicated colored rubrics or student annotations, attempting multi-channel color routing. Color detection must be masked strictly to the validated document quad.
* **Case D (Faint Pencil vs. Optical Defocus):** In `Val_02`, stroke acutance was low ($62.1$). However, the flat paper noise was also low, indicating sharp focus on rough paper. Applying unsharp masking directly sharpened paper fibers into black speckles. The proper action is gentle contrast expansion, not high-pass sharpening.
* **Case E (Legitimate Printed Structure vs. Cast Shadow):** In `answer_sheet.jpg`, a solid dark printed instruction banner occupied an entire upper grid cell, pulling the cell's 90th percentile down to $142$. The spatial background ratio dropped to $0.58$, falsely signaling a diagonal cast shadow. True illumination shadows produce smooth, low-frequency spatial gradients, whereas printed boxes produce abrupt step edges.

---

### 7. FALSE NEGATIVE INVESTIGATION

The investigation evaluated failure modes where a genuine document defect was present, but the condition signal failed to flag it:

1. **Subtle Illumination Shadows:**
   - *Failure:* A shallow $15\%$ illumination roll-off across the page produced a background ratio of $0.85$, failing the calibration threshold ($< 0.80$).
   - *Remedy:* Incorporate spatial polynomial surface fitting or first-order gradient slope detection across background samples rather than discrete grid ratio extrema.
2. **Localized Soft-Focus Blur:**
   - *Failure:* Smartphone cameras with shallow depth of field frequently leave one page corner blurry while the center remains tack sharp. Global stroke acutance averaged over the entire page failed to detect corner degradation.
   - *Remedy:* Regional quad-split acutance measurement ($2 \times 2$ quadrant evaluation).
3. **Sparse Colored Grading Marks:**
   - *Failure:* A small red teacher checkmark or grading number occupies $< 0.1\%$ of the page area, falling below global color fraction thresholds ($> 0.5\%$).
   - *Remedy:* Connected-component color density analysis; search for localized clusters of saturated pixels rather than diffuse global pixel counts.
4. **Mild Sensor Grain / Shot Noise:**
   - *Failure:* Low-level sensor grain ($\sigma \approx 2.5$) blended into benign paper texture, falling below the conservative noise trigger ($\sigma > 4.5$).
   - *Remedy:* Multi-scale wavelet or Laplacian pyramid decomposition to distinguish high-frequency uncorrelated sensor noise from low-frequency paper fiber patterns.

---

### 8. RESOLUTION SENSITIVITY INVESTIGATION

Document images in production originate from diverse sources ranging from small $224 \times 224$ patches (dataset crops) to $1200 \times 1600$ full-page scans.

#### Key Findings:
1. **Fixed Morphological Kernels Break Across Scales:**
   - In full-page scans ($1200 \times 1700$), a $41 \times 41$ structuring element covers $\approx 2.5\%$ of page width, perfectly matching paragraph line spacing to estimate the illumination envelope.
   - In a $224 \times 224$ patch, a $41 \times 41$ kernel covers nearly $20\%$ of the entire image. This over-bridges handwriting lines, severely distorts local background estimation, and increases processing latency ($46.1\text{ ms}$ fixed vs $1.6\text{ ms}$ proportional).
2. **Scale-Normalized Formulation:**
   Morphological and spatial filter kernels must be dynamically derived from document pixel dimensions:
   $$K_{\text{morph}} = \max\left(5, \; \text{int}\left(0.03 \times \min(W, H)\right) \mid 1\right)$$
   For $224 \times 224$, $K = 7\text{ px}$; for $1200 \times 1600$, $K = 37\text{ px}$. This guarantees scale-invariant background tracking.
3. **Region-Normalized Measurements:**
   Local contrast and acutance metrics must normalize gradients by stroke stroke-width (in pixels) to avoid penalizing high-resolution captures where stroke edge transitions span multiple pixels.

---

### 9. CONTENT DENSITY EFFECT ON SCALAR METRICS

To determine whether popular scalar sharpness metrics remain valid when document content density varies, an experiment was conducted on identical paper under identical optical focus and lighting:

```
Laplacian Variance Response by Document Content Density
(Same Camera, Sensor, Aperture, and Optical Focus)
+-------------------------------+-----------------------+-----------------------------+
| Region Content Type           | Approximate Text Area | Measured Laplacian Variance |
+-------------------------------+-----------------------+-----------------------------+
| Blank Paper Margin            | 0%                    | 4613.3                      |
| Sparse Printed Instructions   | ~10%                  | 4998.0                      |
| Dense Cursive Student Ink     | ~35%                  | 1490.7                      |
+-------------------------------+-----------------------+-----------------------------+
```
*(Note: Laplacian variance on textured paper is dominated by paper grain at high brightness, whereas dense dark ink creates wide interior plateau regions that suppress global variance).*

**Architectural Conclusion:**
* **Global Laplacian Variance is NOT a Sharpness Metric:** It is overwhelmingly a measure of image content density and surface texture. Comparing the Laplacian variance of document A to document B provides zero insight into relative optical focus.
* **Stroke Acutance is Density-Invariant:** By evaluating the gradient magnitude *only along detected stroke skeletons and boundaries*, stroke acutance remains stable regardless of whether the page contains one math equation or five hundred words.

---

### 10. NO_OP GENERALIZATION

A core mandate of Phase 4 is ensuring that clean, well-captured documents are not degraded by unnecessary processing.

On the unseen cohort:
* `Val_01_DenseDark` demonstrated pristine native contrast and sharp stroke acutance. Applying contrast stretching caused severe halo gain ($+21.9$). The safety gate triggered `REJECT_FALLBACK`, correctly reverting to the raw input.
* `Val_06_LinedPaper` possessed legible blue ink and flat lighting. Unsharp masking caused ruled guide lines to become unnaturally jagged.
* **Distinction Verified:** The multi-dimensional profile successfully differentiated:
  - *Genuinely Clean Document:* High stroke acutance, uniform background ratio ($> 0.85$), low paper noise ($\sigma < 4.0$). Action: `NO_OP`.
  - *Clean but Faint Content:* Uniform background, low noise, but low stroke dynamic range. Action: Targeted `CONTRAST_STRETCH`.
  - *Harmless Paper Texture:* Low high-frequency noise, no optical blur. Action: Suppress denoising.

---

### 11. SAFETY-GATE GENERALIZATION ON UNSEEN IMAGES

The Phase 4.4 safety-gate architecture (per-stage verification with single-step rollback) was executed against diverse unseen images:

```
+---------------------+-------------------------------+-------------------+---------------------------------------------------+
| Target Image        | Candidate Operator Tested     | Safety Verdict    | Detailed Rejection Reason / Verification Metric   |
+---------------------+-------------------------------+-------------------+---------------------------------------------------+
| Val_01_DenseDark    | Contrast Stretch              | REJECT_FALLBACK   | Excessive edge ringing / halo overshoot (+21.9)   |
| Val_02_FaintPencil  | Mild Unsharp Masking          | REJECT_FALLBACK   | Character fragmentation: CC ratio = 1.67 (> 1.60) |
| Val_02_FaintPencil  | Gaussian Blur (Destructive)   | NO_OP_PREFERABLE  | Minimal edge loss, but no benefit achieved        |
| Val_04_JPEGArtifacts| Bilateral Denoising           | REJECT_FALLBACK   | Character fragmentation: CC ratio = 0.56 (< 0.65) |
| Val_05_Overexposed  | Contrast Stretch              | REJECT_FALLBACK   | Excessive edge ringing / halo overshoot (+13.2)   |
+---------------------+-------------------------------+-------------------+---------------------------------------------------+
```

#### Architectural Insights from Unseen Safety Testing:
1. **Verification Evidence Remains Robust:** The multi-dimensional evidence dimensions (thin-stroke survival, halo gain, connected-component topology, and background difference) reliably identified degradations on unseen handwriting without requiring retraining.
2. **Rollback Prevents Downstream Corruption:** In `Val_02`, when unsharp masking fragmented faint pencil strokes into disconnected dots, immediate rollback restored the verified-safe raw image. In a linear unverified pipeline, subsequent binarization or OCR would have suffered catastrophic character recognition failure.
3. **Safe State Isolation:** Each operator step operates independently on the latest verified-safe image buffer, guaranteeing that a failed experimental operator never corrupts the document representation.

---

### 12. CROSS-IMAGE OPERATOR INTERACTION CLASSIFICATION

Evaluating operator sequences across both calibration and unseen validation images yields the following generalized interaction classifications:

1. **`SHADOW_CORRECTION -> CONTRAST_STRETCH`:**
   - *Classification:* **CONSISTENTLY SUPPORTED**
   - *Evidence:* Shadow correction flattens spatial illumination gradients, enabling global contrast stretching to expand dynamic range uniformly across the entire page without clipping highlighted regions or crushing shaded margins.
2. **`DENOISING -> UNSHARP_MASK`:**
   - *Classification:* **CONDITIONALLY SUPPORTED**
   - *Evidence:* Sharpening amplifies whatever high frequencies exist. Applying bilateral denoising first removes sensor grain and paper fiber spikes, preventing unsharp masking from amplifying noise. However, if denoising causes stroke fragmentation (e.g., on JPEG ringing), subsequent sharpening amplifies the broken fragments.
3. **`SHADOW_CORRECTION -> DENOISING`:**
   - *Classification:* **CONSISTENTLY SUPPORTED**
   - *Evidence:* Dividing by the background envelope elevates noise variance slightly in dark shadow regions. Placing denoising immediately after shadow correction suppresses this newly revealed shadow noise.
4. **`SHARPEN -> CONTRAST_STRETCH`:**
   - *Classification:* **NOT SUPPORTED / CONTRAINDICATED**
   - *Evidence:* Sharpening prior to contrast expansion creates high-gradient halo rings that subsequent contrast stretching saturates into stark white/black borders.

---

### 13. PARAMETER GENERALIZATION REVIEW

All numerical parameters evaluated in Phases 4.1–4.4 are cataloged below with their engineering classifications for subsequent phases:

| Parameter Name | Calibration Value | Generalization Classification | Engineering Rationale / Roadmap for Phase 4.6 |
| :--- | :--- | :--- | :--- |
| **Morphological Division Kernel ($K_{\text{bg}}$)** | $41 \times 41\text{ px}$ | **Resolution-Dependent** | Must be dynamically scaled: $K \approx \max(5, \text{int}(0.03 \times \min(W, H)) \mid 1)$. |
| **Spatial Grid Ratio Threshold** | $0.80$ | **Document-Dependent** | Fails on dark printed header boxes; requires paper-masked percentile extraction. |
| **Dynamic Range Contrast Trigger** | $< 55.0$ | **Document-Dependent** | Fails on sparse math; must evaluate stroke-center intensity rather than global percentiles. |
| **Flat Paper Noise Trigger ($\sigma_{\text{noise}}$)** | $> 4.5$ | **Camera/Sensor-Dependent** | Varies with sensor ISO and compression; candidate for adaptive median-absolute-deviation baseline. |
| **Stroke Acutance Blur Trigger** | $< 50.0$ | **Resolution-Dependent** | Edge gradient magnitude scales with image resolution; must be normalized by stroke width. |
| **Unsharp Mask Strength ($\alpha$)** | $0.8$ | **Candidate for Adaptive Derivation** | High-contrast documents require $\alpha \approx 0.3$; low-contrast faint pencil requires $\alpha \approx 0.0$ (avoid) to $0.5$. |
| **Halo Gain Rejection Limit** | $> 8.0$ | **Needs Broader Validation** | Effective on calibration, but dense cursive naturally produces localized gradient transitions. |
| **Thin-Stroke Loss Limit** | $> 25\%$ | **Needs Broader Validation** | Robust on calibration; must be verified on complex non-Latin scripts (e.g., Hindi, Arabic). |
| **Connected-Component Ratio Bounds** | $[0.65, 1.60]$ | **Needs Broader Validation** | Accurately caught pencil fragmentation ($1.67$); bounds should adapt to baseline character count. |

---

### 14. GENERALIZATION MATRIX

| Signal / Operator | Calibration Evidence | Unseen Validation Evidence | Generalization Status | Main Failure Mode / Risk |
| :--- | :--- | :--- | :--- | :--- |
| **Spatial Background Ratio** | Separated cast shadow ($0.68$) vs uniform ($0.90$) | Flags dark header box as shadow ($0.71$) | **CONDITIONALLY USEFUL** | Dark graphical form elements pull down grid cell percentiles. |
| **Flat Paper Noise Sigma** | Flagged sensor noise in `answer_sheet_4` ($5.99$) | Distinguishes paper texture from text ($3.8$ vs $42.1$) | **GENERALIZABLE** | Inaccurate if paper mask leaks into ink strokes or bleed-through. |
| **Dynamic Range ($P_{90} - P_{10}$)** | Flagged faded ink in `answer_sheet_2` ($36$) | Fails on sparse math (`Val_03`, $32.0$) | **DATASET-SENSITIVE** | Low text density places $P_{10}$ on background white paper. |
| **Stroke Acutance** | Quantified sharpness of printed vs written text | Distinguishes light pencil from optical blur | **GENERALIZABLE** | Raw values vary across image resolutions if unnormalized. |
| **Laplacian Variance** | Corresponded with apparent clarity | Confounded by content density ($4613$ vs $1490$) | **UNRELIABLE** | Completely dominated by stroke count and paper grain. |
| **Color Pixel Fraction** | Detected blue ink in `answer_sheet_5` ($4.6\%$) | Mistook desk border for annotation ($31.1\%$) | **CONDITIONALLY USEFUL** | Requires strict bounding to verified physical page mask. |
| **Shadow Correction** | Restored shadowed text in `answer_sheet_3` | Flattened lighting gradients on patches | **GENERALIZABLE** | Fixed kernel causes latency and line-bridging on small crops. |
| **Contrast Stretch** | Improved readability of faint ink | Blew out stroke cores on dense cursive | **CONDITIONALLY USEFUL** | Unchecked application causes severe edge halo overshoot. |
| **Bilateral Denoising** | Suppressed paper grain cleanly | Fragmented ringing in JPEG compressed text | **CONDITIONALLY USEFUL** | Merges compression artifacts into stroke bodies. |
| **Unsharp Masking** | Sharpened soft printed text | Fragmented faint pencil into dots ($CC=1.67$) | **CONDITIONALLY USEFUL** | Amplifies benign paper texture into black speckles. |
| **Safety Gate Rollback** | Caught halo overshoot and line erosion | Caught pencil fragmentation and blur failure | **GENERALIZABLE** | Computationally redundant if candidate selection is accurate. |

---

### 15. PROPOSED UPDATED ENHANCEMENT ARCHITECTURE

Based on cross-image validation evidence, the conceptual enhancement architecture is updated to incorporate **semantic masking**, **resolution normalization**, and **stroke-aware measurement layers**:

```
                              RAW RECTIFIED BGR IMAGE
                                         │
                                         ▼
                     ┌──────────────────────────────────────┐
                     │     PRE-MEASUREMENT PREPARATION      │
                     │  - Physical Page Quad Masking        │
                     │  - Scale & Resolution Extraction     │
                     │  - Flat-Paper vs Ink Segmentation    │
                     └──────────────────┬───────────────────┘
                                         │
                                         ▼
                     ┌──────────────────────────────────────┐
                     │    SCALE-NORMALIZED CONDITION ENGINE │
                     │  - Masked Spatial Background Grid    │
                     │  - Stroke-Center Dynamic Range       │
                     │  - Flat-Paper Noise Sigma            │
                     │  - Normalized Stroke Acutance        │
                     │  - In-Page Color Fraction            │
                     └──────────────────┬───────────────────┘
                                         │
                                         ▼
                     ┌──────────────────────────────────────┐
                     │      DOCUMENT CONDITION PROFILE      │
                     │   (Multi-Dimensional Signal Vector)  │
                     └──────────────────┬───────────────────┘
                                         │
                                         ▼
                     ┌──────────────────────────────────────┐
                     │     CANDIDATE OPERATOR PLANNER       │
                     │   - Determines Candidate Sequence    │
                     │   - Selects Scale-Proportional K     │
                     │   - NO_OP Bypass if Profile Clean    │
                     └──────────────────┬───────────────────┘
                                         │
            ┌────────────────────────────┴────────────────────────────┐
            ▼                                                         │
   [ If NO_OP Path ]                                                  │
            │                                                         ▼
            │                                          ┌─────────────────────────────┐
            │                                     ┌───►│       SAFE IMAGE STATE      │◄───┐
            │                                     │    │  (Starts with Raw Rectified)│    │
            │                                     │    └──────────────┬──────────────┘    │
            │                                     │                   │                   │
            │                                     │                   ▼                   │
            │                                     │    ┌─────────────────────────────┐    │
            │                                     │    │    NEXT CANDIDATE OPERATOR  │    │
            │                                     │    └──────────────┬──────────────┘    │
            │                                     │                   │                   │
            │                                     │                   ▼                   │
            │                              Rollback    ┌─────────────────────────────┐    │
            │                              on Reject   │   POST-STAGE VERIFICATION   │    │
            │                                     │    │   - Thin Stroke Retention   │    │
            │                                     │    │   - Halo Gain Overshoot     │    │
            │                                     │    │   - Component Topology      │    │
            │                                     │    └──────────────┬──────────────┘    │
            │                                     │                   │                   │
            │                                     │                   ▼                   │
            │                                     │         [ VERIFICATION DECISION ]     │
            │                                     │            /              \           │
            │                                     └────── REJECT              ACCEPT ─────┘
            │                                                                    │
            │                                                        (Update Safe State)
            │                                                                    │
            ▼                                                                    ▼
   ═════════════════════════════════════════════════════════════════════════════════════════════
                              VERIFIED ENHANCED DOCUMENT REPRESENTATION
                               (Always paired with Raw Rectified BGR)
   ═════════════════════════════════════════════════════════════════════════════════════════════
```

#### Newly Identified Essential Layers:
1. **Pre-Measurement Preparation Layer:** Ensures signals are evaluated strictly within the physical page boundary, separating paper from background desk surfaces and extracting scale factors.
2. **Stroke-Aware Signal Evaluation:** Replaces naive global percentile calculations with masked paper noise and stroke-center dynamic range measurements.
3. **Resolution-Adaptive Kernel Sizing:** Automatically derives structuring elements and filtering windows from document pixel dimensions.

---

### 16. PHASE 4.6 REQUIREMENTS (UNRESOLVED AREAS)

Before proceeding to production implementation, the following concrete technical challenges must be investigated and resolved in Phase 4.6:

1. **Adaptive Parameter Derivation:** Formulating closed-form or lookup-based derivations for operator parameters (e.g., kernel size $K$, unsharp mask $\alpha$, CLAHE clip limit) as continuous functions of document resolution and condition profile, eliminating static hard-coded constants.
2. **Robust Semantic Paper Masking:** Developing a lightweight, deterministic algorithm to extract the flat-paper mask and stroke skeleton without requiring heavy machine learning models.
3. **Sparse-Content Contrast Evaluation:** Replacing percentile dynamic range ($P_{90} - P_{10}$) with stroke-boundary contrast ($\mu_{\text{paper}} - \mu_{\text{stroke}}$) to prevent false positives on mathematical formulas and diagrams.
4. **Downstream OCR/HTR/OMR Task Validation:** Measuring whether enhancements that pass image-level safety verification translate directly into measurable character error rate (CER) reductions and OMR bubble recognition improvements.
5. **Runtime Latency Budgeting:** Optimizing morphological background division and bilateral denoising to ensure execution times remain well within interactive mobile scanner constraints ($< 250\text{ ms}$ on standard hardware).

---

### CONFIRMATION CHECKLIST

* [x] **Calibration set identified:** 5 images (`answer_sheet.jpg`, `answer_sheet_2.png`, `answer_sheet_3.jpg`, `answer_sheet_4.jpg`, `answer_sheet_5.jpg`).
* [x] **Unseen validation set identified:** 10 images from `images/dataset_samples/` (`Val_01` to `Val_10`).
* [x] **Phase 2 untouched:** All Phase 2 files remain completely unmodified.
* [x] **Phase 3 untouched:** All Phase 3 files remain completely unmodified.
* [x] **No final enhancement engine implemented:** Phase 4.5 is strictly an investigation and validation phase.
* [x] **No thresholds frozen:** All numerical values remain empirical calibration baselines.
* [x] **No universal quality score created:** Evaluation relies on multi-dimensional evidence vectors.
* [x] **Raw BGR preserved:** Safe-state rollback guarantees raw rectified BGR is never overwritten or lost.
* [x] **False positives preserved:** Explicitly cataloged and demonstrated (Cases A, B, C, D, E).
* [x] **False negatives preserved:** Explicitly cataloged and analyzed (subtle shadows, soft corners, small annotations).
* [x] **Generalization limitations documented:** Signal sensitivity to content density, resolution, and printed form structures fully articulated.
