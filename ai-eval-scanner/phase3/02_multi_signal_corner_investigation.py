"""
phase3/02_multi_signal_corner_investigation.py

AI-EVAL PHASE 3.2: MULTI-SIGNAL CORNER CANDIDATE INVESTIGATION
==============================================================

PURPOSE:
Investigate whether physical page corners can be reconstructed reliably
from multiple boundary signals when corners are visible.

Focus primarily on the two images where physical page corners are visible:
- images/answer_sheet_2.png
- images/answer_sheet_3.jpg

Also investigate:
- images/answer_sheet_4.jpg & images/answer_sheet_5.jpg (Frame-limited cases)
- images/answer_sheet.jpg (Ambiguous/content envelope case)

INVESTIGATION MODULES:
A. Outer Margin Line Candidates (Position, orientation, length, continuity)
B. Robust Line Fitting (RANSAC vs direct PCA/least-squares; success & failure modes)
C. Line-Intersection Candidates (Intersect plausible pairs, compute corner points)
D. Outer-vs-Internal Disambiguation (Physical paper boundary vs printed table rule vs handwriting/shadow)
E. Quadrilateral Hypotheses (4-line/4-corner hypotheses, convexity, geometric consistency)
F. Frame-Limited Cases (Observable sides vs clipped corners, usable orientation/geometry)
G. Ambiguous Cases (Separating printed table box from missing physical boundary)

STRICT GUARDRAILS:
- INVESTIGATION ONLY.
- Do NOT build a production scanner.
- Do NOT implement perspective correction or warp.
- Do NOT call cv2.getPerspectiveTransform() or cv2.warpPerspective().
- Do NOT fabricate physical corners when evidence is missing or clipped.
- Do NOT treat image-frame corners as physical document corners.
- Do NOT freeze universal thresholds, scores, or weights.
- Do NOT modify any Phase 2 or Phase 3.1 frozen files.
"""

import os
import sys
import math
import importlib.util
from typing import Dict, List, Tuple, Optional, Any
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
# GEOMETRY & LINE UTILITIES
# ===========================================================================

class Line2D:
    """Parametric 2D line: A*x + B*y + C = 0 with A^2 + B^2 = 1."""
    def __init__(self, A: float, B: float, C: float, source: str = "", segments: Optional[List[Tuple[float, float, float, float]]] = None):
        norm = math.hypot(A, B)
        if norm > 1e-9:
            self.A = A / norm
            self.B = B / norm
            self.C = C / norm
        else:
            self.A = 1.0
            self.B = 0.0
            self.C = 0.0
        self.source = source
        self.segments = segments or []

    @property
    def angle_degrees(self) -> float:
        """Angle in degrees of the line direction vector (-B, A)."""
        angle = math.degrees(math.atan2(self.A, -self.B))
        return (angle + 180.0) % 180.0

    @property
    def is_horizontal(self) -> bool:
        # Near 0 or 180 deg (within 45 deg)
        ang = self.angle_degrees
        return ang < 45.0 or ang > 135.0

    @property
    def is_vertical(self) -> bool:
        return not self.is_horizontal

    def distance_to_point(self, x: float, y: float) -> float:
        return abs(self.A * x + self.B * y + self.C)

    def project_point(self, x: float, y: float) -> Tuple[float, float]:
        d = self.A * x + self.B * y + self.C
        return (x - self.A * d, y - self.B * d)

    def __repr__(self) -> str:
        return f"Line2D({self.A:.3f}x + {self.B:.3f}y + {self.C:.1f} = 0, {self.source})"


def intersect_lines(l1: Line2D, l2: Line2D) -> Optional[Tuple[float, float]]:
    """Compute Euclidean intersection of two 2D lines."""
    det = l1.A * l2.B - l1.B * l2.A
    if abs(det) < 1e-4:
        return None  # Lines are essentially parallel
    x = (l1.B * l2.C - l2.B * l1.C) / det
    y = (l2.A * l1.C - l1.A * l2.C) / det
    return (float(x), float(y))


def line_from_segment(x1: float, y1: float, x2: float, y2: float, source: str = "") -> Line2D:
    """Create a Line2D from two points."""
    dx = x2 - x1
    dy = y2 - y1
    # Line normal is (dy, -dx)
    A = dy
    B = -dx
    C = -(A * x1 + B * y1)
    return Line2D(A, B, C, source=source, segments=[(x1, y1, x2, y2)])


# ===========================================================================
# MODULE A: OUTER MARGIN LINE CANDIDATES & DETECTION
# ===========================================================================

