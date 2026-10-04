"""
phase3/03_four_corner_hypothesis_validation.py

AI-EVAL PHASE 3.3: FOUR-CORNER HYPOTHESIS VALIDATION
====================================================

PURPOSE:
Investigate how competing four-boundary-line hypotheses should be validated
before perspective transformation is considered safe.

GUARDRAILS:
- INVESTIGATION ONLY.
- Do NOT build a production scanner.
- Do NOT implement perspective correction or warp.
- Do NOT call cv2.getPerspectiveTransform() or cv2.warpPerspective().
- Do NOT freeze universal numerical thresholds, weights, or scoring formulas.
- Do NOT modify any Phase 2 or Phase 3.1/3.2 frozen files.

KEY INVESTIGATION PILLARS:
1. Multi-Line Hypothesis Construction (Combinations of candidate margin lines)
2. Four-Corner Geometric Validity (Convexity, self-intersection, ordering, vanishing perspective)
3. Content Enclosure & Containment (Testing whether active document content lies inside/outside)
4. Multi-Signal Physical Plausibility:
   - Step contrast (Delta V / Delta S)
   - Line segment support along edges
   - Content leak outside hypothesis (detecting inner printed boxes)
   - Exterior background consistency
5. Ambiguity Handling (Explicitly marking competing or unresolved quads as AMBIGUOUS)
6. Frame-Limited & Incomplete Capture Audit (Refraining from corner hallucination)
"""

