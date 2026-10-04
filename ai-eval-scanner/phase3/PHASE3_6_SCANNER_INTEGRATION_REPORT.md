# Phase 3.6: Production Scanner Integration Architecture Investigation Report

**Project**: AI-EVAL-OpenCV  
**Phase**: 3.6 — Production Scanner Integration Architecture Investigation  
**Status**: ARCHITECTURAL INTEGRATION INVESTIGATION (Phase 2 & Phase 3.1–3.5 Frozen; No Phase 4 Enhancement / No OCR)  
**Date**: October 2026  

---

## 1. Executive Summary & Objective

The objective of **Phase 3.6** is to synthesize and integrate the approved concepts from Phase 2.13 and Phases 3.1–3.5 into a single, cohesive, production-oriented scanner architecture.

This phase is **NOT** the final production scanner, nor does it begin Phase 4 image enhancement, OCR, quality scoring, auto-correction, or rescan logic. Instead, it defines:
1. The **exact data flow** and **state machine** routing incoming images.
2. The **strict separation** between physical-page perspective rectification, frame-limited rigid affine deskew, and ambiguous pass-through.
3. The **concrete dataclass interfaces** connecting Phase 2, Phase 3, and downstream Phase 4.
4. An **audit of existing code**, determining what should be promoted to production vs. what must remain diagnostic.

The integrated flow was implemented in [`phase3/06_scanner_integration_investigation.py`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase3/06_scanner_integration_investigation.py) and verified across the complete calibration suite (`answer_sheet.jpg`, `answer_sheet_2.png`, `answer_sheet_3.jpg`, `answer_sheet_4.jpg`, `answer_sheet_5.jpg`) and synthetic edge cases.

---

## 2. Integrated Scanner Architecture & Data Flow

```
                      Input Image (BGR/Grayscale)
                                  │
                                  ▼
             ┌──────────────────────────────────────────┐
             │ Phase 2.13: Document Region Validation   │
             │ detect_and_validate_document_region()   │
             └────────────────────┬─────────────────────┘
                                  │
                                  ▼
                      DocumentValidationResult
                       (Arbitrated Image Status)
                                  │
         ┌────────────────────────┼────────────────────────┐
         │                        │                        │
         ▼                        ▼                        ▼
 [ACCEPTED_PHYSICAL_PAGE]  [ACCEPTED_FRAME_LIMITED]  [AMBIGUOUS / INSUFFICIENT]
         │                        │                        │
         ▼                        ▼                        ▼
 ┌───────────────┐        ┌───────────────┐        ┌───────────────┐
 │ Phase 3.3-C   │        │ Observable    │        │ No Geometric  │
 │ Multi-Line    │        │ Margin Tilt   │        │ Fabrication   │
 │ Consolidation │        │ Estimation    │        │               │
 └───────┬───────┘        └───────┬───────┘        │ Audit Context │
         │                        │                │ Preserved     │
         ▼                        ▼                └───────┬───────┘
 ┌───────────────┐        ┌───────────────┐                │
 │ Phase 3.4     │        │ Rigid 2D      │                │
 │ Validation &  │        │ Affine Deskew │                │
 │ Cyclic Normal.│        │ (cv2.warp-    │                │
 └───────┬───────┘        │  Affine)      │                │
         │                └───────┬───────┘                │
         ▼                        │                        │
 ┌───────────────┐                │                        │
 │ Phase 3.5     │                │                        │
 │ Perspective   │                │                        │
 │ Rectification │                │                        │
 │ (MEAN_EDGE)   │                │                        │
 └───────┬───────┘                │                        │
         │                        │                        │
         ▼                        ▼                        ▼
    PERSPECTIVE                 RIGID                    NO-OP
   HOMOGRAPHY 3x3             AFFINE 2x3                IDENTITY
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  │
                                  ▼
                       ScannedDocumentResult
                   (Delivered to Downstream Phase 4)
```

---

## 3. Data Flow by Document Category

