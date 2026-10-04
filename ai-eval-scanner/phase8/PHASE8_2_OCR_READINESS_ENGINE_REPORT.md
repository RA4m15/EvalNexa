# PHASE 8.2 — OCR/HTR PREPROCESSING & READINESS PREPARATION LAYER REPORT
**Project:** `AI-EVAL-OpenCV` (Automated Exam Evaluation Pipeline)  
**Milestone:** Phase 8.2 — Production Preprocessing & Readiness Preparation Layer (Audited Edition)  
**Author:** Antigravity AI  
**Date:** October 2026  
**Status:** **IMPLEMENTATION VALIDATED — REAL-WORLD CALIBRATION PENDING (CONTROLLED SUITE: 9/9 PASS)**

---

> [!IMPORTANT]
> **PHASE 8.2 SCOPE & ARCHITECTURAL CLARIFICATION**  
> Phase 8.2 implements the controlled preprocessing and readiness preparation layer between **Phase 7 `CONTINUE` intake decisions** and downstream OCR/HTR recognition subsystems.  
> 
> **THIS PHASE IS NOT AN OCR/HTR ENGINE OR FINAL READINESS GATE.**  
> - Phase 8.2 **prepares** normalized image representations and extracts quantitative telemetry evidence.  
> - Phase 8.2 exposes **provisional / investigation-level observations** (`ProvisionalReadinessObservation`).  
> - Phase 8.2 **MUST NOT** make a final production `OCR_READY`, `HTR_READY`, or `NOT_READY` gating decision.  
> - **Final OCR/HTR readiness classification remains explicitly NOT FROZEN** until downstream OCR/HTR error-rate correlation and Phase 11 multi-institution calibration.

---

## 1. EXECUTIVE SUMMARY & OBJECTIVE

Following the completion of **Phase 7 (Production Rescan Decision Engine)**, documents meeting physical quality criteria produce a `CONTINUE` routing verdict. However, as proven in Phase 8.1:

$$\mathbf{CONTINUE \ne OCR\_READY}$$

A document can be physically sharp, complete, and evenly illuminated, yet arrive rotated sideways ($90^\circ, 270^\circ$), upside down ($180^\circ$), with residual baseline tilt ($\pm 3^\circ$), or overlaid with ruled notebook lines.

**Phase 8.2** provides the controlled layer that bridges this gap:
1. It ingests verified safe states from Phase 7 without mutating master buffers.
2. It detects 4-way reading orientation and applies lossless orthogonal de-rotation when evidence is confident.
3. When orientation is ambiguous (e.g. symmetric layouts, missing headers, sparse text), it **NEVER forces a speculative rotation**, flagging `ORIENTATION_AMBIGUOUS` and preserving original canvas alignment.
4. It detects sub-orthogonal line tilt and applies fine rotational deskew within a deadband.
5. It detects ruled notebook lines and generates an auxiliary mask (`rule_lines_mask`) without destructively eroding handwriting strokes.
6. It packages the results into an immutable multi-representation bundle (`ready_gray`, `ready_bin`, `ready_bgr`, and preserved `raw_rectified_bgr`), accompanied by comprehensive line topology, character scale, warnings, and provenance telemetry.

---

## 2. PIPELINE ARCHITECTURE & PLACEMENT

```text
Camera / Sensor Frame
          ↓
Phase 2: Page Region Candidate Detection
          ↓
Phase 3: Perspective Rectification & Alignment
          ↓
Phase 4: Enhancement Baseline
          ↓
Phase 5: Smart Quality Assessment (Tier 1 Veto, Tier 2 Metrics)
          ↓
Phase 6: Intelligent Auto-Correction Engine (Safe-State Lifecycle)
          ↓
Phase 7: Rescan Decision Engine (CONTINUE | HUMAN_REVIEW | RESCAN_REQUIRED)
          ↓ (CONTINUE)
Phase 8.2: Preprocessing & Readiness Preparation Layer  <-- [PHASE 8.2 CONTROLLED LAYER]
          ↓ (PreprocessedImageBundle + TextTopologyMetrics + Warnings)
Future Downstream Text-Line Extraction & Neural HTR Engines (Phase 8.3+ / External)
          ↓
Future Rubric AI Answer Evaluation
```