def detect_margin_line_segments(
    image: np.ndarray,
    roi_bbox: Tuple[int, int, int, int]
) -> Dict[str, List[Tuple[float, float, float, float, float]]]:
    """
    Detect line segments in outer margin bands around the ROI bbox.
    Returns segments classified by margin side: 'TOP', 'BOTTOM', 'LEFT', 'RIGHT'.
    Each segment is (x1, y1, x2, y2, length).
    """
    h_img, w_img = image.shape[:2]
    rx, ry, rw, rh = roi_bbox
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Adaptive threshold / Canny edges
    edges = cv2.Canny(blur, 40, 140)
    
    # Run HoughLinesP
    min_line_len = max(30, int(min(rw, rh) * 0.05))
    max_line_gap = max(10, int(min(rw, rh) * 0.03))
    raw_lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=40, minLineLength=min_line_len, maxLineGap=max_line_gap)
    
    margin_segments: Dict[str, List[Tuple[float, float, float, float, float]]] = {
        "TOP": [], "BOTTOM": [], "LEFT": [], "RIGHT": []
    }
    
    if raw_lines is None:
        return margin_segments

    # Margin band margin tolerance: relative to ROI dimensions
    band_x = max(25, int(rw * 0.12))
    band_y = max(25, int(rh * 0.12))
    
    for l in raw_lines.reshape(-1, 4):
        x1, y1, x2, y2 = [float(v) for v in l]
        length = math.hypot(x2 - x1, y2 - y1)
        if length < min_line_len:
            continue
            
        mx = (x1 + x2) / 2.0
        my = (y1 + y2) / 2.0
        
        # Check angle
        angle = math.degrees(math.atan2(abs(y2 - y1), abs(x2 - x1)))
        
        # Horizontal-ish segment (angle < 35 deg)
        if angle < 35.0:
            # Check if near TOP margin
            if abs(my - ry) <= band_y:
                margin_segments["TOP"].append((x1, y1, x2, y2, length))
            # Check if near BOTTOM margin
            elif abs(my - (ry + rh)) <= band_y:
                margin_segments["BOTTOM"].append((x1, y1, x2, y2, length))
                
        # Vertical-ish segment (angle > 55 deg)
        elif angle > 55.0:
            # Check if near LEFT margin
            if abs(mx - rx) <= band_x:
                margin_segments["LEFT"].append((x1, y1, x2, y2, length))
            # Check if near RIGHT margin
            elif abs(mx - (rx + rw)) <= band_x:
                margin_segments["RIGHT"].append((x1, y1, x2, y2, length))

    # Sort each margin's segments by length descending
    for side in margin_segments:
        margin_segments[side].sort(key=lambda s: s[4], reverse=True)
        
    return margin_segments


# ===========================================================================
# MODULE B: ROBUST LINE FITTING (RANSAC VS PCA / LEAST-SQUARES)
# ===========================================================================

