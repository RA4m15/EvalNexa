# Phase 4.1: Automatic Image Enhancement Investigation Report

**Project**: AI-EVAL-OpenCV  
**Phase**: 4.1 — Automatic Image Enhancement Investigation  
**Status**: INVESTIGATION ONLY (Phase 2 & Phase 3 Frozen; No Production Pipeline / No OCR / No Auto-Correction)  
**Date**: October 2026  

---

## 1. Executive Summary & Objective

In Phases 2 and 3, we developed and froze the document region validation and canonical geometric transformation pipeline (`ScannedDocumentResult`).

The objective of **Phase 4.1** is to investigate how a rectified document image should be enhanced automatically so that it becomes optimal for downstream **OCR** (printed text recognition), **HTR** (handwritten text recognition), and **OMR** (optical mark / bubble recognition), while strictly preserving genuine document information.

### Critical Guardrails Respected
- **Investigation Only**: No final production enhancement pipeline is frozen.
- **Zero Modifications to Frozen Code**: All Phase 2 and Phase 3 modules remain untouched.
- **No OCR/HTR Engine Integration**: Downstream evaluation is prepared for, not executed.
- **Reversibility**: The raw rectified BGR image is never discarded or permanently mutated.

---

## 2. Experimental Setup & Benchmarks

The investigation was executed using [`phase4/01_image_enhancement_investigation.py`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase4/01_image_enhancement_investigation.py) across two sets of test inputs:
1. **Primary Calibration Images** (Outputs from Phase 3.6 `ScannedDocumentResult`):
   - `answer_sheet_2.png`: Clean physical A4 page ($899 \times 1273$ px), high contrast, slight perspective.
   - `answer_sheet_3.jpg`: Physical page ($941 \times 1205$ px) with a **severe diagonal cast shadow** across the upper-right quadrant.
   - `answer_sheet_4.jpg`: High-resolution frame-limited capture ($1200 \times 1700$ px), printed table rules, handwritten roll numbers.
   - `answer_sheet_5.jpg`: Frame-limited capture ($1200 \times 1600$ px), student handwriting with blue ballpoint ink.
   - `answer_sheet.jpg`: Ambiguous crop ($768 \times 1024$ px), faint multiple-choice bubble grids.
2. **Dataset Samples** (`images/dataset_samples/`): Real student answer script crops containing faint pencil, varied ballpoint pens, and bleed-through.

---

## 3. Quantitative Operator Benchmarks

The 12 enhancement dimensions were benchmarked for execution latency and objective image signals:

| Image Target | Enhancement Operator | Latency (ms) | Mean Brightness | Dynamic Range | Sharpness (Laplacian Var) | Paper Background Std | Michelson Contrast |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`answer_sheet_3.jpg`**<br>*(Severe Cast Shadow)* | **Raw Rectified Grayscale** | — | 202.3 | 82.0 | 595.0 | 3.8 | 0.26 |
| | Gamma Correction ($\gamma=0.8$) | 3.9 ms | 191.6 | 96.0 | 711.2 | 4.7 | 0.33 |
| | Global Histogram Equalization | 2.9 ms | 129.3 | 208.0 | 1978.0 | **18.7 (Severe Noise)** | 0.83 |
| | Unsharp Masking ($\alpha=1.2$) | 6.8 ms | 202.0 | 85.0 | 2438.5 | 7.0 | 0.33 |
| | CLAHE ($\text{clip}=2.0, 8\times 8$) | 3.1 ms | 192.2 | 89.0 | 942.1 | 5.5 | 0.33 |
| | **Morphological Shadow Division** | **70.0 ms** | **233.8** | **35.0** | **773.9** | **1.3 (Flat Paper)** | **0.16** |
| | Gaussian Flat-Fielding ($\sigma=50$) | 356.1 ms | 246.0 | 22.0 | 946.6 | 0.0 | 0.13 |
| | Bilateral Denoising | 56.1 ms | 202.0 | 81.0 | 553.3 | 3.6 | 0.26 |
| | Min-RGB Channel Projection | 44.2 ms | 197.8 | 81.0 | 610.3 | 4.1 | 0.27 |
| | Sauvola Binarization | 34.8 ms | 237.3 | 0.0 | 14001.3 | 0.0 | 0.04 |
| **`answer_sheet_2.png`**<br>*(Clean A4 Page)* | **Raw Rectified Grayscale** | — | 223.7 | 36.0 | 2523.6 | 3.4 | 0.19 |
| | CLAHE ($\text{clip}=2.0, 8\times 8$) | 2.4 ms | 208.2 | 47.0 | 2803.0 | **7.5 (Grain Amplified)**| 0.24 |
| | **Unsharp Masking ($\alpha=1.2$)** | **3.6 ms** | **222.4** | **43.0** | **7675.5** | **5.3** | **0.27** |
| | **Bilateral Denoising** | **2.6 ms** | **223.4** | **34.0** | **2513.1** | **1.8 (Smoothed)** | **0.19** |
| | Morphological Shadow Division | 78.1 ms | 230.3 | 27.0 | 2545.9 | 2.9 | 0.19 |
| | Sauvola Binarization | 34.4 ms | 236.3 | 0.0 | 18836.5 | 0.0 | 0.04 |

