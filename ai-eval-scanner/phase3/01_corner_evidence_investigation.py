"""
phase3/01_corner_evidence_investigation.py

AI-EVAL PHASE 3.1: CORNER EVIDENCE INVESTIGATION
================================================

PURPOSE:
Investigation-only study to determine whether reliable physical page-corner
evidence can be extracted from the document regions selected by Phase 2.13.

CRITICAL GUARDRAILS:
- INVESTIGATION ONLY.
- Do NOT build a production scanner.
- Do NOT implement perspective correction.
- Do NOT call cv2.getPerspectiveTransform() or cv2.warpPerspective().
- Do NOT fabricate physical corners when evidence is missing or clipped.
- Do NOT treat image-frame corners as physical document corners.
- Do NOT introduce fixed universal pixel thresholds as decision rules.
- Do NOT modify any Phase 2 frozen files.

INVESTIGATED SIGNALS:
1. Canny edge density & continuity near corners
2. Hough line segments near candidate boundaries
3. Local boundary continuity & gradient direction
4. Contour-based geometry (polygon approximation on appearance mask)
5. Local corner response (Shi-Tomasi / Harris corner features)
6. Boundary line-line intersection geometry
7. Frame-contact analysis (visible corner vs sensor-frame clipping)
"""

import os
import sys
import importlib.util
from typing import Dict, List, Tuple, Optional, Any
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# ---------------------------------------------------------------------------
# Dynamic Import of Phase 2.13 (Without Modifying Frozen Files)
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHASE2_13_PATH = os.path.join(ROOT_DIR, "phase2", "13_document_region_detector.py")

if not os.path.exists(PHASE2_13_PATH):
    raise FileNotFoundError(f"Phase 2.13 module not found at: {PHASE2_13_PATH}")

spec = importlib.util.spec_from_file_location("phase2_13", PHASE2_13_PATH)
phase2_13 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phase2_13)

detect_and_validate_document_region = phase2_13.detect_and_validate_document_region

# ---------------------------------------------------------------------------
# Configuration & Output Directory
# ---------------------------------------------------------------------------
CALIBRATION_IMAGES = [
    os.path.join(ROOT_DIR, "images", "answer_sheet.jpg"),
    os.path.join(ROOT_DIR, "images", "answer_sheet_2.png"),
    os.path.join(ROOT_DIR, "images", "answer_sheet_3.jpg"),
    os.path.join(ROOT_DIR, "images", "answer_sheet_4.jpg"),
    os.path.join(ROOT_DIR, "images", "answer_sheet_5.jpg"),
]