def fit_line_pca(points: np.ndarray, source: str = "PCA") -> Optional[Line2D]:
    """Fit a line to 2D points using PCA / total least squares."""
    if len(points) < 2:
        return None
    mean = np.mean(points, axis=0)
    centered = points - mean
    cov = np.cov(centered, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    # Principal direction has largest eigenvalue (last column in eigh)
    dir_vec = eigvecs[:, -1] # (dx, dy)
    # Normal is (-dy, dx)
    A = -dir_vec[1]
    B = dir_vec[0]
    C = -(A * mean[0] + B * mean[1])
    return Line2D(A, B, C, source=source)


def fit_line_ransac(
    segments: List[Tuple[float, float, float, float, float]],
    dist_threshold: float = 6.0,
    max_iters: int = 100,
    side: str = ""
) -> Tuple[Optional[Line2D], Dict[str, Any]]:
    """
    RANSAC line fitting from a set of line segments.
    Samples discrete points along each segment, runs RANSAC, and evaluates inliers.
    Returns: (FittedLine2D or None, diagnostic_dict)
    """
    diagnostics = {
        "status": "NO_SEGMENTS",
        "total_segments": len(segments),
        "total_points": 0,
        "inliers_count": 0,
        "inlier_ratio": 0.0,
        "iterations_run": 0,
        "failure_reason": None,
    }
    
    if not segments:
        diagnostics["failure_reason"] = "No segments available on this margin"
        return None, diagnostics
        
    # Sample points along segments
    pts = []
    for s in segments:
        x1, y1, x2, y2, length = s
        steps = max(3, int(length / 15.0))
        for t in np.linspace(0.0, 1.0, steps):
            pts.append([x1 + t * (x2 - x1), y1 + t * (y2 - y1)])
            
    pts = np.array(pts, dtype=np.float64)
    diagnostics["total_points"] = len(pts)
    
    if len(pts) < 4:
        # Fallback to direct segment line if only 1 segment
        s = segments[0]
        line = line_from_segment(s[0], s[1], s[2], s[3], source=f"DIRECT_{side}")
        diagnostics["status"] = "FALLBACK_DIRECT_SEGMENT"
        diagnostics["inliers_count"] = len(pts)
        diagnostics["inlier_ratio"] = 1.0
        return line, diagnostics

    # RANSAC loop
    best_inliers = []
    rng = np.random.RandomState(42) # Deterministic for audit reproducibility
    
    for iter_idx in range(max_iters):
        idx1, idx2 = rng.choice(len(pts), 2, replace=False)
        p1 = pts[idx1]
        p2 = pts[idx2]
        if np.hypot(p2[0] - p1[0], p2[1] - p1[1]) < 5.0:
            continue
            
        candidate_line = line_from_segment(p1[0], p1[1], p2[0], p2[1])
        # Compute distances for all points
        dists = np.abs(candidate_line.A * pts[:, 0] + candidate_line.B * pts[:, 1] + candidate_line.C)
        inliers = np.where(dists <= dist_threshold)[0]
        
        if len(inliers) > len(best_inliers):
            best_inliers = inliers

    diagnostics["iterations_run"] = max_iters
    
    if len(best_inliers) < max(4, int(len(pts) * 0.25)):
        # RANSAC failed to find consensus
        diagnostics["status"] = "RANSAC_NO_CONSENSUS"
        diagnostics["failure_reason"] = f"Low consensus inliers ({len(best_inliers)}/{len(pts)})"
        # Try full PCA as fallback
        pca_line = fit_line_pca(pts, source=f"PCA_FALLBACK_{side}")
        return pca_line, diagnostics

    inlier_pts = pts[best_inliers]
    refined_line = fit_line_pca(inlier_pts, source=f"RANSAC_{side}")
    
    diagnostics["status"] = "RANSAC_SUCCESS"
    diagnostics["inliers_count"] = len(best_inliers)
    diagnostics["inlier_ratio"] = float(len(best_inliers) / len(pts))
    return refined_line, diagnostics


# ===========================================================================
# MODULE D: OUTER-VS-INTERNAL DISAMBIGUATION
# ===========================================================================

def analyze_line_nature(
    line: Line2D,
    image: np.ndarray,
    roi_bbox: Tuple[int, int, int, int],
    side: str
) -> Dict[str, Any]:
    """
    Examines local appearance on the two sides of the line (exterior vs interior)
    to classify the nature of the line:
    - PHYSICAL_PAPER_BOUNDARY (high exterior/interior contrast step, exterior desk-like)
    - PRINTED_TABLE_RULE (interior to page, both sides paper-like)
    - SENSOR_FRAME_CUTOFF (line sits on the image frame)
    - AMBIGUOUS
    """
    h_img, w_img = image.shape[:2]
    rx, ry, rw, rh = roi_bbox
    
    # Distance to sensor border
    is_at_sensor_border = False
    if side == "TOP" and abs(line.distance_to_point(w_img / 2.0, 0)) < 4.0:
        is_at_sensor_border = True
    elif side == "BOTTOM" and abs(line.distance_to_point(w_img / 2.0, h_img - 1)) < 4.0:
        is_at_sensor_border = True
    elif side == "LEFT" and abs(line.distance_to_point(0, h_img / 2.0)) < 4.0:
        is_at_sensor_border = True
    elif side == "RIGHT" and abs(line.distance_to_point(w_img - 1, h_img / 2.0)) < 4.0:
        is_at_sensor_border = True
        
    if is_at_sensor_border:
        return {
            "nature": "SENSOR_FRAME_CUTOFF",
            "delta_brightness": 0.0,
            "exterior_mean_v": 0.0,
            "interior_mean_v": 0.0,
            "evidence": "Touches camera sensor frame directly; not an observable paper edge."
        }

    # Sample strip along the line
    # Determine sample points along ROI span
    if side in ("TOP", "BOTTOM"):
        xs = np.linspace(rx + 0.15 * rw, rx + 0.85 * rw, 25)
        # y = -(A*x + C)/B
        if abs(line.B) > 1e-4:
            ys = -(line.A * xs + line.C) / line.B
        else:
            ys = np.full_like(xs, ry if side == "TOP" else ry + rh)
    else: # LEFT, RIGHT
        ys = np.linspace(ry + 0.15 * rh, ry + 0.85 * rh, 25)
        if abs(line.A) > 1e-4:
            xs = -(line.B * ys + line.C) / line.A
        else:
            xs = np.full_like(ys, rx if side == "LEFT" else rx + rw)

    # Convert image to HSV
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    v_chan = hsv[:, :, 2].astype(np.float32)
    
    # Offset normal direction for interior vs exterior
    # Normal is (A, B). Determine whether +(A, B) points outward or inward
    # Point at center of ROI:
    cx, cy = rx + rw / 2.0, ry + rh / 2.0
    # Vector from center to a point on the line:
    test_px, test_py = xs[len(xs)//2], ys[len(ys)//2]
    outward_vec = (test_px - cx, test_py - cy)
    dot = line.A * outward_vec[0] + line.B * outward_vec[1]
    norm_A = line.A if dot >= 0 else -line.A
    norm_B = line.B if dot >= 0 else -line.B
    
    strip_dist = 12.0
    ext_vals = []
    int_vals = []
    
    for px, py in zip(xs, ys):
        # Exterior sample
        ex_x = int(round(px + norm_A * strip_dist))
        ex_y = int(round(py + norm_B * strip_dist))
        # Interior sample
        in_x = int(round(px - norm_A * strip_dist))
        in_y = int(round(py - norm_B * strip_dist))
        
        if 0 <= ex_x < w_img and 0 <= ex_y < h_img:
            ext_vals.append(v_chan[ex_y, ex_x])
        if 0 <= in_x < w_img and 0 <= in_y < h_img:
            int_vals.append(v_chan[in_y, in_x])
            
    mean_ext = float(np.mean(ext_vals)) if ext_vals else 0.0
    mean_int = float(np.mean(int_vals)) if int_vals else 0.0
    delta_v = mean_int - mean_ext # Paper interior is typically brighter than desk background
    
    # Qualitative categorization based on contrast step
    if delta_v > 20.0 and len(ext_vals) >= 10:
        nature = "PHYSICAL_PAPER_BOUNDARY"
        evidence = f"High step contrast (+{delta_v:.1f} V); dark exterior desk vs light paper."
    elif abs(delta_v) < 12.0 and mean_ext > 100.0 and mean_int > 100.0:
        nature = "PRINTED_TABLE_RULE"
        evidence = f"Low contrast step ({delta_v:+.1f} V); both sides light paper; likely printed rule."
    else:
        nature = "AMBIGUOUS"
        evidence = f"Moderate/inconclusive contrast ({delta_v:+.1f} V); lighting gradient or narrow border."
        
    return {
        "nature": nature,
        "delta_brightness": delta_v,
        "exterior_mean_v": mean_ext,
        "interior_mean_v": mean_int,
        "evidence": evidence
    }


# ===========================================================================
# MODULE C & E: LINE INTERSECTIONS & QUADRILATERAL HYPOTHESES
# ===========================================================================

def partition_margin_segments(
    segments: List[Tuple[float, float, float, float, float]],
    side: str,
    roi_bbox: Tuple[int, int, int, int]
) -> Tuple[List[Tuple[float, float, float, float, float]], List[Tuple[float, float, float, float, float]]]:
    """
    Partition segments on a margin into:
    - outer_segments: those lying closest to the exterior candidate perimeter.
    - inner_segments: those lying further inward towards the page content.
    """
    rx, ry, rw, rh = roi_bbox
    outer_segs = []
    inner_segs = []
    
    if side == "TOP":
        split_thresh = ry + 0.04 * rh
        for s in segments:
            my = (s[1] + s[3]) / 2.0
            if my <= split_thresh:
                outer_segs.append(s)
            else:
                inner_segs.append(s)
    elif side == "BOTTOM":
        split_thresh = (ry + rh) - 0.04 * rh
        for s in segments:
            my = (s[1] + s[3]) / 2.0
            if my >= split_thresh:
                outer_segs.append(s)
            else:
                inner_segs.append(s)
    elif side == "LEFT":
        split_thresh = rx + 0.04 * rw
        for s in segments:
            mx = (s[0] + s[2]) / 2.0
            if mx <= split_thresh:
                outer_segs.append(s)
            else:
                inner_segs.append(s)
    elif side == "RIGHT":
        split_thresh = (rx + rw) - 0.04 * rw
        for s in segments:
            mx = (s[0] + s[2]) / 2.0
            if mx >= split_thresh:
                outer_segs.append(s)
            else:
                inner_segs.append(s)
                
    return outer_segs, inner_segs


def build_quadrilateral_hypothesis(
    fitted_lines: Dict[str, Optional[Line2D]],
    image_shape: Tuple[int, int],
    roi_bbox: Tuple[int, int, int, int],
    hyp_name: str = "QUAD_HYPOTHESIS"
) -> Dict[str, Any]:
    """Construct a 4-line / 4-corner hypothesis from a set of margin lines."""
    h_img, w_img = image_shape[:2]
    rx, ry, rw, rh = roi_bbox
    
    l_top = fitted_lines.get("TOP")
    l_bottom = fitted_lines.get("BOTTOM")
    l_left = fitted_lines.get("LEFT")
    l_right = fitted_lines.get("RIGHT")
    
    if l_top and l_bottom and l_left and l_right:
        p_tl = intersect_lines(l_top, l_left)
        p_tr = intersect_lines(l_top, l_right)
        p_br = intersect_lines(l_bottom, l_right)
        p_bl = intersect_lines(l_bottom, l_left)
        
        corners = [p_tl, p_tr, p_br, p_bl]
        all_exist = all(p is not None for p in corners)
        
        if all_exist:
            pts = np.array(corners, dtype=np.float32)
            is_convex = False
            if len(pts) == 4:
                v1 = pts[1] - pts[0]
                v2 = pts[2] - pts[1]
                v3 = pts[3] - pts[2]
                v4 = pts[0] - pts[3]
                crosses = [
                    v1[0]*v2[1] - v1[1]*v2[0],
                    v2[0]*v3[1] - v2[1]*v3[0],
                    v3[0]*v4[1] - v3[1]*v4[0],
                    v4[0]*v1[1] - v4[1]*v1[0],
                ]
                is_convex = all(c > 0 for c in crosses) or all(c < 0 for c in crosses)
                
            in_bounds = all(-0.15 * w_img <= p[0] <= 1.15 * w_img and -0.15 * h_img <= p[1] <= 1.15 * h_img for p in corners)
            approx_area = float(cv2.contourArea(pts)) if is_convex else 0.0
            roi_area = float(rw * rh)
            area_ratio = approx_area / roi_area if roi_area > 0 else 0.0

            return {
                "name": hyp_name,
                "corners": {
                    "TOP_LEFT": p_tl,
                    "TOP_RIGHT": p_tr,
                    "BOTTOM_RIGHT": p_br,
                    "BOTTOM_LEFT": p_bl,
                },
                "is_convex": is_convex,
                "in_bounds": in_bounds,
                "approx_area": approx_area,
                "area_vs_roi_ratio": area_ratio,
                "all_lines_present": True,
                "evaluation": "VALID_CONVEX_QUAD" if (is_convex and in_bounds) else "INVALID_OR_DEGENERATE"
            }
            
    missing = [side for side in ["TOP", "BOTTOM", "LEFT", "RIGHT"] if fitted_lines.get(side) is None]
    return {
        "name": hyp_name,
        "corners": {},
        "is_convex": False,
        "in_bounds": False,
        "all_lines_present": False,
        "missing_sides": missing,
        "evaluation": f"Cannot form complete quad; missing margins: {missing}"
    }


# ===========================================================================
# MAIN MULTI-SIGNAL INVESTIGATION ENGINE
# ===========================================================================

def run_multi_signal_investigation(image_path: str) -> Dict[str, Any]:
    """Execute complete Phase 3.2 investigation for a single image."""
    img_name = os.path.basename(image_path)
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
        
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
        # Fallback to candidates or full frame
        if p2_result.candidate_profiles:
            roi_bbox = p2_result.candidate_profiles[0].box
            roi_source = f"PHASE_2_CANDIDATE_0 ({p2_result.candidate_profiles[0].candidate_id})"
        else:
            roi_bbox = (0, 0, w_img, h_img)
            roi_source = "FULL_IMAGE_FRAME_FALLBACK"

    rx, ry, rw, rh = roi_bbox

    # 2. Detect Margin Line Segments (Module A)
    margin_segments = detect_margin_line_segments(image, roi_bbox)

    # 3. Robust Line Fitting (Module B) & Outer-vs-Internal Partitioning
    outer_fitted_lines: Dict[str, Optional[Line2D]] = {}
    inner_fitted_lines: Dict[str, Optional[Line2D]] = {}
    ransac_diagnostics: Dict[str, Dict[str, Any]] = {}
    outer_nature_records: Dict[str, Dict[str, Any]] = {}
    inner_nature_records: Dict[str, Dict[str, Any]] = {}
    
    for side in ["TOP", "BOTTOM", "LEFT", "RIGHT"]:
        segs = margin_segments[side]
        outer_segs, inner_segs = partition_margin_segments(segs, side, roi_bbox)
        
        # Fit outer line
        o_line, o_diag = fit_line_ransac(outer_segs if outer_segs else segs, side=f"OUTER_{side}")
        outer_fitted_lines[side] = o_line
        ransac_diagnostics[f"OUTER_{side}"] = o_diag
        
        # Fit inner line
        i_line, i_diag = fit_line_ransac(inner_segs if inner_segs else segs, side=f"INNER_{side}")
        inner_fitted_lines[side] = i_line
        ransac_diagnostics[f"INNER_{side}"] = i_diag
        
        # Analyze nature
        if o_line:
            outer_nature_records[side] = analyze_line_nature(o_line, image, roi_bbox, side)
        else:
            outer_nature_records[side] = {
                "nature": "UNAVAILABLE", "delta_brightness": 0.0,
                "exterior_mean_v": 0.0, "interior_mean_v": 0.0,
                "evidence": f"No outer line fitted for {side}."
            }
            
        if i_line:
            inner_nature_records[side] = analyze_line_nature(i_line, image, roi_bbox, side)
        else:
            inner_nature_records[side] = {
                "nature": "UNAVAILABLE", "delta_brightness": 0.0,
                "exterior_mean_v": 0.0, "interior_mean_v": 0.0,
                "evidence": f"No inner line fitted for {side}."
            }

    # 4. Formulate Quadrilateral Hypotheses (Module E)
    hyp_outer = build_quadrilateral_hypothesis(outer_fitted_lines, (h_img, w_img), roi_bbox, "HYP_OUTER_PHYSICAL_PAGE")
    hyp_inner = build_quadrilateral_hypothesis(inner_fitted_lines, (h_img, w_img), roi_bbox, "HYP_INNER_PRINTED_ENVELOPE")
    quad_hypotheses = [hyp_outer, hyp_inner]

    # 5. Frame-Limited Assessment (Module F)
    frame_limited_sides = []
    if abs(ry) < 4:
        frame_limited_sides.append("TOP")
    if abs((ry + rh) - h_img) < 4:
        frame_limited_sides.append("BOTTOM")
    if abs(rx) < 4:
        frame_limited_sides.append("LEFT")
    if abs((rx + rw) - w_img) < 4:
        frame_limited_sides.append("RIGHT")

    # Usable geometric info in frame-limited / partial cases
    usable_geometry = []
    if "LEFT" in outer_fitted_lines and outer_fitted_lines["LEFT"] and "LEFT" not in frame_limited_sides:
        usable_geometry.append(f"Left lateral edge angle={outer_fitted_lines['LEFT'].angle_degrees:.2f} deg")
    if "RIGHT" in outer_fitted_lines and outer_fitted_lines["RIGHT"] and "RIGHT" not in frame_limited_sides:
        usable_geometry.append(f"Right lateral edge angle={outer_fitted_lines['RIGHT'].angle_degrees:.2f} deg")

    # 6. Ambiguous Form Assessment (Module G)
    ambiguous_notes = []
    if image_state == "AMBIGUOUS" or img_name == "answer_sheet.jpg":
        has_paper_step = any(rec.get("nature") == "PHYSICAL_PAPER_BOUNDARY" for rec in outer_nature_records.values())
        if not has_paper_step:
            ambiguous_notes.append("No physical paper boundary steps detected; all boundary lines are printed form rules or cropped borders.")

    # 7. Create Diagnostic Visualization
    vis_path = os.path.join(OUTPUT_DIR, f"phase3_multisignal_vis_{img_name}.png")
    generate_diagnostic_visualization(
        image,
        roi_bbox,
        margin_segments,
        outer_fitted_lines,
        inner_fitted_lines,
        outer_nature_records,
        inner_nature_records,
        quad_hypotheses,
        frame_limited_sides,
        img_name,
        image_state,
        vis_path
    )

    return {
        "image_name": img_name,
        "image_size": (w_img, h_img),
        "phase2_state": image_state,
        "roi_source": roi_source,
        "roi_bbox": roi_bbox,
        "margin_segments_count": {k: len(v) for k, v in margin_segments.items()},
        "outer_fitted_lines": {k: str(v) if v else None for k, v in outer_fitted_lines.items()},
        "inner_fitted_lines": {k: str(v) if v else None for k, v in inner_fitted_lines.items()},
        "ransac_diagnostics": ransac_diagnostics,
        "outer_line_nature": outer_nature_records,
        "inner_line_nature": inner_nature_records,
        "quad_hypotheses": quad_hypotheses,
        "frame_limited_sides": frame_limited_sides,
        "usable_geometry": usable_geometry,
        "ambiguous_notes": ambiguous_notes,
        "visualization_path": vis_path
    }


# ===========================================================================
# VISUALIZATION GENERATOR
# ===========================================================================

def generate_diagnostic_visualization(
    image: np.ndarray,
    roi_bbox: Tuple[int, int, int, int],
    margin_segments: Dict[str, List[Tuple[float, float, float, float, float]]],
    outer_fitted_lines: Dict[str, Optional[Line2D]],
    inner_fitted_lines: Dict[str, Optional[Line2D]],
    outer_nature: Dict[str, Dict[str, Any]],
    inner_nature: Dict[str, Dict[str, Any]],
    quad_hypotheses: List[Dict[str, Any]],
    frame_limited_sides: List[str],
    img_name: str,
    image_state: str,
    output_path: str
):
    """Render a multi-panel visual overlay showing segments, fitted lines, and quad hypotheses."""
    fig, axes = plt.subplots(1, 2, figsize=(16, 9))
    
    # Left Panel: Detected Segments & Nature
    ax1 = axes[0]
    rgb_img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    ax1.imshow(rgb_img)
    rx, ry, rw, rh = roi_bbox
    
    # ROI rectangle
    roi_rect = patches.Rectangle((rx, ry), rw, rh, linewidth=2, edgecolor='cyan', facecolor='none', linestyle='--', label='Phase 2 ROI')
    ax1.add_patch(roi_rect)
    
    # Draw line segments by margin
    colors = {"TOP": "orange", "BOTTOM": "gold", "LEFT": "magenta", "RIGHT": "deepskyblue"}
    for side, segs in margin_segments.items():
        c = colors.get(side, "yellow")
        for s in segs:
            ax1.plot([s[0], s[2]], [s[1], s[3]], color=c, linewidth=1.5, alpha=0.6)

    # Annotate nature of each margin
    y_text = 40
    for side in ["TOP", "BOTTOM", "LEFT", "RIGHT"]:
        o_nat = outer_nature[side]["nature"]
        i_nat = inner_nature[side]["nature"]
        ax1.text(20, y_text, f"{side}: Outer={o_nat} | Inner={i_nat}", color="white", fontsize=8,
                 bbox=dict(boxstyle="round,pad=0.25", facecolor="black", alpha=0.75))
        y_text += 32

    ax1.set_title(f"{img_name}: Segments & Nature ({image_state})", fontsize=11, fontweight='bold')
    ax1.axis("off")

    # Right Panel: Fitted Lines & Quadrilateral Hypotheses
    ax2 = axes[1]
    ax2.imshow(rgb_img)
    
    h_img, w_img = image.shape[:2]
    
    # Draw outer fitted lines in lime green
    for side, line in outer_fitted_lines.items():
        if line:
            if line.is_horizontal:
                x_vals = [0, w_img]
                y_vals = [-(line.A * 0 + line.C) / line.B, -(line.A * w_img + line.C) / line.B]
            else:
                y_vals = [0, h_img]
                x_vals = [-(line.B * 0 + line.C) / line.A, -(line.B * h_img + line.C) / line.A]
            ax2.plot(x_vals, y_vals, color='lime', linewidth=2.0, linestyle='-', alpha=0.85)

    # Draw inner fitted lines in orange
    for side, line in inner_fitted_lines.items():
        if line:
            if line.is_horizontal:
                x_vals = [0, w_img]
                y_vals = [-(line.A * 0 + line.C) / line.B, -(line.A * w_img + line.C) / line.B]
            else:
                y_vals = [0, h_img]
                x_vals = [-(line.B * 0 + line.C) / line.A, -(line.B * h_img + line.C) / line.A]
            ax2.plot(x_vals, y_vals, color='orange', linewidth=1.5, linestyle=':', alpha=0.75)

    # Overlay quad hypotheses
    hyp_styles = [
        {"color": "yellow", "style": "-", "lw": 2.5},
        {"color": "magenta", "style": "--", "lw": 1.8},
    ]
    for idx, hyp in enumerate(quad_hypotheses):
        style = hyp_styles[idx % len(hyp_styles)]
        corners_dict = hyp.get("corners", {})
        if len(corners_dict) == 4:
            pts = [
                corners_dict["TOP_LEFT"],
                corners_dict["TOP_RIGHT"],
                corners_dict["BOTTOM_RIGHT"],
                corners_dict["BOTTOM_LEFT"],
            ]
            poly_x = [p[0] for p in pts] + [pts[0][0]]
            poly_y = [p[1] for p in pts] + [pts[0][1]]
            eval_str = hyp.get("evaluation")
            h_name = hyp.get("name")
            ax2.plot(poly_x, poly_y, color=style["color"], linewidth=style["lw"], linestyle=style["style"],
                     label=f"{h_name} ({eval_str})")
            
            if idx == 0:  # Annotate corners for outer hypothesis
                for c_name, cp in corners_dict.items():
                    ax2.plot(cp[0], cp[1], marker='o', markersize=8, markerfacecolor='cyan', markeredgecolor='black')

    # Mark frame-limited sides
    if frame_limited_sides:
        ax2.text(20, h_img - 35, f"FRAME-LIMITED SIDES: {', '.join(frame_limited_sides)} (Corners Unobservable)",
                 color="white", fontsize=9, fontweight='bold',
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="crimson", alpha=0.85))

    ax2.set_title(f"Outer vs Inner Hypotheses (Green=Outer, Orange=Inner)", fontsize=11, fontweight='bold')
    ax2.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=120)
    plt.close()


