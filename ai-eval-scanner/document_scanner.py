"""
AI-EVAL OpenCV Modular Document Scanner
========================================
Production-grade document boundary detection, 4-corner ordering,
perspective rectification, non-document rejection, and normalized sharpness scoring.
"""

from __future__ import annotations

import os
import math
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, asdict

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class DocumentScanResult:
    """
    Standardized result contract for document detection and quality assessment.
    """
    detected: bool
    corners: Optional[List[Tuple[float, float]]]
    warped_image: Optional[np.ndarray]
    sharpness_raw: float
    sharpness_score: float
    document_score: float
    quality_status: str                     # "PASSED" | "HUMAN_REVIEW" | "RESCAN_REQUIRED"
    reason: Optional[str]
    transform_matrix: Optional[np.ndarray] = None
    area_ratio: float = 0.0
    aspect_ratio: float = 0.0
    debug_artifacts: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.warped_image is not None:
            d["warped_image_shape"] = self.warped_image.shape
            d.pop("warped_image", None)
        if self.transform_matrix is not None:
            d["transform_matrix"] = self.transform_matrix.tolist()
        return d


# ---------------------------------------------------------------------------
# Four-Corner Canonical Ordering
# ---------------------------------------------------------------------------

def order_corners(pts: Union[np.ndarray, List[Any]]) -> np.ndarray:
    """
    Consistently orders four 2D corners into canonical reading order:
    [top-left, top-right, bottom-right, bottom-left].

    Algorithm:
    - Sort corners cyclically (clockwise) around their centroid (cx, cy).
    - Determine the four geometric edges and identify opposite edge pairs: (E0, E2) and (E1, E3).
    - Calculate horizontal alignment scores for each opposite pair.
    - The pair with larger horizontal alignment is designated as the horizontal edge pair (Top & Bottom).
      The other pair is designated as the vertical edge pair (Left & Right).
    - The edge in the horizontal pair with smaller y-centroid (closer to the top of the frame) is the Top edge.
    - Anchor index 0 as Top-Left (endpoint of top edge with smaller x), followed clockwise by
      Top-Right (index 1), Bottom-Right (index 2), Bottom-Left (index 3).
    - Ensures opposite edges form consistent width and height pairs, preserving the physical page
      orientation represented by the capture without 90-degree geometry swaps.
    """
    pts_arr = np.array(pts, dtype=np.float32).reshape(4, 2)
    cx = float(np.mean(pts_arr[:, 0]))
    cy = float(np.mean(pts_arr[:, 1]))
    angles = np.arctan2(pts_arr[:, 1] - cy, pts_arr[:, 0] - cx)
    sort_idx = np.argsort(angles)
    pts_cw = pts_arr[sort_idx]

    # Verify clockwise orientation; if counter-clockwise, invert order
    v1 = pts_cw[1] - pts_cw[0]
    v2 = pts_cw[3] - pts_cw[0]
    if v1[0] * v2[1] - v1[1] * v2[0] < 0:
        pts_cw = pts_cw[[0, 3, 2, 1]]

    # The 4 cyclic edges in clockwise order:
    # E0: P0->P1, E1: P1->P2, E2: P2->P3, E3: P3->P0
    edges = []
    for i in range(4):
        p1 = pts_cw[i]
        p2 = pts_cw[(i + 1) % 4]
        vec = p2 - p1
        length = float(np.linalg.norm(vec))
        horiz = abs(float(vec[0])) / max(1e-6, length)
        mid_y = float((p1[1] + p2[1]) / 2.0)
        edges.append({
            'idx': i,
            'p1': p1,
            'p2': p2,
            'length': length,
            'horiz': horiz,
            'mid_y': mid_y,
        })

    # Pair 0: (E0, E2); Pair 1: (E1, E3)
    h_pair0 = (edges[0]['horiz'] + edges[2]['horiz']) / 2.0
    h_pair1 = (edges[1]['horiz'] + edges[3]['horiz']) / 2.0

    if h_pair0 >= h_pair1:
        horiz_pair = (edges[0], edges[2])
    else:
        horiz_pair = (edges[1], edges[3])

    # Top edge has lower mid_y (closer to top of frame)
    top_edge = horiz_pair[0] if horiz_pair[0]['mid_y'] < horiz_pair[1]['mid_y'] else horiz_pair[1]
    top_idx = top_edge['idx']

    pA = pts_cw[top_idx]
    pB = pts_cw[(top_idx + 1) % 4]
    if pA[0] <= pB[0]:
        ordered = np.roll(pts_cw, -top_idx, axis=0)
    else:
        pts_inv = pts_cw[[0, 3, 2, 1]]
        new_idx = 0
        for k in range(4):
            if np.allclose(pts_inv[k], pB):
                new_idx = k
                break
        ordered = np.roll(pts_inv, -new_idx, axis=0)

    return ordered.astype(np.float32)