### A. Physical Pages (`ACCEPTED_PHYSICAL_PAGE`)
*Applies to: `answer_sheet_2.png`, `answer_sheet_3.jpg`*
1. **Input**: `DocumentValidationResult` confirming `ACCEPTED_PHYSICAL_PAGE`.
2. **Consolidation**: Extract candidate margin lines (RANSAC / PCA), compute 4-line intersections, cluster quads, and identify the single outer physical paper boundary.
3. **Geometric Validation**: Check that points form a strictly convex quadrilateral (non-collinear, non-intersecting bow-tie, positive area $> 100\text{ px}^2$).
4. **Coordinate Normalization**: Anchor top-left corner via proximity to origin and traverse clockwise to yield canonical $[P_0 (\text{TL}), P_1 (\text{TR}), P_2 (\text{BR}), P_3 (\text{BL})]$.
5. **Destination Sizing**: Compute destination width and height using **Average Edge Length (`MEAN_EDGE`)** to eliminate keystone foreshortening distortion.
6. **Perspective Warp**: Apply $3 \times 3$ projective homography via `cv2.warpPerspective(..., flags=INTER_CUBIC, borderMode=BORDER_CONSTANT, borderValue=(255,255,255))`.
7. **Output**: `ScannedDocumentResult(status="RECTIFIED_PHYSICAL_PAGE", transform_type="PERSPECTIVE_HOMOGRAPHY_3X3", ...)`.

### B. Frame-Limited Pages (`ACCEPTED_FRAME_LIMITED`)
*Applies to: `answer_sheet_4.jpg`, `answer_sheet_5.jpg`*
1. **Input**: `DocumentValidationResult` confirming `ACCEPTED_FRAME_LIMITED` (sheet contacts/extends beyond camera sensor bounds).
2. **Corner Fabrication Prohibition**: **Strictly no 4-corner perspective warp is attempted.** Non-existent corners outside the camera sensor are never fabricated.
3. **Observable Edge Tilt**: Detect visible lateral or longitudinal edges (e.g. left and right margins) and extract the dominant skew angle $\theta$ (e.g. $-0.93^\circ$ on `answer_sheet_4`, $+0.86^\circ$ on `answer_sheet_5`).
4. **Rigid Affine Deskew**: Apply a $2 \times 3$ rigid Euclidean rotation matrix around the image center via `cv2.warpAffine(..., flags=INTER_CUBIC)`.
5. **Output**: `ScannedDocumentResult(status="DESKEWED_FRAME_LIMITED", transform_type="RIGID_AFFINE_2X3", ...)`. Image dimensions match the original sensor frame.

### C. Ambiguous / Insufficient Evidence Pages (`AMBIGUOUS`)
*Applies to: `answer_sheet.jpg`*
1. **Input**: `DocumentValidationResult` indicating `AMBIGUOUS` (tightly cropped content, no physical outer paper boundary visible).
2. **Zero Fabrication**: No corner estimation, no perspective warp, no artificial rotation.
3. **Pass-Through**: The original capture is passed through unmodified with comprehensive framing and arbitration metadata.
4. **Output**: `ScannedDocumentResult(status="AMBIGUOUS_UNWARPED", transform_type="NONE_IDENTITY", ...)`, flagged for downstream human review or rescan decision.

---

## 4. Calibration Suite Verification Results

The integrated scanner flow from [`phase3/06_scanner_integration_investigation.py`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase3/06_scanner_integration_investigation.py) was audited across all 5 calibration images and 1 synthetic degenerate test case:

| Calibration Image | Phase 2.13 Status | Router Branch | Transform Type | Output Dimensions | Aspect Ratio | Corners Output | Latency | Audit Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`answer_sheet.jpg`** | `AMBIGUOUS` | Branch C | `NONE_IDENTITY` | $768 \times 1024$ | 0.750 | None (Prohibited) | 283.9 ms | **PASS**: No corners fabricated; pass-through with metadata |
| **`answer_sheet_2.png`** | `ACCEPTED_PHYSICAL_PAGE` | Branch A | `PERSPECTIVE_HOMOGRAPHY_3X3` | $899 \times 1273$ | **0.706** | Yes ($4$ pts) | 7282.3 ms | **PASS**: True A4 aspect ratio recovered ($0.706 \approx 1/\sqrt{2}$) |
| **`answer_sheet_3.jpg`** | `ACCEPTED_PHYSICAL_PAGE` | Branch A | `PERSPECTIVE_HOMOGRAPHY_3X3` | $941 \times 1205$ | 0.781 | Yes ($4$ pts) | 4207.5 ms | **PASS**: Shaded corner resolved; flat canonical rectangle |
| **`answer_sheet_4.jpg`** | `ACCEPTED_FRAME_LIMITED` | Branch B | `RIGID_AFFINE_2X3` | $1200 \times 1700$ | 0.706 | None (Prohibited) | 650.4 ms | **PASS**: Skew $-0.93^\circ$ deskewed; zero perspective keystone |
| **`answer_sheet_5.jpg`** | `ACCEPTED_FRAME_LIMITED` | Branch B | `RIGID_AFFINE_2X3` | $1200 \times 1600$ | 0.750 | None (Prohibited) | 466.5 ms | **PASS**: Skew $+0.86^\circ$ deskewed; zero perspective keystone |
| **`Synth: Bow-Tie Quad`** | Synthetic Quad | Geometry Gate | `REJECTED` | $800 \times 600$ | 1.333 | None (Rejected) | 0.2 ms | **PASS**: Self-intersecting edges caught; warp aborted |

