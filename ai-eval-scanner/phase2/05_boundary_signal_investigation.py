"""
phase2/05_boundary_signal_investigation.py

INVESTIGATION-ONLY CASE-STUDY DIAGNOSTIC:
Examines whether the suspected physical page-join observed around y=560-610 in
the reference case-study image (images/answer_sheet.jpg) has independent evidence
from vertical brightness gradients and HSV colour saturation.

IMPORTANT ARCHITECTURAL & DIAGNOSTIC NOTES:
1. Investigation-only case-study: This script is an exploratory diagnostic tool
   developed for analyzing the physical characteristics of images/answer_sheet.jpg.
2. Specificity of y=607 transition: The sharp numerical transition at y=607 (+82.31)
   is an empirical feature of the two-page booklet fold / shadow in answer_sheet.jpg.
   Multi-image validation shows this transition does NOT occur in other answer sheets.
3. Not a page detector: This script does NOT detect or declare page boundaries.
   The values and thresholds herein must NOT be treated as universal page-boundary rules.
4. No image-specific boundary declaration: y=560-610 is strictly a baseline
   reference region from initial inspection, not a hard-coded page boundary.
5. No cropping, perspective correction, or PASS/FAIL judgment is performed.

Signals investigated:
1. Vertical grayscale brightness profile (row-wise mean).
2. First derivative / row-to-row brightness change via np.diff().
3. HSV saturation profile per row.
4. Co-registered vertical alignment of brightness-gradient and saturation signals.

Outputs saved in phase2/output/:
- 15_vertical_brightness_gradient.png
- 16_hsv_saturation_profile.png
- 17_boundary_signal_comparison.png
"""

import os
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
IMAGE_PATH = "images/answer_sheet.jpg"
OUTPUT_DIR = "phase2/output"

# Reference region under hypothesis from previous investigations of answer_sheet.jpg.
# Used purely as an observational reference band, NOT a page boundary detector.
HYPOTHESIS_Y_START = 560
HYPOTHESIS_Y_END = 610


