# PHASE 8.1 — OCR/HTR READINESS EVIDENCE INVESTIGATION REPORT
**Project:** `AI-EVAL-OpenCV` (Automated Exam Evaluation Pipeline)  
**Milestone:** Phase 8.1 — OCR/HTR Readiness Evidence Investigation (Post-Audit Revised Edition)  
**Author:** Antigravity AI  
**Date:** October 2026  
**Status:** **INVESTIGATION COMPLETE (AUDITED) — ARCHITECTURAL HYPOTHESES & PROVISIONAL SIGNALS ESTABLISHED**

---

> [!IMPORTANT]
> **INVESTIGATION MILESTONE DECLARATION**  
> Phase 8.1 is an **investigation milestone**, NOT a production OCR/HTR readiness gate. All numerical thresholds, operator selections, and readiness boundaries documented herein are **provisional calibration observations** and architectural hypotheses. They do **not** represent frozen production rules and have **not** yet been correlated with downstream OCR/HTR Character Error Rates (CER) or Word Error Rates (WER).

---

## 1. EXECUTIVE SUMMARY & OBJECTIVE

The purpose of **Phase 8.1** is to investigate what evidence indicates that a processed student exam document is genuinely suitable for downstream **OCR (Optical Character Recognition)** and **HTR (Handwritten Text Recognition)**, without prematurely implementing or freezing the final recognition engine.

Following the completion of **Phase 7 (Production Rescan Decision Engine)**, the document intake pipeline classifies images into:
- `CONTINUE`
- `HUMAN_REVIEW`
- `RESCAN_REQUIRED`

A critical architectural finding of Phase 8.1 is that:
$$\mathbf{CONTINUE \ne OCR\_READY}$$

A document can be physically clean, sharp, evenly illuminated, and completely free of fatal border clipping (earning a Phase 7 `CONTINUE` verdict), yet remain **un-transcribable** by downstream OCR/HTR models due to:
1. **Reading Orientation Mismatch:** The page is rotated sideways ($90^\circ, 270^\circ$) or inverted ($180^\circ$).
2. **Line Separation Complexity:** Intersecting ascenders and descenders cause standard horizontal line segmenters to cut glyphs or merge adjacent lines.
3. **Micro-Scale Text:** Character heights sub-sample letter loops and diacritics below typical neural network receptive fields.
4. **Ruled Line Interference:** Notebook ruling lines physically intersect handwritten characters.
5. **Non-Text Layout Complexity:** Freeform diagrams, mathematical derivations, matrices, and blank margins.

Phase 8.1 investigates the evidence signals necessary to evaluate these dimensions while strictly maintaining that **Physical Document Quality** and **Downstream Recognition Readiness** are separate, non-collapsible operational concepts.

---

## 2. PIPELINE ARCHITECTURE & PLACEMENT

Phase 8 sits strictly between Phase 7 intake routing and the downstream OCR/HTR evaluation subsystems:

```
Camera / Physical Image
          ↓
Phase 2: Page Region Candidate Detection
          ↓
Phase 3: Perspective Rectification (Scanner Integration)
          ↓
Phase 4: Image Enhancement Baseline
          ↓
Phase 5: Smart Quality Assessment (Tier 1 Veto, Tier 2 Multi-Dimensional Profile)
          ↓
Phase 6: Intelligent Auto-Correction Engine (Safe-State Lifecycle & Verification)
          ↓
Phase 7: Rescan Decision Engine (CONTINUE | HUMAN_REVIEW | RESCAN_REQUIRED)
          ↓
Phase 8: OCR/HTR Readiness Assessment & Normalization (INVESTIGATION: Phase 8.1)
          ↓
Downstream Text-Line Extraction & HTR Transcription
          ↓
Rubric AI Evaluation & Scoring
```

---

## 3. FUNDAMENTAL DISTINCTION: DOCUMENT QUALITY VS OCR/HTR READINESS

Document processing pipelines frequently collapse physical quality with recognition readiness. Phase 8.1 formalizes their essential divergence:

| Operational Dimension | Physical Document Quality (Phase 5–7) | OCR/HTR Recognition Readiness (Phase 8) |
|---|---|---|
| **Core Question** | "Is the document physically complete, well-lit, and uncorrupted?" | "Can a downstream model reliably segment lines and transcribe glyphs?" |
| **Defect Focus** | Defocus blur, specular flash whiteout, margin occlusion, boundary clipping. | Reading orientation, line pitch, character scale, rule-line crossing, cursive entanglement. |
| **Sensor Perspective** | Camera sensor photons, exposure uniformity, corner geometry. | Machine learning receptive fields, tokenizer vocabularies, polygonal line seams. |
| **Pipeline Consequence** | `RESCAN_REQUIRED` forces the student or operator to physically re-photograph the page. | `CONDITIONALLY_READY` triggers automated pre-OCR digital transformations (e.g. de-rotation, scale normalization). |

---

## 4. DIMENSION 1: READING ORIENTATION & 4-WAY SEMANTIC UPRIGHTNESS

Phase 3 perspective rectification aligns the paper boundary with the coordinate frame, but **deliberately does not infer semantic reading orientation**. An A4 page can be rectified in 4 orthogonal orientations ($0^\circ, 90^\circ, 180^\circ, 270^\circ$).

### Mathematical Formulation of Candidate Orientation Signals:
1. **Axis Anisotropy Ratio ($R_{\text{axis}}$):**
   $$H_{\text{proj}}(y) = \sum_{x=0}^{W-1} \text{Binary}(x, y), \quad V_{\text{proj}}(x) = \sum_{y=0}^{H-1} \text{Binary}(x, y)$$
   $$R_{\text{axis}} = \frac{\text{Var}(H_{\text{proj}})}{\max(1.0, \text{Var}(V_{\text{proj}}))}$$
   - When text lines are horizontal ($0^\circ, 180^\circ$), projection variance along rows is significantly higher than along columns because row sums alternate sharply between dark text lines and bright inter-line spaces.
   - When text lines are vertical ($90^\circ, 270^\circ$), projection variance along columns dominates.

2. **Header Polarity Discriminator ($P_{\text{header}}$):**
   In structured student exam scripts with printed header blocks (metadata, student name, roll number):
   $$P_{\text{header}} = \frac{\sum_{y=0}^{H/3} H_{\text{proj}}(y)}{\max\left(1.0, \sum_{y=2H/3}^{H-1} H_{\text{proj}}(y)\right)}$$

### Empirical Calibration Finding & Strict Scope Clarification:
> [!NOTE]
> **Audit Clarification on Orientation Accuracy:**  
> **100% accuracy was observed on the evaluated calibration cases** (`answer_sheet_2.png` swept across 4 orthogonal quadrants).  
> **This does NOT establish universal orientation reliability.**  
> Orientation thresholds are **NOT frozen** in Phase 8.1.

### Failure Risks & Known Vulnerabilities of Heuristic Orientation:
Orientation detection using projection profiles and header polarity carries substantial failure modes that must be addressed in subsequent validation:
- **Sparse Handwriting:** Pages with only a few isolated handwritten lines lack sufficient projection variance contrast, leading to ambiguous axis determination.
- **Symmetric Layouts:** Centered exam titles, uniform grids, or balanced top/bottom text densities produce polarity ratios close to $1.0$, rendering polarity discrimination unreliable.
- **Missing or Bottom Headers:** Answer sheets without top metadata blocks (e.g. continuation sheets, back pages) can trigger false $180^\circ$ inversions.
- **Mixed Printed/Handwritten Pages:** Form-style sheets with vertical table borders or sidebar instructions introduce high column-projection variance that confounds axis detection.
- **90° / 180° Rotated Text Blocks:** Rotated margin notes or multi-directional sketches break the global orientation assumption.
- **Unusual Layouts:** Two-column formats, landscape answer sheets, or freehand sketches can skew projection variance.

---

## 5. DIMENSION 2: TEXT-LINE SEGMENTATION & LINE PITCH TOPOLOGY