---

## 3. STRICT NON-NEGOTIABLE GUARANTEES OBSERVED

1. **Frozen Phases Untouched:** Zero changes to `phase2/`, `phase3/`, `phase4/`, `phase5/`, `phase6/`, or `phase7/`. All new code resides strictly in `phase8/`.
2. **Buffer Immutability & Safe Isolation:** The upstream `raw_rectified_bgr` master buffer is never mutated. All output bundle arrays (`ready_gray`, `ready_bin`, `ready_bgr`, `rule_lines_mask`, `raw_rectified_bgr`) enforce `flags.writeable = False`.
3. **Ambiguity Protection:** If reading orientation cannot be determined with high confidence, the engine **NEVER forces a speculative rotation**. It flags `ORIENTATION_AMBIGUOUS` and leaves the canvas unaltered.
4. **Scale & Geometry Agnostic:** No A4 aspect ratio assumptions; no portrait-only constraints. Handles landscape documents, square crops, and arbitrary resolutions natively.
5. **Non-Destructive Ruled-Line Representation:** Ruled notebook lines are detected into an auxiliary mask (`rule_lines_mask`) without destructively subtracting character strokes from `ready_gray`.
6. **No Final Decision Gating:** Phase 8.2 delivers prepared representations and telemetry. It does not reject documents or act as an intake gate; final OCR/HTR classification is deferred to downstream models.
7. **Provisional Calibration Baselines:** All numerical thresholds in `ReadinessPreparationConfig` are explicitly documented as calibration baselines, not scientifically frozen values.

---

## 4. PRODUCTION DATA CONTRACTS (`phase8/ocr_readiness_contracts.py`)

### 4.1 Semantic Enums

- **`ReadingOrientation`**:
  - `UPRIGHT_0`: Standard reading orientation ($0^\circ$).
  - `ROTATED_90_CW`: Page rotated $90^\circ$ clockwise (text reads top-to-bottom).
  - `ROTATED_180_INVERTED`: Upside down ($180^\circ$).
  - `ROTATED_270_CCW`: Page rotated $270^\circ$ clockwise / $90^\circ$ counter-clockwise.
  - `AMBIGUOUS`: Insufficient or conflicting evidence; rotation unsafe.

- **`ProvisionalReadinessObservation`** (`INVESTIGATION_ONLY / PROVISIONAL / NOT A FINAL DECISION`):
  - `PROVISIONAL_OCR_CANDIDATE`: High-contrast printed text observation.
  - `PROVISIONAL_HTR_CANDIDATE`: Clean handwritten script observation with separable baselines.
  - `NORMALIZATION_RECOMMENDED`: Pre-OCR digital adjustments indicated (de-rotation / deskew).
  - `COMPLEX_LAYOUT_OBSERVED`: Layout complexity noted (inter-line collisions, ruled lines, micro-scale text).
  - `ORIENTATION_AMBIGUOUS`: Reading orientation uncertain; canvas left unrotated.
  - `UPSTREAM_RESCAN_REQUIRED`: Document received a fatal rescan veto from the upstream Phase 7 gate.

- **`OCRReadinessVerdict`**:
  - Retained strictly as an exploratory backward-compatibility alias for exploratory test suites.
  - Explicitly marked: `INVESTIGATION_ONLY / PROVISIONAL / NOT A FINAL DECISION`.

- **`ReadinessTopologicalDefect`**: `ORIENTATION_ROTATED`, `ORIENTATION_AMBIGUOUS`, `LINE_COLLISION_ENTANGLEMENT`, `POOR_LINE_SEPARATION`, `MICRO_SCALE_TEXT`, `MACRO_SCALE_TEXT`, `RULED_LINE_INTERFERENCE`, `EXCESSIVE_STROKE_FRAGMENTATION`, `STROKE_COALESCENCE`, `SPARSE_OR_BLANK_CONTENT`.

- **`ReadinessNormalizationAction`**: `NO_OP`, `DE_ROTATE_90_CCW`, `DE_ROTATE_180`, `DE_ROTATE_90_CW`, `DESKEW_FINE`, `RULED_LINE_MASK_GENERATED`, `SCALE_NORMALIZATION_CANDIDATE`.

### 4.2 Output Data Contracts