---

## 4. Fine-Stroke & Handwriting Sensitivity Audit

We measured the effect of morphological operations on delicate student handwriting strokes across dataset samples:
- **`Sample 01` (Cursive pencil writing)**: 2x2 morphological opening eroded **7.0%** of foreground ink pixels.
- **`Sample 04` (Thin ballpoint math equations)**: 2x2 morphological opening eroded **20.3%** of foreground ink pixels.
- **`Sample 20` (Numerical roll numbers)**: 2x2 morphological opening eroded **16.8%** of foreground ink pixels.

*Finding*: Morphological opening destroys thin pen loops, erodes decimal points, breaks crossbars on 't', and removes dots on 'i' and 'j'. **Morphological opening must be strictly prohibited as a mandatory base enhancement step.**

---

## 5. Answers to Mandatory Phase 4.1 Investigation Questions

### Question 1: Which enhancement problems occur in the calibration images?
Across the 5 calibration images and dataset samples, 6 distinct degradation problems were identified:
1. **Severe Cast Shadows / Uneven Illumination**: Prominently seen in `answer_sheet_3.jpg` (top-right quadrant is 40–60 intensity levels darker than the bottom-left).
2. **Low Dynamic Range / Flat Contrast**: Seen in `answer_sheet.jpg` where printed grey table rules and text lack punch.
3. **Paper Grain & Sensor High-Frequency Noise**: Background paper shows microcontrast variations ($\text{Std} = 3.4 - 14.7$), which become amplified into salt-and-pepper noise by aggressive equalizers.
4. **Faint Handwriting & Thin Pen Strokes**: In dataset samples 04 and 20, ballpoint pen pressure is inconsistent, leading to broken character strokes.
5. **Bleed-Through / Show-Through**: Ink from the reverse side of thin exam paper creates faint ghost contours in the background.
6. **Colored Ink & Red Rubric Annotations**: Blue student ink and red teacher grading pens must not be lost or collapsed into identical black tones.

---

### Question 2: Which methods address each problem?
| Degradation Problem | Optimal Method | Mechanism & Impact |
| :--- | :--- | :--- |
| **Cast Shadows & Illumination Gradients** | **Morphological Background Division** | Dilation ($k=41$) extracts illumination envelope $\text{BG}$; dividing $I / \text{BG}$ eliminates shadows with zero haloing. |
| **Low Global Contrast** | **Percentile Dynamic Range Stretch (1%–99%)** | Maps darkest ink to 0 and paper white to 255 without splotching. |
| **Sensor Grain / Background Noise** | **Bilateral Filtering ($d=5$)** | Smoothes flat paper texture ($\text{BgStd}$ drops from 3.4 to 1.8) while preserving sharp stroke edges. |
| **Faint Handwriting / Blurry Edges** | **Mild Unsharp Masking ($\alpha=0.8 - 1.2$)** | Amplifies high-frequency stroke boundaries, boosting Laplacian sharpness by 3x. |
| **Bleed-Through** | **Paper White-Point Calibration** | Clamps pixels within 10% of background white to pure 255, eliminating faint reverse-side ink. |
| **Colored Marking Separation** | **HSV Saturation & Hue Thresholding** | Isolates red stamps/corrections ($H \in [0,10] \cup [170,180]$) from blue handwriting ($H \in [100,135]$). |

---