*Diagnostic visualization saved to [`phase3/output/phase3_scanner_integration_flow.png`](file:///c:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase3/output/phase3_scanner_integration_flow.png).*

---

## 5. Answers to Mandatory Phase 3.6 Investigation Questions

### Question 1: Which existing functions/classes can be safely reused?
The following functions and classes from frozen Phase 2 and Phase 3 modules are production-ready:
1. **From `phase2/13_document_region_detector.py`**:
   - `detect_and_validate_document_region()`: High-level entry point.
   - `DocumentValidationResult` and `CandidateEvidenceProfile`: Qualitative evidence contract.
   - `measure_boundary_collars()`, `measure_active_document_edges()`, `measure_texture_microcontrast()`, `measure_boundary_compactness()`, `measure_geometry_shape_prior()`.
2. **From `phase3/04_corner_ordering_investigation.py`**:
   - `validate_corner_set()`: Collinearity, duplicate, non-convex, and bow-tie self-intersection rejection.
   - `order_corners_convex_cyclic()`: Reliable cyclic clockwise ordering with origin anchoring.
3. **From `phase3/05_perspective_transform_investigation.py`**:
   - `compute_destination_dimensions()` (with strategy `"MEAN_EDGE"`).
   - `execute_perspective_warp()` (with `INTER_CUBIC` and `BORDER_CONSTANT` white padding).

---

### Question 2: Which investigation functions should NOT enter production?
The following functions were designed strictly for exploratory diagnostics, sensitivity sweeps, or benchmarking, and must **NOT** enter production:
1. **Interactive / Diagnostic Plot Generators**:
   - `generate_consolidation_visualization()`, `generate_warp_visualizations()`, `generate_ordering_visualizations()`, `plot_boundary_collars()`, etc. (Matplotlib rendering adds hundreds of milliseconds of overhead).
2. **Exhaustive Strategy Comparison Sweeps**:
   - Loops comparing `MAX_EDGE` vs. `MEAN_EDGE` vs. `AREA_ASPECT_PRESERVED` on every document.
   - Comparison loops comparing 4 interpolation algorithms on every image.
   - Sum-difference and polar sorting fallback routines (superseded by cyclic convex ordering).
3. **Synthetic Deformation Generators**:
   - `make_synthetic_sheet()`, `place_on_desk()`, `perturb_corners()`.

---

### Question 3: What is the exact end-to-end Phase 3 input/output contract?
The end-to-end Phase 3 pipeline receives an image and returns a `ScannedDocumentResult`:

```python
@dataclass
class ScannedDocumentResult:
    status: str                             # "RECTIFIED_PHYSICAL_PAGE", "DESKEWED_FRAME_LIMITED", "AMBIGUOUS_UNWARPED", "REJECTED_INVALID_GEOMETRY"
    scanned_image: np.ndarray               # Canonical transformed image (BGR uint8)
    source_dimensions: Tuple[int, int]      # (orig_w, orig_h)
    destination_dimensions: Tuple[int, int] # (dest_w, dest_h)
    transform_type: str                     # "PERSPECTIVE_HOMOGRAPHY_3X3", "RIGID_AFFINE_2X3", "NONE_IDENTITY"
    transform_matrix: Optional[np.ndarray]  # 3x3 homography or 2x3 affine matrix
    source_corners: Optional[np.ndarray]    # Ordered corners if physical page (shape: 4, 2); None otherwise
    aspect_ratio: float                     # dest_w / dest_h
    interpolation_used: str                 # "INTER_CUBIC", "INTER_LINEAR", or "NONE"
    framing_metadata: Dict[str, Any]        # Sensor frame context from Phase 2
    is_reading_orientation_resolved: bool   # Always False (deferred to Phase 4 / OCR)
    processing_notes: List[str]             # Step-by-step diagnostic audit log
```

---

### Question 4: How are PHYSICAL_PAGE, FRAME_LIMITED and AMBIGUOUS states propagated?
State propagation is strictly deterministic based on the qualitative arbitration of Phase 2.13:
- **`ACCEPTED_PHYSICAL_PAGE`** propagates to **Branch A** (Physical Corner Extraction $\to$ Normalization $\to$ Perspective Rectification $\to$ `RECTIFIED_PHYSICAL_PAGE`).
- **`ACCEPTED_FRAME_LIMITED`** propagates to **Branch B** (Observable Edge Skew Estimation $\to$ Rigid 2D Affine Deskew $\to$ `DESKEWED_FRAME_LIMITED`).
- **`AMBIGUOUS`** / **`INSUFFICIENT_CONFIDENCE`** propagates to **Branch C** (No Geometric Fabrication $\to$ Identity Pass-Through $\to$ `AMBIGUOUS_UNWARPED`).

---

### Question 5: How are invalid corners handled?
Before any quad is submitted to projective transformation, it passes through `validate_corner_set()`:
1. Must contain exactly 4 points.
2. Pairwise Euclidean distance must exceed $1.0\text{ px}$ (no duplicate corners).
3. No 3 points may be collinear ($\text{triangle area} > 5.0\text{ px}^2$).
4. Segments must not self-intersect (no bow-tie quads).
5. Convex hull must contain 4 vertices with area $> 100\text{ px}^2$.
If any check fails, the pipeline aborts warping, sets `status="REJECTED_INVALID_GEOMETRY"`, passes through the unmodified source image, and records the exact geometric fault in `processing_notes`.

---

### Question 6: How is perspective rectification invoked only for validated physical pages?
Perspective rectification is guarded behind two strict gates:
1. **Semantic State Gate**: It can only be invoked if Phase 2.13 arbitrates `image_status == "ACCEPTED_PHYSICAL_PAGE"`.
2. **Geometric Gate**: It can only be invoked if `extract_physical_quad()` finds an outer paper boundary cluster and `validate_corner_set()` returns `is_valid == True`.
If either gate fails, `cv2.getPerspectiveTransform()` and `cv2.warpPerspective()` are **never called**.

---

### Question 7: How is frame-limited deskew separated from perspective correction?
They are physically and mathematically isolated:
| Characteristic | Physical Page Rectification | Frame-Limited Deskew |
| :--- | :--- | :--- |
| **Mathematical Transform** | Projective Homography ($3 \times 3$ matrix) | Rigid Euclidean Affine ($2 \times 3$ matrix: $\text{scale} \equiv 1.0$) |
| **Degree of Freedom** | 8 DOF (Keystone, tilt, shear, scale, translation) | 3 DOF (2D translation + 1D in-plane rotation angle $\theta$) |
| **Corner Requirement** | Requires 4 validated physical corners | **Requires 0 corners** (uses observable margin edge lines) |
| **Canvas Dimensions** | Computed from document edge lengths | Preserves exact source sensor canvas ($W_{\text{sensor}} \times H_{\text{sensor}}$) |
| **Artifact Risk** | High risk of runaway keystone if corners are wrong | Zero risk of keystone; purely straightens observable tilt |

---

### Question 8: What information must be preserved for Phase 4?
Phase 4 (Image Enhancement, Binarization, Illumination Correction) requires:
1. **The Rectified/Deskewed Image (`scanned_image`)**: Clean BGR image ready for contrast/adaptive thresholding.
2. **Transform Matrix (`transform_matrix`) & Type (`transform_type`)**: Essential for mapping detected bounding boxes (e.g. OCR text boxes or bubble centroids) back to original camera coordinates.
3. **Framing Metadata (`framing_metadata`)**: Identifies whether the document was cropped by the camera sensor frame.
4. **Aspect Ratio (`aspect_ratio`)**: Informs page layout templates (e.g. distinguishing portrait vs landscape layouts).
5. **Reading Orientation Flag (`is_reading_orientation_resolved: False`)**: Signals that $90^\circ / 180^\circ / 270^\circ$ orientation is unresolved and must be determined by text line orientation in Phase 4.

---

### Question 9: What interfaces should Phase 4 consume?
Phase 4 should consume `ScannedDocumentResult` directly. Its entry signature will be:
```python
def enhance_scanned_document(
    scanned_result: ScannedDocumentResult,
    config: Optional[EnhancementConfig] = None
) -> EnhancedDocumentResult:
    ...
```

---

### Question 10: Are any architectural changes still required before freezing Phase 3?
**No architectural changes are required.** The architecture successfully addresses every requirement:
- Qualitative semantic state preservation.
- Physical page vs. frame-limited boundary isolation.
- Ambiguity as an explicit, safe outcome.
- Zero corner fabrication.
- No A4, portrait, or resolution assumptions.
- Mathematically robust dimension scaling (`MEAN_EDGE`) and interpolation (`INTER_CUBIC`).

Phase 3 is complete, validated, and ready to be frozen.

---
*Report prepared for Phase 3.6 of AI-EVAL-OpenCV.*