Downstream HTR engines (e.g. PyLaia, TrOCR, CRNN) transcribe text line by line. Line segmentation failure is a dominant source of transcription errors in unconstrained handwriting.

### Candidate Line Topology Metrics:
1. **Peak-to-Valley Ratio (PVR):**
   $$\text{PVR} = \frac{\text{Mean}(P_{\text{peaks}})}{\max(1.0, \text{Mean}(P_{\text{valleys}}))}$$
2. **Line Collision Ratio ($R_{\text{collision}}$):**
   The fraction of connected components whose vertical bounding boxes span across detected valley scanlines:
   $$R_{\text{collision}} = \frac{N_{\text{colliding}}}{N_{\text{total\_glyphs}}}$$

### Provisional Calibration Values (NOT Production Thresholds):
> [!WARNING]
> **Audit Clarification on PVR & Collision Values:**  
> The following values are **calibration observations / provisional values**, NOT frozen production thresholds:
> - $\text{PVR} \ge 2.5$: Observed in calibration cases exhibiting distinct, easily sliceable baselines.
> - $1.7 \le \text{PVR} < 2.5$: Observed in calibration cases with moderate line proximity.
> - $\text{PVR} < 1.7$: Observed in controlled stress degradation where ascenders and descenders heavily collided.
> - $R_{\text{collision}} > 15\%$: Observed in stress cases where horizontal cutting sliced through glyphs.
> - $\text{PVR} \ge 1.8$ and $R_{\text{collision}} < 10\%$: Observed in clean handwriting calibration samples.
> 
> **These values must NOT be described or treated as universally valid OCR/HTR boundaries.** They are provisional baseline indicators that require empirical correlation with downstream HTR transcription error rates in Phase 11.

---

## 6. DIMENSION 3: CHARACTER STROKE SCALE & RESOLUTION

Modern convolutional and transformer-based HTR encoders rescale line crops to standard heights (e.g. $32\text{ px}$, $64\text{ px}$, or $128\text{ px}$).

### Calibration Observations on Character Scale:
- In calibration full-page scans (`answer_sheet_2.png`), median character height was approximately $20.0\text{ px}$ with stroke skeleton width of $\sim 2.5\text{ px}$.
- In the 15 tested student crops (`Handwriting224`), median character height was observed to range between **$7.0\text{ px}$ and $11.0\text{ px}$**, with lower quartiles near $5.0$–$6.0\text{ px}$.

### Explicit Audit Corrections on Scale Limits:
> [!CAUTION]
> **Audit Clarification on Scale Boundaries:**  
> - Values such as **$12\text{ px}$**, **$6\text{ px}$**, and **median $7$–$11\text{ px}$** are strictly **dataset and calibration observations**.
> - The investigation does **NOT** claim that "$12\text{ px}$ is the minimum OCR requirement" or that "below $6\text{ px}$ is universally illegible."
> - Actual recognition legibility depends heavily on:
>   1. **Input image DPI / resolution:** A $300\text{ DPI}$ scan preserves glyph morphology at lower relative pixel heights than a compressed JPEG.
>   2. **Crop scale & field of view:** Distance from camera to paper.
>   3. **Handwriting style & cursive density:** Open print vs condensed cursive.
>   4. **Downstream OCR/HTR architecture:** High-resolution vision transformers vs shallow CNN-RNN encoders.
>   5. **Preprocessing & interpolation methods:** Bilinear vs bicubic vs neural super-resolution.
>   6. **Stroke width and character height ratios:** Thin sharp ink vs bleeding marker ink.

---

## 7. DIMENSION 4: SCALE NORMALIZATION & UPSCALING HYPOTHESIS

In the student script dataset crops, small character loop structures (in letters like 'e', 'a', 'g', 'o') occupied only $3$–$4$ pixels across.

### Audit Clarification on Pre-OCR Upscaling:
> [!NOTE]
> Any mandatory claim that the pipeline "requires $2\times$ adaptive scaling" is revised to a **provisional architectural hypothesis**:  
> **"Scale normalization/upscaling should be evaluated for micro-scale text prior to downstream recognition."**  
> $2\times$ is **NOT** frozen as a production multiplier. Its optimal magnitude, interpolation algorithm, and actual effect on CER/WER must be evaluated during downstream engine integration.