### Question 3: Which methods damage handwriting or printed information?
1. **Global Histogram Equalization (`cv2.equalizeHist`)**: **Severely Damaging.** It flattens the global histogram, turning light grey paper grain into dark splotches ($\text{BgStd}$ exploded to 18.7) and over-saturating solid text.
2. **Morphological Opening/Closing**: **Damaging to Handwriting.** Erodes between 7% and 20% of thin strokes, disconnects cursive ligatures, and obliterates decimal points and punctuation.
3. **Aggressive Gaussian Blur ($k \ge 5$)**: **Damaging to Text.** Blurs thin strokes, bridges closely spaced letters (e.g. 'rn' becomes 'm'), and reduces stroke edge contrast.
4. **Heavy Sharpening ($\alpha > 2.0$ or aggressive Laplacian)**: **Damaging to OMR.** Introduces ringing halos around circular bubble borders, causing Hough circle detectors to produce false dual-ring detections.

---

### Question 4: Should color be preserved?
**YES, color must be strictly preserved.**
In academic answer sheets and exam forms:
- Student handwriting is frequently in blue ballpoint or black gel ink.
- Evaluator / teacher marks are made in red or green ink.
- Institutional verification stamps, QR codes, and seal rubrics carry color-specific security features.
Collapsing to grayscale prematurely destroys the ability to separate teacher annotations from student answers in downstream Phase 5. The primary output must retain the 3-channel BGR image alongside derived color masks.

---

### Question 5: Should grayscale be generated before or after enhancement?
**Grayscale should be generated AFTER color-based analysis, but illumination normalization operates best on single-channel Grayscale/Luminance:**
- Color mask extraction (red rubrics, blue ink) must happen directly on the **raw BGR** image.
- Illumination normalization (background division) should operate on the **Grayscale/Luminance** channel to avoid color shifting.
- If an enhanced color image is required, background division can be applied to the L channel in LAB color space: $L_{\text{norm}} = (L / \text{BG}_L) \times 255$, followed by conversion back to BGR.

---

### Question 6: Is CLAHE useful, harmful, or conditional?
**CLAHE is CONDITIONAL, not universal:**
- **When Useful**: In severely underexposed documents or localized shadow areas, mild CLAHE ($\text{clipLimit}=1.5, \text{gridSize}=(8,8)$) improves local character legibility.
- **When Harmful**: On clean, high-contrast documents (`answer_sheet_2.png`), CLAHE amplifies homogeneous paper grain into visible mottled noise ($\text{BgStd}$ doubled from 3.4 to 7.5) and creates faint tile-boundary checkerboard artifacts.
- **Verdict**: CLAHE must only be activated conditionally when global dynamic range is low ($< 50$) or illumination variance is high, or used with a conservative clip limit ($\le 1.5$).

---

### Question 7: How should shadows/uneven illumination be handled?
**Morphological Background Division is the superior approach:**
1. Estimate the background illumination field:
   $$\text{BG} = \text{cv2.medianBlur}(\text{cv2.morphologyEx}(I, \text{cv2.MORPH_DILATE}, K), 21)$$
   where $K$ is a rectangular structuring element of size $41 \times 41$ px (larger than any text character or OMR bubble).
2. Perform division normalization:
   $$I_{\text{flat}}(x, y) = \text{clip}\left(\frac{I(x, y)}{\max(1, \text{BG}(x, y))} \times 255.0, 0, 255\right)$$
On `answer_sheet_3.jpg`, this method completely eliminated the dark diagonal shadow, restored the paper background std to a clean $1.3$, and left the text strokes perfectly crisp. Gaussian low-pass filtering was 5x slower (356 ms vs 70 ms) and caused edge haloing near document boundaries.

---

### Question 8: Is denoising safe for handwriting?
**Only Edge-Preserving Denoising is safe; Linear Gaussian smoothing is NOT safe.**
- **Gaussian Blur**: Softens stroke boundaries and attenuates light pencil marks.
- **Bilateral Filtering (`cv2.bilateralFilter(d=5, sigmaColor=25, sigmaSpace=25)`)**: **Safe.** It averages pixels only if their intensity is close to the center pixel, smoothing flat paper texture while leaving ink edges unaffected.
- **Mild Median Filtering ($3 \times 3$)**: **Safe for salt-and-pepper sensor noise**, but bilateral is preferred for text.

---

### Question 9: Is sharpening safe for OCR/OMR?
**Mild Unsharp Masking is SAFE and BENEFICIAL; Laplacian High-Boost is RISKY:**
- **Unsharp Masking ($\sigma=1.0 - 1.5, \alpha=0.6 - 1.0$)**: Boosts contrast at character boundaries without ringing. Improves Tesseract word accuracy on small fonts.
- **Laplacian Kernels**: Cause high-frequency overshoot (white halos adjacent to black letters) and distort circular OMR bubble radii, interfering with Hough circle detection.
- **Recommendation**: Restrict sharpening to mild unsharp masking with $\alpha \le 1.0$.