import os
import sys
import math
import importlib.util
from typing import Dict, List, Tuple, Optional, Any
from itertools import product
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# ---------------------------------------------------------------------------
# Dynamic Import of Phase 2.13 (Preserving Frozen Files)
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
# Paths and Calibration Images
# ---------------------------------------------------------------------------
OUTPUT_DIR = os.path.join(ROOT_DIR, "phase3", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CALIBRATION_IMAGES = [
    "images/answer_sheet.jpg",
    "images/answer_sheet_2.png",
    "images/answer_sheet_3.jpg",
    "images/answer_sheet_4.jpg",
    "images/answer_sheet_5.jpg",
]


# ===========================================================================
# 1. PARAMETRIC LINE UTILITIES
# ===========================================================================

class Line2D:
    """Parametric line: A*x + B*y + C = 0 with A^2 + B^2 = 1."""
    def __init__(self, A: float, B: float, C: float, label: str = "", segments: Optional[List[Tuple[float, float, float, float]]] = None):
        norm = math.hypot(A, B)
        if norm > 1e-9:
            self.A = A / norm
            self.B = B / norm
            self.C = C / norm
        else:
            self.A, self.B, self.C = 1.0, 0.0, 0.0
        self.label = label
        self.segments = segments or []

    @property
    def angle_deg(self) -> float:
        ang = math.degrees(math.atan2(self.A, -self.B))
        return (ang + 180.0) % 180.0

    @property
    def is_horizontal(self) -> bool:
        a = self.angle_deg
        return a < 45.0 or a > 135.0

    def distance_to_point(self, x: float, y: float) -> float:
        return abs(self.A * x + self.B * y + self.C)

    def __repr__(self) -> str:
        return f"Line2D({self.label}: {self.A:.3f}x+{self.B:.3f}y+{self.C:.1f}=0)"


def intersect_lines(l1: Line2D, l2: Line2D) -> Optional[Tuple[float, float]]:
    det = l1.A * l2.B - l1.B * l2.A
    if abs(det) < 1e-4:
        return None
    x = (l1.B * l2.C - l2.B * l1.C) / det
    y = (l2.A * l1.C - l1.A * l2.C) / det
    return (float(x), float(y))


def line_from_points(p1: Tuple[float, float], p2: Tuple[float, float], label: str = "") -> Line2D:
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return Line2D(dy, -dx, -(dy * p1[0] - dx * p1[1]), label=label)


def fit_line_pca(points: np.ndarray, label: str = "") -> Optional[Line2D]:
    if len(points) < 2:
        return None
    mean = np.mean(points, axis=0)
    centered = points - mean
    cov = np.cov(centered, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    dir_vec = eigvecs[:, -1]
    A, B = -dir_vec[1], dir_vec[0]
    C = -(A * mean[0] + B * mean[1])
    return Line2D(A, B, C, label=label)


def fit_line_ransac(
    segments: List[Tuple[float, float, float, float, float]],
    dist_threshold: float = 6.0,
    max_iters: int = 80,
    label: str = ""
) -> Tuple[Optional[Line2D], float]:
    """Fit line with RANSAC; returns (FittedLine, inlier_ratio)."""
    if not segments:
        return None, 0.0
    pts = []
    for s in segments:
        x1, y1, x2, y2, l = s
        steps = max(3, int(l / 15.0))
        for t in np.linspace(0.0, 1.0, steps):
            pts.append([x1 + t * (x2 - x1), y1 + t * (y2 - y1)])
    pts = np.array(pts, dtype=np.float64)
    if len(pts) < 4:
        s = segments[0]
        l = line_from_points((s[0], s[1]), (s[2], s[3]), label=label)
        return l, 1.0

    best_inliers = []
    rng = np.random.RandomState(42)
    for _ in range(max_iters):
        idx = rng.choice(len(pts), 2, replace=False)
        p1, p2 = pts[idx[0]], pts[idx[1]]
        if np.hypot(p2[0] - p1[0], p2[1] - p1[1]) < 5.0:
            continue
        c_line = line_from_points((p1[0], p1[1]), (p2[0], p2[1]))
        dists = np.abs(c_line.A * pts[:, 0] + c_line.B * pts[:, 1] + c_line.C)
        inliers = np.where(dists <= dist_threshold)[0]
        if len(inliers) > len(best_inliers):
            best_inliers = inliers

    if len(best_inliers) < 3:
        return fit_line_pca(pts, label=label), 0.0
    inlier_ratio = float(len(best_inliers) / len(pts))
    return fit_line_pca(pts[best_inliers], label=label), inlier_ratio


# ===========================================================================
# 2. MULTI-LINE CANDIDATE GENERATION PER MARGIN
# ===========================================================================

def extract_margin_line_candidates(
    image: np.ndarray,
    roi_bbox: Tuple[int, int, int, int]
) -> Dict[str, List[Line2D]]:
    """
    Extract multiple competing line candidates for each margin side (TOP, BOTTOM, LEFT, RIGHT).
    Generates:
    - OUTER_LINE (closest to exterior candidate perimeter)
    - INNER_LINE (recessed inside page; e.g. table rule)
    """
    h_img, w_img = image.shape[:2]
    rx, ry, rw, rh = roi_bbox
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 140)

    min_l = max(30, int(min(rw, rh) * 0.05))
    raw_lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=40, minLineLength=min_l, maxLineGap=15)
    
    margin_segs = {"TOP": [], "BOTTOM": [], "LEFT": [], "RIGHT": []}
    if raw_lines is not None:
        band_x = max(25, int(rw * 0.12))
        band_y = max(25, int(rh * 0.12))
        for l in raw_lines.reshape(-1, 4):
            x1, y1, x2, y2 = [float(v) for v in l]
            length = math.hypot(x2 - x1, y2 - y1)
            if length < min_l:
                continue
            mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            angle = math.degrees(math.atan2(abs(y2 - y1), abs(x2 - x1)))

            if angle < 35.0: # Horizontal
                if abs(my - ry) <= band_y:
                    margin_segs["TOP"].append((x1, y1, x2, y2, length))
                elif abs(my - (ry + rh)) <= band_y:
                    margin_segs["BOTTOM"].append((x1, y1, x2, y2, length))
            elif angle > 55.0: # Vertical
                if abs(mx - rx) <= band_x:
                    margin_segs["LEFT"].append((x1, y1, x2, y2, length))
                elif abs(mx - (rx + rw)) <= band_x:
                    margin_segs["RIGHT"].append((x1, y1, x2, y2, length))

    line_candidates: Dict[str, List[Line2D]] = {"TOP": [], "BOTTOM": [], "LEFT": [], "RIGHT": []}

    for side in ["TOP", "BOTTOM", "LEFT", "RIGHT"]:
        segs = margin_segs[side]
        if not segs:
            continue
        
        # Partition into outer vs inner
        outer_s, inner_s = [], []
        if side == "TOP":
            split_y = ry + 0.04 * rh
            for s in segs:
                (outer_s if (s[1]+s[3])/2.0 <= split_y else inner_s).append(s)
        elif side == "BOTTOM":
            split_y = (ry + rh) - 0.04 * rh
            for s in segs:
                (outer_s if (s[1]+s[3])/2.0 >= split_y else inner_s).append(s)
        elif side == "LEFT":
            split_x = rx + 0.04 * rw
            for s in segs:
                (outer_s if (s[0]+s[2])/2.0 <= split_x else inner_s).append(s)
        elif side == "RIGHT":
            split_x = (rx + rw) - 0.04 * rw
            for s in segs:
                (outer_s if (s[0]+s[2])/2.0 >= split_x else inner_s).append(s)

        # Fit outer line candidate
        if outer_s:
            line_o, ratio_o = fit_line_ransac(outer_s, label=f"{side}_OUTER")
            if line_o:
                line_candidates[side].append(line_o)
        elif segs:
            line_o, ratio_o = fit_line_ransac(segs, label=f"{side}_DOMINANT")
            if line_o:
                line_candidates[side].append(line_o)

        # Fit inner line candidate if distinct from outer
        if inner_s:
            line_i, ratio_i = fit_line_ransac(inner_s, label=f"{side}_INNER")
            if line_i:
                # Check if spatially separated from outer
                if not line_candidates[side] or abs(line_candidates[side][0].C - line_i.C) > 8.0:
                    line_candidates[side].append(line_i)

    return line_candidates