def load_image(path):
    """Load image from disk and return BGR, Gray, and HSV arrays."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input image not found at: {path}")

    bgr = cv2.imread(path)
    if bgr is None:
        raise ValueError(f"Failed to read image at: {path}")

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return bgr, gray, hsv


def compute_vertical_profiles(gray, hsv):
    """
    Compute row-wise vertical profiles across all rows y in [0, H-1].
    - Gray mean brightness
    - Row-to-row first difference (np.diff)
    - HSV saturation mean and std dev
    """
    h, w = gray.shape

    # Row-wise grayscale brightness
    row_brightness = np.mean(gray, axis=1)  # shape (h,)

    # First derivative (row-to-row difference)
    # diff[y] = row_brightness[y+1] - row_brightness[y]
    brightness_diff = np.diff(row_brightness)  # shape (h-1,)

    # HSV saturation channel: S is channel index 1 (range 0..255)
    sat_channel = hsv[:, :, 1]
    row_sat_mean = np.mean(sat_channel, axis=1)  # shape (h,)
    row_sat_std = np.std(sat_channel, axis=1)    # shape (h,)

    return {
        "height": h,
        "width": w,
        "brightness": row_brightness,
        "brightness_diff": brightness_diff,
        "sat_mean": row_sat_mean,
        "sat_std": row_sat_std,
    }


def find_gradient_peaks(brightness_diff, top_n=6):
    """Identify the top positive and negative row-to-row gradient peaks."""
    # Negative gradients: drop from row y to row y+1
    sorted_neg_indices = np.argsort(brightness_diff)[:top_n]
    neg_peaks = [(int(idx), float(brightness_diff[idx])) for idx in sorted_neg_indices]

    # Positive gradients: jump from row y to row y+1
    sorted_pos_indices = np.argsort(brightness_diff)[::-1][:top_n]
    pos_peaks = [(int(idx), float(brightness_diff[idx])) for idx in sorted_pos_indices]

    return neg_peaks, pos_peaks


def find_paired_transitions(brightness_diff, max_gap=40, top_n=5, suppression_radius=6):
    """
    Find paired dark->bright transitions:
    A significant negative drop followed closely (within max_gap rows)
    by a significant positive rise, characteristic of a seam, gap, or groove.

    Applies non-maximum suppression / event grouping using suppression_radius
    to ensure adjacent samples belonging to the same continuous gradient ramp
    are reported as a single transition event rather than duplicate pairs.
    """
    h_diff = len(brightness_diff)
    raw_pairs = []

    neg_thresh = min(-1.0, float(np.percentile(brightness_diff, 5)))
    pos_thresh = max(1.0, float(np.percentile(brightness_diff, 95)))

    for y_neg in range(h_diff):
        val_neg = brightness_diff[y_neg]
        if val_neg <= neg_thresh:
            y_search_end = min(h_diff, y_neg + max_gap)
            for y_pos in range(y_neg + 1, y_search_end):
                val_pos = brightness_diff[y_pos]
                if val_pos >= pos_thresh:
                    valley_depth = val_pos - val_neg
                    span = y_pos - y_neg
                    raw_pairs.append({
                        "y_drop": y_neg,
                        "drop_val": float(val_neg),
                        "y_rise": y_pos,
                        "rise_val": float(val_pos),
                        "span": span,
                        "valley_score": float(valley_depth)
                    })

    # Sort raw candidate pairs by valley score descending
    raw_pairs.sort(key=lambda p: p["valley_score"], reverse=True)

    # Event grouping / non-maximum suppression
    grouped_pairs = []
    for candidate in raw_pairs:
        is_duplicate = False
        for accepted in grouped_pairs:
            # Check if drop or rise overlaps an existing event within suppression radius
            if (abs(candidate["y_drop"] - accepted["y_drop"]) <= suppression_radius or
                abs(candidate["y_rise"] - accepted["y_rise"]) <= suppression_radius):
                is_duplicate = True
                break
        if not is_duplicate:
            grouped_pairs.append(candidate)
            if len(grouped_pairs) >= top_n:
                break

    return grouped_pairs


def analyze_reference_region(profiles, y_start, y_end):
    """
    Extract and summarize numerical stats for the reference hypothesis region.
    Global baseline statistics are handled directly by the caller.
    """
    brightness = profiles["brightness"]
    brightness_diff = profiles["brightness_diff"]
    sat_mean = profiles["sat_mean"]

    h = profiles["height"]
    y_start_clamped = max(0, min(y_start, h - 1))
    y_end_clamped = max(0, min(y_end, h - 1))

    ref_brightness = brightness[y_start_clamped:y_end_clamped + 1]
    ref_diff = brightness_diff[y_start_clamped:min(y_end_clamped, len(brightness_diff))]
    ref_sat = sat_mean[y_start_clamped:y_end_clamped + 1]

    return {
        "y_start": y_start_clamped,
        "y_end": y_end_clamped,
        "ref_bright_min": float(np.min(ref_brightness)),
        "ref_bright_max": float(np.max(ref_brightness)),
        "ref_bright_mean": float(np.mean(ref_brightness)),
        "ref_min_diff": float(np.min(ref_diff)) if len(ref_diff) > 0 else 0.0,
        "ref_max_diff": float(np.max(ref_diff)) if len(ref_diff) > 0 else 0.0,
        "ref_sat_min": float(np.min(ref_sat)),
        "ref_sat_max": float(np.max(ref_sat)),
        "ref_sat_mean": float(np.mean(ref_sat)),
    }


# ---------------------------------------------------------------------------
# Plotting functions
# ---------------------------------------------------------------------------
def plot_brightness_gradient(profiles, output_path, y_ref_start, y_ref_end):
    """
    Output 15: Two-panel plot showing:
    1. Vertical brightness profile (Row y vs Brightness)
    2. First derivative (Row y vs dI/dy) with reference region indicator.
    """
    brightness = profiles["brightness"]
    diff = profiles["brightness_diff"]
    h = profiles["height"]
    rows = np.arange(h)
    diff_rows = np.arange(len(diff))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [1.2, 1.0]})

    # Panel 1: Vertical Brightness Profile
    ax1.plot(rows, brightness, color="#1f77b4", linewidth=1.2, label="Row Mean Brightness")
    ax1.axvspan(y_ref_start, y_ref_end, color="#ff7f0e", alpha=0.22,
                label=f"Hypothesis Zone (y={y_ref_start}-{y_ref_end})")
    ax1.set_ylabel("Grayscale Intensity (0-255)", fontsize=11)
    ax1.set_title("Vertical Brightness Profile & Row-to-Row Gradient", fontsize=13, fontweight="bold")
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(loc="upper right", framealpha=0.9)

    # Panel 2: First Derivative np.diff
    ax2.plot(diff_rows, diff, color="#2ca02c", linewidth=0.9, label="dI/dy (np.diff)")
    ax2.axhline(0, color="gray", linestyle="--", linewidth=0.8)
    ax2.axvspan(y_ref_start, y_ref_end, color="#ff7f0e", alpha=0.22,
                label=f"Hypothesis Zone (y={y_ref_start}-{y_ref_end})")
    ax2.set_xlabel("Vertical Coordinate y (rows: 0 to H-1)", fontsize=11)
    ax2.set_ylabel("First Derivative dI/dy", fontsize=11)
    ax2.set_xlim(0, h)
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.legend(loc="upper right", framealpha=0.9)

    plt.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def plot_hsv_saturation(profiles, output_path, y_ref_start, y_ref_end):
    """
    Output 16: HSV Saturation profile along vertical axis.
    Shows mean saturation per row and +/- 1 std deviation band.
    """
    sat_mean = profiles["sat_mean"]
    sat_std = profiles["sat_std"]
    h = profiles["height"]
    rows = np.arange(h)

    fig, ax = plt.subplots(figsize=(12, 5.5))

    ax.plot(rows, sat_mean, color="#d62728", linewidth=1.4, label="Mean HSV Saturation (S)")
    ax.fill_between(rows, np.maximum(0, sat_mean - sat_std),
                    np.minimum(255, sat_mean + sat_std),
                    color="#d62728", alpha=0.18, label="+/- 1 Std Dev")

    ax.axvspan(y_ref_start, y_ref_end, color="#ff7f0e", alpha=0.22,
                label=f"Hypothesis Zone (y={y_ref_start}-{y_ref_end})")

    ax.set_xlabel("Vertical Coordinate y (rows: 0 to H-1)", fontsize=11)
    ax.set_ylabel("HSV Saturation Value (0-255)", fontsize=11)
    ax.set_title("HSV Saturation Profile Along Vertical Axis", fontsize=13, fontweight="bold")
    ax.set_xlim(0, h)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="upper right", framealpha=0.9)

    plt.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def plot_signal_comparison(gray_img, profiles, output_path, y_ref_start, y_ref_end):
    """
    Output 17: Co-registered multi-panel comparison along vertical axis.
    All plots share the EXACT vertical coordinate y on the vertical axis
    (oriented vertically from top y=0 to bottom y=H-1):
    - Subplot 1: Narrow vertical strip of grayscale image
    - Subplot 2: Row Mean Brightness profile
    - Subplot 3: First derivative dI/dy
    - Subplot 4: HSV Saturation profile
    """
    h = profiles["height"]
    brightness = profiles["brightness"]
    diff = profiles["brightness_diff"]
    sat_mean = profiles["sat_mean"]
    rows = np.arange(h)
    diff_rows = np.arange(len(diff))

    fig, axes = plt.subplots(1, 4, figsize=(15, 9), sharey=True,
                             gridspec_kw={"width_ratios": [1.0, 1.8, 1.8, 1.8]})

    ax_img, ax_bright, ax_diff, ax_sat = axes

    # Subplot 1: Grayscale Image overview
    ax_img.imshow(gray_img, cmap="gray", aspect="auto")
    ax_img.axhspan(y_ref_start, y_ref_end, color="red", alpha=0.35, label="Hypothesis")
    ax_img.set_title("Input Image", fontsize=11, fontweight="bold")
    ax_img.set_ylabel("Vertical Coordinate y (pixels)", fontsize=11)
    ax_img.set_xticks([])

    # Subplot 2: Brightness profile (aligned vertically)
    ax_bright.plot(brightness, rows, color="#1f77b4", linewidth=1.3)
    ax_bright.axhspan(y_ref_start, y_ref_end, color="#ff7f0e", alpha=0.22)
    ax_bright.set_title("Mean Brightness", fontsize=11, fontweight="bold")
    ax_bright.set_xlabel("Intensity (0-255)", fontsize=10)
    ax_bright.grid(True, linestyle="--", alpha=0.5)

    # Subplot 3: First derivative dI/dy (aligned vertically)
    ax_diff.plot(diff, diff_rows, color="#2ca02c", linewidth=1.0)
    ax_diff.axvline(0, color="gray", linestyle="--", linewidth=0.8)
    ax_diff.axhspan(y_ref_start, y_ref_end, color="#ff7f0e", alpha=0.22)
    ax_diff.set_title("Brightness Gradient (dI/dy)", fontsize=11, fontweight="bold")
    ax_diff.set_xlabel("dI/dy", fontsize=10)
    ax_diff.grid(True, linestyle="--", alpha=0.5)

    # Subplot 4: Saturation profile (aligned vertically)
    ax_sat.plot(sat_mean, rows, color="#d62728", linewidth=1.3)
    ax_sat.axhspan(y_ref_start, y_ref_end, color="#ff7f0e", alpha=0.22)
    ax_sat.set_title("HSV Saturation (S)", fontsize=11, fontweight="bold")
    ax_sat.set_xlabel("Saturation (0-255)", fontsize=10)
    ax_sat.grid(True, linestyle="--", alpha=0.5)

    # Invert shared y-axis so row 0 is at top, matching image coordinates
    ax_img.set_ylim(h - 1, 0)

    plt.suptitle("Co-Registered Boundary Signal Comparison along Vertical Axis",
                 fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main Investigation Runner
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("AI-EVAL Phase 2: Boundary Signal Investigation (Case-Study Diagnostic)")
    print("Script: phase2/05_boundary_signal_investigation.py")
    print("=" * 70)

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Load Image
    print(f"\n[1] Loading image: {IMAGE_PATH}")
    bgr, gray, hsv = load_image(IMAGE_PATH)
    h, w = gray.shape
    print(f"    Image dimensions: {w} x {h} (width x height)")

    # 2. Compute profiles
    print("\n[2] Computing vertical brightness and colour signals...")
    profiles = compute_vertical_profiles(gray, hsv)
    brightness = profiles["brightness"]
    brightness_diff = profiles["brightness_diff"]
    sat_mean = profiles["sat_mean"]

    # 3. Numerical analysis: Gradients and Peaks
    neg_peaks, pos_peaks = find_gradient_peaks(brightness_diff, top_n=6)
    paired_transitions = find_paired_transitions(brightness_diff, max_gap=40, top_n=5)

    print("\n" + "-" * 70)
    print("NUMERICAL FINDINGS: BRIGHTNESS GRADIENT (FIRST DERIVATIVE)")
    print("-" * 70)

    print("\n  Top Negative Brightness Gradients (steepest intensity drops):")
    print("    Rank | Row y  | dI/dy (y -> y+1) | Note")
    print("    " + "-" * 50)
    for rank, (y_idx, val) in enumerate(neg_peaks, 1):
        in_ref = "IN HYPOTHESIS ZONE" if HYPOTHESIS_Y_START <= y_idx <= HYPOTHESIS_Y_END else ""
        print(f"    {rank:4d} | y={y_idx:4d} | {val:14.3f} | {in_ref}")

    print("\n  Top Positive Brightness Gradients (steepest intensity rises):")
    print("    Rank | Row y  | dI/dy (y -> y+1) | Note")
    print("    " + "-" * 50)
    for rank, (y_idx, val) in enumerate(pos_peaks, 1):
        in_ref = "IN HYPOTHESIS ZONE" if HYPOTHESIS_Y_START <= y_idx <= HYPOTHESIS_Y_END else ""
        print(f"    {rank:4d} | y={y_idx:4d} | {val:14.3f} | {in_ref}")

    print("\n  Paired Dark->Bright Transitions (Non-Maximum Suppressed, max_gap <= 40 rows):")
    print("    Rank | Drop y | Drop val | Rise y | Rise val | Span (px) | Valley Depth")
    print("    " + "-" * 66)
    for rank, p in enumerate(paired_transitions, 1):
        in_ref = " *" if (HYPOTHESIS_Y_START <= p["y_drop"] <= HYPOTHESIS_Y_END or
                          HYPOTHESIS_Y_START <= p["y_rise"] <= HYPOTHESIS_Y_END) else ""
        print(f"    {rank:4d} | y={p['y_drop']:4d} | {p['drop_val']:8.2f} | "
              f"y={p['y_rise']:4d} | {p['rise_val']:8.2f} | {p['span']:9d} | "
              f"{p['valley_score']:12.2f}{in_ref}")
    if any("*" in str(p) for p in paired_transitions):
        print("    (* denotes transition overlapping the reference hypothesis region)")

    # 4. Numerical analysis: Saturation Profile
    sat_min_idx = int(np.argmin(sat_mean))
    sat_max_idx = int(np.argmax(sat_mean))
    global_sat_mean = float(np.mean(sat_mean))
    global_bright_mean = float(np.mean(brightness))

    print("\n" + "-" * 70)
    print("NUMERICAL FINDINGS: HSV SATURATION PROFILE")
    print("-" * 70)
    print(f"  Global Minimum Saturation: {sat_mean[sat_min_idx]:.2f} at row y={sat_min_idx}")
    print(f"  Global Maximum Saturation: {sat_mean[sat_max_idx]:.2f} at row y={sat_max_idx}")
    print(f"  Overall Mean Saturation:   {global_sat_mean:.2f} (std={np.std(sat_mean):.2f})")

    # 5. Inspection of hypothesis region y ≈ 560-610
    ref_stats = analyze_reference_region(profiles, HYPOTHESIS_Y_START, HYPOTHESIS_Y_END)
    print("\n" + "-" * 70)
    print(f"REFERENCE REGION INSPECTION (y={HYPOTHESIS_Y_START} to {HYPOTHESIS_Y_END})")
    print("Treating y=560-610 purely as an empirical hypothesis reference for answer_sheet.jpg")
    print("-" * 70)
    print(f"  Brightness range in zone:  {ref_stats['ref_bright_min']:.2f} to {ref_stats['ref_bright_max']:.2f} "
          f"(mean={ref_stats['ref_bright_mean']:.2f}, global mean={global_bright_mean:.2f})")
    print(f"  Steepest drop in zone:     dI/dy = {ref_stats['ref_min_diff']:.2f}")
    print(f"  Steepest rise in zone:     dI/dy = {ref_stats['ref_max_diff']:.2f}")
    print(f"  Saturation range in zone:  {ref_stats['ref_sat_min']:.2f} to {ref_stats['ref_sat_max']:.2f} "
          f"(mean={ref_stats['ref_sat_mean']:.2f}, global mean={global_sat_mean:.2f})")

    # 6. Generate and save diagnostic visualizations
    print("\n" + "-" * 70)
    print("GENERATING DIAGNOSTIC VISUALIZATIONS")
    print("-" * 70)

    out15 = os.path.join(OUTPUT_DIR, "15_vertical_brightness_gradient.png")
    plot_brightness_gradient(profiles, out15, HYPOTHESIS_Y_START, HYPOTHESIS_Y_END)
    print(f"  [Saved] {out15}")

    out16 = os.path.join(OUTPUT_DIR, "16_hsv_saturation_profile.png")
    plot_hsv_saturation(profiles, out16, HYPOTHESIS_Y_START, HYPOTHESIS_Y_END)
    print(f"  [Saved] {out16}")

    out17 = os.path.join(OUTPUT_DIR, "17_boundary_signal_comparison.png")
    plot_signal_comparison(gray, profiles, out17, HYPOTHESIS_Y_START, HYPOTHESIS_Y_END)
    print(f"  [Saved] {out17}")

    print("\n" + "=" * 70)
    print("INVESTIGATION COMPLETE (No boundaries declared, diagnostic only)")
    print("=" * 70)


if __name__ == "__main__":
    main()
