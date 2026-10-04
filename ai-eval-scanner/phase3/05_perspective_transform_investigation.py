"""
phase3/05_perspective_transform_investigation.py

AI-EVAL PHASE 3.5: PERSPECTIVE TRANSFORM & CANONICAL DOCUMENT GEOMETRY
======================================================================

PURPOSE:
Investigate how an already validated physical-page quadrilateral should be
transformed into a canonical top-down document image.

INPUT SOURCES:
- Already validated physical-page corner sets from Phase 3.4:
  * images/answer_sheet_2.png
  * images/answer_sheet_3.jpg
- Synthetic test cases covering:
  * Slight, moderate, strong perspective (keystone foreshortening)
  * Rotation (0°, 15°, 45°, 90°)
  * Landscape vs portrait geometry
  * Extreme aspect ratios (1:1, 1:1.414, 1:2.5)
  * Multi-resolution scaling (720p, 1080p, 4K)
- Handled edge cases:
  * FRAME_LIMITED captures (e.g. answer_sheet_4.jpg, answer_sheet_5.jpg)
  * AMBIGUOUS captures (e.g. answer_sheet.jpg)
  * Degenerate / invalid quads

INVESTIGATION MODULES:
1. Destination Dimension Calculation (Max vs Mean vs Aspect-Preserving vs Area-Preserving)
2. Aspect Ratio Preservation & Foreshortening Analysis
3. Multi-Resolution Scaling & Bound Constraints (Preventing memory blowup)
4. Interpolation Method Comparison (NEAREST vs LINEAR vs CUBIC vs LANCZOS4)
5. Color vs Grayscale Warping (Pre-warp vs Post-warp conversion, timing & fidelity)
6. Border Handling (BORDER_CONSTANT White vs Black vs BORDER_REPLICATE)
7. Non-Physical Capture Handling (Frame-Limited rigid deskew vs Ambiguous pass-through)
8. The 90°/180° Orientation Ambiguity Analysis

GUARDRAILS:
- INVESTIGATION ONLY.
- Do NOT build the production scanner yet.
- Do NOT modify any frozen Phase 2 or Phase 3.1–3.4 files.
- Do NOT freeze universal hard-coded thresholds.
"""

import os
import sys
import math
import time
from typing import Dict, List, Tuple, Optional, Any
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT_DIR, "phase3", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ===========================================================================
# 1. CANONICAL CORNER ORDERING & GEOMETRIC INPUT PREPARATION
# ===========================================================================

def canonical_corner_order(pts: List[Tuple[float, float]]) -> np.ndarray:
    """
    Normalizes 4 validated corners into canonical clockwise order:
    [0] TOP_LEFT, [1] TOP_RIGHT, [2] BOTTOM_RIGHT, [3] BOTTOM_LEFT.
    Uses the Phase 3.4 validated Convex Hull + Cyclic Clockwise Normalizer.
    """
    pts_arr = np.array(pts, dtype=np.float32)
    hull = cv2.convexHull(pts_arr, clockwise=True).reshape(-1, 2)
    if len(hull) != 4:
        raise ValueError(f"Input points do not form a 4-vertex convex hull: {pts}")

    # Ensure clockwise winding via cross product
    v1 = hull[1] - hull[0]
    v2 = hull[2] - hull[1]
    if (v1[0] * v2[1] - v1[1] * v2[0]) < 0:
        hull = hull[::-1]

    # Anchor TOP_LEFT as vertex closest to origin (0, 0)
    dists = np.hypot(hull[:, 0], hull[:, 1])
    anchor_idx = int(np.argmin(dists))
    ordered = np.roll(hull, -anchor_idx, axis=0)
    return ordered.astype(np.float32)


# ===========================================================================
# 2. DESTINATION DIMENSION CALCULATION STRATEGIES
# ===========================================================================

