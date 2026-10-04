# PHASE 8.3 — OCR/HTR CORRELATION EVIDENCE INVESTIGATION REPORT (POST-AUDIT CALIBRATED EDITION)
**Project:** `AI-EVAL-OpenCV` (Automated Exam Evaluation Pipeline)  
**Milestone:** Phase 8.3 — OCR/HTR Correlation Evidence Investigation (Audited & Calibrated)  
**Author:** Antigravity AI  
**Date:** October 2026  
**Status:** **INVESTIGATION COMPLETE — CONTROLLED EMPIRICAL EVIDENCE OBTAINED; GENERALIZATION REMAINS LIMITED**

---

> [!IMPORTANT]
> **INVESTIGATION MILESTONE DECLARATION**  
> Phase 8.3 is an **empirical investigation and evidence-gathering phase**, NOT a final production OCR/HTR integration or frozen classifier.  
> In strict accordance with pipeline governance:
> 1. Phases 2 through 7 remain frozen and untouched.
> 2. Phase 8.2 production preparation contracts and engine remain frozen and untouched.
> 3. No OCR/HTR models were trained or fine-tuned.
> 4. No final `OCR_READY` classifier or frozen thresholds were implemented.
> 5. Downstream transcription evaluations were conducted using a controlled, offline neural OCR capability (native Windows Media OCR Engine via WinRT).
> 6. All conclusions distinguish between controlled empirical measurements and architectural hypotheses.

---

## 1. EXECUTIVE SUMMARY & RESEARCH OBJECTIVE

### 1.1 The Primary Question
Phase 8.1 established theoretical readiness hypotheses, and Phase 8.2 built a controlled image preparation engine that extracts topological telemetry and generates candidate representations. 

The primary objective of **Phase 8.3** is to determine empirically:

$$\mathbf{How\ do\ the\ image\ representations\ and\ telemetry\ produced\ by\ Phase\ 8.2\ relate\ to\ actual\ downstream\ OCR/HTR\ recognition\ performance?}$$

Prior to freezing downstream input specifications, Phase 8.3 subjected Phase 8.2 outputs to systematic empirical evaluation against an offline neural recognition engine without assuming:
- that enhanced grayscale is always best,
- that binary representations are useful for OCR, or
- that an OCR engine's confidence score represents ground truth.

---

## 2. EVIDENCE STRENGTH CLASSIFICATION

To prevent overclaiming and clearly separate measured evidence from architectural hypotheses, all findings in this investigation are categorized by evidence strength:

| Finding / Topic | Evidence Strength Level | Scope & Boundary of Finding |
| :--- | :--- | :--- |
| **Sideways orientation ($90^\circ, 270^\circ$) harms tested OCR** | **STRONG CONTROLLED EVIDENCE** | 100% recognition failure observed on sideways controlled text in evaluated engine. |
| **Phase 8.2 recovers tested cardinal rotations** | **STRONG CONTROLLED EVIDENCE** | De-rotation restored baseline CER on evaluated controlled benchmark images. |
| **$R_1$ outperformed $R_2$ in tested benchmark** | **MODERATE / LIMITED EVIDENCE** | True for the tested synthetic benchmark and Windows Media OCR; not universal. |
| **Peripheral background distorts orientation heuristic** | **STRONG EMPIRICAL EVIDENCE** | Observed directly on uncropped `answer_sheet_2.png` capture. |
| **Character scale affects recognition** | **EXPLORATORY EVIDENCE** | Tested 9px condition failed; tested $\ge 12\text{px}$ succeeded in evaluated setup. |
| **9px / 12px universal scale threshold** | **NOT SUPPORTED** | Evidence indicates a failure region in tested setup, not a universal threshold. |
| **Telemetry variables predict OCR readiness** | **INSUFFICIENT EVIDENCE** | Pearson and Spearman coefficients disagree; sample is narrow ($N=11$). |
| **HTR benefit from deskew** | **HYPOTHESIS** | Not tested on HTR models; remains an architectural hypothesis for line slicers. |
| **OCR internal rotated bounding-box mechanism** | **NOT SUPPORTED / SPECULATIVE** | Engine internal architecture is unverified; engine-specific tolerance observed. |

---

## 3. SEPARATION OF BENCHMARK COHORTS

To maintain rigorous experimental integrity, results from different datasets and modalities are strictly separated:

1. **Controlled Synthetic Benchmark:** Standardized text canvases with mathematically known transformations (rotations, skews, scale variations) and character-level ground truth.
2. **Real Exam-Sheet Observations:** Actual project images (`answer_sheet_2.png`) evaluated for qualitative/semi-quantitative behavior under uncropped physical conditions.
3. **Handwriting Dataset (HTR):** Not evaluated in Phase 8.3. No handwriting corpus with verified character-level transcription ground truth was processed through an HTR model in this milestone.
4. **Qualitative Observations:** Unverified document edge-cases without verified transcription ground truth.