```python
@dataclass(frozen=True)
class PreprocessedImageBundle:
    ready_gray: np.ndarray          # Normalized, de-rotated, deskewed grayscale (read-only)
    ready_bin: np.ndarray           # Adaptive binarization for line segmentation (read-only)
    ready_bgr: Optional[np.ndarray] # Normalized 3-channel color image (read-only)
    raw_rectified_bgr: np.ndarray   # Frozen master buffer from Phase 3/6 (read-only)
    rule_lines_mask: Optional[np.ndarray] = None # Detected ruling lines (read-only)

@dataclass(frozen=True)
class TextTopologyMetrics:
    # All values are CALIBRATION BASELINES — NOT SCIENTIFICALLY FROZEN
    axis_anisotropy_ratio: float
    header_polarity_ratio: float
    orientation_confidence: float
    detected_line_count: int
    peak_to_valley_ratio: float
    median_line_pitch_px: float
    line_collision_ratio: float
    detected_skew_angle_deg: float
    median_char_height_px: float
    char_height_p25_px: float
    char_height_p75_px: float
    estimated_stroke_width_px: float
    ruled_line_pixel_fraction: float
    ruled_line_stroke_collision_ratio: float
    stroke_fragmentation_ratio: float
    stroke_coalescence_ratio: float
    component_count: int

@dataclass(frozen=True)
class OCRReadinessPreparationResult:
    document_id: str
    verdict: OCRReadinessVerdict                 # INVESTIGATION_ONLY / PROVISIONAL
    provisional_observation: ProvisionalReadinessObservation # Exploratory telemetry categorization
    detected_orientation: ReadingOrientation
    applied_rotation_deg: int
    detected_skew_angle_deg: float
    applied_deskew_angle_deg: float
    is_orientation_ambiguous: bool
    applied_actions: List[ReadinessNormalizationAction]
    blockers: List[ReadinessTopologicalDefect]
    warnings: List[str]                          # Non-vetoing layout warnings
    unresolved_ambiguities: List[str]            # Flags for downstream attention
    recommended_downstream_actions: List[str]
    image_bundle: PreprocessedImageBundle        # Prepared representation bundle
    metrics: TextTopologyMetrics                 # Quantitative topology telemetry
    latency_ms: float
    provenance_notes: List[str]                  # Audit trail
```

---

## 5. DISTINCTION: PREPROCESSING STATE VS FINAL OCR DECISION

A critical conceptual clarification mandated by audit:

| Dimension | Preprocessing & Evidence State (Phase 8.2) | Final OCR/HTR Readiness Gate (Future / Phase 11) |
|---|---|---|
| **Operational Role** | Prepares normalized representations, extracts telemetry, flags ambiguities. | Decides whether to route to specific OCR engines, HTR models, or human transcription. |
| **Pipeline Action** | **Always delivers the prepared image bundle** (unless Phase 7 issued `RESCAN_REQUIRED`). | May halt automated processing, invoke fallback models, or assign confidence scores. |
| **Observation Meaning** | `COMPLEX_LAYOUT_OBSERVED` flags that line collisions or ruling lines exist. | Determines whether a specific OCR engine can parse the lines without unacceptable CER/WER. |
| **Status in Pipeline** | **IMPLEMENTATION VALIDATED** | **NOT YET FROZEN (Requires Real-World Correlation)** |

### Clarification on End-to-End Test Observation (`Phase 7 CONTINUE → COMPLEX_LAYOUT_OBSERVED`)
In Test 8, `answer_sheet_2.png` passed Phase 7 with `CONTINUE`. Phase 8.2 processed the image, verified upright orientation ($0^\circ$), detected ruling lines ($2.0\%$ coverage) and inter-line collision ($21.1\%$), and generated `rule_lines_mask`.
- It assigned the exploratory telemetry observation `COMPLEX_LAYOUT_OBSERVED` (formerly `NOT_READY`).
- **This is NOT an intake gate veto or document rejection.**
- The prepared multi-representation bundle (`ready_gray`, `ready_bin`, `ready_bgr`, `rule_lines_mask`) was successfully created, write-protected, and delivered to downstream consumers in $76\text{ ms}$.

---

## 6. PARAMETER AUDIT & OPERATOR BEHAVIOR