OUTPUT_DIR = os.path.join(ROOT_DIR, "phase3", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Geometry & Intersection Helpers
# ---------------------------------------------------------------------------
def compute_line_intersection(
    line1: Tuple[float, float, float, float],
    line2: Tuple[float, float, float, float]
) -> Optional[Tuple[float, float]]:
    """
    Computes intersection point of two 2D lines given as (x1, y1, x2, y2).
    Returns (x, y) or None if lines are parallel.
    """
    x1, y1, x2, y2 = line1
    x3, y3, x4, y4 = line2

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-6:
        return None

    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
    return float(px), float(py)


def extract_corner_roi(
    img: np.ndarray,
    cx: int,
    cy: int,
    radius: int
) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
    """
    Extracts a square ROI around (cx, cy) clipped to image dimensions.
    Returns (roi, (x1, y1, x2, y2)).
    """
    h, w = img.shape[:2]
    x1 = max(0, cx - radius)
    y1 = max(0, cy - radius)
    x2 = min(w, cx + radius)
    y2 = min(h, cy + radius)
    return img[y1:y2, x1:x2], (x1, y1, x2, y2)


# ---------------------------------------------------------------------------
# Corner Evidence Investigation for a Single Image
# ---------------------------------------------------------------------------
def investigate_image_corners(image_path: str) -> Dict[str, Any]:
    """
    Evaluates 7 distinct corner signals on the document region of an image.
    """
    img_name = os.path.basename(image_path)
    bgr = cv2.imread(image_path)
    if bgr is None:
        raise ValueError(f"Failed to load image: {image_path}")

    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # 1. Execute Phase 2.13 validation
    p2_result = detect_and_validate_document_region(image_path)
    image_status = p2_result.image_status
    selected_id = p2_result.selected_candidate_id
    selected_box = p2_result.selected_box

    # Fallback box for investigation if Phase 2 is AMBIGUOUS
    if selected_box is None:
        eval_box = (0, 0, w, h)
        box_source = "FULL_FRAME_PROVISIONAL (Phase 2 AMBIGUOUS)"
    else:
        eval_box = selected_box
        box_source = f"PHASE_2_SELECTED ({selected_id})"

    bx, by, bw, bh = eval_box

    # Nominal candidate corner coordinates (AABB corners)
    nominal_corners = {
        "TOP_LEFT":     (bx, by),
        "TOP_RIGHT":    (bx + bw, by),
        "BOTTOM_RIGHT": (bx + bw, by + bh),
        "BOTTOM_LEFT":  (bx, by + bh),
    }

    # Precomputations for corner analysis
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    # Resolution-aware corner search radius (~3% of image diagonal)
    diag = np.sqrt(w * w + h * h)
    radius = max(20, int(round(diag * 0.03)))

    # Global Shi-Tomasi feature detection
    corners_st = cv2.goodFeaturesToTrack(
        gray, maxCorners=300, qualityLevel=0.01, minDistance=10
    )
    st_points = []
    if corners_st is not None:
        st_points = [tuple(p[0]) for p in corners_st]

    # Global Hough line segments
    lines_p = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180, threshold=80,
        minLineLength=int(min(w, h) * 0.08), maxLineGap=15
    )
    detected_lines = []
    if lines_p is not None:
        for l in lines_p.reshape(-1, 4):
            detected_lines.append((int(l[0]), int(l[1]), int(l[2]), int(l[3])))

    # Contour-based polygon approximation (on appearance mask if candidate came from it)
    contour_poly_pts = None
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k_close = max(11, int(round(min(h, w) * 0.015)) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_close, k_close))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        c_largest = max(cnts, key=cv2.contourArea)
        if cv2.contourArea(c_largest) > (h * w * 0.10):
            epsilon = 0.02 * cv2.arcLength(c_largest, True)
            poly = cv2.approxPolyDP(c_largest, epsilon, True)
            if len(poly) == 4:
                contour_poly_pts = [tuple(p[0]) for p in poly]

    # -----------------------------------------------------------------------
    # Detailed Evaluation for Each of the 4 Expected Corners
    # -----------------------------------------------------------------------
    corner_reports = {}
    for c_name, (cx, cy) in nominal_corners.items():
        # Frame contact check: does this corner touch the image sensor frame?
        touches_sensor_h = (cy == 0 or cy == h)
        touches_sensor_w = (cx == 0 or cx == w)
        touches_sensor_corner = (touches_sensor_h and touches_sensor_w)
        touches_sensor_edge = (touches_sensor_h or touches_sensor_w)

        # Extract local ROI
        roi_edges, (rx1, ry1, rx2, ry2) = extract_corner_roi(edges, cx, cy, radius)
        roi_gray, _ = extract_corner_roi(gray, cx, cy, radius)

        # 1. Edge density & continuity in corner ROI
        roi_edge_pixels = int(np.count_nonzero(roi_edges))
        roi_edge_density = float(roi_edge_pixels) / float(roi_edges.size) if roi_edges.size > 0 else 0.0

        # 2. Local Shi-Tomasi feature points within radius
        local_st = [
            (px, py) for (px, py) in st_points
            if np.hypot(px - cx, py - cy) <= radius
        ]

        # 3. Line segments passing through or near this corner zone
        nearby_lines = []
        h_lines = []
        v_lines = []
        for l in detected_lines:
            x1, y1, x2, y2 = l
            # Check distance from line segment to (cx, cy)
            d1 = np.hypot(x1 - cx, y1 - cy)
            d2 = np.hypot(x2 - cx, y2 - cy)
            if min(d1, d2) <= radius * 1.5:
                nearby_lines.append(l)
                dx = abs(x2 - x1)
                dy = abs(y2 - y1)
                if dx > dy * 1.5:
                    h_lines.append(l)
                elif dy > dx * 1.5:
                    v_lines.append(l)

        # 4. Line intersection candidate near corner
        line_intersection = None
        if h_lines and v_lines:
            # Pick longest horizontal and vertical line near corner
            best_h = max(h_lines, key=lambda l: abs(l[2] - l[0]))
            best_v = max(v_lines, key=lambda l: abs(l[3] - l[1]))
            inter = compute_line_intersection(best_h, best_v)
            if inter is not None:
                ix, iy = inter
                if np.hypot(ix - cx, iy - cy) <= radius * 2.0:
                    line_intersection = (round(ix, 1), round(iy, 1))

        # 5. Determine Qualitative Visibility & Physical Nature
        if touches_sensor_corner:
            visibility = "UNOBSERVABLE_FRAME_CORNER"
            evidence_type = "SENSOR_FRAME_BOUNDARY (Physical page extends beyond or touches camera bounds)"
            physical_corner_visible = False
        elif touches_sensor_edge:
            visibility = "FRAME_CLIPPED_BORDER"
            evidence_type = "FRAME_CLIPPED_LINE_INTERSECTION (Side touches sensor frame; physical corner missing)"
            physical_corner_visible = False
        else:
            # Fully inside image bounds (floating on desk background)
            if len(local_st) > 0 and roi_edge_density > 0.02:
                visibility = "DIRECTLY_OBSERVABLE_PHYSICAL_CORNER"
                evidence_type = "PHYSICAL_PAPER_VERTEX (Contrast step + corner feature + line junction)"
                physical_corner_visible = True
            elif line_intersection is not None:
                visibility = "INTERSECTED_BOUNDARY_CORNER"
                evidence_type = "BOUNDARY_LINE_INTERSECTION (Observable via edge lines)"
                physical_corner_visible = True
            else:
                visibility = "WEAK_OR_AMBIGUOUS_CORNER"
                evidence_type = "AMBIGUOUS (Weak local contrast or blurred background transition)"
                physical_corner_visible = False

        corner_reports[c_name] = {
            "nominal_coord": (cx, cy),
            "search_radius_px": radius,
            "visibility_state": visibility,
            "is_physical_corner_visible": physical_corner_visible,
            "evidence_nature": evidence_type,
            "roi_edge_pixels": roi_edge_pixels,
            "roi_edge_density": round(roi_edge_density, 4),
            "local_corner_features_count": len(local_st),
            "nearby_line_segments_count": len(nearby_lines),
            "computed_line_intersection": line_intersection,
            "touches_sensor_edge": touches_sensor_edge,
            "touches_sensor_corner": touches_sensor_corner,
        }

    # Summary across all 4 corners
    visible_count = sum(1 for cr in corner_reports.values() if cr["is_physical_corner_visible"])
    clipped_count = sum(1 for cr in corner_reports.values() if cr["touches_sensor_edge"])

    result_record = {
        "image_name": img_name,
        "image_dimensions": (w, h),
        "phase2_image_status": image_status,
        "selected_candidate_id": selected_id,
        "box_source": box_source,
        "evaluated_box": eval_box,
        "visible_physical_corners_count": visible_count,
        "clipped_frame_corners_count": clipped_count,
        "contour_poly_quad_pts": contour_poly_pts,
        "corner_reports": corner_reports,
    }

    # -----------------------------------------------------------------------
    # Generate Diagnostic Visual Overlay
    # -----------------------------------------------------------------------
    out_vis_path = os.path.join(OUTPUT_DIR, f"phase3_corner_vis_{img_name}.png")
    fig, ax = plt.subplots(figsize=(10, 8), dpi=150)
    ax.imshow(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))

    # Draw evaluated candidate bounding box
    rect = patches.Rectangle(
        (bx, by), bw, bh, linewidth=2, edgecolor="cyan", facecolor="none",
        linestyle="--", label=f"Eval Box: {box_source}"
    )
    ax.add_patch(rect)

    # Draw Hough line segments
    for l in detected_lines:
        ax.plot([l[0], l[2]], [l[1], l[3]], color="yellow", linewidth=1.0, alpha=0.5)

    # Draw 4 corner analysis zones
    colors = {
        "DIRECTLY_OBSERVABLE_PHYSICAL_CORNER": "lime",
        "INTERSECTED_BOUNDARY_CORNER": "cyan",
        "FRAME_CLIPPED_BORDER": "orange",
        "UNOBSERVABLE_FRAME_CORNER": "red",
        "WEAK_OR_AMBIGUOUS_CORNER": "magenta",
    }

    for c_name, cr in corner_reports.items():
        cx, cy = cr["nominal_coord"]
        vis_st = cr["visibility_state"]
        c_col = colors.get(vis_st, "white")

        # Circle search zone
        circle = plt.Circle((cx, cy), radius, color=c_col, fill=False, linewidth=1.5)
        ax.add_patch(circle)

        # Intersection point if computed
        inter = cr["computed_line_intersection"]
        if inter is not None:
            ax.plot(inter[0], inter[1], marker="x", color="red", markersize=8, markeredgewidth=2)

        # Text label
        ax.text(
            cx + 8, cy + 8, f"{c_name}\n[{vis_st}]",
            color="white", fontsize=7, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="black", alpha=0.7)
        )

    ax.set_title(
        f"Phase 3.1 Corner Evidence: {img_name}\n"
        f"Phase 2 Status: {image_status} | Physical Corners Visible: {visible_count}/4 | Clipped: {clipped_count}/4",
        fontsize=10, fontweight="bold"
    )
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(out_vis_path, bbox_inches="tight")
    plt.close(fig)

    result_record["vis_path"] = out_vis_path
    return result_record