# ===========================================================================
# 3. QUADRILATERAL GEOMETRIC VALIDATION
# ===========================================================================

def validate_quadrilateral_geometry(
    corners: Dict[str, Tuple[float, float]],
    image_shape: Tuple[int, int],
    roi_bbox: Tuple[int, int, int, int]
) -> Dict[str, Any]:
    """
    Check pure mathematical quadrilateral geometry:
    - 4 corners exist
    - Strict convexity & clockwise ordering
    - Opposite side divergence / convergence (perspective consistency)
    - Aspect ratio & area reasonableness relative to ROI
    """
    h_img, w_img = image_shape[:2]
    rx, ry, rw, rh = roi_bbox
    roi_area = float(rw * rh)

    tl = corners.get("TOP_LEFT")
    tr = corners.get("TOP_RIGHT")
    br = corners.get("BOTTOM_RIGHT")
    bl = corners.get("BOTTOM_LEFT")

    if not (tl and tr and br and bl):
        return {
            "is_geometrically_valid": False,
            "failure_reason": "Missing one or more corner coordinates",
            "is_convex": False,
            "area": 0.0,
            "area_ratio": 0.0,
        }

    pts = np.array([tl, tr, br, bl], dtype=np.float32)

    # 1. Clockwise cross-product convexity check
    # Vectors around perimeter: TL->TR, TR->BR, BR->BL, BL->TL
    v = [pts[(i + 1) % 4] - pts[i] for i in range(4)]
    crosses = [v[i][0] * v[(i + 1) % 4][1] - v[i][1] * v[(i + 1) % 4][0] for i in range(4)]
    
    # Strictly positive (clockwise) or strictly negative (counterclockwise)
    all_pos = all(c > 1e-3 for c in crosses)
    all_neg = all(c < -1e-3 for c in crosses)
    is_convex = all_pos or all_neg
    has_self_intersection = not is_convex

    # 2. Polygon area
    area = float(cv2.contourArea(pts)) if is_convex else 0.0
    area_ratio = (area / roi_area) if roi_area > 0 else 0.0

    # 3. Interior angles (in degrees)
    interior_angles = []
    for i in range(4):
        p_prev = pts[(i - 1) % 4]
        p_curr = pts[i]
        p_next = pts[(i + 1) % 4]
        v1 = p_prev - p_curr
        v2 = p_next - p_curr
        cos_th = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9)
        cos_th = np.clip(cos_th, -1.0, 1.0)
        interior_angles.append(float(np.degrees(np.arccos(cos_th))))

    # 4. Opposite side parallelism / perspective convergence
    # Top side vector vs Bottom side vector
    v_top = pts[1] - pts[0]
    v_bottom = pts[2] - pts[3]
    ang_tb = abs(math.degrees(math.atan2(v_top[1], v_top[0]) - math.atan2(v_bottom[1], v_bottom[0]))) % 180.0
    if ang_tb > 90.0: ang_tb = 180.0 - ang_tb

    # Left side vector vs Right side vector
    v_left = pts[3] - pts[0]
    v_right = pts[2] - pts[1]
    ang_lr = abs(math.degrees(math.atan2(v_left[1], v_left[0]) - math.atan2(v_right[1], v_right[0]))) % 180.0
    if ang_lr > 90.0: ang_lr = 180.0 - ang_lr

    # Check whether corners are reasonably bounded
    in_bounds = all(-0.15 * w_img <= p[0] <= 1.15 * w_img and -0.15 * h_img <= p[1] <= 1.15 * h_img for p in pts)

    is_valid = is_convex and in_bounds and (area_ratio > 0.3)

    return {
        "is_geometrically_valid": is_valid,
        "is_convex": is_convex,
        "has_self_intersection": has_self_intersection,
        "interior_angles": interior_angles,
        "opposite_angle_diffs": {"top_bottom_deg": ang_tb, "left_right_deg": ang_lr},
        "area": area,
        "area_ratio_vs_roi": area_ratio,
        "in_bounds": in_bounds,
        "failure_reason": None if is_valid else ("Non-convex or self-intersecting" if not is_convex else "Out of bounds or degenerate area")
    }


