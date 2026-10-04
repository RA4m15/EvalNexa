"""
phase2/07_page_region_candidate_detection.py

ARCHITECTURAL REFACTOR — PAGE-REGION CANDIDATE GENERATION & EVALUATION SYSTEM

PURPOSE:
An investigation-only candidate generation and diagnostic evaluation framework
designed for multi-hypothesis answer-sheet page detection across varying framing,
zoom, resolution, and aspect ratios.

LOCKED ARCHITECTURAL PRINCIPLES:
1. Two-Stage Separation:
   - Stage 1 (Validity Gate): Rejects physically impossible or degenerate candidates
     (extreme slivers, tiny specks, contentless noise). Does NOT use frame coverage
     as positive evidence.
   - Stage 2 (Diagnostic Ranking): Multi-role evidence evaluation.
2. Evidence Roles:
   - Primary Evidence: Relative paper-vs-background appearance (interior vs surround)
     and active content/edge capture.
   - Supporting Evidence: Robust high-percentile local texture contrast and content
     envelope coherence.
   - Weak Prior: Aspect-ratio plausibility (neutral across common portrait documents,
     never assuming strict A4).
   - Penalties: Background color leakage into interior and extreme lopsided content.
   - Removed from Positive Scoring: Raw frame coverage, unconditioned quadrant CV,
     and image-specific gradient step thresholds.
3. Strategy D Isolation:
   - Structural sub-region split is isolated as an experimental case-study strategy
     and does not participate in generic candidate generation.

NOTE: All scoring formulas and ranking weights are provisional architectural scaffolding,
not calibrated thresholds. No claim of final robustness or generalization is made.
"""

import os
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CALIBRATION_IMAGES = [
    "answer_sheet.jpg",
    "answer_sheet_2.png",
    "answer_sheet_3.jpg",
    "answer_sheet_4.jpg",
    "answer_sheet_5.jpg",
]
IMAGES_DIR = "images"
OUTPUT_DIR = "phase2/output"

# ---------------------------------------------------------------------------
# Feature #1 — Local Boundary Appearance: Provisional Collar Width
# ---------------------------------------------------------------------------
# PROVISIONAL CONSTANT — easy to replace or make resolution-adaptive later.
# Investigation showed 15-20 px informative at 768x1024 / 1200x1600 resolutions.
# Final width is NOT decided here; this is a clearly isolated placeholder.
PROV_COLLAR_WIDTH = 15

# Diagnostic visualization image (reference case study)
PRIMARY_VIS_IMAGE = "images/answer_sheet.jpg"