# ===========================================================================
# SCRIPT ENTRYPOINT & AUDIT EXECUTION
# ===========================================================================

def main():
    print("=" * 80)
    print("AI-EVAL PHASE 3.2: MULTI-SIGNAL CORNER CANDIDATE INVESTIGATION")
    print("=" * 80)
    print("Focus: Reconstructing page corners from multi-signal boundaries")
    print("Guardrails: Investigation only; NO warp; NO perspective transform; NO final thresholds.")
    print("-" * 80)

    results = []
    for rel_path in CALIBRATION_IMAGES:
        full_path = os.path.join(ROOT_DIR, rel_path)
        print(f"\n>> Processing: {rel_path}...")
        try:
            res = run_multi_signal_investigation(full_path)
            results.append(res)
            
            print(f"   Image State     : {res['phase2_state']}")
            print(f"   ROI Source      : {res['roi_source']}")
            print(f"   ROI BBox        : {res['roi_bbox']}")
            print(f"   Segments Detected: {res['margin_segments_count']}")
            print("   Margin Line Nature (Outer vs Inner):")
            for side in ["TOP", "BOTTOM", "LEFT", "RIGHT"]:
                o_nat = res["outer_line_nature"][side]
                i_nat = res["inner_line_nature"][side]
                print(f"     * {side:6s} -> Outer: {o_nat['nature']:24s} ({o_nat['delta_brightness']:+.1f} V)")
                print(f"               -> Inner: {i_nat['nature']:24s} ({i_nat['delta_brightness']:+.1f} V)")
            print(f"   Quad Hypotheses : {len(res['quad_hypotheses'])}")
            for idx, hyp in enumerate(res['quad_hypotheses']):
                print(f"     [{idx+1}] {hyp.get('name')}: {hyp.get('evaluation')}")
                if hyp.get("corners"):
                    for c_name, coord in hyp["corners"].items():
                        c_str = f"({coord[0]:.1f}, {coord[1]:.1f})" if coord else "None"
                        print(f"         - {c_name:12s}: {c_str}")
            if res["frame_limited_sides"]:
                print(f"   Frame-Limited Sides: {res['frame_limited_sides']}")
            if res["usable_geometry"]:
                print(f"   Usable Geometry    : {res['usable_geometry']}")
            if res["ambiguous_notes"]:
                print(f"   Ambiguity Notes    : {res['ambiguous_notes']}")
            print(f"   Overlay Saved   : {res['visualization_path']}")

        except Exception as e:
            print(f"   [ERROR] Failed processing {rel_path}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("MULTI-SIGNAL CORNER INVESTIGATION SUMMARY")
    print("=" * 80)
    for res in results:
        print(f"Image: {res['image_name']:20s} | State: {res['phase2_state']:26s} | Frame-Clipped: {res['frame_limited_sides']}")
    print("=" * 80)


if __name__ == "__main__":
    main()