# ---------------------------------------------------------------------------
# Quadrilateral Geometric Validation
# ---------------------------------------------------------------------------

def validate_quadrilateral(
    corners: np.ndarray,
    img_w: int,
    img_h: int,
    min_area_ratio: float = 0.12,
    max_area_ratio: float = 0.85,
    min_angle_deg: float = 55.0,
    max_angle_deg: float = 125.0,
    min_aspect: float = 0.25,
    max_aspect: float = 4.0,
) -> Tuple[bool, str]:
    """
    Validates that a 4-point contour constitutes a valid, non-degenerate document page:
    - Area within sensible physical bounds of the sensor frame.
    - Corners inside or directly adjacent to image bounds.
    - Rejects contours tracking the camera sensor frame edges.
    - Approximately rectangular corner angles (55°–125°).
    - Sensible aspect ratio supporting portrait, landscape, booklets, letter, legal, A4.
    """
    total_area = float(img_w * img_h)
    area = float(cv2.contourArea(corners))
    area_ratio = area / total_area

    if area_ratio < min_area_ratio:
        return False, f"Target object too small (area ratio {area_ratio:.3f} < {min_area_ratio})"
    if area_ratio > max_area_ratio:
        return False, f"Boundary exceeds reasonable document bounds (area ratio {area_ratio:.3f} > {max_area_ratio})"

    margin = 8
    for pt in corners:
        x, y = pt[0], pt[1]
        if x < -margin or x > img_w + margin or y < -margin or y > img_h + margin:
            return False, f"Corner coordinates ({x:.1f}, {y:.1f}) outside sensor frame bounds"

    # Reject candidates where 3 or more vertices sit directly along the camera sensor boundary
    sensor_border_margin = 12
    sensor_border_touch = 0
    for pt in corners:
        x, y = float(pt[0]), float(pt[1])
        if x <= sensor_border_margin or x >= img_w - sensor_border_margin or y <= sensor_border_margin or y >= img_h - sensor_border_margin:
            sensor_border_touch += 1
    if sensor_border_touch >= 3:
        return False, "Quadrilateral tracks camera frame boundary rather than document"

    ordered = order_corners(corners)
    tl, tr, br, bl = ordered

    w_top = float(np.linalg.norm(tr - tl))
    w_bot = float(np.linalg.norm(br - bl))
    h_left = float(np.linalg.norm(bl - tl))
    h_right = float(np.linalg.norm(br - tr))

    avg_w = (w_top + w_bot) / 2.0
    avg_h = (h_left + h_right) / 2.0

    if avg_w < 25.0 or avg_h < 25.0:
        return False, "Document dimensions too small"

    aspect = avg_w / max(1.0, avg_h)
    if aspect < min_aspect or aspect > max_aspect:
        return False, f"Unreasonable document aspect ratio ({aspect:.2f})"

    angles = []
    for i in range(4):
        p_prev = ordered[(i - 1) % 4]
        p_curr = ordered[i]
        p_next = ordered[(i + 1) % 4]

        v1 = p_prev - p_curr
        v2 = p_next - p_curr

        norm1 = float(np.linalg.norm(v1))
        norm2 = float(np.linalg.norm(v2))
        if norm1 < 1e-4 or norm2 < 1e-4:
            return False, "Degenerate edge in quadrilateral"

        cos_a = np.clip(np.dot(v1, v2) / (norm1 * norm2), -1.0, 1.0)
        ang = float(np.degrees(np.arccos(cos_a)))
        angles.append(ang)

        if ang < min_angle_deg or ang > max_angle_deg:
            return False, f"Non-rectangular corner angle ({ang:.1f}° at corner {i})"

    return True, f"Valid quadrilateral (area_ratio={area_ratio:.3f}, aspect={aspect:.2f})"


# ---------------------------------------------------------------------------
# Multi-Pass Document Boundary Detection
# ---------------------------------------------------------------------------

def _line_intersection(l_h: Tuple[int, int, int, int], l_v: Tuple[int, int, int, int]) -> Optional[Tuple[float, float]]:
    dx_h = float(l_h[2] - l_h[0])
    dy_h = float(l_h[3] - l_h[1])
    dx_v = float(l_v[2] - l_v[0])
    dy_v = float(l_v[3] - l_v[1])
    A = np.array([[-dy_h, dx_h], [-dy_v, dx_v]], dtype=np.float64)
    B = np.array([-dy_h * float(l_h[0]) + dx_h * float(l_h[1]), -dy_v * float(l_v[0]) + dx_v * float(l_v[1])], dtype=np.float64)
    det = float(np.linalg.det(A))
    if abs(det) < 1e-4:
        return None
    pt = np.linalg.solve(A, B)
    return float(pt[0]), float(pt[1])