# ===========================================================================
# 1. Multi-Signal Precomputations
# ===========================================================================
def load_and_preprocess(image_path):
    """
    Load image and precompute Grayscale, HSV Saturation, Canny Edges,
    and Local Variance Map.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    bgr = cv2.imread(image_path)
    if bgr is None:
        raise ValueError(f"Failed to read image: {image_path}")

    h, w, _ = bgr.shape
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]

    # Canny edges (standard diagnostic parameters)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    # Local variance map: Var(X) = E[X^2] - (E[X])^2
    # Kernel size scales softly with resolution to avoid extreme pixel-scale bias
    diag = np.sqrt(h * h + w * w)
    ksize = max(9, int(round(diag * 0.01)) | 1)  # ~1% of diagonal, odd integer
    kernel = np.ones((ksize, ksize), np.float32) / (ksize * ksize)
    gray_f = gray.astype(np.float32)
    mean_gray = cv2.filter2D(gray_f, -1, kernel)
    mean_sq_gray = cv2.filter2D(gray_f ** 2, -1, kernel)
    var_map = np.maximum(0.0, mean_sq_gray - (mean_gray ** 2))

    return {
        "bgr": bgr,
        "gray": gray,
        "sat": sat,
        "edges": edges,
        "var_map": var_map,
        "height": h,
        "width": w,
        "ksize": ksize,
    }


# ===========================================================================
# FEATURE #1 — LOCAL BOUNDARY APPEARANCE: RAW EDGE MEASUREMENT LAYER
# ===========================================================================
def _collar_stats(gray_img, sat_img, r1, r2, c1, c2, img_h, img_w):
    """
    Extract raw stats from a collar strip defined by pixel rows [r1, r2)
    and columns [c1, c2), clipped safely to image bounds.

    Returns dict with mean_b, mean_s, std_b, std_s, valid_px,
    or all-None if the clipped region is empty.
    """
    r1c = max(0, r1)
    r2c = min(img_h, r2)
    c1c = max(0, c1)
    c2c = min(img_w, c2)

    if r2c <= r1c or c2c <= c1c:
        return {"mean_b": None, "mean_s": None, "std_b": None, "std_s": None, "valid_px": 0}

    strip_b = gray_img[r1c:r2c, c1c:c2c].astype(np.float32)
    strip_s = sat_img[r1c:r2c, c1c:c2c].astype(np.float32)
    valid_px = strip_b.size

    return {
        "mean_b": float(np.mean(strip_b)),
        "mean_s": float(np.mean(strip_s)),
        "std_b":  float(np.std(strip_b)),
        "std_s":  float(np.std(strip_s)),
        "valid_px": valid_px,
    }


def _gradient_at_seam(gray_img, axis, seam_idx, c1, c2, img_h, img_w, half_w=2):
    """
    Compute mean Sobel gradient magnitude along a 1-D seam.

    axis=0  → horizontal seam at row=seam_idx, cols [c1, c2)
    axis=1  → vertical seam at col=seam_idx,   rows [c1, c2)

    half_w: number of pixels either side of the seam included in the
    gradient strip (keeps the window narrow, centred on the boundary).
    """
    if axis == 0:
        r1 = max(0, seam_idx - half_w)
        r2 = min(img_h, seam_idx + half_w + 1)
        c1c, c2c = max(0, c1), min(img_w, c2)
        if r2 <= r1 or c2c <= c1c:
            return 0.0
        strip = gray_img[r1:r2, c1c:c2c].astype(np.float32)
    else:
        r1c, r2c = max(0, c1), min(img_h, c2)  # c1/c2 are rows when axis=1
        c1_s = max(0, seam_idx - half_w)
        c2_s = min(img_w, seam_idx + half_w + 1)
        if r2c <= r1c or c2_s <= c1_s:
            return 0.0
        strip = gray_img[r1c:r2c, c1_s:c2_s].astype(np.float32)

    sob_x = cv2.Sobel(strip, cv2.CV_32F, 1, 0, ksize=3)
    sob_y = cv2.Sobel(strip, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(sob_x**2 + sob_y**2)
    return float(np.mean(mag))


def _classify_edge_state(outer_stats, inner_stats, img_h, img_w):
    """
    Determine the state of one edge and any contamination reason.

    Rules (in order):
    1. UNOBSERVED   — outer collar has 0 valid pixels.
    2. POTENTIALLY_CONTAMINATED / POSSIBLE_ADJACENT_PAGE —
         outer collar looks paper-like (mean_b > 160 AND mean_s < 25)
         while inner collar is also paper-like. This suggests another
         physical sheet immediately outside the candidate edge.
         NOTE: low delta_S alone is NOT sufficient; brightness level is
         required to avoid flagging dark backgrounds with low saturation.
    3. POTENTIALLY_CONTAMINATED / NO_CONTRAST —
         absolute delta_brightness is very small (< 5) AND
         boundary_gradient_mag will be checked externally; flag is set
         here only on the brightness criterion so the caller can
         cross-reference gradient evidence independently.
    4. OBSERVED      — all other cases.

    Returns (state, reason).
    """
    if outer_stats["valid_px"] == 0:
        return "UNOBSERVED", None

    outer_b = outer_stats["mean_b"]
    outer_s = outer_stats["mean_s"]
    inner_b = inner_stats["mean_b"]
    inner_s = inner_stats["mean_s"]

    # Paper-like region heuristic: bright AND achromatic
    PAPER_BRIGHT_FLOOR = 160.0
    PAPER_SAT_CEILING  = 25.0

    outer_looks_like_paper = (outer_b is not None
                              and outer_b > PAPER_BRIGHT_FLOOR
                              and outer_s < PAPER_SAT_CEILING)
    inner_looks_like_paper = (inner_b is not None
                              and inner_b > PAPER_BRIGHT_FLOOR
                              and inner_s < PAPER_SAT_CEILING)

    if outer_looks_like_paper and inner_looks_like_paper:
        return "POTENTIALLY_CONTAMINATED", "POSSIBLE_ADJACENT_PAGE"

    # No-contrast flag (brightness only; gradient checked later by caller)
    if inner_b is not None and abs(inner_b - outer_b) < 5.0:
        return "POTENTIALLY_CONTAMINATED", "NO_CONTRAST"

    return "OBSERVED", None


def measure_boundary_collars(cand, gray_img, sat_img, img_h, img_w,
                              collar_width=PROV_COLLAR_WIDTH):
    """
    Feature #1 — Local Boundary Appearance: Raw Edge Measurement Layer.

    For each of the four edges (TOP, BOTTOM, LEFT, RIGHT) of the candidate
    bounding box, compute:
      - inner collar strip  (collar_width px inside the candidate edge)
      - outer collar strip  (collar_width px outside the candidate edge)

    Returns a dict with four EdgeRecord dicts keyed by edge name,
    plus summary counts (observed_edge_count, unobserved_edge_count,
    contaminated_edge_count).

    IMPORTANT: Nothing is normalised, clipped, or converted to a score here.
    All values are physical pixel measurements only.
    """
    x, y, bw, bh = cand["box"]
    x2, y2 = x + bw, y + bh  # exclusive right/bottom

    # Sobel gradient image (pre-computed once, used for seam gradient queries)
    gray_f = gray_img.astype(np.float32)
    sob_x = cv2.Sobel(gray_f, cv2.CV_32F, 1, 0, ksize=3)
    sob_y = cv2.Sobel(gray_f, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.sqrt(sob_x**2 + sob_y**2)  # (img_h, img_w)

    edge_specs = {
        #  edge    inner rows        inner cols      outer rows        outer cols      seam axis  seam coord  seam span cols/rows
        "TOP":    dict(
            inner_r=(y,          y + collar_width),
            inner_c=(x,          x2),
            outer_r=(y - collar_width, y),
            outer_c=(x,          x2),
            seam_axis=0, seam_idx=y, seam_c1=x, seam_c2=x2,
        ),
        "BOTTOM": dict(
            inner_r=(y2 - collar_width, y2),
            inner_c=(x,          x2),
            outer_r=(y2,         y2 + collar_width),
            outer_c=(x,          x2),
            seam_axis=0, seam_idx=y2, seam_c1=x, seam_c2=x2,
        ),
        "LEFT":   dict(
            inner_r=(y,          y2),
            inner_c=(x,          x + collar_width),
            outer_r=(y,          y2),
            outer_c=(x - collar_width, x),
            seam_axis=1, seam_idx=x, seam_c1=y, seam_c2=y2,
        ),
        "RIGHT":  dict(
            inner_r=(y,          y2),
            inner_c=(x2 - collar_width, x2),
            outer_r=(y,          y2),
            outer_c=(x2,         x2 + collar_width),
            seam_axis=1, seam_idx=x2, seam_c1=y, seam_c2=y2,
        ),
    }

    edge_records = {}
    for edge_name, spec in edge_specs.items():
        inner_st = _collar_stats(
            gray_img, sat_img,
            spec["inner_r"][0], spec["inner_r"][1],
            spec["inner_c"][0], spec["inner_c"][1],
            img_h, img_w,
        )
        outer_st = _collar_stats(
            gray_img, sat_img,
            spec["outer_r"][0], spec["outer_r"][1],
            spec["outer_c"][0], spec["outer_c"][1],
            img_h, img_w,
        )

        state, reason = _classify_edge_state(outer_st, inner_st, img_h, img_w)

        # Compute delta values (raw arithmetic only; None-safe)
        if inner_st["mean_b"] is not None and outer_st["mean_b"] is not None:
            delta_b = inner_st["mean_b"] - outer_st["mean_b"]   # + means interior brighter
            delta_s = outer_st["mean_s"] - inner_st["mean_s"]   # + means exterior more chromatic
        else:
            delta_b = None
            delta_s = None

        # Boundary gradient magnitude (seam-centred, independent of collar stats)
        # Use pre-computed gradient magnitude image for efficiency
        ax = spec["seam_axis"]
        sidx = spec["seam_idx"]
        sc1, sc2 = spec["seam_c1"], spec["seam_c2"]
        half_w = 2
        if ax == 0:   # horizontal seam at row=sidx
            r1s = max(0, sidx - half_w)
            r2s = min(img_h, sidx + half_w + 1)
            c1s, c2s = max(0, sc1), min(img_w, sc2)
        else:         # vertical seam at col=sidx
            r1s, r2s = max(0, sc1), min(img_h, sc2)
            c1s = max(0, sidx - half_w)
            c2s = min(img_w, sidx + half_w + 1)

        if r2s > r1s and c2s > c1s:
            seam_strip = grad_mag[r1s:r2s, c1s:c2s]
            boundary_gradient_mag = float(np.mean(seam_strip))
        else:
            boundary_gradient_mag = 0.0

        edge_records[edge_name] = {
            "edge":                 edge_name,
            "state":               state,
            "contamination_reason": reason,
            # Brightness
            "inner_brightness":     inner_st["mean_b"],
            "outer_brightness":     outer_st["mean_b"],
            "delta_brightness":     delta_b,
            # Saturation
            "inner_saturation":     inner_st["mean_s"],
            "outer_saturation":     outer_st["mean_s"],
            "delta_saturation":     delta_s,
            # Gradient (independent stream)
            "boundary_gradient_mag": boundary_gradient_mag,
            # Pixel counts
            "inner_valid_px":       inner_st["valid_px"],
            "outer_valid_px":       outer_st["valid_px"],
            # Spread metrics (contamination early-warning)
            "inner_brightness_std": inner_st["std_b"],
            "outer_brightness_std": outer_st["std_b"],
            "inner_saturation_std": inner_st["std_s"],
            "outer_saturation_std": outer_st["std_s"],
        }

    observed   = sum(1 for r in edge_records.values() if r["state"] == "OBSERVED")
    unobserved = sum(1 for r in edge_records.values() if r["state"] == "UNOBSERVED")
    contaminated = sum(1 for r in edge_records.values() if r["state"] == "POTENTIALLY_CONTAMINATED")

    return {
        "edge_records":          edge_records,
        "observed_edge_count":   observed,
        "unobserved_edge_count": unobserved,
        "contaminated_edge_count": contaminated,
        "collar_width_used":     collar_width,
    }


# ===========================================================================
# FEATURE #2 — ACTIVE DOCUMENT EDGES: RAW MEASUREMENT LAYER
# ===========================================================================
def measure_active_document_edges(cand, edges_img, img_h, img_w):
    """
    Feature #2 — Active Document Edges: Raw Measurement Layer.

    Measures the internal edge structure of a candidate box using the
    pre-computed Canny edge map.  All measurements are candidate-interior
    only — no scene-wide ratio such as candidate_edges / total_scene_edges
    is computed here.

    Returned measurements
    ---------------------
    edge_pixel_count        : int    absolute number of edge pixels in the ROI
    edge_density            : float  edge_pixel_count / roi_area  (0.0 – 1.0)
    roi_area                : int    bounding-box pixel area (clipped to image)
    active_row_count        : int    rows that contain > 0 edge pixels
    active_row_fraction     : float  active_row_count / roi_height
    active_col_count        : int    columns that contain > 0 edge pixels
    active_col_fraction     : float  active_col_count / roi_width

    row_edge_profile        : ndarray  per-row edge-pixel count  (length = roi_h)
    col_edge_profile        : ndarray  per-col edge-pixel count  (length = roi_w)

    Row distribution stats (over rows that contain >= 1 edge pixel):
      row_dist_mean, row_dist_std, row_dist_min, row_dist_max
      row_dist_p25, row_dist_p75, row_dist_iqr
      row_dist_cov            coefficient of variation (std/mean) — spread indicator
      row_dist_gini           Gini coefficient — concentration indicator

    Column distribution stats (equivalent set for columns):
      col_dist_mean … col_dist_gini

    NOTE: Nothing is normalised into a score.  Raw physical counts only.
    """
    x, y, bw, bh = cand["box"]

    # Clip ROI safely to image bounds
    r1 = max(0, y)
    r2 = min(img_h, y + bh)
    c1 = max(0, x)
    c2 = min(img_w, x + bw)

    roi_h = max(1, r2 - r1)
    roi_w = max(1, c2 - c1)
    roi_area = roi_h * roi_w

    roi_edges = edges_img[r1:r2, c1:c2]          # uint8 Canny map, values 0 or 255
    edge_binary = (roi_edges > 0).astype(np.int32)

    # ---- Basic counts --------------------------------------------------
    edge_pixel_count = int(np.sum(edge_binary))
    edge_density = edge_pixel_count / float(roi_area)  # true pixel fraction

    # ---- Row / column activity -----------------------------------------
    row_edge_profile = np.sum(edge_binary, axis=1)  # (roi_h,) counts per row
    col_edge_profile = np.sum(edge_binary, axis=0)  # (roi_w,) counts per col

    active_row_count = int(np.count_nonzero(row_edge_profile))
    active_col_count = int(np.count_nonzero(col_edge_profile))
    active_row_fraction = active_row_count / float(roi_h)
    active_col_fraction = active_col_count / float(roi_w)

    # ---- Distribution statistics helper --------------------------------
    def _dist_stats(profile):
        """
        Compute distribution statistics over the non-zero entries of profile.
        Returns a dict; all values are raw, unclipped.
        If no non-zero entries exist, returns None for each stat.
        """
        active = profile[profile > 0].astype(np.float64)
        if active.size == 0:
            return {
                "mean": 0.0, "std": 0.0,
                "min": 0.0, "max": 0.0,
                "p25": 0.0, "p75": 0.0, "iqr": 0.0,
                "cov": 0.0, "gini": 0.0,
            }
        mn   = float(np.mean(active))
        sd   = float(np.std(active))
        mn_v = float(np.min(active))
        mx_v = float(np.max(active))
        p25  = float(np.percentile(active, 25))
        p75  = float(np.percentile(active, 75))
        iqr  = p75 - p25
        cov  = sd / mn if mn > 0.0 else 0.0

        # Gini coefficient: measure of concentration (0=uniform, 1=all in one)
        # Computed on the full profile (including zeros) so empty rows count.
        full = profile.astype(np.float64)
        full_sorted = np.sort(full)
        n = full_sorted.size
        if n > 1 and np.sum(full_sorted) > 0:
            cum = np.cumsum(full_sorted)
            gini = float((2.0 * np.sum((np.arange(1, n + 1) * full_sorted))) /
                         (n * np.sum(full_sorted)) - (n + 1) / n)
            gini = abs(gini)   # numerical safety; result is always >= 0
        else:
            gini = 0.0

        return {
            "mean": mn, "std": sd,
            "min": mn_v, "max": mx_v,
            "p25": p25, "p75": p75, "iqr": iqr,
            "cov": cov, "gini": gini,
        }

    row_stats = _dist_stats(row_edge_profile)
    col_stats = _dist_stats(col_edge_profile)

    return {
        # Totals
        "edge_pixel_count":     edge_pixel_count,
        "edge_density":         edge_density,
        "roi_area":             roi_area,
        # Row activity
        "active_row_count":     active_row_count,
        "active_row_fraction":  active_row_fraction,
        # Column activity
        "active_col_count":     active_col_count,
        "active_col_fraction":  active_col_fraction,
        # Profiles (stored as lists for JSON-friendliness if needed later)
        "row_edge_profile":     row_edge_profile,
        "col_edge_profile":     col_edge_profile,
        # Distribution stats
        "row_dist":             row_stats,
        "col_dist":             col_stats,
    }


# ===========================================================================
# FEATURE #3 — TEXTURE / MICROCONTRAST: RAW MEASUREMENT LAYER
# ===========================================================================
def measure_texture_microcontrast(cand, var_map, var_ksize, img_h, img_w):
    """
    Feature #3 — Texture / Microcontrast: Raw Measurement Layer.

    Measures local visual variation inside a candidate using the pre-computed
    local variance map produced by load_and_preprocess().  The variance map
    uses a resolution-aware kernel (ksize ~ 1% of image diagonal, odd-integer)
    and is passed in directly — no second preprocessing pipeline is created.

    The var_ksize argument is the kernel side-length actually used, preserved
    as audit metadata alongside every result.

    IMPORTANT: High local variance is NOT interpreted as document evidence here.
    Wood/desk surfaces also produce high local variance.  Raw values only.

    Returned measurements
    ---------------------
    var_ksize               : int    window side-length (from precomputation)
    roi_pixel_count         : int    pixels in the clipped ROI

    Global ROI statistics:
      mean_var              : float  mean of local variance over ROI
      std_var               : float  standard deviation of local variance over ROI
      min_var               : float  minimum local variance in ROI
      max_var               : float  maximum local variance in ROI
      p50_var               : float  50th percentile (median)
      p75_var               : float  75th percentile
      p90_var               : float  90th percentile
      p95_var               : float  95th percentile

    High-variance spatial coverage (measured at ROI-internal percentile thresholds):
      hv_frac_above_p50     : float  fraction of ROI pixels with var > ROI P50
      hv_frac_above_p75     : float  fraction of ROI pixels with var > ROI P75
      hv_frac_above_p90     : float  fraction of ROI pixels with var > ROI P90
      (These measure internal spread; by construction P50-based fraction ~0.50)

    Row-wise texture profile:
      row_tex_profile       : ndarray  per-row mean variance (length = roi_h)
      row_tex_mean          : float    mean of row profile
      row_tex_std           : float    std of row profile
      row_tex_min           : float    min of row profile
      row_tex_max           : float    max of row profile
      row_tex_cov           : float    coefficient of variation (std/mean)
      row_tex_gini          : float    Gini coefficient (concentration across rows)

    Column-wise texture profile:
      col_tex_profile       : ndarray  per-col mean variance (length = roi_w)
      col_tex_mean … col_tex_gini  (same set as row_tex_*)
    """
    x, y, bw, bh = cand["box"]

    # Clip ROI safely to image bounds
    r1 = max(0, y)
    r2 = min(img_h, y + bh)
    c1 = max(0, x)
    c2 = min(img_w, x + bw)
    roi_h = max(1, r2 - r1)
    roi_w = max(1, c2 - c1)

    roi_var = var_map[r1:r2, c1:c2].astype(np.float64)  # float64 for precision
    roi_pixel_count = roi_var.size

    flat = roi_var.ravel()

    # ---- Global percentile / spread statistics -------------------------
    mean_var = float(np.mean(flat))
    std_var  = float(np.std(flat))
    min_var  = float(np.min(flat))
    max_var  = float(np.max(flat))
    p50_var  = float(np.percentile(flat, 50))
    p75_var  = float(np.percentile(flat, 75))
    p90_var  = float(np.percentile(flat, 90))
    p95_var  = float(np.percentile(flat, 95))

    # ---- High-variance spatial coverage --------------------------------
    # Measured relative to the candidate's own internal thresholds.
    # Does NOT use image-wide or hard-coded absolute thresholds.
    hv_frac_above_p50 = float(np.mean(flat > p50_var))
    hv_frac_above_p75 = float(np.mean(flat > p75_var))
    hv_frac_above_p90 = float(np.mean(flat > p90_var))

    # ---- Spatial texture profile helper --------------------------------
    def _tex_profile_stats(profile_1d):
        """
        Compute spread statistics over a 1-D array of per-row or per-col
        mean variance values.  All inputs are already float64.
        """
        n = profile_1d.size
        if n == 0:
            return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0,
                    "cov": 0.0, "gini": 0.0}

        mn  = float(np.mean(profile_1d))
        sd  = float(np.std(profile_1d))
        mn_v = float(np.min(profile_1d))
        mx_v = float(np.max(profile_1d))
        cov = sd / mn if mn > 0.0 else 0.0

        # Gini on the full profile (zeros included)
        full_sorted = np.sort(profile_1d)
        total = np.sum(full_sorted)
        if n > 1 and total > 0:
            indices = np.arange(1, n + 1, dtype=np.float64)
            gini = abs(float(
                (2.0 * np.sum(indices * full_sorted)) / (n * total) - (n + 1) / n
            ))
        else:
            gini = 0.0

        return {"mean": mn, "std": sd, "min": mn_v, "max": mx_v,
                "cov": cov, "gini": gini}

    # ---- Row / column texture profiles ---------------------------------
    # Per-row mean variance: captures whether texture is concentrated in
    # certain horizontal bands (e.g. ruled lines, dense handwriting blocks)
    row_tex_profile = np.mean(roi_var, axis=1)   # shape (roi_h,)
    col_tex_profile = np.mean(roi_var, axis=0)   # shape (roi_w,)

    row_stats = _tex_profile_stats(row_tex_profile)
    col_stats = _tex_profile_stats(col_tex_profile)

    return {
        # Audit metadata
        "var_ksize":              var_ksize,
        "roi_pixel_count":        roi_pixel_count,
        # Global statistics
        "mean_var":               mean_var,
        "std_var":                std_var,
        "min_var":                min_var,
        "max_var":                max_var,
        "p50_var":                p50_var,
        "p75_var":                p75_var,
        "p90_var":                p90_var,
        "p95_var":                p95_var,
        # Internal high-variance coverage (fraction, 0.0 – 1.0)
        "hv_frac_above_p50":      hv_frac_above_p50,
        "hv_frac_above_p75":      hv_frac_above_p75,
        "hv_frac_above_p90":      hv_frac_above_p90,
        # Spatial profiles
        "row_tex_profile":        row_tex_profile,
        "col_tex_profile":        col_tex_profile,
        "row_tex_mean":           row_stats["mean"],
        "row_tex_std":            row_stats["std"],
        "row_tex_min":            row_stats["min"],
        "row_tex_max":            row_stats["max"],
        "row_tex_cov":            row_stats["cov"],
        "row_tex_gini":           row_stats["gini"],
        "col_tex_mean":           col_stats["mean"],
        "col_tex_std":            col_stats["std"],
        "col_tex_min":            col_stats["min"],
        "col_tex_max":            col_stats["max"],
        "col_tex_cov":            col_stats["cov"],
        "col_tex_gini":           col_stats["gini"],
    }


# ===========================================================================
# FEATURE #4 -- BOUNDARY COMPACTNESS / CONTENT CONTAINMENT: RAW MEASUREMENT
# ===========================================================================
def _get_boundary_band_width(roi_w, roi_h):
    """
    Isolated scale parameter for Feature #4 boundary band width.
    Derived as a small fraction (2%) of candidate min dimension, clamped to [5, 30] px.
    Kept isolated and NOT tuned to calibration images.
    """
    return max(5, min(30, int(round(min(roi_w, roi_h) * 0.02))))


def _compute_1d_runs(binary_1d):
    """
    Computes number of contiguous active runs (bands) and the longest run length
    from a 1D boolean/binary array.
    """
    if len(binary_1d) == 0 or not np.any(binary_1d):
        return 0, 0
    padded = np.pad(binary_1d.astype(np.int8), (1, 1), mode="constant", constant_values=0)
    diffs = np.diff(padded)
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0]
    lengths = ends - starts
    num_bands = int(len(lengths))
    longest_run = int(np.max(lengths)) if num_bands > 0 else 0
    return num_bands, longest_run


def measure_boundary_compactness(cand, edges_img, img_h, img_w):
    """
    Feature #4 -- Boundary Compactness / Content Containment: Raw Spatial Descriptor.

    Measures how internal edge activity is spatially distributed relative to the
    candidate boundaries.

    Important Semantic Rules:
    - This feature measures: "How is internal edge activity spatially distributed
      relative to the candidate boundaries?"
    - It does NOT measure: "Is this candidate definitely a document?"
    - It does NOT measure: "Is more filled area better?"
    - Blank margins are VALID; real answer sheets often have wide margins.
    - No A4 assumption. No fixed document dimensions. No score/weighting.
    - Centroid and content-bbox AR are retained for diagnostics but clearly
      labeled as diagnostic/redundant.

    Returned measurements:
    ---------------------
    has_content             : bool   True if >= 1 edge pixel was found in ROI
    cand_box                : tuple  (x, y, w, h)
    cand_area               : int    candidate pixel area (clipped to image)

    Content bounding box (absolute coords):
      cb_x, cb_y, cb_w, cb_h: int
      cb_area               : int    cb_w * cb_h

    Diagnostic / Redundant geometry:
      cb_ar                 : float  content bbox AR (diagnostic/redundant)
      centroid_x_norm       : float  normalized x centroid (diagnostic/redundant)
      centroid_y_norm       : float  normalized y centroid (diagnostic/redundant)

    Containment & Margin fractions (existing):
      fill_ratio            : float  cb_area / cand_area (raw diagnostic, gen-dependent)
      margin_left, margin_right, margin_top, margin_bottom : float
      dist_left, dist_right, dist_top, dist_bottom         : int

    Occupancy profiles (existing):
      active_row_fraction, active_col_fraction : float
      row_profile, col_profile                 : np.ndarray

    1. Edge Activity Near Each Candidate Boundary (TOP, BOTTOM, LEFT, RIGHT):
      boundary_activity     : dict of {boundary: {boundary, band_width, edge_pixels, edge_density, active_fraction}}

    2. Dead-Border Width Per Side:
      dead_borders          : dict of {top_dead_border_px, bottom_dead_border_px, left_dead_border_px, right_dead_border_px}

    3. Row/Column Occupancy Structure:
      occupancy_structure   : dict of {active_row_fraction, active_col_fraction,
                                       num_active_row_bands, num_active_col_bands,
                                       longest_active_row_run, longest_active_col_run,
                                       active_row_span, active_col_span}
    """
    x, y, bw, bh = cand["box"]

    # Clip ROI safely to image bounds
    r1 = max(0, y)
    r2 = min(img_h, y + bh)
    c1 = max(0, x)
    c2 = min(img_w, x + bw)
    roi_h = max(1, r2 - r1)
    roi_w = max(1, c2 - c1)
    cand_area = roi_h * roi_w

    roi_edges = edges_img[r1:r2, c1:c2]
    edge_binary = (roi_edges > 0)

    # ---- 1. Edge Activity Near Each Candidate Boundary -----------------
    band_width_scale = _get_boundary_band_width(roi_w, roi_h)

    # TOP band
    top_h = max(1, min(band_width_scale, roi_h))
    top_band = edge_binary[0:top_h, :]
    top_pixels = int(np.count_nonzero(top_band))
    top_density = float(top_pixels) / float(top_band.size)
    top_active_fraction = float(np.count_nonzero(np.sum(top_band, axis=0) > 0)) / float(roi_w)

    # BOTTOM band
    bot_h = max(1, min(band_width_scale, roi_h))
    bot_band = edge_binary[roi_h - bot_h:roi_h, :]
    bot_pixels = int(np.count_nonzero(bot_band))
    bot_density = float(bot_pixels) / float(bot_band.size)
    bot_active_fraction = float(np.count_nonzero(np.sum(bot_band, axis=0) > 0)) / float(roi_w)

    # LEFT band
    left_w = max(1, min(band_width_scale, roi_w))
    left_band = edge_binary[:, 0:left_w]
    left_pixels = int(np.count_nonzero(left_band))
    left_density = float(left_pixels) / float(left_band.size)
    left_active_fraction = float(np.count_nonzero(np.sum(left_band, axis=1) > 0)) / float(roi_h)

    # RIGHT band
    right_w = max(1, min(band_width_scale, roi_w))
    right_band = edge_binary[:, roi_w - right_w:roi_w]
    right_pixels = int(np.count_nonzero(right_band))
    right_density = float(right_pixels) / float(right_band.size)
    right_active_fraction = float(np.count_nonzero(np.sum(right_band, axis=1) > 0)) / float(roi_h)

    boundary_activity = {
        "TOP": {
            "boundary": "TOP",
            "band_width": top_h,
            "edge_pixels": top_pixels,
            "edge_density": top_density,
            "active_fraction": top_active_fraction,
        },
        "BOTTOM": {
            "boundary": "BOTTOM",
            "band_width": bot_h,
            "edge_pixels": bot_pixels,
            "edge_density": bot_density,
            "active_fraction": bot_active_fraction,
        },
        "LEFT": {
            "boundary": "LEFT",
            "band_width": left_w,
            "edge_pixels": left_pixels,
            "edge_density": left_density,
            "active_fraction": left_active_fraction,
        },
        "RIGHT": {
            "boundary": "RIGHT",
            "band_width": right_w,
            "edge_pixels": right_pixels,
            "edge_density": right_density,
            "active_fraction": right_active_fraction,
        },
    }

    # ---- Occupancy profiles -------------------------------------------
    row_profile = np.sum(edge_binary, axis=1)   # (roi_h,)
    col_profile = np.sum(edge_binary, axis=0)   # (roi_w,)
    active_row_mask = (row_profile > 0)
    active_col_mask = (col_profile > 0)
    active_row_fraction = float(np.count_nonzero(active_row_mask)) / float(roi_h)
    active_col_fraction = float(np.count_nonzero(active_col_mask)) / float(roi_w)

    # ---- 3. Row/Column Occupancy Structure ----------------------------
    num_row_bands, longest_row_run = _compute_1d_runs(active_row_mask)
    num_col_bands, longest_col_run = _compute_1d_runs(active_col_mask)

    # Find rows and columns that contain at least one edge pixel
    active_rows = np.where(active_row_mask)[0]
    active_cols = np.where(active_col_mask)[0]

    if active_rows.size == 0 or active_cols.size == 0:
        # No content detected inside this candidate
        dead_borders = {
            "top_dead_border_px": None,
            "bottom_dead_border_px": None,
            "left_dead_border_px": None,
            "right_dead_border_px": None,
        }
        occupancy_structure = {
            "active_row_fraction": 0.0,
            "active_col_fraction": 0.0,
            "num_active_row_bands": 0,
            "num_active_col_bands": 0,
            "longest_active_row_run": 0,
            "longest_active_col_run": 0,
            "active_row_span": 0,
            "active_col_span": 0,
        }
        return {
            "has_content": False,
            "cand_box": cand["box"],
            "cand_area": cand_area,
            "cb_x": None, "cb_y": None, "cb_w": None, "cb_h": None,
            "cb_area": 0,
            "cb_ar": None,
            "fill_ratio": 0.0,
            "margin_left": None, "margin_right": None,
            "margin_top": None, "margin_bottom": None,
            "dist_left": None, "dist_right": None,
            "dist_top": None, "dist_bottom": None,
            "centroid_x_norm": None, "centroid_y_norm": None,
            "active_row_fraction": 0.0,
            "active_col_fraction": 0.0,
            "row_profile": row_profile,
            "col_profile": col_profile,
            "boundary_activity": boundary_activity,
            "dead_borders": dead_borders,
            "occupancy_structure": occupancy_structure,
        }

    # Content bounding box in ROI-local coordinates
    cb_row_min = int(active_rows[0])
    cb_row_max = int(active_rows[-1])
    cb_col_min = int(active_cols[0])
    cb_col_max = int(active_cols[-1])

    # Convert to full-image absolute coordinates
    cb_x = c1 + cb_col_min
    cb_y = r1 + cb_row_min
    cb_w = max(1, cb_col_max - cb_col_min + 1)
    cb_h = max(1, cb_row_max - cb_row_min + 1)
    cb_area = cb_w * cb_h
    cb_ar = float(cb_h) / float(cb_w)

    # ---- 2. Dead-Border Width Per Side --------------------------------
    top_dead_border_px = cb_row_min
    bottom_dead_border_px = roi_h - (cb_row_max + 1)
    left_dead_border_px = cb_col_min
    right_dead_border_px = roi_w - (cb_col_max + 1)

    dead_borders = {
        "top_dead_border_px": top_dead_border_px,
        "bottom_dead_border_px": bottom_dead_border_px,
        "left_dead_border_px": left_dead_border_px,
        "right_dead_border_px": right_dead_border_px,
    }

    # Occupancy structure details
    active_row_span = int(cb_row_max - cb_row_min + 1)
    active_col_span = int(cb_col_max - cb_col_min + 1)
    occupancy_structure = {
        "active_row_fraction": active_row_fraction,
        "active_col_fraction": active_col_fraction,
        "num_active_row_bands": num_row_bands,
        "num_active_col_bands": num_col_bands,
        "longest_active_row_run": longest_row_run,
        "longest_active_col_run": longest_col_run,
        "active_row_span": active_row_span,
        "active_col_span": active_col_span,
    }

    # ---- Containment (raw diagnostic, potentially candidate-gen-dependent)
    fill_ratio = cb_area / float(cand_area)

    # ---- Margin fractions (relative to candidate span) ----------------
    cand_x  = c1
    cand_y  = r1
    cand_x2 = c2
    cand_y2 = r2
    span_w = float(roi_w)
    span_h = float(roi_h)

    margin_left   = float(max(0.0, (cb_x - cand_x) / span_w))
    margin_right  = float(max(0.0, (cand_x2 - (cb_x + cb_w)) / span_w))
    margin_top    = float(max(0.0, (cb_y - cand_y) / span_h))
    margin_bottom = float(max(0.0, (cand_y2 - (cb_y + cb_h)) / span_h))

    # Boundary distances (matching dead borders in px)
    dist_left   = left_dead_border_px
    dist_right  = right_dead_border_px
    dist_top    = top_dead_border_px
    dist_bottom = bottom_dead_border_px

    # ---- Normalized centroid (diagnostic / redundant) -----------------
    centroid_x = cb_x + cb_w / 2.0
    centroid_y = cb_y + cb_h / 2.0
    centroid_x_norm = (centroid_x - cand_x) / span_w
    centroid_y_norm = (centroid_y - cand_y) / span_h

    return {
        "has_content":          True,
        "cand_box":             cand["box"],
        "cand_area":            cand_area,
        # Content bounding box (absolute coords)
        "cb_x":                 cb_x,
        "cb_y":                 cb_y,
        "cb_w":                 cb_w,
        "cb_h":                 cb_h,
        "cb_area":              cb_area,
        # Diagnostic / redundant geometry
        "cb_ar":                cb_ar,
        "centroid_x_norm":      centroid_x_norm,
        "centroid_y_norm":      centroid_y_norm,
        # Containment & Margin fractions (existing)
        "fill_ratio":           fill_ratio,
        "margin_left":          margin_left,
        "margin_right":         margin_right,
        "margin_top":           margin_top,
        "margin_bottom":        margin_bottom,
        # Margin distances (px)
        "dist_left":            dist_left,
        "dist_right":           dist_right,
        "dist_top":             dist_top,
        "dist_bottom":          dist_bottom,
        # Occupancy profiles
        "active_row_fraction":  active_row_fraction,
        "active_col_fraction":  active_col_fraction,
        "row_profile":          row_profile,
        "col_profile":          col_profile,
        # 1. Edge activity near each candidate boundary
        "boundary_activity":    boundary_activity,
        # 2. Dead-border width per side
        "dead_borders":         dead_borders,
        # 3. Row/Column occupancy structure
        "occupancy_structure":  occupancy_structure,
    }


# ===========================================================================
# FEATURE #5 -- GEOMETRY / SHAPE PRIOR: RAW MEASUREMENT
# ===========================================================================
def measure_geometry_shape_prior(cand, img_h, img_w):
    """
    Feature #5 -- Geometry / Shape Prior: Raw Measurement Layer.

    Measures raw candidate geometric properties and spatial relationship to the
    image frame.

    Design rules:
    - This feature measures: "Candidate geometry and spatial relationship to the image frame."
    - It does NOT measure: "Document confidence", "Page quality", "OCR readability",
      or "Whether this is the correct page."
    - No A4 assumption. No portrait or landscape assumption.
    - No fixed aspect ratio or fixed dimension thresholds.
    - No scoring. No weights. No document-acceptance rules.
    - Frame contact and margins are descriptive only (touching frame is not bad,
      not touching is not good).
    - Mathematically redundant metrics are explicitly marked as DIAGNOSTIC / REDUNDANT.

    Returned measurements:
    ---------------------
    candidate_x, candidate_y            : int    top-left corner
    candidate_width, candidate_height   : int    width, height
    candidate_area                      : int    width * height
    candidate_diagonal                  : float  sqrt(w^2 + h^2)
    aspect_ratio_w_over_h               : float  width / height
    aspect_ratio_h_over_w               : float  height / width

    width_fraction_of_image             : float  width / img_w
    height_fraction_of_image            : float  height / img_h
    area_fraction_of_image              : float  area / (img_w * img_h) [redundant]

    rectangularity                      : float  1.0 [redundant for axis-aligned box]
    rectangularity_note                 : str    explanation of redundancy

    touches_top, touches_bottom         : bool   whether candidate touches edge
    touches_left, touches_right         : bool
    number_of_frame_touching_sides      : int    count of touched edges (0-4)

    margin_to_top, margin_to_bottom     : int    distance to image borders (px)
    margin_to_left, margin_to_right     : int
    margin_to_top_norm, margin_to_bottom_norm : float
    margin_to_left_norm, margin_to_right_norm : float

    diagonal_to_perimeter               : float  diagonal / (2 * (w + h))
    diagonal_to_sqrt_area               : float  diagonal / sqrt(area)
    """
    x, y, bw, bh = cand["box"]

    area = int(bw * bh)
    diag = float(np.sqrt(float(bw)**2 + float(bh)**2))

    ar_w_h = float(bw) / float(max(1, bh))
    ar_h_w = float(bh) / float(max(1, bw))

    w_frac = float(bw) / float(max(1, img_w))
    h_frac = float(bh) / float(max(1, img_h))
    area_frac = float(area) / float(max(1, img_w * img_h))

    # Frame contact (diagnostic only)
    touches_top = bool(y <= 0)
    touches_bottom = bool((y + bh) >= img_h)
    touches_left = bool(x <= 0)
    touches_right = bool((x + bw) >= img_w)
    touching_sides = int(sum([touches_top, touches_bottom, touches_left, touches_right]))

    # Frame margins (diagnostic only)
    margin_top = int(max(0, y))
    margin_bottom = int(max(0, img_h - (y + bh)))
    margin_left = int(max(0, x))
    margin_right = int(max(0, img_w - (x + bw)))

    margin_top_norm = float(margin_top) / float(max(1, img_h))
    margin_bottom_norm = float(margin_bottom) / float(max(1, img_h))
    margin_left_norm = float(margin_left) / float(max(1, img_w))
    margin_right_norm = float(margin_right) / float(max(1, img_w))

    # Dimensionless shape consistency descriptors
    perimeter = float(2 * (bw + bh))
    diag_to_perim = float(diag / perimeter) if perimeter > 0 else 0.0
    diag_to_sqrt_area = float(diag / np.sqrt(float(area))) if area > 0 else 0.0

    return {
        "candidate_x": x,
        "candidate_y": y,
        "candidate_width": bw,
        "candidate_height": bh,
        "candidate_area": area,
        "candidate_diagonal": diag,
        "aspect_ratio_w_over_h": ar_w_h,
        "aspect_ratio_h_over_w": ar_h_w,
        "width_fraction_of_image": w_frac,
        "height_fraction_of_image": h_frac,
        "area_fraction_of_image": area_frac,
        "rectangularity": 1.0,
        "rectangularity_note": "DIAGNOSTIC / REDUNDANT: Candidate representation is axis-aligned rectangle by definition",
        "touches_top": touches_top,
        "touches_bottom": touches_bottom,
        "touches_left": touches_left,
        "touches_right": touches_right,
        "number_of_frame_touching_sides": touching_sides,
        "margin_to_top": margin_top,
        "margin_to_bottom": margin_bottom,
        "margin_to_left": margin_left,
        "margin_to_right": margin_right,
        "margin_to_top_norm": margin_top_norm,
        "margin_to_bottom_norm": margin_bottom_norm,
        "margin_to_left_norm": margin_left_norm,
        "margin_to_right_norm": margin_right_norm,
        "diagonal_to_perimeter": diag_to_perim,
        "diagonal_to_sqrt_area": diag_to_sqrt_area,
    }


# ===========================================================================
# 2. Raw Candidate Generation Strategies
# ===========================================================================
def generate_frame_candidate(h, w):
    """Strategy A: Document fills camera frame (full-view hypothesis)."""
    return {
        "id": "cand_frame_full",
        "strategy": "Frame View",
        "box": (0, 0, w, h),  # (x, y, w, h)
        "description": "Entire camera frame assuming tightly framed document",
        "is_special_case": False,
    }


def generate_appearance_mask_candidates(gray, sat, min_area_fraction=0.10):
    """
    Strategy B: Document candidate derived from paper-vs-background segmentation.
    Uses Otsu binarization and morphological closing to group paper regions.
    """
    h, w = gray.shape
    total_area = h * w
    candidates = []

    _, thresh_gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel_size = max(11, int(round(min(h, w) * 0.015)) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    closed = cv2.morphologyEx(thresh_gray, cv2.MORPH_CLOSE, kernel)

    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for idx, c in enumerate(cnts):
        area = cv2.contourArea(c)
        if area >= total_area * min_area_fraction:
            x, y, cw, ch = cv2.boundingRect(c)
            candidates.append({
                "id": f"cand_app_mask_{idx+1}",
                "strategy": "Appearance Mask",
                "box": (x, y, cw, ch),
                "description": f"Otsu paper appearance contour (area={area/total_area*100:.1f}%)",
                "is_special_case": False,
            })

    return candidates


def generate_content_envelope_candidate(edges, var_map, min_content_fraction=0.10):
    """
    Strategy C: Bounding envelope enclosing active content (edges & text variance).
    """
    h, w = edges.shape
    total_area = h * w

    content_mask = (edges > 0) | (var_map > np.percentile(var_map, 65))
    kernel_size = max(15, int(round(min(h, w) * 0.02)) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    dilated = cv2.dilate(content_mask.astype(np.uint8) * 255, kernel, iterations=2)

    cnts, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return []

    valid_boxes = [cv2.boundingRect(c) for c in cnts if cv2.contourArea(c) > (total_area * 0.03)]
    if not valid_boxes:
        return []

    x_min = min(b[0] for b in valid_boxes)
    y_min = min(b[1] for b in valid_boxes)
    x_max = max(b[0] + b[2] for b in valid_boxes)
    y_max = max(b[1] + b[3] for b in valid_boxes)

    bw = x_max - x_min
    bh = y_max - y_min
    if (bw * bh) >= (total_area * min_content_fraction):
        return [{
            "id": "cand_content_envelope",
            "strategy": "Content Envelope",
            "box": (x_min, y_min, bw, bh),
            "description": "Active content texture and edge bounding envelope",
            "is_special_case": False,
        }]
    return []


def generate_structural_subregion_candidates(gray, h, w):
    """
    Strategy D (ISOLATED SPECIAL-CASE / EXPERIMENTAL INVESTIGATION ONLY):
    Investigates structural split candidates if a significant internal transition
    is detected. Tagged explicitly as special-case logic so it does NOT act as a
    generic page detector on single-page documents.
    """
    row_means = np.mean(gray, axis=1)
    diff = np.diff(row_means)

    max_jump_idx = int(np.argmax(diff))
    max_jump_val = float(diff[max_jump_idx])

    candidates = []
    # Retained purely as an isolated case study diagnostic for images like answer_sheet.jpg
    if max_jump_val > 25.0 and (0.25 * h < max_jump_idx < 0.75 * h):
        split_y = max_jump_idx
        candidates.append({
            "id": "cand_sub_top",
            "strategy": "Structural Sub-region (Experimental)",
            "box": (0, 0, w, split_y),
            "description": f"Experimental upper section (y=0 to y={split_y})",
            "is_special_case": True,
        })
        candidates.append({
            "id": "cand_sub_bottom",
            "strategy": "Structural Sub-region (Experimental)",
            "box": (0, split_y, w, h - split_y),
            "description": f"Experimental lower section (y={split_y} to y={h})",
            "is_special_case": True,
        })

    return candidates


def deduplicate_candidates(candidates, iou_thresh=0.90):
    """Deduplicate near-identical candidate boxes based on IoU."""
    def compute_iou(boxA, boxB):
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
        yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])

        inter = max(0, xB - xA) * max(0, yB - yA)
        areaA = boxA[2] * boxA[3]
        areaB = boxB[2] * boxB[3]
        return inter / float(areaA + areaB - inter + 1e-6)

    unique = []
    for cand in candidates:
        duplicate = False
        for ex in unique:
            if compute_iou(cand["box"], ex["box"]) >= iou_thresh:
                duplicate = True
                break
        if not duplicate:
            unique.append(cand)
    return unique


# ===========================================================================
# 3. STAGE 1 — VALIDITY GATE
# ===========================================================================
def check_candidate_validity(box, img_h, img_w, edges):
    """
    STAGE 1: Candidate Validity Filter.
    Rejects ONLY physically impossible or degenerate candidates:
    - Extreme slivers / degenerate aspect ratios (< 0.15 or > 8.0)
    - Minimum dimension (< 25 pixels)
    - Tiny area specks (< 1.5% of total sensor frame)
    - Completely contentless / empty regions (0 edge pixels)

    Does NOT use frame coverage as positive evidence.
    Does NOT assume A4 or any fixed document dimensions.
    """
    x, y, w, h = box
    total_area = img_h * img_w
    box_area = w * h

    rejections = []

    # 1. Coordinate and dimension checks
    if w < 25 or h < 25:
        rejections.append(f"Dimension too small (w={w}, h={h} < 25px)")

    if x < 0 or y < 0 or (x + w) > img_w or (y + h) > img_h:
        rejections.append("Bounding box extends outside image boundaries")

    # 2. Geometric sliver check (extremely degenerate aspect ratios only)
    ar = float(h) / float(w)
    if ar < 0.15 or ar > 8.0:
        rejections.append(f"Degenerate sliver aspect ratio (AR={ar:.2f})")

    # 3. Area threshold (rejects microscopic noise fragments, not small documents)
    area_fraction = box_area / float(total_area)
    if area_fraction < 0.015:
        rejections.append(f"Microscopic region area ({area_fraction*100:.2f}% < 1.5%)")

    # 4. Content existence (must contain high-frequency edge information)
    roi_edges = edges[max(0, y):min(img_h, y + h), max(0, x):min(img_w, x + w)]
    edge_count = int(np.count_nonzero(roi_edges))
    if edge_count < 10:
        rejections.append(f"Contentless region (edge count={edge_count} < 10)")

    is_valid = len(rejections) == 0
    return is_valid, rejections


# ===========================================================================
# 4. STAGE 2 — CANDIDATE RANKING (FEATURE EVALUATION)
# ===========================================================================
def evaluate_candidate_features(cand, precomputed):
    """
    STAGE 2: Extracts independent diagnostic features for valid candidates.
    Organized strictly by architectural roles:
    - Primary Evidence: Relative Appearance, Active Content/Edge Capture
    - Supporting Evidence: Robust Local Texture, Content Envelope Coherence
    - Weak Prior: Aspect-Ratio Plausibility (Neutral, no A4 assumption)
    - Penalties: External Background Leakage, Conditional Emptiness
    """
    gray = precomputed["gray"]
    sat = precomputed["sat"]
    edges = precomputed["edges"]
    var_map = precomputed["var_map"]
    img_h = precomputed["height"]
    img_w = precomputed["width"]
    total_pixels = img_h * img_w
    total_edges = max(1, int(np.count_nonzero(edges)))

    x, y, w, h = cand["box"]
    box_area = w * h
    coverage = box_area / float(total_pixels)

    # -----------------------------------------------------------------------
    # Region Segmentations: Interior ROI vs Exterior Surround
    # -----------------------------------------------------------------------
    roi_gray = gray[y:y+h, x:x+w]
    roi_sat = sat[y:y+h, x:x+w]
    roi_edges = edges[y:y+h, x:x+w]
    roi_var = var_map[y:y+h, x:x+w]

    mean_b_in = float(np.mean(roi_gray))
    mean_s_in = float(np.mean(roi_sat))
    edges_in = int(np.count_nonzero(roi_edges))
    edge_density_in = edges_in / float(box_area)

    # Exterior complementary region (if candidate does not occupy full frame)
    has_exterior = coverage < 0.98
    if has_exterior:
        # Create boolean mask for exterior pixels
        ext_mask = np.ones((img_h, img_w), dtype=bool)
        ext_mask[y:y+h, x:x+w] = False
        ext_pixels = int(np.count_nonzero(ext_mask))
        if ext_pixels > 0:
            mean_b_ext = float(np.mean(gray[ext_mask]))
            mean_s_ext = float(np.mean(sat[ext_mask]))
            edges_ext = int(np.count_nonzero(edges[ext_mask]))
            edge_density_ext = edges_ext / float(ext_pixels)
        else:
            mean_b_ext, mean_s_ext, edge_density_ext = mean_b_in, mean_s_in, 0.0
    else:
        # Full frame: no exterior exists
        mean_b_ext = mean_b_in
        mean_s_ext = mean_s_in
        edge_density_ext = 0.0

    # -----------------------------------------------------------------------
    # [PRIMARY EVIDENCE 1]: Relative Paper Appearance
    # Measures whether interior is brighter and less saturated than exterior.
    # -----------------------------------------------------------------------
    delta_brightness = mean_b_in - mean_b_ext
    delta_saturation = mean_s_ext - mean_s_in  # positive if interior is less saturated

    if has_exterior:
        # Normalized relative contrast indicators
        app_bright_rel = np.clip(delta_brightness / 40.0, -1.0, 1.0)
        app_sat_rel = np.clip(delta_saturation / 25.0, -1.0, 1.0)
        # Combined relative paper-contrast score mapped to [0, 1]
        score_app_primary = float(np.clip(0.5 + 0.3 * app_bright_rel + 0.2 * app_sat_rel, 0.0, 1.0))
    else:
        # Neutral relative appearance for full-frame candidates (neither rewarded nor penalized)
        score_app_primary = 0.50

    # -----------------------------------------------------------------------
    # [PRIMARY EVIDENCE 2]: Active Content / Edge Capture
    # Measures what fraction of document edges are enclosed and interior density.
    # -----------------------------------------------------------------------
    content_capture_ratio = edges_in / float(total_edges)  # fraction of scene edges captured
    if has_exterior and edge_density_ext > 1e-4:
        edge_contrast_ratio = edge_density_in / edge_density_ext
    else:
        edge_contrast_ratio = 1.0

    # Score rewards capturing content while maintaining structured text edge density (~3% - 10%)
    score_edge_primary = float(np.clip(content_capture_ratio * 0.7 + np.clip(edge_density_in / 0.06, 0.0, 1.0) * 0.3, 0.0, 1.0))

    # -----------------------------------------------------------------------
    # [SUPPORTING EVIDENCE 3]: Robust Local Texture Contrast
    # Uses 90th percentile of local variance rather than page-wide mean variance.
    # Measures actual contrast of ink strokes without dilution by blank margins.
    # -----------------------------------------------------------------------
    var_p90 = float(np.percentile(roi_var, 90)) if roi_var.size > 0 else 0.0
    var_mean = float(np.mean(roi_var)) if roi_var.size > 0 else 0.0
    # Provisional soft scaling for p90 variance (typical ink strokes show p90 in [400, 2500])
    score_tex_supporting = float(np.clip(var_p90 / 1500.0, 0.0, 1.0))

    # -----------------------------------------------------------------------
    # [SUPPORTING EVIDENCE 4]: Content Envelope Fit / Coherence
    # Evaluates whether the candidate bounding box tightly wraps active content.
    # -----------------------------------------------------------------------
    row_edges = np.sum(roi_edges > 0, axis=1)
    col_edges = np.sum(roi_edges > 0, axis=0)
    active_rows = np.count_nonzero(row_edges > 2)
    active_cols = np.count_nonzero(col_edges > 2)
    row_content_ratio = active_rows / float(max(1, h))
    col_content_ratio = active_cols / float(max(1, w))
    score_coherence_supporting = float(np.clip(0.5 * row_content_ratio + 0.5 * col_content_ratio, 0.0, 1.0))

    # -----------------------------------------------------------------------
    # [WEAK PRIOR 5]: Aspect Ratio Plausibility (Neutral, No A4 Assumption)
    # Broadly favors reasonable portrait document proportions [1.1 - 2.0].
    # Never uses frame coverage as a positive score!
    # -----------------------------------------------------------------------
    ar = float(h) / float(w)
    if 1.15 <= ar <= 1.85:
        prior_ar = 1.0
    elif 0.8 <= ar < 1.15 or 1.85 < ar <= 2.2:
        prior_ar = 0.75
    elif 0.5 <= ar < 0.8 or 2.2 < ar <= 3.0:
        prior_ar = 0.45
    else:
        prior_ar = 0.20

    # -----------------------------------------------------------------------
    # [PENALTIES]: Explicit Background Leakage & Conditional Emptiness
    # -----------------------------------------------------------------------
    # Penalty 1: Background leakage (interior incorporates high saturation desk wood)
    penalty_bg_leak = 0.0
    if mean_s_in > 30.0:
        penalty_bg_leak = float(np.clip((mean_s_in - 30.0) / 30.0 * 0.20, 0.0, 0.20))

    # Penalty 2: Lopsided emptiness (only applied if sufficient total edges exist)
    penalty_lopsided = 0.0
    if edges_in > 100:
        hw, hh = w // 2, h // 2
        q1 = np.count_nonzero(roi_edges[0:hh, 0:hw])
        q2 = np.count_nonzero(roi_edges[0:hh, hw:w])
        q3 = np.count_nonzero(roi_edges[hh:h, 0:hw])
        q4 = np.count_nonzero(roi_edges[hh:h, hw:w])
        quad_counts = [q1, q2, q3, q4]
        min_q = min(quad_counts)
        max_q = max(quad_counts)
        if max_q > 0 and (min_q / float(max_q)) < 0.05:
            penalty_lopsided = 0.10

    # -----------------------------------------------------------------------
    # Provisional Diagnostic Ranking Score
    # Combines Primary, Supporting, and Prior terms minus Penalties.
    # Clearly exposed and documented as provisional scaffolding.
    # -----------------------------------------------------------------------
    prov_primary = 0.50 * score_app_primary + 0.50 * score_edge_primary
    prov_supporting = 0.50 * score_tex_supporting + 0.50 * score_coherence_supporting
    prov_score = (
        0.65 * prov_primary +
        0.25 * prov_supporting +
        0.10 * prior_ar -
        penalty_bg_leak -
        penalty_lopsided
    )
    prov_score = float(np.clip(prov_score, 0.0, 1.0))

    return {
        # Raw Metrics
        "aspect_ratio": ar,
        "frame_coverage_pct": coverage * 100.0,
        "mean_b_in": mean_b_in,
        "mean_s_in": mean_s_in,
        "mean_b_ext": mean_b_ext,
        "mean_s_ext": mean_s_ext,
        "delta_brightness": delta_brightness,
        "delta_saturation": delta_saturation,
        "edge_density_pct": edge_density_in * 100.0,
        "content_capture_pct": content_capture_ratio * 100.0,
        "var_p90": var_p90,
        "var_mean": var_mean,
        # Architectural Feature Values
        "feat_app_primary": score_app_primary,
        "feat_edge_primary": score_edge_primary,
        "feat_tex_supporting": score_tex_supporting,
        "feat_coherence_supporting": score_coherence_supporting,
        "prior_aspect_ratio": prior_ar,
        "penalty_bg_leak": penalty_bg_leak,
        "penalty_lopsided": penalty_lopsided,
        # Provisional Composite
        "score_provisional": prov_score,
    }


# ===========================================================================
# 5. Pipeline Execution for an Image
# ===========================================================================
def process_image_candidates(image_path):
    """
    Executes raw generation, Stage-1 validity filtering, and Stage-2 feature
    evaluation for a single image.
    """
    pre = load_and_preprocess(image_path)
    h, w = pre["height"], pre["width"]
    edges = pre["edges"]

    # 1. Candidate Generation
    raw_candidates = []
    raw_candidates.append(generate_frame_candidate(h, w))
    raw_candidates.extend(generate_appearance_mask_candidates(pre["gray"], pre["sat"]))
    raw_candidates.extend(generate_content_envelope_candidate(pre["edges"], pre["var_map"]))
    # Structural sub-regions are explicitly marked as experimental case-study candidates
    raw_candidates.extend(generate_structural_subregion_candidates(pre["gray"], h, w))

    # Deduplication
    unique_candidates = deduplicate_candidates(raw_candidates, iou_thresh=0.90)

    # 2. Stage 1: Validity Filtering
    valid_candidates = []
    invalid_candidates = []
    for cand in unique_candidates:
        is_valid, rejections = check_candidate_validity(cand["box"], h, w, edges)
        cand_record = {**cand, "is_valid": is_valid, "rejections": rejections}
        if is_valid:
            valid_candidates.append(cand_record)
        else:
            invalid_candidates.append(cand_record)

    # 3. Stage 2: Feature Evaluation & Provisional Ranking
    evaluated_candidates = []
    for cand in valid_candidates:
        feats = evaluate_candidate_features(cand, pre)
        # Feature #1: Raw boundary collar measurement (NOT in scoring yet)
        boundary_data = measure_boundary_collars(
            cand, pre["gray"], pre["sat"], h, w,
            collar_width=PROV_COLLAR_WIDTH,
        )
        # Feature #2: Raw active document edge measurement (NOT in scoring yet)
        edge_data = measure_active_document_edges(cand, pre["edges"], h, w)
        # Feature #3: Raw texture / microcontrast measurement (NOT in scoring yet)
        texture_data = measure_texture_microcontrast(
            cand, pre["var_map"], pre["ksize"], h, w
        )
        # Feature #4: Raw boundary compactness / content containment (NOT in scoring yet)
        compactness_data = measure_boundary_compactness(cand, pre["edges"], h, w)
        # Feature #5: Raw geometry / shape prior (NOT in scoring yet)
        geometry_data = measure_geometry_shape_prior(cand, h, w)
        evaluated_candidates.append({
            **cand,
            "features": feats,
            "boundary": boundary_data,
            "edge_meas": edge_data,
            "texture": texture_data,
            "compactness": compactness_data,
            "geometry": geometry_data,
        })

    # Sort descending by provisional score
    evaluated_candidates.sort(key=lambda c: c["features"]["score_provisional"], reverse=True)
    for rank, c in enumerate(evaluated_candidates, 1):
        c["rank"] = rank

    return {
        "image_path": image_path,
        "precomputed": pre,
        "raw_count": len(raw_candidates),
        "unique_count": len(unique_candidates),
        "valid_count": len(valid_candidates),
        "invalid_count": len(invalid_candidates),
        "invalid_candidates": invalid_candidates,
        "evaluated_candidates": evaluated_candidates,
    }


# ===========================================================================
# 6. Diagnostic Visualizations
# ===========================================================================
def plot_candidate_overlays(bgr_img, evaluated_cands, out_path):
    """
    Diagnostic overlay for primary visualization case study.
    Displays ranked candidate bounding boxes on the original image.
    """
    rgb_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
    h, w, _ = rgb_img.shape

    fig, ax = plt.subplots(figsize=(10, 13))
    ax.imshow(rgb_img)

    palette = ["#00FF00", "#FFD700", "#00FFFF", "#FF3366", "#FF9900", "#3399FF"]

    for cand in evaluated_cands:
        rank = cand["rank"]
        x, y, bw, bh = cand["box"]
        color = palette[(rank - 1) % len(palette)]
        score = cand["features"]["score_provisional"]
        strat = cand["strategy"]

        rect = patches.Rectangle((x, y), bw, bh, linewidth=2.8, edgecolor=color,
                                 facecolor="none", linestyle="-")
        ax.add_patch(rect)

        label_text = f"#{rank} {strat} (Prov={score:.3f})\n[{x},{y},{bw}x{bh}]"
        text_y = y + 25 if y + 25 < h - 10 else y - 10
        ax.text(x + 10, text_y, label_text, color="black", fontsize=9, fontweight="bold",
                bbox=dict(facecolor=color, alpha=0.85, edgecolor="black", boxstyle="round,pad=0.3"))

    ax.set_title("Stage-2 Provisional Candidate Ranking Overlays", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    plt.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def plot_evidence_breakdown(evaluated_cands, out_path):
    """
    Diagnostic bar chart displaying individual architectural features.
    """
    categories = ["Rel App (Pri)", "Edge Capt (Pri)", "Tex P90 (Supp)", "Coherence (Supp)", "AR Prior (Weak)"]
    n_cands = len(evaluated_cands)
    fig, ax = plt.subplots(figsize=(12, 6.5))

    x = np.arange(len(categories))
    width = 0.8 / max(1, n_cands)

    palette = ["#2ca02c", "#ff7f0e", "#1f77b4", "#d62728", "#9467bd"]

    for idx, c in enumerate(evaluated_cands):
        feats = c["features"]
        scores = [
            feats["feat_app_primary"],
            feats["feat_edge_primary"],
            feats["feat_tex_supporting"],
            feats["feat_coherence_supporting"],
            feats["prior_aspect_ratio"],
        ]
        offset = (idx - (n_cands - 1) / 2) * width
        ax.bar(x + offset, scores, width,
               label=f"#{c['rank']} {c['id']} (Prov={feats['score_provisional']:.3f})",
               color=palette[idx % len(palette)], alpha=0.85, edgecolor="black", linewidth=0.7)

    ax.set_ylabel("Diagnostic Feature Value (0.0 to 1.0)", fontsize=11)
    ax.set_title("Architectural Evidence Feature Breakdown Across Candidates", fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=10, fontweight="bold")
    ax.set_ylim(0.0, 1.15)
    ax.grid(True, axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper right", fontsize=9, framealpha=0.9)

    plt.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


# ===========================================================================
# 7. Main Execution & Multi-Image Evaluation
# ===========================================================================
def main():
    print("=" * 78)
    print("AI-EVAL Phase 2: Page-Region Candidate Detection (Refactored Architecture)")
    print("Script: phase2/07_page_region_candidate_detection.py")
    print("=" * 78)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for fname in CALIBRATION_IMAGES:
        fpath = os.path.join(IMAGES_DIR, fname)
        print(f"\n" + "-" * 78)
        print(f"PROCESSING IMAGE: {fname}")
        print("-" * 78)

        res = process_image_candidates(fpath)
        print(f"  Image Size: {res['precomputed']['width']} x {res['precomputed']['height']} px")
        print(f"  Raw Candidates Generated: {res['raw_count']} (Unique after IoU deduplication: {res['unique_count']})")
        print(f"  Stage-1 Validity Decisions: {res['valid_count']} VALID, {res['invalid_count']} REJECTED")

        if res["invalid_candidates"]:
            for inv in res["invalid_candidates"]:
                print(f"    - [REJECTED] {inv['id']} box={inv['box']}: {', '.join(inv['rejections'])}")

        print("\n  STAGE-2 EVALUATED CANDIDATES (Ranked by Provisional Score):")
        print(f"  {'Rank':<5} | {'Candidate ID':<22} | {'Box (x,y,w,h)':<18} | {'ProvScore':<9} | {'RelApp':<7} | {'EdgeCap':<7} | {'TexP90':<7} | {'Coher':<7} | {'ARPrior'}")
        print("  " + "-" * 95)

        for c in res["evaluated_candidates"]:
            f = c["features"]
            box_str = f"({c['box'][0]},{c['box'][1]},{c['box'][2]},{c['box'][3]})"
            print(f"  #{c['rank']:<4} | {c['id']:<22} | {box_str:<18} | {f['score_provisional']:<9.4f} | "
                  f"{f['feat_app_primary']:<7.3f} | {f['feat_edge_primary']:<7.3f} | {f['feat_tex_supporting']:<7.3f} | "
                  f"{f['feat_coherence_supporting']:<7.3f} | {f['prior_aspect_ratio']:<7.3f}")

        # Detailed breakdown of individual raw metrics
        print("\n  DETAILED FEATURE BREAKDOWN:")
        for c in res["evaluated_candidates"]:
            f = c["features"]
            special_tag = " [SPECIAL CASE / EXPERIMENTAL]" if c.get("is_special_case", False) else ""
            print(f"    Candidate #{c['rank']}: {c['id']} ({c['strategy']}){special_tag}")
            print(f"      Box: {c['box']} | Coverage: {f['frame_coverage_pct']:.1f}% | AR: {f['aspect_ratio']:.2f}")
            print(f"      Appearance: Brightness (In={f['mean_b_in']:.1f}, Ext={f['mean_b_ext']:.1f}, Delta={f['delta_brightness']:+.1f}) | "
                  f"Saturation (In={f['mean_s_in']:.1f}, Ext={f['mean_s_ext']:.1f}, Delta={f['delta_saturation']:+.1f})")
            print(f"      Content: Edge Density={f['edge_density_pct']:.2f}%, Content Captured={f['content_capture_pct']:.1f}%")
            print(f"      Texture: Local Var P90={f['var_p90']:.1f} (Mean={f['var_mean']:.1f})")
            print(f"      Penalties: BG Leak={f['penalty_bg_leak']:.3f}, Lopsided={f['penalty_lopsided']:.3f}")
            print(f"      Provisional Score: {f['score_provisional']:.4f}")

        # ---------------------------------------------------------------
        # LOCAL BOUNDARY APPEARANCE — RAW EDGE MEASUREMENT LAYER
        # Feature #1 diagnostic output (NOT integrated into scoring yet)
        # ---------------------------------------------------------------
        print(f"\n  LOCAL BOUNDARY APPEARANCE (Feature #1 — collar width={PROV_COLLAR_WIDTH}px, raw measurements only):")
        for c in res["evaluated_candidates"]:
            bd = c["boundary"]
            special_tag = " [EXPERIMENTAL]" if c.get("is_special_case", False) else ""
            print(f"\n    Candidate #{c['rank']}: {c['id']}{special_tag}")
            print(f"      Box: {c['box']}")
            print(f"      Edge Summary: Observed={bd['observed_edge_count']}/4  "
                  f"Unobserved={bd['unobserved_edge_count']}/4  "
                  f"PotentiallyContaminated={bd['contaminated_edge_count']}/4")

            for edge_name in ["TOP", "BOTTOM", "LEFT", "RIGHT"]:
                er = bd["edge_records"][edge_name]
                state_str = er["state"]
                if er["contamination_reason"]:
                    state_str += f" ({er['contamination_reason']})"

                if er["state"] == "UNOBSERVED":
                    print(f"      {edge_name:6s}: {state_str}  "
                          f"inner_valid_px={er['inner_valid_px']}  outer_valid_px={er['outer_valid_px']}")
                else:
                    db_str = f"{er['delta_brightness']:+.1f}" if er["delta_brightness"] is not None else "N/A"
                    ds_str = f"{er['delta_saturation']:+.1f}" if er["delta_saturation"] is not None else "N/A"
                    ib = f"{er['inner_brightness']:.1f}" if er["inner_brightness"] is not None else "N/A"
                    ob = f"{er['outer_brightness']:.1f}" if er["outer_brightness"] is not None else "N/A"
                    is_ = f"{er['inner_saturation']:.1f}" if er["inner_saturation"] is not None else "N/A"
                    os_ = f"{er['outer_saturation']:.1f}" if er["outer_saturation"] is not None else "N/A"
                    ib_std = f"{er['inner_brightness_std']:.1f}" if er["inner_brightness_std"] is not None else "N/A"
                    ob_std = f"{er['outer_brightness_std']:.1f}" if er["outer_brightness_std"] is not None else "N/A"
                    is_std = f"{er['inner_saturation_std']:.1f}" if er["inner_saturation_std"] is not None else "N/A"
                    os_std = f"{er['outer_saturation_std']:.1f}" if er["outer_saturation_std"] is not None else "N/A"
                    print(f"      {edge_name:6s}: {state_str}")
                    print(f"             Brightness: inner={ib} (std={ib_std})  outer={ob} (std={ob_std})  dB={db_str}")
                    print(f"             Saturation: inner={is_} (std={is_std})  outer={os_} (std={os_std})  dS={ds_str}")
                    print(f"             Gradient@seam={er['boundary_gradient_mag']:.2f}  "
                          f"inner_px={er['inner_valid_px']}  outer_px={er['outer_valid_px']}")

        # ---------------------------------------------------------------
        # ACTIVE DOCUMENT EDGES — RAW MEASUREMENT LAYER
        # Feature #2 diagnostic output (NOT integrated into scoring yet)
        # ---------------------------------------------------------------
        print(f"\n  ACTIVE DOCUMENT EDGES (Feature #2 — interior-only, raw measurements):")
        for c in res["evaluated_candidates"]:
            em = c["edge_meas"]
            rd = em["row_dist"]
            cd = em["col_dist"]
            special_tag = " [EXPERIMENTAL]" if c.get("is_special_case", False) else ""
            print(f"\n    Candidate #{c['rank']}: {c['id']}{special_tag}")
            print(f"      Box: {c['box']}  ROI area: {em['roi_area']} px")
            print(f"      Edge pixels: {em['edge_pixel_count']}")
            print(f"      Edge density: {em['edge_density']:.5f}  "
                  f"({em['edge_density']*100:.3f}%)")
            print(f"      Active row fraction:  {em['active_row_fraction']:.4f}  "
                  f"({em['active_row_count']} / {em['row_edge_profile'].size} rows)")
            print(f"      Active col fraction:  {em['active_col_fraction']:.4f}  "
                  f"({em['active_col_count']} / {em['col_edge_profile'].size} cols)")
            print(f"      Row distribution (active rows only):")
            print(f"        mean={rd['mean']:.2f}  std={rd['std']:.2f}  "
                  f"min={rd['min']:.0f}  max={rd['max']:.0f}")
            print(f"        P25={rd['p25']:.1f}  P75={rd['p75']:.1f}  IQR={rd['iqr']:.1f}")
            print(f"        COV={rd['cov']:.4f}  Gini={rd['gini']:.4f}")
            print(f"      Col distribution (active cols only):")
            print(f"        mean={cd['mean']:.2f}  std={cd['std']:.2f}  "
                  f"min={cd['min']:.0f}  max={cd['max']:.0f}")
            print(f"        P25={cd['p25']:.1f}  P75={cd['p75']:.1f}  IQR={cd['iqr']:.1f}")
            print(f"        COV={cd['cov']:.4f}  Gini={cd['gini']:.4f}")

        # ---------------------------------------------------------------
        # TEXTURE / MICROCONTRAST — RAW MEASUREMENT LAYER
        # Feature #3 diagnostic output (NOT integrated into scoring yet)
        # NOTE: High values do NOT imply document content.
        #       Wood/desk surfaces also produce high local variance.
        # ---------------------------------------------------------------
        print(f"\n  TEXTURE / MICROCONTRAST (Feature #3 — window={res['evaluated_candidates'][0]['texture']['var_ksize']}px, raw measurements only):")
        for c in res["evaluated_candidates"]:
            tx = c["texture"]
            special_tag = " [EXPERIMENTAL]" if c.get("is_special_case", False) else ""
            print(f"\n    Candidate #{c['rank']}: {c['id']}{special_tag}")
            print(f"      Box: {c['box']}  ROI pixels: {tx['roi_pixel_count']}")
            print(f"      Window (kernel) size: {tx['var_ksize']} x {tx['var_ksize']} px")
            print(f"      Local variance — global stats:")
            print(f"        mean={tx['mean_var']:.2f}  std={tx['std_var']:.2f}  "
                  f"min={tx['min_var']:.2f}  max={tx['max_var']:.2f}")
            print(f"        P50={tx['p50_var']:.2f}  P75={tx['p75_var']:.2f}  "
                  f"P90={tx['p90_var']:.2f}  P95={tx['p95_var']:.2f}")
            print(f"      High-variance spatial coverage (internal thresholds):")
            print(f"        fraction > P50: {tx['hv_frac_above_p50']:.4f}  "
                  f"fraction > P75: {tx['hv_frac_above_p75']:.4f}  "
                  f"fraction > P90: {tx['hv_frac_above_p90']:.4f}")
            print(f"      Row texture profile:")
            print(f"        mean={tx['row_tex_mean']:.2f}  std={tx['row_tex_std']:.2f}  "
                  f"min={tx['row_tex_min']:.2f}  max={tx['row_tex_max']:.2f}")
            print(f"        COV={tx['row_tex_cov']:.4f}  Gini={tx['row_tex_gini']:.4f}")
            print(f"      Col texture profile:")
            print(f"        mean={tx['col_tex_mean']:.2f}  std={tx['col_tex_std']:.2f}  "
                  f"min={tx['col_tex_min']:.2f}  max={tx['col_tex_max']:.2f}")
            print(f"        COV={tx['col_tex_cov']:.4f}  Gini={tx['col_tex_gini']:.4f}")

        # ---------------------------------------------------------------
        # BOUNDARY COMPACTNESS / CONTENT CONTAINMENT -- RAW MEASUREMENT
        # Feature #4 diagnostic output (NOT integrated into scoring yet)
        # NOTE: Large margins do NOT classify a candidate as bad.
        #       Blank paper margins are physically valid.
        # ---------------------------------------------------------------
        print(f"\n  BOUNDARY COMPACTNESS / CONTENT CONTAINMENT (Feature #4 -- raw measurements):")
        for c in res["evaluated_candidates"]:
            cp = c["compactness"]
            special_tag = " [EXPERIMENTAL]" if c.get("is_special_case", False) else ""
            print(f"\n    Candidate: {c['id']}{special_tag}")

            ba = cp["boundary_activity"]
            print(f"\n    Boundary activity:")
            for b_name in ["TOP", "BOTTOM", "LEFT", "RIGHT"]:
                b_info = ba[b_name]
                print(f"      {b_name:<6}: band_width={b_info['band_width']} px, "
                      f"edge_pixels={b_info['edge_pixels']}, "
                      f"edge_density={b_info['edge_density']:.4f}, "
                      f"active_fraction={b_info['active_fraction']:.4f}")

            db = cp["dead_borders"]
            print(f"\n    Dead borders:")
            for b_name, key in [("TOP", "top_dead_border_px"),
                                ("BOTTOM", "bottom_dead_border_px"),
                                ("LEFT", "left_dead_border_px"),
                                ("RIGHT", "right_dead_border_px")]:
                val_str = f"{db[key]} px" if db[key] is not None else "None (no edges)"
                print(f"      {b_name:<6}: {val_str}")

            occ = cp["occupancy_structure"]
            print(f"\n    Occupancy structure:")
            print(f"      active row fraction   : {occ['active_row_fraction']:.4f}")
            print(f"      active column fraction: {occ['active_col_fraction']:.4f}")
            print(f"      active row bands      : {occ['num_active_row_bands']}")
            print(f"      active column bands   : {occ['num_active_col_bands']}")
            print(f"      longest row run       : {occ['longest_active_row_run']} px")
            print(f"      longest column run    : {occ['longest_active_col_run']} px")
            print(f"      active row span       : {occ['active_row_span']} px")
            print(f"      active column span    : {occ['active_col_span']} px")

            print(f"\n    Existing raw measurements:")
            print(f"      fill ratio            : {cp['fill_ratio']:.4f} ({cp['fill_ratio']*100:.1f}%) [raw diagnostic, candidate-gen dependent]")
            if cp["has_content"]:
                print(f"      content bbox          : x={cp['cb_x']}, y={cp['cb_y']}, w={cp['cb_w']}, h={cp['cb_h']} (area={cp['cb_area']} px)")
                print(f"      centroid              : x={cp['centroid_x_norm']:.4f}, y={cp['centroid_y_norm']:.4f} [diagnostic/redundant -- bbox-centered]")
                print(f"      content bbox AR       : {cp['cb_ar']:.3f} [diagnostic/redundant -- geometry-derived]")
            else:
                print(f"      content bbox          : None (no edge activity)")
                print(f"      centroid              : None [diagnostic/redundant]")
                print(f"      content bbox AR       : None [diagnostic/redundant]")

        # ---------------------------------------------------------------
        # GEOMETRY / SHAPE PRIOR -- RAW MEASUREMENT
        # Feature #5 diagnostic output (NOT integrated into scoring yet)
        # ---------------------------------------------------------------
        print(f"\n  GEOMETRY / SHAPE PRIOR (Feature #5 -- raw measurements):")
        for c in res["evaluated_candidates"]:
            gm = c["geometry"]
            special_tag = " [EXPERIMENTAL]" if c.get("is_special_case", False) else ""
            print(f"\n    Candidate: {c['id']}{special_tag}")

            print(f"\n    Basic geometry:")
            print(f"      x            : {gm['candidate_x']}")
            print(f"      y            : {gm['candidate_y']}")
            print(f"      width        : {gm['candidate_width']}")
            print(f"      height       : {gm['candidate_height']}")
            print(f"      area         : {gm['candidate_area']} px")
            print(f"      aspect ratio : {gm['aspect_ratio_w_over_h']:.4f} (width/height) | {gm['aspect_ratio_h_over_w']:.4f} (height/width)")
            print(f"      diagonal     : {gm['candidate_diagonal']:.2f} px")

            print(f"\n    Normalized geometry:")
            print(f"      width fraction : {gm['width_fraction_of_image']:.4f}")
            print(f"      height fraction: {gm['height_fraction_of_image']:.4f}")
            print(f"      area fraction  : {gm['area_fraction_of_image']:.4f} [DIAGNOSTIC / REDUNDANT: width fraction * height fraction]")

            print(f"\n    Frame contact:")
            print(f"      top           : {gm['touches_top']}")
            print(f"      bottom        : {gm['touches_bottom']}")
            print(f"      left          : {gm['touches_left']}")
            print(f"      right         : {gm['touches_right']}")
            print(f"      touching sides: {gm['number_of_frame_touching_sides']} / 4")

            print(f"\n    Frame margins:")
            print(f"      top   : {gm['margin_to_top']} px (norm: {gm['margin_to_top_norm']:.4f})")
            print(f"      bottom: {gm['margin_to_bottom']} px (norm: {gm['margin_to_bottom_norm']:.4f})")
            print(f"      left  : {gm['margin_to_left']} px (norm: {gm['margin_to_left_norm']:.4f})")
            print(f"      right : {gm['margin_to_right']} px (norm: {gm['margin_to_right_norm']:.4f})")

            print(f"\n    Any additional non-redundant geometry descriptors:")
            print(f"      rectangularity        : {gm['rectangularity']:.4f} [{gm['rectangularity_note']}]")
            print(f"      diagonal-to-perimeter : {gm['diagonal_to_perimeter']:.4f} (dimensionless shape factor)")
            print(f"      diagonal-to-sqrt-area : {gm['diagonal_to_sqrt_area']:.4f} (aspect elongation factor)")

        # Generate diagnostic plots for the primary reference case study
        if fname == "answer_sheet.jpg":
            out19 = os.path.join(OUTPUT_DIR, "19_candidate_regions_overlay.png")
            plot_candidate_overlays(res["precomputed"]["bgr"], res["evaluated_candidates"], out19)
            print(f"\n  [Diagnostic Plot Saved] {out19}")

            out20 = os.path.join(OUTPUT_DIR, "20_candidate_evaluation_breakdown.png")
            plot_evidence_breakdown(res["evaluated_candidates"], out20)
            print(f"  [Diagnostic Plot Saved] {out20}")

    print("\n" + "=" * 78)
    print("ARCHITECTURAL REFACTOR EVALUATION COMPLETE across 5 images.")
    print("Important: Scores remain provisional scaffolding; thresholds are uncalibrated.")
    print("=" * 78)


if __name__ == "__main__":
    main()