# ===========================================================================
# 4. PHYSICAL PLAUSIBILITY & CONTENT ENCLOSURE VALIDATION
# ===========================================================================

def validate_physical_plausibility(
    quad_corners: Dict[str, Tuple[float, float]],
    margin_lines: Dict[str, Line2D],
    image: np.ndarray,
    roi_bbox: Tuple[int, int, int, int]
) -> Dict[str, Any]:
    """
    Evaluates physical plausibility using multiple independent criteria:
    1. Orthogonal Brightness Step (Delta V) on each side
    2. Content leak outside quad: active gradient content outside this hypothesis
    3. Exterior background consistency: is exterior dark desk or white paper?
    4. Distance to candidate ROI perimeter
    """
    h_img, w_img = image.shape[:2]
    rx, ry, rw, rh = roi_bbox
    cx, cy = rx + rw / 2.0, ry + rh / 2.0

    pts = np.array([quad_corners[c] for c in ["TOP_LEFT", "TOP_RIGHT", "BOTTOM_RIGHT", "BOTTOM_LEFT"]], dtype=np.int32)
    
    # 1. Mask of the quad hypothesis
    quad_mask = np.zeros((h_img, w_img), dtype=np.uint8)
    cv2.fillPoly(quad_mask, [pts], 255)

    # 2. Content Leak Analysis: Check gradient activity in ROI that falls OUTSIDE this quad
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.hypot(sobel_x, sobel_y)
    
    # ROI active content mask
    roi_mask = np.zeros((h_img, w_img), dtype=np.uint8)
    roi_mask[ry:ry+rh, rx:rx+rw] = 255
    
    outside_quad_in_roi = cv2.bitwise_and(roi_mask, cv2.bitwise_not(quad_mask))
    leak_pixels = np.count_nonzero((grad_mag > 40.0) & (outside_quad_in_roi > 0))
    total_roi_active = max(1, np.count_nonzero((grad_mag > 40.0) & (roi_mask > 0)))
    leak_ratio = float(leak_pixels / total_roi_active)

    # 3. Exterior vs Interior sampling for all 4 boundary lines
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    v_chan = hsv[:, :, 2].astype(np.float32)
    s_chan = hsv[:, :, 1].astype(np.float32)

    line_steps = {}
    physical_side_count = 0
    printed_side_count = 0

    for side, line in margin_lines.items():
        # Sample 20 points along the quad side segment
        p1_name = "TOP_LEFT" if side in ("TOP", "LEFT") else "BOTTOM_RIGHT"
        p2_name = "TOP_RIGHT" if side == "TOP" else ("BOTTOM_LEFT" if side in ("BOTTOM", "LEFT") else "BOTTOM_RIGHT")
        if side == "LEFT": p1_name, p2_name = "TOP_LEFT", "BOTTOM_LEFT"
        elif side == "RIGHT": p1_name, p2_name = "TOP_RIGHT", "BOTTOM_RIGHT"
        elif side == "BOTTOM": p1_name, p2_name = "BOTTOM_LEFT", "BOTTOM_RIGHT"

        p1 = quad_corners[p1_name]
        p2 = quad_corners[p2_name]

        # Normal vector pointing outward from center
        mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
        out_vec = (mx - cx, my - cy)
        norm_A = line.A if (line.A * out_vec[0] + line.B * out_vec[1]) >= 0 else -line.A
        norm_B = line.B if (line.A * out_vec[0] + line.B * out_vec[1]) >= 0 else -line.B

        ext_vals = []
        int_vals = []
        for t in np.linspace(0.15, 0.85, 15):
            px = p1[0] + t * (p2[0] - p1[0])
            py = p1[1] + t * (p2[1] - p1[1])
            # Exterior sample (+12 px normal)
            ex_x, ex_y = int(round(px + norm_A * 12.0)), int(round(py + norm_B * 12.0))
            # Interior sample (-12 px normal)
            in_x, in_y = int(round(px - norm_A * 12.0)), int(round(py - norm_B * 12.0))

            if 0 <= ex_x < w_img and 0 <= ex_y < h_img: ext_vals.append(v_chan[ex_y, ex_x])
            if 0 <= in_x < w_img and 0 <= in_y < h_img: int_vals.append(v_chan[in_y, in_x])

        mean_ext = float(np.mean(ext_vals)) if ext_vals else 0.0
        mean_int = float(np.mean(int_vals)) if int_vals else 0.0
        delta_v = mean_int - mean_ext

        if delta_v > 25.0:
            nature = "PHYSICAL_PAPER_BOUNDARY"
            physical_side_count += 1
        elif abs(delta_v) < 12.0 and mean_ext > 100.0:
            nature = "PRINTED_TABLE_RULE"
            printed_side_count += 1
        else:
            nature = "AMBIGUOUS"

        line_steps[side] = {
            "nature": nature,
            "delta_v": delta_v,
            "mean_ext_v": mean_ext,
            "mean_int_v": mean_int
        }

    # Qualitative classification of the hypothesis
    if physical_side_count >= 3 and leak_ratio < 0.05:
        hyp_class = "PHYSICALLY_PLAUSIBLE_PAPER_PAGE"
        rationale = f"{physical_side_count}/4 physical sides with strong contrast steps; content fully enclosed (leak={leak_ratio:.1%})."
    elif printed_side_count >= 2 or leak_ratio > 0.10:
        hyp_class = "INTERNAL_PRINTED_ENVELOPE"
        rationale = f"Excludes significant active content (leak={leak_ratio:.1%}) or bounded by printed rules ({printed_side_count} printed sides)."
    else:
        hyp_class = "AMBIGUOUS_OR_UNCONFIRMED"
        rationale = f"Inconclusive boundary signals ({physical_side_count} physical, {printed_side_count} printed; leak={leak_ratio:.1%})."

    return {
        "hypothesis_classification": hyp_class,
        "physical_sides_count": physical_side_count,
        "printed_sides_count": printed_side_count,
        "content_leak_ratio": leak_ratio,
        "side_steps": line_steps,
        "rationale": rationale
    }