---

## 4. EXPERIMENT 1: MULTI-REPRESENTATION BENCHMARK ($R_0$ vs $R_1$ vs $R_2$ vs $R_3$)

### 4.1 Controlled Synthetic Benchmark Results
A standardized document block containing multi-line printed examination text and horizontal ruling lines was evaluated across four representations:
- **$R_0$ — Raw Grayscale:** Minimally processed single-channel conversion (`cv2.cvtColor(BGR2GRAY)`).
- **$R_1$ — Prepared Grayscale:** Phase 8.2 normalized, de-rotated, CLAHE-enhanced grayscale.
- **$R_2$ — Binary Derivative:** Phase 8.2 adaptive Gaussian binarized mask (`bundle.ready_bin`), inverted to dark text on light background.
- **$R_3$ — Ruled-Line Handled:** Grayscale with ruling lines suppressed via morphological masking and Telea inpainting.

$$\text{Ground Truth Lines: 4} \quad | \quad \text{Ground Truth Characters: 312} \quad | \quad \text{Ground Truth Words: 39}$$

```text
Controlled Synthetic Benchmark Evaluation:
  R0_Raw             -> CER: 0.0000 | WER: 0.0000 | Lines: 4 | Latency: 78.1ms
  R1_Prepared_Gray   -> CER: 0.0000 | WER: 0.0000 | Lines: 4 | Latency: 42.0ms
  R2_Binary          -> CER: 0.0187 | WER: 0.1282 | Lines: 4 | Latency: 45.9ms
  R3_Ruled_Handled   -> CER: 0.0000 | WER: 0.0000 | Lines: 4 | Latency: 56.6ms
```