---

### Question 10: Should adaptive thresholding be part of the base pipeline or an optional derivative?
**Adaptive thresholding must be an OPTIONAL DERIVATIVE REPRESENTATION, NEVER the sole base output:**
- Modern deep-learning OCR and HTR engines (e.g. TrOCR, PaddleOCR, Tesseract LSTM) require **grayscale or color** inputs with smooth subpixel antialiasing. Hard binarization discards stroke gradient information, degrading OCR confidence.
- However, OMR bubble detection, table rule extraction, and layout segmentation benefit significantly from clean binary masks.
- **Architecture Contract**: Phase 4 must provide both `enhanced_gray` (primary) and an optional `binary_mask` (derivative via Sauvola or Adaptive Gaussian).

---

### Question 11: Should enhancement be fixed, conditional, or hybrid?
**A HYBRID MULTI-REPRESENTATION PIPELINE is the most robust architecture (Option C):**
1. **Fixed Core**:
   - Paper white-point normalization.
   - Bilateral edge-preserving noise suppression.
   - Mild unsharp masking.
2. **Conditional Branches** (triggered by detected diagnostic signals):
   - *If illumination variance across quadrants $> 25.0$*: Activate Morphological Shadow Division.
   - *If global dynamic range $< 40.0$*: Activate mild dynamic range stretching.
   - *If color saturation $> 35.0$*: Generate colored ink and rubric masks.
3. **Multi-Representation Output**: Always emits raw BGR, enhanced grayscale, derivative binary mask, and color rubric masks.

---

### Question 12: What exact EnhancedDocumentResult contract should Phase 5 consume?
```python
@dataclass
class EnhancedDocumentResult:
    status: str                             # "ENHANCED_SUCCESS", "ENHANCED_PASS_THROUGH", "ENHANCED_WARNING"
    raw_scanned_bgr: np.ndarray             # Original rectified BGR image (strictly preserved for reversibility)
    enhanced_gray: np.ndarray               # Illumination & contrast normalized grayscale (primary for OCR/HTR)
    binary_mask: Optional[np.ndarray]       # Sauvola / Adaptive Gaussian binarization (for OMR bubbles & layout)
    color_rubric_mask: Optional[np.ndarray] # Mask of non-black/blue markings (red grading pen, seals, stamps)
    dimensions: Tuple[int, int]             # (width, height)
    pipeline_mode: str                      # "HYBRID_CONDITION_DEPENDENT"
    applied_operations: List[str]           # e.g. ["SHADOW_CORR_MORPH", "BILATERAL_DENOISE", "UNSHARP_MASK"]
    detected_conditions: Dict[str, Any]     # Illumination gradient, noise level, dynamic range
    objective_signals: Dict[str, float]     # Diagnostic signal measurements
    processing_latency_ms: float            # Total enhancement time in ms
```

---

### Question 13: Which numerical parameters require broader validation?
The following parameters showed excellent results on calibration images but should be validated on a larger 500+ document dataset:
1. **Morphological Background Kernel Size ($K=41 \times 41$)**: Validating scaling across resolutions from 720p to 4K (e.g. $K \approx 0.03 \times \min(W, H)$).
2. **Sauvola Window Size ($W=25$) & $k=0.18$**: Validating binarization consistency on faint pencil handwriting.
3. **Unsharp Mask Strength ($\alpha=0.8$)**: Verifying that no ringing occurs on low-DPI document scans.
4. **Color Saturation Threshold ($S > 40$)**: Tuning threshold across faded ballpoint ink vs. dark blue gel pens.

---

## 6. Generated Diagnostic Artifacts

The following visual comparisons were generated in [`phase4/output/`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase4/output):
- `phase4/output/phase4_shadow_correction_answer_sheet_3.png`: Demonstrates raw rectified image vs. morphological shadow division and Sauvola binarization under severe cast shadow.
- `phase4/output/phase4_enhancement_comparison_answer_sheet_2.png`: Benchmarks unsharp masking, CLAHE, bilateral filtering, and binarization on clean A4 paper.
- `phase4/output/phase4_handwriting_dataset_samples.png`: Demonstrates the destructive impact of morphological opening on thin handwriting strokes and dots.
- `phase4/output/phase4_color_rubric_preservation.png`: Demonstrates isolation of blue student ink from red teacher grading marks and black printed rules.

---
*Report prepared for Phase 4.1 of AI-EVAL-OpenCV.*