# ===========================================================================
# 5. COMPLETE HYPOTHESIS VALIDATION ENGINE FOR SINGLE IMAGE
# ===========================================================================

def run_hypothesis_validation(image_path: str) -> Dict[str, Any]:
    """Execute complete Phase 3.3 four-corner hypothesis validation for an image."""
    img_name = os.path.basename(image_path)
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Failed to load image: {image_path}")
    h_img, w_img = image.shape[:2]

    # 1. Run Phase 2.13 Document Region Detector
    p2_result = detect_and_validate_document_region(image_path)
    image_state = p2_result.image_status
    selected_id = p2_result.selected_candidate_id
    selected_box = p2_result.selected_box

    if selected_box:
        roi_bbox = selected_box
        roi_source = f"PHASE_2_SELECTED ({selected_id})"
    else:
        if p2_result.candidate_profiles:
            roi_bbox = p2_result.candidate_profiles[0].box
            roi_source = f"PHASE_2_CANDIDATE_0 ({p2_result.candidate_profiles[0].candidate_id})"
        else:
            roi_bbox = (0, 0, w_img, h_img)
            roi_source = "FULL_IMAGE_FRAME_FALLBACK"

    rx, ry, rw, rh = roi_bbox

    # 2. Check for frame clipping
    frame_clipped_sides = []
    if abs(ry) < 4: frame_clipped_sides.append("TOP")
    if abs((ry + rh) - h_img) < 4: frame_clipped_sides.append("BOTTOM")
    if abs(rx) < 4: frame_clipped_sides.append("LEFT")
    if abs((rx + rw) - w_img) < 4: frame_clipped_sides.append("RIGHT")

    # 3. Extract multiple candidate lines per margin
    line_candidates = extract_margin_line_candidates(image, roi_bbox)

    # 4. Formulate combinations of 4 lines (TOP x BOTTOM x LEFT x RIGHT)
    top_lines = line_candidates.get("TOP", [])
    bot_lines = line_candidates.get("BOTTOM", [])
    lef_lines = line_candidates.get("LEFT", [])
    rig_lines = line_candidates.get("RIGHT", [])

    hypothesis_reports = []
    
    if top_lines and bot_lines and lef_lines and rig_lines:
        for t_line, b_line, l_line, r_line in product(top_lines, bot_lines, lef_lines, rig_lines):
            comb_name = f"{t_line.label} + {b_line.label} + {l_line.label} + {r_line.label}"
            
            # Compute intersections
            c_tl = intersect_lines(t_line, l_line)
            c_tr = intersect_lines(t_line, r_line)
            c_br = intersect_lines(b_line, r_line)
            c_bl = intersect_lines(b_line, l_line)

            corners = {"TOP_LEFT": c_tl, "TOP_RIGHT": c_tr, "BOTTOM_RIGHT": c_br, "BOTTOM_LEFT": c_bl}
            margin_lines = {"TOP": t_line, "BOTTOM": b_line, "LEFT": l_line, "RIGHT": r_line}

            # Geometric validation
            geom_val = validate_quadrilateral_geometry(corners, (h_img, w_img), roi_bbox)

            # Physical plausibility
            if geom_val["is_geometrically_valid"]:
                phys_val = validate_physical_plausibility(corners, margin_lines, image, roi_bbox)
            else:
                phys_val = {
                    "hypothesis_classification": "GEOMETRICALLY_INVALID",
                    "physical_sides_count": 0,
                    "printed_sides_count": 0,
                    "content_leak_ratio": 0.0,
                    "side_steps": {},
                    "rationale": geom_val["failure_reason"]
                }

            hypothesis_reports.append({
                "combination_name": comb_name,
                "corners": corners,
                "geometry": geom_val,
                "plausibility": phys_val,
            })
    else:
        # Incomplete lines
        missing = [side for side in ["TOP", "BOTTOM", "LEFT", "RIGHT"] if not line_candidates.get(side)]
        hypothesis_reports.append({
            "combination_name": "INCOMPLETE_MARGIN_LINES",
            "corners": {},
            "geometry": {"is_geometrically_valid": False, "failure_reason": f"Missing margin lines: {missing}"},
            "plausibility": {"hypothesis_classification": "UNAVAILABLE", "rationale": f"Missing margins: {missing}"}
        })

    # 5. Image-Level Hypothesis Arbitration
    plausible_physical_quads = [
        h for h in hypothesis_reports
        if h["geometry"]["is_geometrically_valid"] and h["plausibility"]["hypothesis_classification"] == "PHYSICALLY_PLAUSIBLE_PAPER_PAGE"
    ]
    internal_printed_quads = [
        h for h in hypothesis_reports
        if h["geometry"]["is_geometrically_valid"] and h["plausibility"]["hypothesis_classification"] == "INTERNAL_PRINTED_ENVELOPE"
    ]

    if frame_clipped_sides:
        overall_verdict = "FRAME_LIMITED_UNOBSERVABLE_CORNERS"
        verdict_rationale = f"Document edges {frame_clipped_sides} are clipped by camera frame; physical corners unobservable."
        winning_hypothesis = None
    elif len(plausible_physical_quads) == 1:
        overall_verdict = "VALIDATED_PHYSICAL_PAGE_QUAD"
        winning_hypothesis = plausible_physical_quads[0]
        verdict_rationale = f"Single unambiguous physical page hypothesis validated ({winning_hypothesis['combination_name']})."
    elif len(plausible_physical_quads) > 1:
        overall_verdict = "AMBIGUOUS_COMPETING_PHYSICAL_QUADS"
        winning_hypothesis = None
        verdict_rationale = f"{len(plausible_physical_quads)} competing quads exhibit physical boundary signals; no single winner declared."
    elif internal_printed_quads and not plausible_physical_quads:
        overall_verdict = "INTERNAL_PRINTED_QUAD_ONLY (NO_PHYSICAL_CORNERS)"
        winning_hypothesis = None
        verdict_rationale = "Only internal printed form quads detected; physical paper boundaries absent or cropped away."
    else:
        overall_verdict = "NO_VALID_QUAD_HYPOTHESIS"
        winning_hypothesis = None
        verdict_rationale = "No geometrically valid four-corner hypothesis could be constructed."

    # 6. Generate Diagnostic Visualization
    vis_path = os.path.join(OUTPUT_DIR, f"phase3_hyp_val_{img_name}.png")
    generate_validation_visualization(
        image,
        roi_bbox,
        hypothesis_reports,
        overall_verdict,
        frame_clipped_sides,
        img_name,
        vis_path
    )

    return {
        "image_name": img_name,
        "image_state": image_state,
        "roi_source": roi_source,
        "roi_bbox": roi_bbox,
        "frame_clipped_sides": frame_clipped_sides,
        "hypotheses_evaluated_count": len(hypothesis_reports),
        "plausible_physical_quads_count": len(plausible_physical_quads),
        "internal_printed_quads_count": len(internal_printed_quads),
        "overall_verdict": overall_verdict,
        "verdict_rationale": verdict_rationale,
        "winning_hypothesis": winning_hypothesis,
        "all_hypotheses": hypothesis_reports,
        "visualization_path": vis_path
    }