![Figure 1: Representation CER/WER Comparison](file:///C:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase8/output/phase8_3_representation_cer_wer_comparison.png)

#### Specific Error Pattern in $R_2$ (Binary)
- **Ground Truth:** `"learning"` $\longrightarrow$ **$R_2$ Hypothesis:** `"leaming"` (character substitution `'rn'` $\to$ `'m'`).
- **Ground Truth:** `"representations."` $\longrightarrow$ **$R_2$ Hypothesis:** `"repr..."` (terminal punctuation fragmentation).
- **Outcome:** 5 out of 39 words corrupted ($\text{WER} = 12.82\%$).

#### Evidence-Calibrated Interpretation
Within the evaluated controlled benchmark and Windows Media Neural OCR engine, $R_1$ Prepared Grayscale produced lower recognition error than $R_2$ Binary. $R_2$ showed measurable degradation in this experiment. These results do not establish a universal rule for all OCR/HTR engines or document types.

$R_2$ may remain useful as an auxiliary representation for structural analysis, connected components, projection profiling, or other non-recognition tasks. Its suitability as an OCR input remains engine- and corpus-dependent.

$R_1$ is **not frozen as a universal downstream standard**, but remains a viable candidate representation for future testing.

---

### 4.2 Real Exam-Sheet Observation (`answer_sheet_2.png`)

When evaluated on an uncropped phone capture of a real exam answer sheet (`images/answer_sheet_2.png`), the following recognition behavior was observed:

```text
Real Exam-Sheet Observation (answer_sheet_2.png):
  R0_Raw             -> Detected Lines: 34 | Total Chars:  916 | Header CER: 0.4453 | Latency: 233.8ms
  R1_Prepared_Gray   -> Detected Lines: 11 | Total Chars:   22 | Header CER: 0.8828 | Latency: 112.8ms
  R2_Binary          -> Detected Lines:  0 | Total Chars:    0 | Header CER: 1.0000 | Latency: 148.8ms
  R3_Ruled_Handled   -> Detected Lines: 12 | Total Chars:   24 | Header CER: 0.8672 | Latency: 110.9ms
```

#### Investigation of Orientation Estimator Sensitivity
Investigation of Phase 8.2 telemetry revealed:
- `detected_orientation = ReadingOrientation.ROTATED_270_CCW`
- `detected_skew = -2.25 deg`

The experiment exposed a failure mode in which peripheral/background content influenced the orientation estimator. Because `answer_sheet_2.png` is an uncropped capture containing dark background margins, the 1D projection profile variance was higher along the vertical axis of the canvas than the horizontal axis. This caused Phase 8.2 to misdiagnose the upright sheet as $270^\circ$ CCW and rotate it $+90^\circ$ clockwise, turning an already upright document sideways.

Once rotated sideways by Phase 8.2, downstream OCR recognition collapsed from 34 detected lines down to 11 lines, and binary derivative $R_2$ detected 0 lines.

This indicates that orientation evidence should be evaluated on an appropriate document region and should be protected by additional consistency checks before production deployment. In accordance with scope governance, **no Phase 8.2 code was altered to mask this finding.**

---

## 5. EXPERIMENT 2: READING ORIENTATION DEGRADATION & RECOVERY

A clean text canvas was rotated to the four cardinal angles ($0^\circ, 90^\circ, 180^\circ, 270^\circ$) under controlled conditions:

```text
Controlled Cardinal Orientation Sweep:
  0° UPRIGHT         -> Uncorrected CER: 0.1371 (Lines: 5) | Phase 8.2 Corrected CER: 0.1371 (Lines: 5)
  90° ROTATED CW     -> Uncorrected CER: 1.0000 (Lines: 0) | Phase 8.2 Corrected CER: 0.1371 (Lines: 5)
  180° INVERTED      -> Uncorrected CER: 0.8094 (Lines: 5) | Phase 8.2 Corrected CER: 0.1371 (Lines: 5)
  270° ROTATED CCW   -> Uncorrected CER: 1.0000 (Lines: 0) | Phase 8.2 Corrected CER: 0.1371 (Lines: 5)
```

![Figure 2: Reading Orientation Degradation Profile](file:///C:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase8/output/phase8_3_orientation_degradation_profile.png)

### 5.1 Evidence-Calibrated Interpretation
The evaluated OCR engine was highly sensitive to sideways orientation, while Phase 8.2 successfully recovered the tested cardinal rotations on the evaluated controlled inputs.
- Sideways rotations ($90^\circ, 270^\circ$) prevented line extraction entirely (0 lines detected).
- Inverted text ($180^\circ$) allowed horizontal line detection but produced severe glyph misinterpretation ($\text{CER} = 0.8094$).
- On these isolated, clean canvases, Phase 8.2 correctly identified each rotation and restored the upright baseline ($\text{CER} = 0.1371$).

---

## 6. EXPERIMENT 3: RESIDUAL BASELINE SKEW SENSITIVITY

Document sheets were tilted through the residual skew range $[-3.5^\circ, +3.5^\circ]$ in steps of $1.0^\circ\text{--}1.5^\circ$:

```text
Residual Baseline Skew Sweep:
  Tilt: -3.5° -> Uncorrected CER: 0.0866 | Phase 8.2 Deskewed CER: 0.0866 (Detected: -3.50°)
  Tilt: -2.0° -> Uncorrected CER: 0.0866 | Phase 8.2 Deskewed CER: 0.0866 (Detected: -2.00°)
  Tilt: -1.0° -> Uncorrected CER: 0.0866 | Phase 8.2 Deskewed CER: 0.0866 (Detected: -1.00°)
  Tilt: +0.0° -> Uncorrected CER: 0.0866 | Phase 8.2 Deskewed CER: 0.0866 (Detected: -0.00°)
  Tilt: +1.0° -> Uncorrected CER: 0.0866 | Phase 8.2 Deskewed CER: 0.0866 (Detected: +1.00°)
  Tilt: +2.0° -> Uncorrected CER: 0.0866 | Phase 8.2 Deskewed CER: 0.0866 (Detected: +2.00°)
  Tilt: +3.5° -> Uncorrected CER: 0.0866 | Phase 8.2 Deskewed CER: 0.0866 (Detected: +3.50°)
```

![Figure 3: Skew Angle vs OCR Error](file:///C:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase8/output/phase8_3_skew_angle_vs_ocr_error.png)

### 6.1 Evidence-Calibrated Interpretation
Within the evaluated Windows Media Neural OCR experiment, the tested skew range did not produce a measurable CER difference between the uncorrected and Phase 8.2 deskewed representations ($\text{CER} = 0.0866$ constant). 

This observation is engine-specific and does not establish a universal OCR skew tolerance.

### 6.2 Separation of OCR Evidence from HTR Hypotheses
While the evaluated OCR engine exhibited tolerance across $\pm 3.5^\circ$, it is hypothesized that line-based HTR models (which perform horizontal line striping or 1D sequence decoding) may be more sensitive to tilted baselines. However, **HTR implications remain a hypothesis requiring direct HTR evaluation**, as no HTR model was benchmarked in Phase 8.3.

---

## 7. EXPERIMENT 4: TELEMETRY SIGNALS & SCALE EXPERIMENT

### 7.1 Character Scale Observations
Canvases with varying font scales were evaluated to measure the relationship between median character height ($x$-height) and downstream OCR performance:

```text
Character Scale Sweep:
  Font Scale 0.35 (Median Height:  9px) -> CER: 1.0000 | Detected Lines: 0
  Font Scale 0.45 (Median Height: 12px) -> CER: 0.0000 | Detected Lines: 2
  Font Scale 0.55 (Median Height: 13px) -> CER: 0.0000 | Detected Lines: 2
  Font Scale 0.70 (Median Height: 14px) -> CER: 0.0000 | Detected Lines: 2
  Font Scale 0.85 (Median Height: 15px) -> CER: 0.0000 | Detected Lines: 2
  Font Scale 1.10 (Median Height: 18px) -> CER: 0.0909 | Detected Lines: 2
```

![Figure 4: Scale Cliff and Telemetry Correlation](file:///C:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase8/output/phase8_3_scale_cliff_and_telemetry_correlation.png)

#### Calibrated Interpretation
In the evaluated controlled scale experiment, the tested 9px condition produced complete recognition failure while the tested $\ge 12\text{px}$ conditions produced successful recognition. This is evidence of a scale-dependent failure region in the tested setup, not proof of a universal 9px or 12px threshold.

The observed results suggest a possible nonlinear relationship between character scale and recognition performance in the tested setup. The underlying mechanism and generality remain unverified.

**No 9px or 12px production thresholds are frozen.**

---

### 7.2 Correlation Stability & Statistical Limitations

The statistical association between Phase 8.2 telemetry variables and downstream CER was evaluated across a cohort of $N=11$ trials (6 scale variations and 5 line-gap variations):

$$\text{Total Sample Size } N = 11 \quad | \quad \text{Valid CER Values: } 11 \quad | \quad \text{Excluded Cases: } 0$$

```text
Statistical Correlation with Downstream Character Error Rate (CER):
  1. Median Character Height (px):  Pearson r = -0.4899 | Spearman rho = -0.0727
  2. Line Collision Ratio:          Pearson r = -0.5014 | Spearman rho = +0.0727
  3. Peak-to-Valley Ratio (PVR):    Pearson r = +0.3536 | Spearman rho = -0.2909
```

#### Correlation Stability Analysis
The observed Pearson coefficients suggest possible linear association in the evaluated sample, but the corresponding Spearman coefficients do not consistently support a monotonic relationship. Therefore the present evidence is **exploratory and insufficient for threshold derivation or production prediction.**

Consequently:
- These telemetry variables must **NOT** be described as "predictive."
- They must **NOT** be treated as validated readiness indicators.
- No production thresholds or readiness classifiers may be derived from them.

#### Outlier and Distribution Warning
In each evaluated variable where Pearson ($r$) and Spearman ($\rho$) disagree materially:
1. **Character Height:** Pearson $r = -0.4899$ vs Spearman $\rho = -0.0727$.
2. **Line Collision Ratio:** Pearson $r = -0.5014$ vs Spearman $\rho = +0.0727$.
3. **Peak-to-Valley Ratio:** Pearson $r = +0.3536$ vs Spearman $\rho = -0.2909$.

These discrepancies indicate that:
- outliers (e.g. total failure at 9px dominating linear variance),
- non-linear step-like relationships,
- narrow sample ranges, and
- repeated synthetic conditions
may strongly influence the calculated coefficients. The small sample size ($N=11$) provides **exploratory evidence only**, and no statistical significance is claimed or implied.

---

## 8. ARCHITECTURAL FINDINGS / FUTURE CONSIDERATIONS

In accordance with Phase 8.3 governance, the following points represent observations and future design considerations, **not frozen production contracts**:

1. **Candidate Representation:** Prepared grayscale showed favorable recognition behavior in the evaluated benchmark and should remain a candidate downstream representation.
2. **Auxiliary Role for Binary Representations:** Binary representations should remain available as auxiliary structural representations because their recognition behavior was worse in the evaluated benchmark.
3. **Orientation Region Gating:** Orientation estimation should operate on an appropriate document region and should use additional consistency evidence before any future production freeze.
4. **Deskew Consideration:** Phase 8.2 deskew remains a candidate preprocessing step, but its downstream benefit requires broader OCR/HTR validation.

---

## 9. FINAL MILESTONE STATUS

```text
Phase 8.3 Investigation
→ COMPLETE

Controlled OCR evidence
→ ESTABLISHED FOR EVALUATED CASES

OCR/HTR generalization
→ LIMITED

Telemetry correlation
→ EXPLORATORY / NOT SUFFICIENT FOR PRODUCTION PREDICTION

Character-scale thresholds
→ NOT FROZEN

Representation standard
→ NOT FROZEN

Production OCR/HTR classifier
→ NOT FROZEN

OCR/HTR engine integration
→ NOT IMPLEMENTED

Thresholds
→ PROVISIONAL

Phase 8.4
→ NOT STARTED
```