def extract_line_quad_candidates(
    gray_img: np.ndarray,
    orig_w: int,
    orig_h: int,
    scale_factor: float = 1.0,
    min_area_ratio: float = 0.10,
    max_area_ratio: float = 0.85,
) -> List[Tuple[float, np.ndarray, str, float]]:
    """
    Extracts quadrilateral candidates from dominant physical paper boundary lines
    using Hough transform, contrast step analysis, and line intersection.
    Robust against clothing, arms, and furniture around held documents.
    """
    h, w = gray_img.shape
    blurred = cv2.GaussianBlur(gray_img, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 100)

    min_line_len = max(30, int(round(35 * scale_factor)))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=30, minLineLength=min_line_len, maxLineGap=int(round(25 * scale_factor)))
    if lines is None or len(lines) < 4:
        return []

    v_lines = []
    h_lines = []
    for line in lines:
        x1, y1, x2, y2 = line.ravel()
        length = float(np.hypot(x2 - x1, y2 - y1))
        angle = float(np.abs(np.arctan2(y2 - y1, x2 - x1) * 180.0 / np.pi))
        if 65.0 < angle < 115.0:  # vertical
            if y1 > y2:
                x1, y1, x2, y2 = x2, y2, x1, y1
            v_lines.append((int(x1), int(y1), int(x2), int(y2), length, (x1 + x2) / 2.0, (y1 + y2) / 2.0))
        elif angle < 25.0 or angle > 155.0:  # horizontal
            if x1 > x2:
                x1, y1, x2, y2 = x2, y2, x1, y1
            h_lines.append((int(x1), int(y1), int(x2), int(y2), length, (x1 + x2) / 2.0, (y1 + y2) / 2.0))

    if not v_lines or not h_lines:
        return []

    v_lines.sort(key=lambda l: l[4], reverse=True)
    h_lines.sort(key=lambda l: l[4], reverse=True)

    quads: List[Tuple[float, np.ndarray, str, float]] = []
    top_v = v_lines[:12]
    top_h = h_lines[:12]

    min_dim = 40.0 * scale_factor

    for t in top_h:
        for b in top_h:
            if b[6] <= t[6] + min_dim:
                continue
            for l in top_v:
                for r in top_v:
                    if r[5] <= l[5] + min_dim:
                        continue
                    tl = _line_intersection((t[0], t[1], t[2], t[3]), (l[0], l[1], l[2], l[3]))
                    tr = _line_intersection((t[0], t[1], t[2], t[3]), (r[0], r[1], r[2], r[3]))
                    br = _line_intersection((b[0], b[1], b[2], b[3]), (r[0], r[1], r[2], r[3]))
                    bl = _line_intersection((b[0], b[1], b[2], b[3]), (l[0], l[1], l[2], l[3]))
                    if tl is None or tr is None or br is None or bl is None:
                        continue

                    corners_orig = (np.array([tl, tr, br, bl], dtype=np.float32)) / scale_factor
                    margin = 25.0
                    if np.any(corners_orig < -margin) or np.any(corners_orig[:, 0] > orig_w + margin) or np.any(corners_orig[:, 1] > orig_h + margin):
                        continue

                    w_t = float(np.hypot(corners_orig[1][0] - corners_orig[0][0], corners_orig[1][1] - corners_orig[0][1]))
                    w_b = float(np.hypot(corners_orig[2][0] - corners_orig[3][0], corners_orig[2][1] - corners_orig[3][1]))
                    h_l = float(np.hypot(corners_orig[3][0] - corners_orig[0][0], corners_orig[3][1] - corners_orig[0][1]))
                    h_r = float(np.hypot(corners_orig[2][0] - corners_orig[1][0], corners_orig[2][1] - corners_orig[1][1]))
                    avg_w = (w_t + w_b) / 2.0
                    avg_h = (h_l + h_r) / 2.0
                    if avg_w < 100.0 or avg_h < 100.0:
                        continue

                    ar = avg_w / max(1.0, avg_h)
                    # Requirement 5: Reasonable rectangular/perspective geometry
                    if ar < 0.45 or ar > 1.85:
                        continue

                    # Requirement 4: Similarity of opposite edge lengths
                    diff_w = abs(w_t - w_b) / max(w_t, w_b)
                    diff_h = abs(h_l - h_r) / max(h_l, h_r)
                    if diff_w > 0.32 or diff_h > 0.32:
                        continue

                    area_orig = float(cv2.contourArea(corners_orig))
                    area_ratio = area_orig / float(orig_w * orig_h)
                    if min_area_ratio <= area_ratio <= max_area_ratio:
                        quads.append((area_orig, corners_orig, "Line boundary quad", float(ar)))

    return quads