# ===========================================================================
# 6. VISUALIZATION GENERATOR
# ===========================================================================

def generate_validation_visualization(
    image: np.ndarray,
    roi_bbox: Tuple[int, int, int, int],
    hypotheses: List[Dict[str, Any]],
    verdict: str,
    frame_clipped_sides: List[str],
    img_name: str,
    output_path: str
):
    fig, ax = plt.subplots(figsize=(10, 12))
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    ax.imshow(rgb)
    rx, ry, rw, rh = roi_bbox
    h_img, w_img = image.shape[:2]

    # Draw Phase 2 ROI
    rect = patches.Rectangle((rx, ry), rw, rh, linewidth=2, edgecolor='cyan', facecolor='none', linestyle='--', label='Phase 2 ROI')
    ax.add_patch(rect)

    # Color scheme for hypothesis types
    colors = {
        "PHYSICALLY_PLAUSIBLE_PAPER_PAGE": ("lime", "-", 3.0),
        "INTERNAL_PRINTED_ENVELOPE": ("orange", "--", 2.0),
        "AMBIGUOUS_OR_UNCONFIRMED": ("yellow", ":", 1.8),
        "GEOMETRICALLY_INVALID": ("red", ":", 1.5)
    }

    drawn_labels = set()
    for hyp in hypotheses:
        corners = hyp.get("corners", {})
        if len(corners) == 4 and all(c is not None for c in corners.values()):
            pts = [corners["TOP_LEFT"], corners["TOP_RIGHT"], corners["BOTTOM_RIGHT"], corners["BOTTOM_LEFT"]]
            poly_x = [p[0] for p in pts] + [pts[0][0]]
            poly_y = [p[1] for p in pts] + [pts[0][1]]
            c_type = hyp["plausibility"]["hypothesis_classification"]
            color, ls, lw = colors.get(c_type, ("magenta", "-", 1.5))
            
            lbl = c_type if c_type not in drawn_labels else ""
            if lbl: drawn_labels.add(c_type)
            ax.plot(poly_x, poly_y, color=color, linestyle=ls, linewidth=lw, label=lbl if lbl else None)

            # Draw corner markers for physical quad
            if c_type == "PHYSICALLY_PLAUSIBLE_PAPER_PAGE":
                for c_name, cp in corners.items():
                    ax.plot(cp[0], cp[1], marker='o', markersize=8, markerfacecolor='cyan', markeredgecolor='black')
                    ax.text(cp[0] + 12, cp[1] - 12, c_name, color='white', fontsize=7,
                            bbox=dict(boxstyle="round,pad=0.2", facecolor="black", alpha=0.75))

    # Annotate Frame-Clipped
    if frame_clipped_sides:
        ax.text(20, h_img - 30, f"FRAME CLIPPED: {', '.join(frame_clipped_sides)} (Corners Unobservable)",
                color="white", fontsize=9, fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.3", facecolor="crimson", alpha=0.85))

    ax.set_title(f"{img_name}: Four-Corner Hypothesis Validation\nVerdict: {verdict}", fontsize=11, fontweight='bold')
    ax.legend(loc='upper right', fontsize=8, framealpha=0.85)
    ax.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=120)
    plt.close()