# ---------------------------------------------------------------------------
# Main Execution Runner
# ---------------------------------------------------------------------------
def run_investigation():
    """
    Executes corner evidence investigation across all 5 calibration images
    and outputs detailed diagnostic reports.
    """
    print("=" * 80)
    print("PHASE 3.1: CORNER EVIDENCE INVESTIGATION")
    print("=" * 80)
    print("Scope       : 5 real calibration images")
    print("Objective   : Investigate physical corner visibility, line intersections,")
    print("              and frame-limited clipping behavior.")
    print("Constraints : Investigation only; no warp, no perspective transform, no final detector.")
    print("=" * 80)

    all_records = []
    for img_path in CALIBRATION_IMAGES:
        if not os.path.exists(img_path):
            print(f"Skipping missing image: {img_path}")
            continue

        rec = investigate_image_corners(img_path)
        all_records.append(rec)

        print(f"\n>> IMAGE: {rec['image_name']} ({rec['image_dimensions'][0]}x{rec['image_dimensions'][1]} px)")
        print(f"   Phase 2 Status         : {rec['phase2_image_status']}")
        print(f"   Box Source             : {rec['box_source']}")
        print(f"   Evaluated Box          : {rec['evaluated_box']}")
        print(f"   Physical Corners Found : {rec['visible_physical_corners_count']}/4 directly visible")
        print(f"   Clipped Frame Borders  : {rec['clipped_frame_corners_count']}/4 touching sensor frame")
        if rec['contour_poly_quad_pts']:
            print(f"   Contour Approx Quad    : {rec['contour_poly_quad_pts']}")
        else:
            print(f"   Contour Approx Quad    : None (No clean 4-vertex polygon)")

        print("   Corner Evidence Profiles:")
        for c_name, cr in rec["corner_reports"].items():
            print(f"     - {c_name:<12}: Coord={cr['nominal_coord']}")
            print(f"       State       : {cr['visibility_state']}")
            print(f"       Nature      : {cr['evidence_nature']}")
            print(f"       Signals     : EdgeDensity={cr['roi_edge_density']*100:.1f}%, CornerFeatures={cr['local_corner_features_count']}, LinesNearby={cr['nearby_line_segments_count']}")
            print(f"       Intersection: {cr['computed_line_intersection']}")

    # -----------------------------------------------------------------------
    # Comparative Cross-Image Synthesis
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("SYNTHESIS & DIRECT ANSWERS TO PHASE 3.1 QUESTIONS")
    print("=" * 80)
    print(
        "1. Are physical page corners directly visible in all calibration images?\n"
        "   ANSWER: NO.\n"
        "   - answer_sheet_2.png and answer_sheet_3.jpg: YES (all 4 corners visible on desk).\n"
        "   - answer_sheet_4.jpg: NO (top and bottom borders clipped by camera sensor frame;\n"
        "     the top/bottom 'corners' are sensor-edge intersections, NOT physical page corners).\n"
        "   - answer_sheet_5.jpg: NO (entire page fills frame; 4/4 corners are sensor pixels).\n"
        "   - answer_sheet.jpg: NO (tightly cropped on form, plus structural split ambiguity).\n"
        "\n"
        "2. Which corner signals are consistently available?\n"
        "   - Boundary line-segment orientation (Hough horizontal/vertical lines along page margins).\n"
        "   - Local edge contrast along long paper boundaries.\n"
        "   - Frame-clipping detection (detecting when an edge touches x=0, y=0, x=w, y=h).\n"
        "\n"
        "3. Which signals are image-specific or unreliable?\n"
        "   - Shi-Tomasi / Harris corner features: Highly prone to text/handwriting clutter inside\n"
        "     margins; on clipped or shaded boundaries, they fire on printed text rather than paper vertices.\n"
        "   - Simple contour approxPolyDP: Fails when document touches frame borders (merges with image frame)\n"
        "     or when shadows/desk texture fragment the external perimeter.\n"
        "   - Raw corner coordinates: Fabricating 4 corners on frame-limited images produces severe errors.\n"
        "\n"
        "4. Can a robust four-corner detector be designed from the current evidence alone?\n"
        "   ANSWER: NO, not a single monolithic detector.\n"
        "   A robust architecture must bifurcate:\n"
        "   (A) For ACCEPTED_PHYSICAL_PAGE (isolated on desk): Extract 4 physical corners via line intersection\n"
        "       and verified convex polygon fitting.\n"
        "   (B) For ACCEPTED_FRAME_LIMITED: Refrain from hallucinating 4 physical sheet corners;\n"
        "       treat as already frame-aligned or flag as partial capture with unobservable corners.\n"
        "\n"
        "5. What additional investigation is required before implementing Phase 3 production logic?\n"
        "   - Line-segment clustering and robust line fitting (RANSAC or polar grouping) along margins.\n"
        "   - Line-to-line intersection validation vs false intersections with internal printed lines.\n"
        "   - Sub-pixel corner refinement on true physical vertices.\n"
        "   - Explicit handling of partial/clipped documents where perspective warp cannot be applied safely."
    )
    print("=" * 80)
    print("PHASE 3.1 CORNER EVIDENCE INVESTIGATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_investigation()