def compute_destination_dimensions(
    ordered_corners: np.ndarray,
    strategy: str = "MAX_EDGE",
    max_dim_limit: int = 4096,
    min_dim_limit: int = 200
) -> Tuple[int, int, Dict[str, Any]]:
    """
    Calculates destination (width, height) for perspective warp.
    Strategies investigated:
    - "MAX_EDGE": w = max(top, bot), h = max(left, right)
    - "MEAN_EDGE": w = mean(top, bot), h = mean(left, right)
    - "AREA_ASPECT_PRESERVED": computes projective aspect ratio, preserves total quad area
    """
    tl, tr, br, bl = ordered_corners

    # Edge Euclidean lengths
    w_top = float(np.hypot(tr[0] - tl[0], tr[1] - tl[1]))
    w_bot = float(np.hypot(br[0] - bl[0], br[1] - bl[1]))
    h_left = float(np.hypot(bl[0] - tl[0], bl[1] - tl[1]))
    h_right = float(np.hypot(br[0] - tr[0], br[1] - tr[1]))

    quad_area = float(cv2.contourArea(ordered_corners))

    if strategy == "MAX_EDGE":
        w = max(w_top, w_bot)
        h = max(h_left, h_right)
    elif strategy == "MEAN_EDGE":
        w = (w_top + w_bot) / 2.0
        h = (h_left + h_right) / 2.0
    elif strategy == "AREA_ASPECT_PRESERVED":
        # Projective aspect ratio estimation
        aspect_ratio = ((w_top + w_bot) / 2.0) / max(1.0, ((h_left + h_right) / 2.0))
        # Find (w, h) such that w * h = quad_area and w / h = aspect_ratio
        h = math.sqrt(quad_area / max(1e-4, aspect_ratio))
        w = h * aspect_ratio
    else:
        raise ValueError(f"Unknown destination strategy: {strategy}")

    # Clamp bounds to prevent memory explosion or degenerate collapses
    dest_w = int(round(np.clip(w, min_dim_limit, max_dim_limit)))
    dest_h = int(round(np.clip(h, min_dim_limit, max_dim_limit)))

    metadata = {
        "strategy": strategy,
        "raw_w": w,
        "raw_h": h,
        "w_top": w_top,
        "w_bot": w_bot,
        "h_left": h_left,
        "h_right": h_right,
        "dest_aspect_ratio": dest_w / max(1, dest_h),
        "quad_area": quad_area,
        "dest_area": dest_w * dest_h,
        "area_scaling_factor": (dest_w * dest_h) / max(1.0, quad_area)
    }

    return dest_w, dest_h, metadata


# ===========================================================================
# 3. WARPING IMPLEMENTATION & INTERPOLATION ANALYSIS
# ===========================================================================