# ===========================================================================
# 7. SCRIPT ENTRYPOINT & AUDIT EXECUTION
# ===========================================================================

def main():
    print("=" * 80)
    print("AI-EVAL PHASE 3.3: FOUR-CORNER HYPOTHESIS VALIDATION")
    print("=" * 80)
    print("Focus: Validating competing 4-boundary hypotheses before warp is considered")
    print("Guardrails: Investigation only; NO warp; NO perspective transform; NO final thresholds.")
    print("-" * 80)

    results = []
    for rel_path in CALIBRATION_IMAGES:
        full_path = os.path.join(ROOT_DIR, rel_path)
        print(f"\n>> Validating: {rel_path}...")
        try:
            res = run_hypothesis_validation(full_path)
            results.append(res)
            print(f"   Image State       : {res['image_state']}")
            print(f"   ROI BBox          : {res['roi_bbox']} ({res['roi_source']})")
            print(f"   Hypotheses Tested : {res['hypotheses_evaluated_count']}")
            print(f"   Physical Quads    : {res['plausible_physical_quads_count']}")
            print(f"   Printed Quads     : {res['internal_printed_quads_count']}")
            print(f"   Overall Verdict   : {res['overall_verdict']}")
            print(f"   Rationale         : {res['verdict_rationale']}")
            print("   Detailed Hypotheses Breakdown:")
            for idx, hyp in enumerate(res["all_hypotheses"]):
                c_name = hyp["combination_name"]
                c_class = hyp["plausibility"]["hypothesis_classification"]
                c_leak = hyp["plausibility"].get("content_leak_ratio", 0.0)
                c_phys = hyp["plausibility"].get("physical_sides_count", 0)
                print(f"     [{idx+1}] {c_name}")
                print(f"         Class: {c_class} | PhysSides: {c_phys}/4 | Leak: {c_leak:.1%}")
                if hyp["corners"]:
                    pts_str = ", ".join([f"{k}:({v[0]:.1f},{v[1]:.1f})" for k, v in hyp["corners"].items() if v])
                    print(f"         Corners: {pts_str}")

            if res["winning_hypothesis"]:
                win = res["winning_hypothesis"]
                print(f"   WINNING HYPOTHESIS: {win['combination_name']}")
                for c_name, cp in win["corners"].items():
                    print(f"     - {c_name:12s}: ({cp[0]:.1f}, {cp[1]:.1f})")
                print(f"     - Geometry       : Convex={win['geometry']['is_convex']}, AreaRatio={win['geometry']['area_ratio_vs_roi']:.2f}")
                print(f"     - Plausibility   : Leak={win['plausibility']['content_leak_ratio']:.1%}, PhysSides={win['plausibility']['physical_sides_count']}/4")

            print(f"   Overlay Saved     : {res['visualization_path']}")

        except Exception as e:
            print(f"   [ERROR] Failed validating {rel_path}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("PHASE 3.3 HYPOTHESIS VALIDATION SUMMARY")
    print("=" * 80)
    for res in results:
        print(f"Image: {res['image_name']:20s} | Verdict: {res['overall_verdict']:38s} | PhysQuads: {res['plausible_physical_quads_count']}")
    print("=" * 80)


if __name__ == "__main__":
    main()