def _extract_quad_candidates_at_scale(
    gray_img: np.ndarray,
    orig_w: int,
    orig_h: int,
    scale_factor: float,
    min_area_ratio: float,
    max_area_ratio: float,
) -> List[Tuple[float, np.ndarray, str, float]]:
    """
    Extracts quadrilateral candidates at a specific scale factor, scaling corner coordinates
    back to the original image coordinate frame.
    """
    total_area_orig = float(orig_w * orig_h)
    blurred = cv2.GaussianBlur(gray_img, (5, 5), 0)

    edge_thresholds = [
        (30, 100),
        (50, 150),
        (75, 200),
        (20, 80),
        (15, 60),
    ]

    kernels = [
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
    ]

    candidate_quads: List[Tuple[float, np.ndarray, str, float]] = []

    def evaluate_contour_candidate(cnt: np.ndarray):
        area_curr = cv2.contourArea(cnt)
        area_orig = area_curr / (scale_factor * scale_factor)
        if area_orig / total_area_orig < min_area_ratio * 0.8:
            return
        hull = cv2.convexHull(cnt)
        peri = cv2.arcLength(hull, True)
        if peri < 40.0:
            return

        for eps_factor in (0.015, 0.02, 0.025, 0.03):
            approx = cv2.approxPolyDP(hull, eps_factor * peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                corners_scaled = approx.reshape(4, 2).astype(np.float32)
                corners_orig = corners_scaled / scale_factor
                is_valid, msg = validate_quadrilateral(
                    corners_orig, orig_w, orig_h,
                    min_area_ratio=min_area_ratio,
                    max_area_ratio=max_area_ratio
                )
                if is_valid:
                    ordered = order_corners(corners_orig)
                    w_top = np.linalg.norm(ordered[1] - ordered[0])
                    w_bot = np.linalg.norm(ordered[2] - ordered[3])
                    h_l = np.linalg.norm(ordered[3] - ordered[0])
                    h_r = np.linalg.norm(ordered[2] - ordered[1])
                    ar = ((w_top + w_bot) / 2.0) / max(1.0, ((h_l + h_r) / 2.0))
                    candidate_quads.append((float(cv2.contourArea(ordered)), ordered, msg, float(ar)))
                    break

    for low_t, high_t in edge_thresholds:
        edges = cv2.Canny(blurred, low_t, high_t)
        cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            evaluate_contour_candidate(c)
        for k in kernels:
            closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k, iterations=1)
            cnts_closed, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts_closed:
                evaluate_contour_candidate(c)

    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    for k in kernels:
        closed_otsu = cv2.morphologyEx(otsu, cv2.MORPH_CLOSE, k, iterations=1)
        cnts_otsu, _ = cv2.findContours(closed_otsu, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts_otsu:
            evaluate_contour_candidate(c)

    # Paper substrate threshold (targets bright white/light sheets against background)
    mean_val = float(np.mean(blurred))
    th_val = min(170, max(85, int(mean_val + 20)))
    _, paper_th = cv2.threshold(blurred, th_val, 255, cv2.THRESH_BINARY)
    k_small = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed_paper = cv2.morphologyEx(paper_th, cv2.MORPH_CLOSE, k_small, iterations=1)
    cnts_paper, _ = cv2.findContours(closed_paper, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts_paper:
        evaluate_contour_candidate(c)

    adapt = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 10)
    closed_adapt = cv2.morphologyEx(adapt, cv2.MORPH_CLOSE, k_small, iterations=1)
    cnts_adapt, _ = cv2.findContours(closed_adapt, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts_adapt:
        evaluate_contour_candidate(c)

    return candidate_quads


def detect_document_quad(
    image: np.ndarray,
    min_area_ratio: float = 0.10,
    max_area_ratio: float = 0.85,
) -> Optional[Dict[str, Any]]:
    """
    Robust multi-pass, physical paper document boundary detector:
    1. Extracts candidate quadrilaterals from:
       - Physical boundary lines (Hough transform + contrast step across line)
       - Multi-scale contour approximations (Canny, Otsu, Paper threshold, Adaptive)
    2. Rigorously evaluates every candidate against physical paper criteria:
       - Bright paper substrate across all 4 quadrants (rejects dark clothing/room/furniture)
       - Low color saturation (neutral paper rather than colored room walls or clothes)
       - Continuous paper boundary: high gradient magnitude along all 4 outer edges
       - Geometric symmetry: opposite edge lengths must be similar (within 38%)
       - Reasonable rectangular perspective (angles 60°-120°, aspect ratio 0.35-2.6)
       - Internal handwriting/text stroke density
    3. Ranks candidates by Paper Confidence Score to pick the actual physical sheet.
    """
    img_h, img_w = image.shape[:2]
    total_area = float(img_w * img_h)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image

    candidate_quads: List[Tuple[float, np.ndarray, str, float]] = []

    # Scale factor for fast line & contour detection on high-res images
    max_dim = max(img_h, img_w)
    working_scale = 640.0 / float(max_dim) if max_dim > 640 else 1.0
    if working_scale < 1.0:
        dw = int(round(img_w * working_scale))
        dh = int(round(img_h * working_scale))
        downscaled = cv2.resize(gray, (dw, dh), interpolation=cv2.INTER_AREA)
        line_quads = extract_line_quad_candidates(downscaled, img_w, img_h, working_scale, min_area_ratio, max_area_ratio)
        candidate_quads.extend(line_quads)
        contour_quads = _extract_quad_candidates_at_scale(downscaled, img_w, img_h, working_scale, min_area_ratio, max_area_ratio)
        candidate_quads.extend(contour_quads)
    else:
        line_quads = extract_line_quad_candidates(gray, img_w, img_h, 1.0, min_area_ratio, max_area_ratio)
        candidate_quads.extend(line_quads)
        contour_quads = _extract_quad_candidates_at_scale(gray, img_w, img_h, 1.0, min_area_ratio, max_area_ratio)
        candidate_quads.extend(contour_quads)

    if not candidate_quads:
        return None

    # Pre-calculate gradient magnitude for edge boundary evaluation
    sobelx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
    sobely = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    mag = cv2.magnitude(sobelx, sobely)

    scored_candidates = []
    for area, corners, msg, ar in candidate_quads:
        area_ratio = area / total_area
        if area_ratio < min_area_ratio or area_ratio > max_area_ratio:
            continue

        ordered = order_corners(corners)
        tl, tr, br, bl = ordered

        # Check edge length symmetry
        w_t = float(np.hypot(tr[0] - tl[0], tr[1] - tl[1]))
        w_b = float(np.hypot(br[0] - bl[0], br[1] - bl[1]))
        h_l = float(np.hypot(bl[0] - tl[0], bl[1] - tl[1]))
        h_r = float(np.hypot(br[0] - tr[0], br[1] - tr[1]))

        diff_w = abs(w_t - w_b) / max(w_t, w_b, 1.0)
        diff_h = abs(h_l - h_r) / max(h_l, h_r, 1.0)
        if diff_w > 0.32 or diff_h > 0.32:
            continue

        try:
            # Warp candidate to 160x220 patch to measure substrate, saturation, and strokes
            pts_dst = np.array([[0, 0], [160, 0], [160, 220], [0, 220]], dtype=np.float32)
            M_fast = cv2.getPerspectiveTransform(ordered, pts_dst)
            patch = cv2.warpPerspective(image, M_fast, (160, 220), flags=cv2.INTER_LINEAR)

            gray_p = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY) if patch.ndim == 3 else patch

            # Requirement 7: Reject clothing / room clutter by pixel distributions
            dark_frac = float(np.mean(gray_p < 75))
            if dark_frac > 0.065:
                continue

            if patch.ndim == 3:
                hsv_p = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
                sat_frac = float(np.mean(hsv_p[:, :, 1] > 60))
                if sat_frac > 0.038:  # Reject colorful covers/clothing
                    continue
            else:
                sat_frac = 0.0

            # Requirement 1: Bright paper surface across all 4 quadrants
            q_tl = float(np.mean(gray_p[0:110, 0:80]))
            q_tr = float(np.mean(gray_p[0:110, 80:160]))
            q_bl = float(np.mean(gray_p[110:220, 0:80]))
            q_br = float(np.mean(gray_p[110:220, 80:160]))
            min_quad = min(q_tl, q_tr, q_bl, q_br)
            mean_lum = float(np.mean(gray_p))

            if min_quad < 82.0 or mean_lum < 92.0:
                continue

            # Requirement 2: Internal handwriting / text strokes
            bg_p = cv2.GaussianBlur(gray_p, (15, 15), 0)
            diff_p = bg_p.astype(np.float32) - gray_p.astype(np.float32)
            strk_mask = diff_p > 10.0
            stroke_ratio = float(np.mean(strk_mask))
            if stroke_ratio < 0.025:
                continue

            # Stroke uniformity across horizontal columns (reject wrinkles on outer edge)
            left_s = float(np.mean(strk_mask[:, :32]))
            mid_s = float(np.mean(strk_mask[:, 32:128]))
            if abs(left_s - mid_s) > 0.06:
                continue

            # Requirement 3: Continuous paper boundary along the 4 sides
            edge_mags = []
            for i in range(4):
                p1 = ordered[i]
                p2 = ordered[(i + 1) % 4]
                n_samples = max(10, int(np.hypot(p2[0] - p1[0], p2[1] - p1[1])) // 6)
                xs = np.clip(np.linspace(p1[0], p2[0], n_samples).astype(int), 0, img_w - 1)
                ys = np.clip(np.linspace(p1[1], p2[1], n_samples).astype(int), 0, img_h - 1)
                edge_mags.append(float(np.mean(mag[ys, xs])))
            mean_edge = float(np.mean(edge_mags))
            if mean_edge < 12.0:
                continue

            # Boundary contrast step across all 4 candidate sides
            steps = []
            t_xs = np.clip(np.linspace(ordered[0][0], ordered[1][0], 15).astype(int), 10, img_w - 11)
            t_ys = np.clip(np.linspace(ordered[0][1], ordered[1][1], 15).astype(int), 15, img_h - 16)
            steps.append(abs(float(np.mean(gray[t_ys - 10, t_xs])) - float(np.mean(gray[t_ys + 10, t_xs]))))

            l_xs = np.clip(np.linspace(ordered[0][0], ordered[3][0], 15).astype(int), 15, img_w - 16)
            l_ys = np.clip(np.linspace(ordered[0][1], ordered[3][1], 15).astype(int), 10, img_h - 11)
            steps.append(abs(float(np.mean(gray[l_ys, l_xs - 10])) - float(np.mean(gray[l_ys, l_xs + 10]))))

            r_xs = np.clip(np.linspace(ordered[1][0], ordered[2][0], 15).astype(int), 15, img_w - 16)
            r_ys = np.clip(np.linspace(ordered[1][1], ordered[2][1], 15).astype(int), 10, img_h - 11)
            steps.append(abs(float(np.mean(gray[r_ys, r_xs + 10])) - float(np.mean(gray[r_ys, r_xs - 10]))))

            b_xs = np.clip(np.linspace(ordered[3][0], ordered[2][0], 15).astype(int), 10, img_w - 11)
            b_ys = np.clip(np.linspace(ordered[3][1], ordered[2][1], 15).astype(int), 15, img_h - 16)
            steps.append(abs(float(np.mean(gray[b_ys + 10, b_xs])) - float(np.mean(gray[b_ys - 10, b_xs]))))
            mean_step = float(np.mean(steps))

            # Document geometry match: standard document aspect ratios (~0.71 portrait or ~1.41 landscape)
            geom_match = max(0.0, 1.0 - min(abs(ar - 0.71) / 0.71, abs(ar - 1.41) / 1.41))
            sym_score = 1.0 - (diff_w + diff_h) / 2.0

            # Score: Purely based on physical boundary, substrate purity, and text density (NO raw area bias)
            confidence = (mean_edge * 0.35) + (mean_step * 1.5) + (geom_match * 10.0) + (stroke_ratio * 25.0) + (sym_score * 8.0)
            scored_candidates.append((confidence, area, ordered, msg, ar, mean_edge))
        except Exception:
            continue

    if not scored_candidates:
        return None

    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    best_conf, best_area, best_corners, best_msg, best_ar, best_edge = scored_candidates[0]

    return {
        "corners": best_corners,
        "area": best_area,
        "area_ratio": best_area / total_area,
        "aspect_ratio": best_ar,
        "validation_msg": best_msg,
        "confidence": best_conf,
        "edge_gradient": best_edge,
    }


# ---------------------------------------------------------------------------
# Perspective Correction
# ---------------------------------------------------------------------------

def warp_perspective(
    image: np.ndarray,
    ordered_corners: np.ndarray,
    interp_method: int = cv2.INTER_CUBIC,
) -> Tuple[np.ndarray, np.ndarray, Tuple[int, int]]:
    """
    Applies cv2.getPerspectiveTransform() and cv2.warpPerspective() to project
    the arbitrary quadrilateral into an unwarped rectangular document image.
    Crops out all background outside the document boundary.
    Destination dimensions are calculated from corresponding ordered opposite edges:
    - top (TL->TR) and bottom (BL->BR) define output width
    - left (TL->BL) and right (TR->BR) define output height
    """
    tl, tr, br, bl = ordered_corners

    width_top = float(np.linalg.norm(tr - tl))
    width_bottom = float(np.linalg.norm(br - bl))
    max_w = int(round(max(width_top, width_bottom)))

    height_left = float(np.linalg.norm(bl - tl))
    height_right = float(np.linalg.norm(br - tr))
    max_h = int(round(max(height_left, height_right)))

    max_w = max(100, max_w)
    max_h = max(100, max_h)

    dst_corners = np.array([
        [0.0, 0.0],
        [float(max_w - 1), 0.0],
        [float(max_w - 1), float(max_h - 1)],
        [0.0, float(max_h - 1)]
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(ordered_corners, dst_corners)
    warped = cv2.warpPerspective(
        image,
        M,
        (max_w, max_h),
        flags=interp_method,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255)
    )

    return warped, M, (max_w, max_h)


# ---------------------------------------------------------------------------
# Non-Document Validation & Surface Triage
# ---------------------------------------------------------------------------

def validate_document_substrate_and_content(
    warped_bgr: np.ndarray,
    min_mean_luminance: float = 85.0,
    max_mean_saturation: float = 85.0,
    min_stroke_ratio: float = 0.0025,
) -> Tuple[bool, str, str]:
    """
    Rejects non-document objects that form sharp rectangles:
    - Closed dark copies / notebook covers (low mean luminance < 85)
    - Brightly colored plastic/cloth folders (high saturation > 85)
    - Completely empty tables, floors, or plain walls (stroke ratio < 0.0025)

    Accepts genuine handwritten and printed examination answer sheets.
    """
    h, w = warped_bgr.shape[:2]
    total_pixels = h * w
    if total_pixels == 0:
        return False, "EMPTY_IMAGE", "Image payload is empty"

    gray = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2GRAY) if warped_bgr.ndim == 3 else warped_bgr
    hsv = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2HSV) if warped_bgr.ndim == 3 else None

    mean_gray = float(np.mean(gray))
    mean_sat = float(np.mean(hsv[:, :, 1])) if hsv is not None else 0.0

    if mean_gray < min_mean_luminance:
        return False, "DARK_NON_DOCUMENT_SURFACE", (
            f"Surface is too dark for examination paper (mean luminance {mean_gray:.1f} < {min_mean_luminance}). "
            "Ensure document page is open and well illuminated."
        )

    if mean_sat > max_mean_saturation:
        return False, "SATURATED_NON_DOCUMENT_COVER", (
            f"Surface exhibits excessive color saturation ({mean_sat:.1f} > {max_mean_saturation}). "
            "Target appears to be a colored notebook cover or non-paper object."
        )

    sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.hypot(sobel_x, sobel_y)

    bg_blur = cv2.GaussianBlur(gray, (31, 31), 0)
    local_contrast = bg_blur.astype(np.float32) - gray.astype(np.float32)

    stroke_mask = (local_contrast > 12.0) & (grad_mag > 18.0)
    stroke_count = int(np.count_nonzero(stroke_mask))
    stroke_ratio = stroke_count / float(max(1, total_pixels))

    if stroke_ratio < min_stroke_ratio:
        return False, "BLANK_SURFACE_NO_CONTENT", (
            f"No discernible handwriting or printed content detected (stroke density {stroke_ratio:.4f} < {min_stroke_ratio}). "
            "Please open to written answer page."
        )

    return True, "DOCUMENT_VALIDATED", (
        f"Valid document content verified (luminance={mean_gray:.1f}, strokes={stroke_ratio:.4f})"
    )


# ---------------------------------------------------------------------------
# Calibrated Sharpness Scoring
# ---------------------------------------------------------------------------

def compute_sharpness_metrics(
    image_gray_or_bgr: np.ndarray,
    defocus_threshold: float = 55.0,
) -> Tuple[float, float, bool]:
    """
    Computes both:
    1. sharpness_raw: Unscaled diagnostic Laplacian variance (e.g. 1500+).
    2. sharpness_score: User-facing clarity score normalized in range 0.0–100.0.
    3. blur_detected: Boolean flag indicating optical defocus / motion blur.
    """
    if image_gray_or_bgr.ndim == 3:
        gray = cv2.cvtColor(image_gray_or_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = image_gray_or_bgr

    raw_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    if raw_var < defocus_threshold:
        blur_flag = True
        score = max(5.0, min(54.9, (raw_var / defocus_threshold) * 50.0))
    else:
        blur_flag = False
        progress = min(1.0, (raw_var - defocus_threshold) / 945.0)
        score = 55.0 + (progress * 44.5)

    return round(raw_var, 2), round(score, 1), blur_flag


# ---------------------------------------------------------------------------
# Camera Preview Boundary Overlay
# ---------------------------------------------------------------------------

def draw_document_overlay(
    image: np.ndarray,
    corners: Optional[np.ndarray],
    is_valid: bool = True,
) -> np.ndarray:
    """
    Draws four-corner quadrilateral overlay suitable for live camera preview feedback:
    - Green polygon and anchor circles when a valid document is locked.
    - Amber polygon when detection is in progress or geometric validity is weak.
    """
    overlay = image.copy()
    if corners is None or len(corners) != 4:
        return overlay

    pts = np.int32(corners).reshape((-1, 1, 2))
    color = (0, 220, 0) if is_valid else (0, 165, 255)

    cv2.polylines(overlay, [pts], isClosed=True, color=color, thickness=3, lineType=cv2.LINE_AA)

    corner_labels = ["TL", "TR", "BR", "BL"]
    for i, pt in enumerate(corners):
        px, py = int(round(pt[0])), int(round(pt[1]))
        cv2.circle(overlay, (px, py), 9, (255, 255, 255), -1, lineType=cv2.LINE_AA)
        cv2.circle(overlay, (px, py), 7, color, -1, lineType=cv2.LINE_AA)
        cv2.putText(
            overlay, corner_labels[i],
            (px + 12, py + 4),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5,
            (255, 255, 255), 2, cv2.LINE_AA
        )

    return overlay


# ---------------------------------------------------------------------------
# High-Level Scanner Pipeline Function
# ---------------------------------------------------------------------------

def scan_document(
    image_input: Union[str, np.ndarray],
    debug: bool = False,
    debug_dir: Optional[str] = None,
) -> DocumentScanResult:
    """
    End-to-end scanner pipeline:
    1. Intake & image loading
    2. Multi-threshold document quadrilateral detection
    3. Non-document rejection (selfies, blank walls, dark/saturated covers)
    4. Canonical 4-corner ordering
    5. Perspective rectification (warped straight page, background removed)
    6. Calibrated 0–100 sharpness score calculation (retaining raw variance)
    7. Diagnostic debug artifact generation if enabled
    """
    if isinstance(image_input, str):
        if not os.path.exists(image_input):
            return DocumentScanResult(
                detected=False,
                corners=None,
                warped_image=None,
                sharpness_raw=0.0,
                sharpness_score=0.0,
                document_score=0.0,
                quality_status="RESCAN_REQUIRED",
                reason=f"Image file not found: {image_input}"
            )
        img = cv2.imread(image_input)
        if img is None:
            return DocumentScanResult(
                detected=False,
                corners=None,
                warped_image=None,
                sharpness_raw=0.0,
                sharpness_score=0.0,
                document_score=0.0,
                quality_status="RESCAN_REQUIRED",
                reason=f"Failed to decode image from path: {image_input}"
            )
        image_name = os.path.basename(image_input)
    elif isinstance(image_input, np.ndarray):
        img = image_input
        image_name = "captured_frame"
    else:
        raise TypeError(f"Unsupported image_input type: {type(image_input)}")

    img_h, img_w = img.shape[:2]

    quad_res = detect_document_quad(img)

    if quad_res is None:
        raw_sharp, score_sharp, _ = compute_sharpness_metrics(img)
        return DocumentScanResult(
            detected=False,
            corners=None,
            warped_image=None,
            sharpness_raw=raw_sharp,
            sharpness_score=score_sharp,
            document_score=0.0,
            quality_status="RESCAN_REQUIRED",
            reason="No document boundary detected. Position answer sheet flat inside the camera frame.",
            area_ratio=0.0,
            aspect_ratio=0.0
        )

    corners = quad_res["corners"]
    corners_list = [(float(pt[0]), float(pt[1])) for pt in corners]

    warped, M, (dest_w, dest_h) = warp_perspective(img, corners)

    is_valid_content, failure_code, content_msg = validate_document_substrate_and_content(warped)
    if not is_valid_content:
        raw_sharp, score_sharp, _ = compute_sharpness_metrics(warped)
        return DocumentScanResult(
            detected=False,
            corners=corners_list,
            warped_image=warped,
            sharpness_raw=raw_sharp,
            sharpness_score=score_sharp,
            document_score=0.0,
            quality_status="RESCAN_REQUIRED",
            reason=content_msg,
            transform_matrix=M,
            area_ratio=quad_res["area_ratio"],
            aspect_ratio=quad_res["aspect_ratio"]
        )

    sharpness_raw, sharpness_score, blur_detected = compute_sharpness_metrics(warped)

    if blur_detected:
        quality_status = "RESCAN_REQUIRED"
        reason = f"Image is blurry (sharpness score {sharpness_score}/100 below threshold 55.0). Hold camera steady."
    else:
        quality_status = "PASSED"
        reason = None

    document_score = sharpness_score

    debug_artifacts: Optional[Dict[str, str]] = None
    if debug:
        out_dir = debug_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_output")
        os.makedirs(out_dir, exist_ok=True)
        base = os.path.splitext(image_name)[0]

        path_orig = os.path.join(out_dir, f"{base}_1_original.jpg")
        path_overlay = os.path.join(out_dir, f"{base}_2_boundary_overlay.jpg")
        path_warped = os.path.join(out_dir, f"{base}_3_warped_document.jpg")

        cv2.imwrite(path_orig, img)
        overlay_img = draw_document_overlay(img, corners, is_valid=True)
        cv2.imwrite(path_overlay, overlay_img)
        cv2.imwrite(path_warped, warped)

        debug_artifacts = {
            "original": path_orig,
            "boundary_overlay": path_overlay,
            "warped_document": path_warped,
        }

    return DocumentScanResult(
        detected=True,
        corners=corners_list,
        warped_image=warped,
        sharpness_raw=sharpness_raw,
        sharpness_score=sharpness_score,
        document_score=document_score,
        quality_status=quality_status,
        reason=reason,
        transform_matrix=M,
        area_ratio=quad_res["area_ratio"],
        aspect_ratio=quad_res["aspect_ratio"],
        debug_artifacts=debug_artifacts
    )