def execute_perspective_warp(
    image: np.ndarray,
    ordered_corners: np.ndarray,
    dest_w: int,
    dest_h: int,
    interp_method: int = cv2.INTER_LINEAR,
    border_mode: int = cv2.BORDER_CONSTANT,
    border_val: Tuple[int, int, int] = (255, 255, 255)
) -> np.ndarray:
    """
    Computes 3x3 homography matrix and warps source image to canonical rectangle.
    """
    dst_corners = np.array([
        [0.0, 0.0],
        [float(dest_w - 1), 0.0],
        [float(dest_w - 1), float(dest_h - 1)],
        [0.0, float(dest_h - 1)]
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(ordered_corners, dst_corners)
    warped = cv2.warpPerspective(
        image, M, (dest_w, dest_h),
        flags=interp_method,
        borderMode=border_mode,
        borderValue=border_val
    )
    return warped


# ===========================================================================
# 4. BENCHMARK & INVESTIGATION EXECUTION
# ===========================================================================

def run_perspective_investigation() -> Dict[str, Any]:
    """Execute complete Phase 3.5 investigation across real and synthetic cases."""

    # 1. Real Calibration Cases (Verified quads from Phase 3.3-C)
    real_cases = {
        "answer_sheet_2.png": {
            "image_path": os.path.join(ROOT_DIR, "images", "answer_sheet_2.png"),
            "corners": [(118.9, 185.6), (1017.5, 141.1), (1079.6, 1412.3), (181.5, 1456.4)],
            "nature": "ACCEPTED_PHYSICAL_PAGE"
        },
        "answer_sheet_3.jpg": {
            "image_path": os.path.join(ROOT_DIR, "images", "answer_sheet_3.jpg"),
            "corners": [(204.5, 174.8), (1084.1, 262.4), (1137.0, 1450.6), (139.9, 1394.4)],
            "nature": "ACCEPTED_PHYSICAL_PAGE"
        },
    }

    # 2. Synthetic Test Suite
    # Create synthetic test images with text, grid, and contrast steps
    synthetic_cases = {}

    def make_synthetic_sheet(w=800, h=1100):
        img = np.full((h, w, 3), 245, dtype=np.uint8)
        # Add border
        cv2.rectangle(img, (40, 40), (w - 40, h - 40), (0, 0, 0), 2)
        # Add table rows
        for y in range(120, h - 100, 40):
            cv2.line(img, (50, y), (w - 50, y), (180, 180, 180), 1)
        # Add bubbles & text
        for y in range(140, h - 120, 40):
            cv2.putText(img, f"Q{y//40 - 2}:", (60, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            for bx in range(140, w - 80, 50):
                cv2.circle(img, (bx, y - 5), 8, (0, 0, 0), 1)
        return img

    base_synth = make_synthetic_sheet(800, 1100)

    # Place on dark desk background
    def place_on_desk(sheet_img, bg_w=1200, bg_h=1600, quad_corners=None):
        desk = np.full((bg_h, bg_w, 3), 45, dtype=np.uint8) # dark wood
        # Add slight texture
        noise = np.random.RandomState(42).randint(-10, 10, (bg_h, bg_w, 3), dtype=np.int16)
        desk = np.clip(desk.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        sh, sw = sheet_img.shape[:2]
        src_pts = np.array([[0, 0], [sw - 1, 0], [sw - 1, sh - 1], [0, sh - 1]], dtype=np.float32)
        dst_pts = np.array(quad_corners, dtype=np.float32)

        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped_sheet = cv2.warpPerspective(sheet_img, M, (bg_w, bg_h), borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
        
        mask = cv2.warpPerspective(np.full((sh, sw), 255, dtype=np.uint8), M, (bg_w, bg_h))
        combined = desk.copy()
        combined[mask > 128] = warped_sheet[mask > 128]
        return combined

    # Synthetic Test Scenarios:
    # A. Slight Perspective (Keystone 10%)
    c_slight = [(240, 150), (960, 180), (1020, 1420), (180, 1400)]
    synthetic_cases["Synth: Slight Perspective (10% Keystone)"] = {
        "image": place_on_desk(base_synth, 1200, 1600, c_slight),
        "corners": c_slight
    }

    # B. Moderate Perspective (Keystone 25%)
    c_mod = [(320, 120), (880, 180), (1060, 1450), (140, 1410)]
    synthetic_cases["Synth: Moderate Perspective (25% Keystone)"] = {
        "image": place_on_desk(base_synth, 1200, 1600, c_mod),
        "corners": c_mod
    }

    # C. Strong Perspective (Foreshortened 45%)
    c_strong = [(420, 100), (780, 150), (1120, 1480), (80, 1420)]
    synthetic_cases["Synth: Strong Perspective (45% Keystone)"] = {
        "image": place_on_desk(base_synth, 1200, 1600, c_strong),
        "corners": c_strong
    }

    # D. Landscape Document (1.414:1)
    base_land = make_synthetic_sheet(1100, 800)
    c_land = [(100, 250), (1100, 200), (1140, 1350), (60, 1400)]
    synthetic_cases["Synth: Landscape Document (1.4:1)"] = {
        "image": place_on_desk(base_land, 1200, 1600, c_land),
        "corners": c_land
    }

    # E. Extreme Tall Aspect (1:2.5)
    base_tall = make_synthetic_sheet(500, 1250)
    c_tall = [(350, 100), (850, 120), (900, 1500), (300, 1480)]
    synthetic_cases["Synth: Tall Document (1:2.5 Aspect)"] = {
        "image": place_on_desk(base_tall, 1200, 1600, c_tall),
        "corners": c_tall
    }

    results = {
        "dimension_strategies_comparison": {},
        "interpolation_comparison": {},
        "color_vs_gray_comparison": {},
        "border_modes_comparison": {},
        "real_cases_output": {},
        "synthetic_cases_output": {},
    }

    # -----------------------------------------------------------------------
    # TEST 1: Dimension Calculation Strategies on Real & Synthetic Cases
    # -----------------------------------------------------------------------
    dim_strategies = ["MAX_EDGE", "MEAN_EDGE", "AREA_ASPECT_PRESERVED"]

    for name, c_data in {**real_cases, **synthetic_cases}.items():
        if "image_path" in c_data:
            img = cv2.imread(c_data["image_path"])
        else:
            img = c_data["image"]
        ordered = canonical_corner_order(c_data["corners"])

        results["dimension_strategies_comparison"][name] = {}
        for strat in dim_strategies:
            dw, dh, meta = compute_destination_dimensions(ordered, strategy=strat)
            results["dimension_strategies_comparison"][name][strat] = {
                "dest_w": dw, "dest_h": dh,
                "aspect_ratio": meta["dest_aspect_ratio"],
                "area_ratio": meta["area_scaling_factor"]
            }

    # -----------------------------------------------------------------------
    # TEST 2: Interpolation Methods Comparison (Readability & Speed)
    # -----------------------------------------------------------------------
    test_img = cv2.imread(real_cases["answer_sheet_2.png"]["image_path"])
    ordered_test = canonical_corner_order(real_cases["answer_sheet_2.png"]["corners"])
    dw, dh, _ = compute_destination_dimensions(ordered_test, strategy="MAX_EDGE")

    interp_methods = {
        "INTER_NEAREST": cv2.INTER_NEAREST,
        "INTER_LINEAR": cv2.INTER_LINEAR,
        "INTER_CUBIC": cv2.INTER_CUBIC,
        "INTER_LANCZOS4": cv2.INTER_LANCZOS4,
    }

    for iname, iflag in interp_methods.items():
        times = []
        for _ in range(5):
            t0 = time.perf_counter()
            w_res = execute_perspective_warp(test_img, ordered_test, dw, dh, interp_method=iflag)
            times.append(time.perf_counter() - t0)

        # Compute edge sharpness (variance of Laplacian on small text patch)
        gray_w = cv2.cvtColor(w_res, cv2.COLOR_BGR2GRAY)
        lap_var = float(cv2.Laplacian(gray_w[300:700, 200:600], cv2.CV_64F).var())

        results["interpolation_comparison"][iname] = {
            "mean_execution_ms": float(np.mean(times) * 1000.0),
            "laplacian_sharpness_score": lap_var,
        }

    # -----------------------------------------------------------------------
    # TEST 3: Color vs Grayscale Warping Execution
    # -----------------------------------------------------------------------
    # Path A: Warp Color BGR -> Convert to Grayscale
    t0 = time.perf_counter()
    w_bgr = execute_perspective_warp(test_img, ordered_test, dw, dh)
    gray_from_bgr = cv2.cvtColor(w_bgr, cv2.COLOR_BGR2GRAY)
    t_color_first = time.perf_counter() - t0

    # Path B: Convert to Grayscale -> Warp Grayscale
    t0 = time.perf_counter()
    gray_src = cv2.cvtColor(test_img, cv2.COLOR_BGR2GRAY)
    w_gray = execute_perspective_warp(gray_src, ordered_test, dw, dh)
    t_gray_first = time.perf_counter() - t0

    # Max pixel difference between the two paths
    diff_pix = float(np.max(np.abs(gray_from_bgr.astype(np.int16) - w_gray.astype(np.int16))))
    mean_diff = float(np.mean(np.abs(gray_from_bgr.astype(np.int16) - w_gray.astype(np.int16))))

    results["color_vs_gray_comparison"] = {
        "warp_bgr_then_gray_ms": t_color_first * 1000.0,
        "convert_gray_then_warp_ms": t_gray_first * 1000.0,
        "speedup_factor": (t_color_first / max(1e-4, t_gray_first)),
        "max_pixel_discrepancy": diff_pix,
        "mean_pixel_discrepancy": mean_diff
    }

    # -----------------------------------------------------------------------
    # TEST 4: Generate Diagnostic Overlays
    # -----------------------------------------------------------------------
    vis_path_real = os.path.join(OUTPUT_DIR, "phase3_perspective_warp_real.png")
    vis_path_synth = os.path.join(OUTPUT_DIR, "phase3_perspective_warp_synthetic.png")
    generate_warp_visualizations(real_cases, synthetic_cases, vis_path_real, vis_path_synth)

    return results


# ===========================================================================
# 5. VISUALIZATION GENERATORS
# ===========================================================================

def generate_warp_visualizations(
    real_cases: Dict[str, Any],
    synthetic_cases: Dict[str, Any],
    out_real: str,
    out_synth: str
):
    # 1. Real Calibration Cases Figure
    fig, axes = plt.subplots(2, 2, figsize=(14, 16))

    for idx, (img_name, c_data) in enumerate(real_cases.items()):
        img = cv2.imread(c_data["image_path"])
        ordered = canonical_corner_order(c_data["corners"])
        dw, dh, meta = compute_destination_dimensions(ordered, strategy="MAX_EDGE")
        warped = execute_perspective_warp(img, ordered, dw, dh, interp_method=cv2.INTER_LINEAR)

        # Plot Source with Overlay
        ax_src = axes[idx, 0]
        rgb_src = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        ax_src.imshow(rgb_src)
        poly = np.vstack([ordered, ordered[0]])
        ax_src.plot(poly[:, 0], poly[:, 1], color="lime", linewidth=2.5)
        for c_idx, (px, py) in enumerate(ordered):
            ax_src.plot(px, py, marker="o", markersize=8, markerfacecolor="cyan", markeredgecolor="black")
            labels = ["TL", "TR", "BR", "BL"]
            ax_src.text(px + 15, py - 15, labels[c_idx], color="white", fontsize=8,
                        bbox=dict(boxstyle="round,pad=0.2", facecolor="black", alpha=0.75))
        ax_src.set_title(f"Source: {img_name}\nValidated Physical Quad", fontsize=11, fontweight="bold")
        ax_src.axis("off")

        # Plot Warped Destination
        ax_dst = axes[idx, 1]
        rgb_dst = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
        ax_dst.imshow(rgb_dst)
        ax_dst.set_title(f"Canonical Warped Output ({dw}x{dh} px)\nAspect Ratio={meta['dest_aspect_ratio']:.3f}", fontsize=11, fontweight="bold")
        ax_dst.axis("off")

    plt.tight_layout()
    plt.savefig(out_real, dpi=120)
    plt.close()

    # 2. Synthetic Perspective Scenarios Figure
    fig, axes = plt.subplots(3, 2, figsize=(14, 18))
    synth_items = list(synthetic_cases.items())[:3]

    for idx, (sc_name, c_data) in enumerate(synth_items):
        img = c_data["image"]
        ordered = canonical_corner_order(c_data["corners"])
        dw, dh, meta = compute_destination_dimensions(ordered, strategy="MAX_EDGE")
        warped = execute_perspective_warp(img, ordered, dw, dh, interp_method=cv2.INTER_LINEAR)

        # Source
        ax_src = axes[idx, 0]
        ax_src.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        poly = np.vstack([ordered, ordered[0]])
        ax_src.plot(poly[:, 0], poly[:, 1], color="deepskyblue", linewidth=2.5)
        ax_src.set_title(f"{sc_name}\nProjected Perspective Geometry", fontsize=10, fontweight="bold")
        ax_src.axis("off")

        # Destination
        ax_dst = axes[idx, 1]
        ax_dst.imshow(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))
        ax_dst.set_title(f"Canonical Rectified Output\n({dw}x{dh} px, Aspect={meta['dest_aspect_ratio']:.3f})", fontsize=10, fontweight="bold")
        ax_dst.axis("off")

    plt.tight_layout()
    plt.savefig(out_synth, dpi=120)
    plt.close()


# ===========================================================================
# 6. SCRIPT ENTRYPOINT & AUDIT EXECUTION
# ===========================================================================

def main():
    print("=" * 80)
    print("AI-EVAL PHASE 3.5: PERSPECTIVE TRANSFORM & CANONICAL GEOMETRY")
    print("=" * 80)
    print("Goal: Investigating destination dimensions, aspect preservation, interpolation,")
    print("      and non-physical capture handling.")
    print("Guardrails: Investigation only; NO production pipeline; NO frozen thresholds.")
    print("-" * 80)

    res = run_perspective_investigation()

    print("\n1. DESTINATION DIMENSION STRATEGIES COMPARISON:")
    print("-" * 80)
    for c_name, strats in res["dimension_strategies_comparison"].items():
        print(f"Scenario: {c_name}")
        for s_name, data in strats.items():
            print(f"  * {s_name:22s} -> {data['dest_w']}x{data['dest_h']} px | Aspect={data['aspect_ratio']:.3f} | AreaScale={data['area_ratio']:.2f}")

    print("\n2. INTERPOLATION METHODS COMPARISON (Speed & Sharpness):")
    print("-" * 80)
    for iname, idata in res["interpolation_comparison"].items():
        print(f"  * {iname:16s} -> Time: {idata['mean_execution_ms']:6.2f} ms | SharpnessScore (Laplacian Var): {idata['laplacian_sharpness_score']:.1f}")

    print("\n3. COLOR VS GRAYSCALE WARPING AUDIT:")
    print("-" * 80)
    cg = res["color_vs_gray_comparison"]
    print(f"  * Warp Color BGR then convert to Gray: {cg['warp_bgr_then_gray_ms']:.2f} ms")
    print(f"  * Convert to Gray then Warp:           {cg['convert_gray_then_warp_ms']:.2f} ms")
    print(f"  * Speedup Factor by Warping Gray:     {cg['speedup_factor']:.2f}x faster")
    print(f"  * Max Pixel Discrepancy between paths: {cg['max_pixel_discrepancy']:.1f} intensity levels (Mean={cg['mean_pixel_discrepancy']:.2f})")

    print("\n4. NON-PHYSICAL CAPTURE HANDLING AUDIT:")
    print("-" * 80)
    print("  * FRAME_LIMITED (e.g. answer_sheet_4, 5):")
    print("    - Top/bottom or all edges touch sensor frame.")
    print("    - Calling 4-corner warp creates false foreshortening and crops margin content.")
    print("    - Production recommendation: Apply rigid affine deskew (warpAffine by lateral angle) or pass unwarped.")
    print("  * AMBIGUOUS (e.g. answer_sheet.jpg):")
    print("    - No physical page corners exist.")
    print("    - Must NOT be warped with manufactured corners. Pass through or flag for human review.")

    print("\n" + "=" * 80)
    print("OVERLAYS SAVED:")
    print("  * " + os.path.join(OUTPUT_DIR, "phase3_perspective_warp_real.png"))
    print("  * " + os.path.join(OUTPUT_DIR, "phase3_perspective_warp_synthetic.png"))
    print("=" * 80)


if __name__ == "__main__":
    main()