---

## 8. DIMENSION 5: RULED PAPER & ARTIFACT INTERFERENCE

Many exam answer sheets feature pre-printed horizontal ruling lines (blue, gray, or faint black).
- **Physical Collision:** Ruling lines physically intersect vertical character stems (e.g. 't', 'l', 'd', 'p', 'q') and cross through lowercase loops.
- **spurious Ligatures:** In standard binarization, continuous horizontal ruling lines can merge with characters, creating spurious horizontal ligatures.

### Audit Clarification on Ruled-Line Suppression:
> [!IMPORTANT]
> Morphological line subtraction is **NOT** universally required or universally safe.  
> **Ruled-line suppression is a candidate preprocessing operation whose benefit and stroke-loss risk require downstream validation.**  
> Aggressive morphological line removal carries a severe risk of damaging horizontal handwriting strokes (such as crossbars on 't', 'f', 'E', 'H', minus signs, and fraction bars). It must only be applied conditionally when proven beneficial.

---

## 9. DIMENSION 6: CONTENT ZONING (TEXT VS NON-TEXT DIAGRAMS)

Exam answer sheets contain diverse modalities:
- Narrative text answers
- Mathematical equations and matrices
- Geometric sketches, flowcharts, and circuit diagrams
- Blank margins and whitespace

### Audit Clarification on Content Zoning Evidence:
> [!NOTE]
> Initial experiments indicated that stroke density anisotropy and stroke-length variance provide **promising evidence for content zoning**.  
> However, because ground-truth labelled region masks were not evaluated in Phase 8.1, the system does **NOT claim robust semantic isolation**. Fully validated semantic zoning requires future benchmark validation with polygon-annotated ground truth.

---

## 10. DIMENSION 7: BINARIZATION FIDELITY, STROKE FRAGMENTATION & COALESCENCE

Topological connectivity of strokes dictates downstream segmentation:
- **Stroke Fragmentation:** Breaks continuous strokes into detached fragments, causing recognizers to misinterpret broken glyphs (e.g. broken 'd' as 'c' + 'l').
- **Stroke Coalescence:** Bridges adjacent characters into single continuous blobs, disabling character and word tokenization.

These metrics were captured as descriptive topological properties rather than definitive rejection gates.

---

## 11. EMPIRICAL EVIDENCE: PROVING `CONTINUE != OCR_READY`

Phase 8.1 conducted targeted experiments proving that documents certified as `CONTINUE` by Phase 7 can fail OCR readiness:

```
+-------------------------------------------------------------------------------------------------------------------------------+
|                                              CONTINUE != OCR_READY PROOF MATRIX                                                |
+------------------------------------+----------------+------------------+------------------------+-----------------------------+
| Test Scenario                      | Phase 5 QA     | Phase 7 Decision | Provisional Readiness  | Identified Readiness Blocker|
+------------------------------------+----------------+------------------+------------------------+-----------------------------+
| Pristine Document Rotated 90° CW   | GOOD           | CONTINUE         | CONDITIONALLY_READY    | ORIENTATION_ROTATED         |
| Pristine Document Inverted 180°    | GOOD           | CONTINUE         | CONDITIONALLY_READY    | ORIENTATION_ROTATED         |
| Severe Line Entanglement Script    | GOOD           | CONTINUE         | NOT_READY              | LINE_COLLISION_ENTANGLEMENT |
| Ruled Sheet with Heavy Gridlines   | GOOD           | CONTINUE         | CONDITIONALLY_READY    | RULED_LINE_INTERFERENCE     |
| Real Student Script (Small Scale)  | ACCEPTABLE     | CONTINUE         | CONDITIONALLY_READY    | MICRO_HANDWRITING           |
+------------------------------------+----------------+------------------+------------------------+-----------------------------+
```

This empirically validates that **Document Quality** (intake usability) and **OCR Readiness** (recognition usability) are orthogonal operational vectors.

