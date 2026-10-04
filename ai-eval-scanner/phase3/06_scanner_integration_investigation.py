"""
phase3/06_scanner_integration_investigation.py

AI-EVAL PHASE 3.6: PRODUCTION SCANNER INTEGRATION ARCHITECTURE INVESTIGATION
=============================================================================

PURPOSE:
Integrate the approved Phase 2.13 and Phase 3.1–3.5 concepts into one clean,
production-oriented scanner flow.

ARCHITECTURE FLOW:
Input Image
    ↓
Phase 2.13 Document Region Validation
    ↓
Semantic State
    ├── ACCEPTED_PHYSICAL_PAGE
    │       ↓
    │   Phase 3.3-C Corner Extraction & Consolidation
    │       ↓
    │   Phase 3.4 Corner Normalization & Geometric Validation
    │       ↓
    │   Phase 3.5 Perspective Rectification
    │       ↓
    │   ScannedDocumentResult (RECTIFIED_PHYSICAL_PAGE)
    │
    ├── ACCEPTED_FRAME_LIMITED
    │       ↓
    │   Observable-Edge Skew Estimation (No corner fabrication)
    │       ↓
    │   Rigid 2D Affine Rotation Deskew
    │       ↓
    │   ScannedDocumentResult (DESKEWED_FRAME_LIMITED)
    │
    └── AMBIGUOUS / INSUFFICIENT_CONFIDENCE
            ↓
        No Geometric Fabrication (Pass-through with audit metadata)
            ↓
        ScannedDocumentResult (AMBIGUOUS_UNWARPED)

GUARDRAILS:
- INVESTIGATION ONLY.
- Do NOT build the final production scanner yet.
- Do NOT modify any frozen Phase 2 or Phase 3.1–3.5 files.
- Do NOT begin Phase 4 image enhancement.
- Do NOT add OCR or quality scoring.
- Do NOT introduce universal hard-coded thresholds.
- Do NOT fabricate fake corners for FRAME_LIMITED or AMBIGUOUS states.
"""