### 6.1 Centralized Calibration Parameters (`ReadinessPreparationConfig`)

Every parameter in `ReadinessPreparationConfig` is explicitly marked as a **calibration baseline**, not a scientifically frozen rule:

```python
@dataclass(frozen=True)
class ReadinessPreparationConfig:
    # Orientation discrimination parameters (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    min_axis_anisotropy_for_h: float = 1.30      # Ratio > 1.30 implies horizontal text lines
    max_axis_anisotropy_for_v: float = 0.75      # Ratio < 0.75 implies vertical text lines
    min_polarity_confidence_margin: float = 0.18 # |ratio - 1.0| must exceed this to distinguish polarities
    min_content_variance: float = 5.0            # Below this variance, canvas is considered blank/sparse
    allow_auto_rotation: bool = True             # If True, losslessly de-rotates confident orientations

    # Fine baseline deskew parameters (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    deskew_max_angle_deg: float = 5.0            # Max tilt searched (degrees)
    deskew_angle_step_deg: float = 0.25          # Search step resolution (degrees)
    deskew_deadband_deg: float = 0.40            # Skew below this threshold is not altered
    allow_auto_deskew: bool = True               # If True, deskews canvas if skew exceeds deadband

    # Line topology calibration values (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    pvr_clean_baseline: float = 2.20             # PVR above this indicates easily separable lines
    pvr_entangled_baseline: float = 1.65         # PVR below this indicates baseline entanglement
    line_collision_threshold: float = 0.15       # Collision fraction above this flags line overlap

    # Scale calibration values (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    micro_char_height_px: float = 12.0           # Median height below this flags micro-scale text
    macro_char_height_px: float = 65.0           # Median height above this flags macro-scale text

    # Ruled paper candidate parameters (CALIBRATION BASELINE — NOT SCIENTIFICALLY FROZEN)
    ruled_line_collision_threshold: float = 0.15 # Collision fraction above this flags rule interference
```

### 6.2 Vulnerabilities of Projection-Based Deskew

The Radon / horizontal projection variance sweep is an effective sub-orthogonal deskew estimator, but downstream validation must account for known sensitivities:
- **Ruled Paper Lines:** Strong horizontal ruling lines dominate projection variance, causing the estimator to lock onto ruling lines rather than handwritten baselines (though in most notebooks, ruling lines and baseline intent coincide).
- **Residual Page Borders:** Dark border remnants from perspective warping introduce spurious projection spikes.
- **Printed Header Blocks:** Large bold headers skew projection variance away from body handwriting tilt.
- **Dense Mathematical Formulas:** Multi-level fractions, exponents, and summation symbols disperse horizontal projection variance.
- **Diagrams & Freehand Sketches:** Non-horizontal stroke distributions confound angle optimization.
- **Sparse Content:** Pages with few words lack sufficient projection contrast to resolve subtle angles.

For these reasons, the deadband ($0.40^\circ$) prevents speculative over-correction on near-level pages.

### 6.3 Controlled Rotation Validation vs Real-World Orientation Robustness

The 4-way rotation tests passing in controlled environments proves **implementation correctness of the orthogonal transformation and signal extraction algorithms**.
- It does **NOT** establish universal orientation reliability on unconstrained real-world student exams.
- As documented in Phase 8.1, sparse handwriting, symmetric title pages, and missing top metadata headers remain known failure risks that require Phase 11 multi-institution validation.

---

## 7. VALIDATION TEST SUITE RESULTS (`phase8/run_phase8_2_validation.py`)

All 9 test cases in the automated validation suite passed cleanly:

```
================================================================================
STARTING PHASE 8.2 PRODUCTION PREPROCESSING & READINESS VALIDATION SUITE
================================================================================

--- Test 1: Safe Buffer Immutability ---
  [PASS] All 4 bundle buffers are strictly read-only; mutation raises ValueError.

--- Test 2: Input Contract Compliance ---
  [PASS] Successfully ingested SafeImageState.
  [PASS] Successfully ingested SafeImageState with Phase 7 CONTINUE.
  [PASS] RescanDecisionResult (RESCAN_REQUIRED) safely outputs NOT_READY immediately.
  [PASS] Successfully ingested raw 2D numpy array.

--- Test 3: 4-Way Orientation Detection & De-Rotation ---
  [PASS] 0° UPRIGHT         -> Detected: UPRIGHT_0            | Applied Rot: 0° CW
  [PASS] 90° ROTATED CW     -> Detected: ROTATED_90_CW        | Applied Rot: 270° CW
  [PASS] 180° INVERTED      -> Detected: ROTATED_180_INVERTED | Applied Rot: 180° CW
  [PASS] 270° ROTATED CCW   -> Detected: ROTATED_270_CCW      | Applied Rot: 90° CW

--- Test 4: Ambiguous Orientation Handling ---
  [PASS] Symmetric canvas identified as AMBIGUOUS; zero speculative rotation applied.

--- Test 5: Fine Baseline Deskew ---
  [PASS] +2.5° tilt detected (+2.50°) and deskewed.
  [PASS] 0.2° tilt within deadband correctly left unaltered.

--- Test 6: Ruled Paper Auxiliary Mask Generation ---
  [PASS] Auxiliary rule mask generated (5.99% coverage); un-eroded ready_gray preserved.

--- Test 7: Aspect Ratio & Geometry Invariance ---
  [PASS] Landscape Sheet (1200x800)   successfully processed (Shape: (800, 1200)).
  [PASS] Square Crop (700x700)        successfully processed (Shape: (700, 700)).
  [PASS] Tall Canvas (600x1400)       successfully processed (Shape: (1400, 600)).

--- Test 8: End-to-End Multi-Phase Pipeline Integration ---
  [PASS] End-to-end integration verified: Phase 7 CONTINUE -> Phase 8.2 Prepared Representation Delivered [Provisional Observation: COMPLEX_LAYOUT_OBSERVED] (Latency: 76.1ms).

--- Test 9: Telemetry Completeness ---
  [PASS] All TextTopologyMetrics populated with finite quantitative values.

================================================================================
PHASE 8.2 VALIDATION SUMMARY: 9 PASSED, 0 FAILED (TOTAL 9)
================================================================================
```

### Categorization of Validation Evidence:
- **Contract & Invariant Tests (Tests 1, 2):** Proved physical numpy write-protection and multi-input ingestion compliance.
- **Controlled Transformation Tests (Tests 3, 5, 6):** Proved algorithm correctness for $90^\circ/180^\circ/270^\circ$ orthogonal normalization, sub-orthogonal deskew, and non-destructive rule masking.
- **Ambiguity Safety Tests (Test 4):** Proved the engine never forces speculative rotations when polarity is ambiguous.
- **Geometry Tests (Test 7):** Proved complete aspect ratio independence across landscape, square, and tall canvases.
- **Integration Tests (Tests 8, 9):** Proved end-to-end cross-phase dataflow (Phase 3 $\rightarrow$ Phase 5 $\rightarrow$ Phase 6 $\rightarrow$ Phase 7 $\rightarrow$ Phase 8.2) and telemetry completeness.

> [!NOTE]
> **Interpretation Notice:** The 9/9 passing result validates **structural and algorithmic correctness**. It does **NOT** constitute proof that downstream OCR/HTR transcription accuracy has been evaluated or achieved.

---

## 8. PHASE 7 REGRESSION SUITE EXECUTION

The complete **Phase 7.2 regression suite** ([`phase7/run_phase7_2_validation.py`](file:///C:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase7/run_phase7_2_validation.py)) was executed:
- All **13 tests passed** (including Phase 6.3 and Phase 6.5 regression tests).
- **Phase 7 regression suite passed; no regression was observed in the tested cases.**

---

## 9. FINAL AUDIT STATUS

```text
Phase 8.2 Implementation
→ COMPLETE

Phase 8.2 Structural Architecture
→ APPROVED

Phase 8.2 Controlled Validation
→ PASSED

OCR/HTR Final Readiness Classifier
→ NOT FROZEN

OCR/HTR Model Integration
→ NOT IMPLEMENTED

Numerical Calibration
→ PROVISIONAL

Real-world OCR/HTR Correlation
→ PENDING

Phase 11 Calibration
→ REQUIRED

Phase 8.3
→ NOT STARTED
```

**STOP: Phase 8.2 audit corrections are complete. Phase 8.3 has NOT been started.**