---

## 12. CONTROLLED ORIENTATION EXPERIMENT RESULTS

The 4-way orthogonal reading orientation detector was evaluated across all four quadrants on `answer_sheet_2.png`:

```
+----------------------------------------------------------------------------------------------------+
|                                    4-WAY ORIENTATION SWEEP RESULTS                                 |
+----------------------+--------------------+--------------------+------------+----------------------+
| Injected Orientation | Detected Axis      | Polarity Ratio     | Confidence | Detected Orientation |
+----------------------+--------------------+--------------------+------------+----------------------+
| **0° (Upright)**     | Horizontal (3.73)  | Top/Bot = 1.30     | 0.90       | UPRIGHT_0    [OBS]   |
| **90° (Rotated CW)** | Vertical   (0.27)  | Right/Left = 1.30  | 0.90       | ROTATED_90_CW [OBS]  |
| **180° (Inverted)**  | Horizontal (3.73)  | Top/Bot = 0.77     | 0.86       | ROTATED_180  [OBS]   |
| **270° (Rot CCW)**   | Vertical   (0.27)  | Right/Left = 0.77  | 0.86       | ROTATED_270_CCW[OBS] |
+----------------------+--------------------+--------------------+------------+----------------------+
```
*Note: 100% accuracy was observed on these specific evaluated calibration cases. As detailed in Section 4, this does not establish universal orientation reliability.*

---

## 13. DATASET SEGMENTATION & BENCHMARK LIMITATIONS

To maintain scientific rigor, the evidence evaluated in Phase 8.1 is explicitly separated into four distinct categories and must **not** be treated as a single homogeneous benchmark:

| Evidence Category | Source & Description | Scope & Purpose | Limitations |
|---|---|---|---|
| **1. Full-Page Exam-Sheet Evidence** | `answer_sheet_2.png`, full-resolution student submission. | Holistic page evaluation, orientation sweeps, line layout. | Small sample size; unruled high-contrast paper. |
| **2. Project Calibration Images** | `answer_sheet_3.jpg` (shadow remediated via Phase 6). | Cross-phase pipeline integration test (Phase 5 $\rightarrow$ 6 $\rightarrow$ 7 $\rightarrow$ 8). | Corrected lighting; represents controlled lab conditions. |
| **3. 224x224 Handwriting Crops** | 15 cropped images from `dataset/AnswerScripts/Handwriting224`. | Character scale, stroke width, and ruled line observation. | Cropped sub-regions lack full-page headers and margins; cannot evaluate global orientation. |
| **4. Controlled Synthetic Stress Cases** | Artificially compressed line spacing and downscaled synthetic crops. | Isolating specific failure modes (touching lines, extreme scale reduction). | Synthetic degradations do not fully reflect natural student handwriting variation. |

---

## 14. LACK OF DIRECT OCR CER/WER CORRELATION (EXPLICIT BOUNDARY)

Phase 8.1 is an **evidence investigation** phase. In accordance with strict scope constraints, downstream OCR engines (e.g. Tesseract, TrOCR, CRNN) were **not** executed, and Character Error Rates (CER) or Word Error Rates (WER) were **not** measured.

Therefore:
- The signals investigated in Phase 8.1 are **observed image characteristics** and **hypothesized predictors** of recognition difficulty.
- They are **not yet statistically validated predictors of OCR error rates**.
- Quantitative correlation between PVR, line collision ratio, character height, and empirical CER/WER remains an explicit hypothesis requiring validation in Phase 8.2 and Phase 11.

---

## 15. PROVISIONAL OCR/HTR READINESS TAXONOMY (ARCHITECTURAL HYPOTHESIS)

Phase 8.1 establishes the following 4-state readiness taxonomy as an **investigation-level architectural hypothesis**:

```
+-----------------------------------------------------------------------------------------------------+
|                              PROVISIONAL OCR/HTR READINESS TAXONOMY                                 |
+-------------------------+---------------------------------------------------------------------------+
| Readiness State         | Architectural Intent & Provisional Meaning                                |
+-------------------------+---------------------------------------------------------------------------+
| **`OCR_READY`**         | Printed or highly structured text, upright (0°), well-separated baselines.|
|                         | Immediate OCR pipeline candidate.                                         |
+-------------------------+---------------------------------------------------------------------------+
| **`HTR_READY`**         | Upright handwritten script with separable baselines and legible scale.    |
|                         | Immediate line-level HTR candidate.                                       |
+-------------------------+---------------------------------------------------------------------------+
| **`CONDITIONALLY_READY`**| Document is physically usable but requires automated digital pre-OCR      |
|                         | normalization: orthogonal rotation, line deskew, candidate line           |
|                         | suppression, or scale normalization.                                      |
+-------------------------+---------------------------------------------------------------------------+
| **`NOT_READY`**         | Severe topological line entanglement, micro-scale illegibility, or        |
|                         | unresolvable layout topology. Candidate for human review / transcription. |
+-------------------------+---------------------------------------------------------------------------+
```

> [!WARNING]
> **PROVISIONAL DEFINITION NOTICE:**  
> The definitions and boundaries of these states are strictly **provisional and investigation-level**.  
> In particular, numerical rules such as:
> - $\text{PVR} \ge 2.5 \implies \text{OCR\_READY}$
> - $\text{PVR} \ge 1.8 \text{ and } R_{\text{collision}} < 10\% \implies \text{HTR\_READY}$
> - $\text{scale} \ge 12\text{ px} \implies \text{READY}$
> - $\text{scale} < 6\text{ px} \implies \text{NOT\_READY}$  
> 
> **are NOT frozen.** These thresholds require real-world empirical calibration and downstream OCR/HTR error-rate correlation in Phase 11.

---

## 16. PRE-OCR NORMALIZATION: PROVISIONAL ARCHITECTURAL HYPOTHESES

For future pipeline design, the following pre-OCR normalization operations are identified as candidate hypotheses:
1. **Orthogonal De-Rotation Hypothesis:** Evaluates rotating documents identified as $90^\circ, 180^\circ,$ or $270^\circ$ into upright orientation before OCR.
2. **Fine Baseline Deskew Hypothesis:** Evaluates correcting small residual page/line skew ($1^\circ$–$5^\circ$) via Radon or Hough projections.
3. **Scale Normalization Hypothesis:** Evaluates whether upscaling line patches containing micro-scale handwriting improves neural HTR tokenization.
4. **Ruled-Line Suppression Hypothesis:** Evaluates whether directional morphological line subtraction improves recognition without damaging genuine character strokes.

---

## 17. SAFETY CONSTRAINTS & NON-HALLUCINATION GUARANTEES

1. **No Glyph Hallucination:** The readiness assessment only inspects topological and geometric signal evidence; it never attempts to guess or infer unreadable characters.
2. **Blocker Transparency:** Any non-ready verdict must provide an explicit list of detected topological blockers.
3. **Safe-State Immutability:** OCR readiness telemetry operates on frozen image buffers without mutating earlier pipeline representations.

---

## 18. PHASE 8.1 AUDIT STATUS

```
+-------------------------------------------------------------------------------------+
|                                PHASE 8.1 AUDIT STATUS                               |
+------------------------------------------+------------------------------------------+
| Architectural Dimension                  | Status                                   |
+------------------------------------------+------------------------------------------+
| Pipeline Architecture Direction          | APPROVED                                 |
| Evidence Signals (Orientation, PVR, etc.)| APPROVED FOR FURTHER VALIDATION          |
| Numerical Thresholds                     | PROVISIONAL                              |
| Operator Choices                         | PROVISIONAL                              |
| OCR/HTR Engine Selection                 | NOT FROZEN                               |
| Production Readiness Classifier          | NOT YET FROZEN                           |
| Phase 8.2 Implementation                 | NOT STARTED                              |
+------------------------------------------+------------------------------------------+
```

Phase 8.1 is an **investigation milestone**, not a production OCR/HTR readiness gate.

---

**STOP: Phase 8.1 audit corrections complete. Phase 8.2 has NOT been started.**