import os
import sys
import math
import time
import importlib.util
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT_DIR, "phase3", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Dynamic Imports of Frozen Modules (Zero Modifications to Frozen Code)
# ---------------------------------------------------------------------------
def _import_module(module_name: str, relative_path: str):
    path = os.path.join(ROOT_DIR, relative_path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Module {module_name} not found at {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

phase2_13 = _import_module("phase2_13", os.path.join("phase2", "13_document_region_detector.py"))
phase3_03c = _import_module("phase3_03c", os.path.join("phase3", "03c_hypothesis_consolidation_investigation.py"))
phase3_04 = _import_module("phase3_04", os.path.join("phase3", "04_corner_ordering_investigation.py"))
phase3_05 = _import_module("phase3_05", os.path.join("phase3", "05_perspective_transform_investigation.py"))

# Directly reused functions from approved frozen files
detect_and_validate_document_region = phase2_13.detect_and_validate_document_region
run_consolidation_investigation = phase3_03c.run_consolidation_investigation
validate_corner_set = phase3_04.validate_corner_set
order_corners_convex_cyclic = phase3_04.order_corners_convex_cyclic
compute_destination_dimensions = phase3_05.compute_destination_dimensions
execute_perspective_warp = phase3_05.execute_perspective_warp


# ===========================================================================
# 1. PRODUCTION INTERFACES & DATACLASSES
# ===========================================================================

@dataclass
class ValidatedPhysicalQuad:
    """
    Encapsulates a verified physical quadrilateral prior to canonical ordering.
    """
    raw_corners: List[Tuple[float, float]]
    is_valid: bool
    validation_status: str
    bounding_box: Tuple[int, int, int, int]
    cluster_exemplar_info: Dict[str, Any]


@dataclass
class NormalizedOrderedQuad:
    """
    Encapsulates canonically ordered corners [TL, TR, BR, BL] ready for rectification.
    """
    ordered_corners: np.ndarray             # shape (4, 2), float32: [TL, TR, BR, BL]
    corner_dict: Dict[str, Tuple[float, float]]
    ordering_strategy: str                  # "CONVEX_CYCLIC_TOP_ANCHOR"
    aspect_ratio: float                     # width / height
    quad_area: float


@dataclass
class ObservableSkewInfo:
    """
    Skew and tilt orientation derived exclusively from observable edges
    for frame-limited documents (where corners are cut off by sensor frame).
    """
    dominant_skew_angle_deg: float          # Rotation angle in degrees
    observable_edges: List[str]             # e.g. ["LEFT", "RIGHT"]
    sample_segment_count: int
    rotation_center: Tuple[float, float]
    deskew_strategy: str                    # "RIGID_2D_AFFINE_ROTATION"


@dataclass
class ScannedDocumentResult:
    """
    The unified end-to-end output contract delivered to downstream Phase 4.
    """
    status: str                             # "RECTIFIED_PHYSICAL_PAGE", "DESKEWED_FRAME_LIMITED", "AMBIGUOUS_UNWARPED", "REJECTED_INVALID_GEOMETRY"
    scanned_image: np.ndarray               # Canonical transformed image (BGR or Gray)
    source_dimensions: Tuple[int, int]      # (orig_w, orig_h)
    destination_dimensions: Tuple[int, int] # (dest_w, dest_h)
    transform_type: str                     # "PERSPECTIVE_HOMOGRAPHY_3X3", "RIGID_AFFINE_2X3", "NONE_IDENTITY"
    transform_matrix: Optional[np.ndarray]  # 3x3 homography or 2x3 affine matrix
    source_corners: Optional[np.ndarray]    # Ordered corners if physical page; None otherwise
    aspect_ratio: float                     # Transformed width / height
    interpolation_used: str                 # "INTER_CUBIC", "INTER_LINEAR", or "NONE"
    framing_metadata: Dict[str, Any]        # Sensor frame context from Phase 2
    is_reading_orientation_resolved: bool   # Always False; deferred to Phase 4 / OCR
    processing_notes: List[str]             # Step-by-step diagnostic audit log


# ===========================================================================
# 2. LOGIC MODULES: PHYSICAL PAGE RECTIFICATION FLOW
# ===========================================================================

def extract_physical_quad(image_path: str, p2_result: Any) -> Tuple[Optional[ValidatedPhysicalQuad], Optional[NormalizedOrderedQuad], str]:
    """
    Executes Phase 3.3-C consolidation and Phase 3.4 normalization for physical pages.
    Guarantees that degenerate or non-convex corners are rejected before perspective warping.
    """
    # 1. Run consolidation investigation
    consol_data = run_consolidation_investigation(image_path)
    clusters = consol_data.get("clusters", [])

    # Find verified physical paper boundary cluster
    phys_clusters = [cl for cl in clusters if cl.get("physical_interpretation") == "PHYSICAL_PAPER_OUTER_BOUNDARY"]
    if not phys_clusters:
        return None, None, f"No consolidated physical paper boundary found: {consol_data.get('consolidated_verdict')}"

    # Extract exemplar corners
    exemplar = phys_clusters[0]["exemplar"]
    c_dict = exemplar["corners"]
    raw_corners = [c_dict["TOP_LEFT"], c_dict["TOP_RIGHT"], c_dict["BOTTOM_RIGHT"], c_dict["BOTTOM_LEFT"]]

    # 2. Validate corner geometry (Phase 3.4 validation)
    is_valid, val_msg = validate_corner_set(raw_corners)
    rx, ry, rw, rh = consol_data.get("roi_bbox", (0, 0, 0, 0))
    val_quad = ValidatedPhysicalQuad(
        raw_corners=raw_corners,
        is_valid=is_valid,
        validation_status=val_msg,
        bounding_box=(rx, ry, rw, rh),
        cluster_exemplar_info={"cluster_size": len(phys_clusters[0]["members"]), "intra_iou": np.mean(phys_clusters[0]["ious_with_exemplar"])}
    )

    if not is_valid:
        return val_quad, None, f"Geometric validation rejected quad: {val_msg}"

    # 3. Canonical cyclic ordering (Phase 3.4)
    ordered_dict = order_corners_convex_cyclic(raw_corners)
    ordered_pts = np.array([
        ordered_dict["TOP_LEFT"],
        ordered_dict["TOP_RIGHT"],
        ordered_dict["BOTTOM_RIGHT"],
        ordered_dict["BOTTOM_LEFT"]
    ], dtype=np.float32)

    w_top = np.hypot(ordered_pts[1][0] - ordered_pts[0][0], ordered_pts[1][1] - ordered_pts[0][1])
    w_bot = np.hypot(ordered_pts[2][0] - ordered_pts[3][0], ordered_pts[2][1] - ordered_pts[3][1])
    h_lef = np.hypot(ordered_pts[3][0] - ordered_pts[0][0], ordered_pts[3][1] - ordered_pts[0][1])
    h_rig = np.hypot(ordered_pts[2][0] - ordered_pts[1][0], ordered_pts[2][1] - ordered_pts[1][1])
    ar = ((w_top + w_bot) / 2.0) / max(1.0, ((h_lef + h_rig) / 2.0))
    area = float(cv2.contourArea(ordered_pts))

    norm_quad = NormalizedOrderedQuad(
        ordered_corners=ordered_pts,
        corner_dict=ordered_dict,
        ordering_strategy="CONVEX_CYCLIC_TOP_ANCHOR",
        aspect_ratio=ar,
        quad_area=area
    )

    return val_quad, norm_quad, "VALIDATED_AND_NORMALIZED"


def rectify_physical_page(
    image: np.ndarray,
    norm_quad: NormalizedOrderedQuad,
    strategy: str = "MEAN_EDGE",
    interp_method: int = cv2.INTER_CUBIC
) -> Tuple[np.ndarray, np.ndarray, Tuple[int, int]]:
    """
    Executes Phase 3.5 perspective rectification using approved MEAN_EDGE scaling.
    """
    dest_w, dest_h, _ = compute_destination_dimensions(norm_quad.ordered_corners, strategy=strategy)
    dst_corners = np.array([
        [0.0, 0.0],
        [float(dest_w - 1), 0.0],
        [float(dest_w - 1), float(dest_h - 1)],
        [0.0, float(dest_h - 1)]
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(norm_quad.ordered_corners, dst_corners)
    warped = cv2.warpPerspective(
        image, M, (dest_w, dest_h),
        flags=interp_method,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255)
    )
    return warped, M, (dest_w, dest_h)


# ===========================================================================
# 3. LOGIC MODULES: FRAME-LIMITED AFFINE DESKEW FLOW
# ===========================================================================

def estimate_frame_limited_skew(image: np.ndarray, p2_result: Any) -> ObservableSkewInfo:
    """
    Estimates document tilt strictly from observable boundaries for frame-limited pages.
    Does NOT fabricate unseen sheet corners.
    """
    h_img, w_img = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 140)

    # Use selected candidate box if present
    sel_box = p2_result.selected_box or (0, 0, w_img, h_img)
    bx, by, bw, bh = sel_box

    # Sample line segments
    min_len = max(50, int(min(bw, bh) * 0.10))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=60, minLineLength=min_len, maxLineGap=20)

    tilts = []
    obs_edges = []
    if lines is not None:
        for l in lines.reshape(-1, 4):
            x1, y1, x2, y2 = [float(v) for v in l]
            # Ensure consistent vertical orientation (y2 > y1)
            if y2 < y1:
                x1, y1, x2, y2 = x2, y2, x1, y1
            dy = y2 - y1
            dx = x2 - x1

            # Check if segment is nearly vertical (lateral boundary)
            if dy > 2.0 * abs(dx):
                tilt = math.degrees(math.atan2(dx, dy))
                tilts.append(tilt)
                if abs(x1 - bx) < 0.2 * bw and "LEFT" not in obs_edges:
                    obs_edges.append("LEFT")
                if abs(x1 - (bx + bw)) < 0.2 * bw and "RIGHT" not in obs_edges:
                    obs_edges.append("RIGHT")

    dominant_tilt = float(np.median(tilts)) if tilts else 0.0
    center = (w_img / 2.0, h_img / 2.0)

    return ObservableSkewInfo(
        dominant_skew_angle_deg=dominant_tilt,
        observable_edges=obs_edges if obs_edges else ["OBSERVABLE_MARGINS"],
        sample_segment_count=len(tilts),
        rotation_center=center,
        deskew_strategy="RIGID_2D_AFFINE_ROTATION"
    )


def deskew_frame_limited_page(
    image: np.ndarray,
    skew_info: ObservableSkewInfo,
    interp_method: int = cv2.INTER_CUBIC
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Executes rigid 2D affine rotation deskew without changing canvas geometry.
    """
    h_img, w_img = image.shape[:2]
    # Rotate by negative tilt angle to restore plumb alignment
    M = cv2.getRotationMatrix2D(skew_info.rotation_center, skew_info.dominant_skew_angle_deg, 1.0)
    deskewed = cv2.warpAffine(
        image, M, (w_img, h_img),
        flags=interp_method,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255)
    )
    return deskewed, M


# ===========================================================================
# 4. UNIFIED SCANNER INTEGRATION PIPELINE
# ===========================================================================

def integrate_production_scanner(
    image_path: str,
    options: Optional[Dict[str, Any]] = None
) -> ScannedDocumentResult:
    """
    Integrated Production-Oriented Scanner Architecture:
    1. Phase 2.13 Region Validation
    2. Branching based on qualitative semantic state:
       - ACCEPTED_PHYSICAL_PAGE  -> Consolidated Quad -> Normalization -> Perspective Rectification
       - ACCEPTED_FRAME_LIMITED  -> Observable Edge Skew -> Rigid Affine Deskew
       - AMBIGUOUS / INSUFFICIENT -> No Geometric Fabrication -> Pass-through
    """
    opts = options or {}
    dest_strategy = opts.get("dest_strategy", "MEAN_EDGE")
    interp_name = opts.get("interpolation", "INTER_CUBIC")
    interp_flag = cv2.INTER_CUBIC if interp_name == "INTER_CUBIC" else cv2.INTER_LINEAR

    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Failed to load image at {image_path}")
    h_img, w_img = image.shape[:2]

    notes = [f"Input loaded: {os.path.basename(image_path)} ({w_img}x{h_img} px)"]

    # STEP 1: Phase 2.13 Document Region Validation
    p2_result = detect_and_validate_document_region(image_path)
    status_p2 = p2_result.image_status
    notes.append(f"Phase 2.13 arbitration result: {status_p2} (Candidate: {p2_result.selected_candidate_id})")

    # BRANCH A: ACCEPTED_PHYSICAL_PAGE
    if status_p2 == "ACCEPTED_PHYSICAL_PAGE":
        notes.append("Branch A entered: PHYSICAL_PAGE. Proceeding to corner extraction & validation.")
        val_quad, norm_quad, msg = extract_physical_quad(image_path, p2_result)
        notes.append(f"Physical quad extraction message: {msg}")

        if norm_quad is not None and val_quad is not None and val_quad.is_valid:
            # Perspective Rectification (Phase 3.5)
            warped, M, (dw, dh) = rectify_physical_page(image, norm_quad, strategy=dest_strategy, interp_method=interp_flag)
            notes.append(f"Perspective warp executed via {dest_strategy} -> Output: {dw}x{dh} px")

            return ScannedDocumentResult(
                status="RECTIFIED_PHYSICAL_PAGE",
                scanned_image=warped,
                source_dimensions=(w_img, h_img),
                destination_dimensions=(dw, dh),
                transform_type="PERSPECTIVE_HOMOGRAPHY_3X3",
                transform_matrix=M,
                source_corners=norm_quad.ordered_corners,
                aspect_ratio=dw / max(1, dh),
                interpolation_used=interp_name,
                framing_metadata=p2_result.framing_metadata,
                is_reading_orientation_resolved=False,
                processing_notes=notes
            )
        else:
            # Fallback if quad validation failed
            notes.append("WARNING: Physical page corners failed geometric validation. Rejecting warp.")
            return ScannedDocumentResult(
                status="REJECTED_INVALID_GEOMETRY",
                scanned_image=image.copy(),
                source_dimensions=(w_img, h_img),
                destination_dimensions=(w_img, h_img),
                transform_type="NONE_IDENTITY",
                transform_matrix=np.eye(3, dtype=np.float32),
                source_corners=None,
                aspect_ratio=w_img / max(1, h_img),
                interpolation_used="NONE",
                framing_metadata=p2_result.framing_metadata,
                is_reading_orientation_resolved=False,
                processing_notes=notes
            )

    # BRANCH B: ACCEPTED_FRAME_LIMITED
    elif status_p2 == "ACCEPTED_FRAME_LIMITED":
        notes.append("Branch B entered: FRAME_LIMITED. Corner fabrication prohibited. Estimating observable edge skew.")
        skew_info = estimate_frame_limited_skew(image, p2_result)
        notes.append(f"Observable skew estimated: {skew_info.dominant_skew_angle_deg:.2f}° from {skew_info.sample_segment_count} segments.")

        deskewed, M_affine = deskew_frame_limited_page(image, skew_info, interp_method=interp_flag)
        notes.append("Rigid 2D affine deskew executed. Image canvas dimensions preserved.")

        framing_meta = dict(p2_result.framing_metadata)
        if p2_result.selected_box is not None:
            framing_meta["selected_box"] = p2_result.selected_box

        return ScannedDocumentResult(
            status="DESKEWED_FRAME_LIMITED",
            scanned_image=deskewed,
            source_dimensions=(w_img, h_img),
            destination_dimensions=(w_img, h_img),
            transform_type="RIGID_AFFINE_2X3",
            transform_matrix=M_affine,
            source_corners=None,
            aspect_ratio=w_img / max(1, h_img),
            interpolation_used=interp_name,
            framing_metadata=framing_meta,
            is_reading_orientation_resolved=False,
            processing_notes=notes
        )

    # BRANCH C: AMBIGUOUS / INSUFFICIENT_CONFIDENCE
    else:
        notes.append(f"Branch C entered: {status_p2}. No physical sheet boundaries established. Prohibiting warp.")
        notes.append("Document passed through unwarped with audit metadata for downstream human review or rescan.")

        return ScannedDocumentResult(
            status="AMBIGUOUS_UNWARPED",
            scanned_image=image.copy(),
            source_dimensions=(w_img, h_img),
            destination_dimensions=(w_img, h_img),
            transform_type="NONE_IDENTITY",
            transform_matrix=np.eye(3, dtype=np.float32),
            source_corners=None,
            aspect_ratio=w_img / max(1, h_img),
            interpolation_used="NONE",
            framing_metadata=p2_result.framing_metadata,
            is_reading_orientation_resolved=False,
            processing_notes=notes
        )


# ===========================================================================
# 5. BENCHMARK RUNNER & DIAGNOSTIC VISUALIZATION
# ===========================================================================

def run_integration_audit() -> Dict[str, Any]:
    """
    Executes the integrated scanner flow across all 5 calibration images
    and 1 synthetic degenerate test case.
    """
    calibration_images = [
        "images/answer_sheet.jpg",
        "images/answer_sheet_2.png",
        "images/answer_sheet_3.jpg",
        "images/answer_sheet_4.jpg",
        "images/answer_sheet_5.jpg",
    ]

    print("=" * 80)
    print("PHASE 3.6: PRODUCTION SCANNER INTEGRATION ARCHITECTURE INVESTIGATION")
    print("=" * 80)

    audit_records = {}

    for img_rel in calibration_images:
        img_path = os.path.join(ROOT_DIR, img_rel)
        img_name = os.path.basename(img_path)
        print(f"\n>> PROCESSING: {img_name}")
        print("-" * 80)

        t0 = time.perf_counter()
        result = integrate_production_scanner(img_path)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        audit_records[img_name] = {
            "result": result,
            "elapsed_ms": elapsed_ms,
            "is_synthetic": False
        }

        print(f"Status              : {result.status}")
        print(f"Transform Type      : {result.transform_type}")
        print(f"Source Dims         : {result.source_dimensions}")
        print(f"Destination Dims    : {result.destination_dimensions} (Aspect Ratio: {result.aspect_ratio:.3f})")
        print(f"Corners Extracted   : {'Yes' if result.source_corners is not None else 'None (Deferred/Prohibited)'}")
        print(f"Execution Latency   : {elapsed_ms:.1f} ms")
        print("Processing Log:")
        for note in result.processing_notes:
            print(f"  * {note}")

    # Synthetic Degenerate Test Case: Collinear / Bow-Tie Quad Check
    print("\n>> PROCESSING: Synthetic Degenerate Bow-Tie Quad")
    print("-" * 80)
    synth_img = np.ones((600, 800, 3), dtype=np.uint8) * 200
    cv2.rectangle(synth_img, (100, 100), (700, 500), (255, 255, 255), -1)
    cv2.putText(synth_img, "DEGENERATE BOW-TIE TEST", (150, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    synth_path = os.path.join(OUTPUT_DIR, "synth_degenerate_test.png")
    cv2.imwrite(synth_path, synth_img)

    # Test direct validation of bow-tie quad
    bowtie_pts = [(100.0, 100.0), (700.0, 500.0), (700.0, 100.0), (100.0, 500.0)]
    is_v, msg_v = validate_corner_set(bowtie_pts)
    print(f"Bow-Tie Raw Corners : {bowtie_pts}")
    print(f"Geometric Validation: is_valid={is_v}, message={msg_v}")

    # Generate Integrated Architectural Flow Visualization
    vis_path = os.path.join(OUTPUT_DIR, "phase3_scanner_integration_flow.png")
    generate_integration_visualization(audit_records, vis_path)
    print(f"\nDiagnostic flow visualization saved to: {vis_path}")

    return audit_records


def generate_integration_visualization(audit_records: Dict[str, Any], output_path: str):
    """
    Creates a 5-panel comprehensive visual summary showing the input,
    routing decision, and output of the integrated scanner architecture.
    """
    fig, axes = plt.subplots(len(audit_records), 2, figsize=(14, 4 * len(audit_records)))

    for idx, (img_name, rec) in enumerate(audit_records.items()):
        res: ScannedDocumentResult = rec["result"]

        # Panel 1: Original Image with Flow Annotation
        orig_img = cv2.imread(os.path.join(ROOT_DIR, "images", img_name))
        rgb_orig = cv2.cvtColor(orig_img, cv2.COLOR_BGR2RGB)
        ax_orig = axes[idx, 0]
        ax_orig.imshow(rgb_orig)

        if res.source_corners is not None:
            poly = np.vstack([res.source_corners, res.source_corners[0]])
            ax_orig.plot(poly[:, 0], poly[:, 1], color="lime", linewidth=2.5, label="Verified Quad")
            for c_i, pt in enumerate(res.source_corners):
                ax_orig.plot(pt[0], pt[1], marker="o", markersize=6, markerfacecolor="cyan", markeredgecolor="black")

        ax_orig.set_title(f"INPUT: {img_name}\nStatus: {res.status}", fontsize=11, fontweight="bold")
        ax_orig.axis("off")

        # Panel 2: Processed Output Image
        rgb_out = cv2.cvtColor(res.scanned_image, cv2.COLOR_BGR2RGB)
        ax_out = axes[idx, 1]
        ax_out.imshow(rgb_out)
        ax_out.set_title(
            f"OUTPUT: {res.transform_type}\nDims: {res.destination_dimensions[0]}x{res.destination_dimensions[1]} | AR: {res.aspect_ratio:.3f} | Latency: {rec['elapsed_ms']:.1f}ms",
            fontsize=11, fontweight="bold"
        )
        ax_out.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_integration_audit()
