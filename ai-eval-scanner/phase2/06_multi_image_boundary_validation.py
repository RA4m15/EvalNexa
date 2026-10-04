"""
phase2/06_multi_image_boundary_validation.py

Investigation-only script:
Validates boundary signals discovered during Phase 2 across ALL five answer-sheet
images in images/ using identical, uniform processing without image-specific tuning.

Signals investigated for each image:
1. Vertical grayscale mean brightness profile
2. Row-to-row brightness gradient (first derivative via np.diff)
3. HSV mean saturation profile
4. Vertical edge-density profile (Canny edge fraction per row)
5. Row-wise local variance profile (intensity contrast/texture per row)

Outputs:
- phase2/output/18_multi_image_boundary_validation.txt (tabular comparison report)
- phase2/output/18_multi_image_boundary_comparison.png (multi-signal comparative plot)

CONSTRAINTS:
- Diagnostic only.
- No page boundary declaration, no hard-coded thresholds, no crop or perspective warp.
- Uniform treatment of all images.
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
IMAGE_FILES = [
    "answer_sheet.jpg",
    "answer_sheet_2.png",
    "answer_sheet_3.jpg",
    "answer_sheet_4.jpg",
    "answer_sheet_5.jpg"
]
IMAGES_DIR = "images"
OUTPUT_DIR = "phase2/output"
REPORT_TXT = os.path.join(OUTPUT_DIR, "18_multi_image_boundary_validation.txt")
COMPARISON_PNG = os.path.join(OUTPUT_DIR, "18_multi_image_boundary_comparison.png")

# Common Canny parameters applied uniformly to all images
CANNY_LOW = 50
CANNY_HIGH = 150
BLUR_KSIZE = (5, 5)


def analyze_single_image(img_path):
    """
    Computes all 5 signals for a single image uniformly.
    Returns dictionary with raw signals and summary statistics.
    """
    filename = os.path.basename(img_path)
    bgr = cv2.imread(img_path)
    if bgr is None:
        raise ValueError(f"Could not read image: {img_path}")

    h, w, c = bgr.shape
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    # 1. Grayscale mean brightness profile
    brightness = np.mean(gray, axis=1)  # shape (h,)

    # 2. Row-to-row brightness gradient
    brightness_diff = np.diff(brightness)  # shape (h-1,)

    # 3. HSV saturation profile (S channel = index 1)
    sat_channel = hsv[:, :, 1]
    sat_mean = np.mean(sat_channel, axis=1)  # shape (h,)

    # 4. Vertical edge density profile
    blurred = cv2.GaussianBlur(gray, BLUR_KSIZE, 0)
    edges = cv2.Canny(blurred, CANNY_LOW, CANNY_HIGH)
    edge_density = np.mean(edges > 0, axis=1)  # fraction in [0, 1]

    # 5. Row-wise variance profile
    variance = np.var(gray, axis=1)  # variance across columns per row

    # Numerical metrics
    # Gradient extremes
    top_pos_idx = int(np.argmax(brightness_diff))
    top_pos_val = float(brightness_diff[top_pos_idx])
    top_neg_idx = int(np.argmin(brightness_diff))
    top_neg_val = float(brightness_diff[top_neg_idx])

    # Top 3 positive and negative gradient locations
    pos_top3 = [(int(i), float(brightness_diff[i])) for i in np.argsort(brightness_diff)[::-1][:3]]
    neg_top3 = [(int(i), float(brightness_diff[i])) for i in np.argsort(brightness_diff)[:3]]

    # Saturation extremes
    sat_min_idx = int(np.argmin(sat_mean))
    sat_min_val = float(sat_mean[sat_min_idx])
    sat_max_idx = int(np.argmax(sat_mean))
    sat_max_val = float(sat_mean[sat_max_idx])

    # Edge density extremes
    edge_min_idx = int(np.argmin(edge_density))
    edge_min_val = float(edge_density[edge_min_idx])
    edge_max_idx = int(np.argmax(edge_density))
    edge_max_val = float(edge_density[edge_max_idx])

    # Variance extremes
    var_min_idx = int(np.argmin(variance))
    var_min_val = float(variance[var_min_idx])
    var_max_idx = int(np.argmax(variance))
    var_max_val = float(variance[var_max_idx])

    return {
        "filename": filename,
        "width": w,
        "height": h,
        "channels": c,
        "brightness": brightness,
        "brightness_diff": brightness_diff,
        "sat_mean": sat_mean,
        "edge_density": edge_density,
        "variance": variance,
        "top_pos_idx": top_pos_idx,
        "top_pos_val": top_pos_val,
        "top_neg_idx": top_neg_idx,
        "top_neg_val": top_neg_val,
        "pos_top3": pos_top3,
        "neg_top3": neg_top3,
        "sat_min_idx": sat_min_idx,
        "sat_min_val": sat_min_val,
        "sat_max_idx": sat_max_idx,
        "sat_max_val": sat_max_val,
        "edge_min_idx": edge_min_idx,
        "edge_min_val": edge_min_val,
        "edge_max_idx": edge_max_idx,
        "edge_max_val": edge_max_val,
        "var_min_idx": var_min_idx,
        "var_min_val": var_min_val,
        "var_max_idx": var_max_idx,
        "var_max_val": var_max_val,
    }


def generate_comparison_plot(results, out_path):
    """
    Generate unified comparative visualization across all 5 images.
    Signals are plotted against normalized vertical coordinate y/H in [0.0, 1.0]
    to enable meaningful cross-image scale comparison.
    """
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    fig, axes = plt.subplots(5, 1, figsize=(14, 15), sharex=True)

    # 1. Grayscale Brightness
    ax1 = axes[0]
    for res, color in zip(results, colors):
        norm_y = np.linspace(0.0, 1.0, res["height"])
        ax1.plot(norm_y, res["brightness"], color=color, linewidth=1.1,
                 label=f"{res['filename']} ({res['width']}x{res['height']})")
    ax1.set_ylabel("Mean Brightness (0-255)", fontsize=10)
    ax1.set_title("1. Vertical Mean Grayscale Brightness", fontsize=11, fontweight="bold")
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(loc="upper right", fontsize=8, framealpha=0.9)

    # 2. Brightness Gradient dI/dy
    ax2 = axes[1]
    for res, color in zip(results, colors):
        norm_y = np.linspace(0.0, 1.0, len(res["brightness_diff"]))
        ax2.plot(norm_y, res["brightness_diff"], color=color, linewidth=0.9,
                 label=res["filename"])
    ax2.axhline(0, color="gray", linestyle="--", linewidth=0.7)
    ax2.set_ylabel("dI/dy (np.diff)", fontsize=10)
    ax2.set_title("2. Row-to-Row Brightness Gradient (dI/dy)", fontsize=11, fontweight="bold")
    ax2.grid(True, linestyle="--", alpha=0.5)

    # 3. HSV Saturation
    ax3 = axes[2]
    for res, color in zip(results, colors):
        norm_y = np.linspace(0.0, 1.0, res["height"])
        ax3.plot(norm_y, res["sat_mean"], color=color, linewidth=1.1,
                 label=res["filename"])
    ax3.set_ylabel("Mean Saturation (0-255)", fontsize=10)
    ax3.set_title("3. HSV Mean Colour Saturation (S Channel)", fontsize=11, fontweight="bold")
    ax3.grid(True, linestyle="--", alpha=0.5)

    # 4. Vertical Edge Density
    ax4 = axes[3]
    for res, color in zip(results, colors):
        norm_y = np.linspace(0.0, 1.0, res["height"])
        ax4.plot(norm_y, res["edge_density"] * 100.0, color=color, linewidth=1.0,
                 label=res["filename"])
    ax4.set_ylabel("Edge Density (%)", fontsize=10)
    ax4.set_title("4. Vertical Edge Density (Canny Edge Pixel %)", fontsize=11, fontweight="bold")
    ax4.grid(True, linestyle="--", alpha=0.5)

    # 5. Row-wise Local Variance
    ax5 = axes[4]
    for res, color in zip(results, colors):
        norm_y = np.linspace(0.0, 1.0, res["height"])
        ax5.plot(norm_y, res["variance"], color=color, linewidth=1.0,
                 label=res["filename"])
    ax5.set_ylabel("Intensity Variance", fontsize=10)
    ax5.set_title("5. Row-wise Intensity Variance (Texture / Contrast)", fontsize=11, fontweight="bold")
    ax5.set_xlabel("Normalized Vertical Coordinate (y / Height) [0.0 = Top, 1.0 = Bottom]", fontsize=11)
    ax5.set_xlim(0.0, 1.0)
    ax5.grid(True, linestyle="--", alpha=0.5)

    plt.suptitle("Phase 2 Multi-Image Boundary Signal Comparison Across 5 Answer Sheets",
                 fontsize=13, fontweight="bold", y=0.995)
    plt.tight_layout(rect=[0, 0, 1, 0.99])
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def build_text_report(results):
    """Format tabular and narrative report for phase2/output/18_multi_image_boundary_validation.txt."""
    lines = []
    lines.append("=" * 78)
    lines.append("AI-EVAL PHASE 2: MULTI-IMAGE BOUNDARY SIGNAL VALIDATION REPORT")
    lines.append("=" * 78)
    lines.append("")
    lines.append("Investigation Purpose:")
    lines.append("Evaluate whether the 5 primary signals (Brightness, Gradient, Saturation,")
    lines.append("Edge Density, Variance) behave consistently or vary across all 5 test images.")
    lines.append("No page boundaries declared. No image-specific thresholds used.")
    lines.append("")

    lines.append("-" * 78)
    lines.append("1. IMAGE INVENTORY & BASIC PROPERTIES")
    lines.append("-" * 78)
    lines.append(f"{'Filename':<20} | {'Dimensions (WxH)':<16} | {'Aspect Ratio':<12} | {'Channels'}")
    lines.append("-" * 78)
    for res in results:
        aspect = res["height"] / res["width"]
        dim_str = f"{res['width']}x{res['height']}"
        lines.append(f"{res['filename']:<20} | {dim_str:<16} | {aspect:<12.3f} | {res['channels']}")
    lines.append("")

    lines.append("-" * 78)
    lines.append("2. BRIGHTNESS GRADIENT (FIRST DERIVATIVE dI/dy) EXTREMES")
    lines.append("-" * 78)
    lines.append(f"{'Filename':<20} | {'Max Pos dI/dy':<14} | {'at y (y/H)':<15} | {'Max Neg dI/dy':<14} | {'at y (y/H)':<15}")
    lines.append("-" * 78)
    for res in results:
        h = res["height"]
        pos_loc = f"y={res['top_pos_idx']:4d} ({res['top_pos_idx']/h:.3f})"
        neg_loc = f"y={res['top_neg_idx']:4d} ({res['top_neg_idx']/h:.3f})"
        lines.append(f"{res['filename']:<20} | {res['top_pos_val']:+14.2f} | {pos_loc:<15} | {res['top_neg_val']:+14.2f} | {neg_loc:<15}")
    lines.append("")

    lines.append("-" * 78)
    lines.append("3. TOP GRADIENT PEAKS PER IMAGE (Top 3 Positive & Negative)")
    lines.append("-" * 78)
    for res in results:
        h = res["height"]
        lines.append(f"Image: {res['filename']} (H={h})")
        pos_str = ", ".join([f"y={idx} ({idx/h:.3f}): {val:+.2f}" for idx, val in res["pos_top3"]])
        neg_str = ", ".join([f"y={idx} ({idx/h:.3f}): {val:+.2f}" for idx, val in res["neg_top3"]])
        lines.append(f"  Top Positive Peaks: {pos_str}")
        lines.append(f"  Top Negative Peaks: {neg_str}")
    lines.append("")

    lines.append("-" * 78)
    lines.append("4. HSV SATURATION PROFILE EXTREMES")
    lines.append("-" * 78)
    lines.append(f"{'Filename':<20} | {'Sat Min':<9} | {'at y (y/H)':<15} | {'Sat Max':<9} | {'at y (y/H)':<15} | {'Mean Sat'}")
    lines.append("-" * 78)
    for res in results:
        h = res["height"]
        min_loc = f"y={res['sat_min_idx']:4d} ({res['sat_min_idx']/h:.3f})"
        max_loc = f"y={res['sat_max_idx']:4d} ({res['sat_max_idx']/h:.3f})"
        mean_sat = float(np.mean(res["sat_mean"]))
        lines.append(f"{res['filename']:<20} | {res['sat_min_val']:9.2f} | {min_loc:<15} | {res['sat_max_val']:9.2f} | {max_loc:<15} | {mean_sat:8.2f}")
    lines.append("")

    lines.append("-" * 78)
    lines.append("5. VERTICAL EDGE DENSITY EXTREMES (Canny edges %)")
    lines.append("-" * 78)
    lines.append(f"{'Filename':<20} | {'Edge Min %':<11} | {'at y (y/H)':<15} | {'Edge Max %':<11} | {'at y (y/H)':<15}")
    lines.append("-" * 78)
    for res in results:
        h = res["height"]
        min_loc = f"y={res['edge_min_idx']:4d} ({res['edge_min_idx']/h:.3f})"
        max_loc = f"y={res['edge_max_idx']:4d} ({res['edge_max_idx']/h:.3f})"
        lines.append(f"{res['filename']:<20} | {res['edge_min_val']*100:11.2f}% | {min_loc:<15} | {res['edge_max_val']*100:11.2f}% | {max_loc:<15}")
    lines.append("")

    lines.append("-" * 78)
    lines.append("6. ROW-WISE LOCAL VARIANCE EXTREMES")
    lines.append("-" * 78)
    lines.append(f"{'Filename':<20} | {'Var Min':<10} | {'at y (y/H)':<15} | {'Var Max':<10} | {'at y (y/H)':<15} | {'Mean Var'}")
    lines.append("-" * 78)
    for res in results:
        h = res["height"]
        min_loc = f"y={res['var_min_idx']:4d} ({res['var_min_idx']/h:.3f})"
        max_loc = f"y={res['var_max_idx']:4d} ({res['var_max_idx']/h:.3f})"
        mean_var = float(np.mean(res["variance"]))
        lines.append(f"{res['filename']:<20} | {res['var_min_val']:10.1f} | {min_loc:<15} | {res['var_max_val']:10.1f} | {max_loc:<15} | {mean_var:8.1f}")
    lines.append("")

    lines.append("=" * 78)
    lines.append("END OF VALIDATION REPORT")
    lines.append("=" * 78)

    return "\n".join(lines)


def main():
    print("=" * 75)
    print("AI-EVAL Phase 2: Multi-Image Boundary Signal Validation")
    print("Script: phase2/06_multi_image_boundary_validation.py")
    print("=" * 75)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = []
    for fname in IMAGE_FILES:
        fpath = os.path.join(IMAGES_DIR, fname)
        print(f"\nProcessing: {fpath} ...")
        res = analyze_single_image(fpath)
        results.append(res)
        print(f"  Dimensions : {res['width']} x {res['height']}")
        print(f"  Max +dI/dy : {res['top_pos_val']:+.2f} at row y={res['top_pos_idx']} (y/H={res['top_pos_idx']/res['height']:.3f})")
        print(f"  Max -dI/dy : {res['top_neg_val']:+.2f} at row y={res['top_neg_idx']} (y/H={res['top_neg_idx']/res['height']:.3f})")
        print(f"  Sat range  : {res['sat_min_val']:.2f} to {res['sat_max_val']:.2f} (mean={np.mean(res['sat_mean']):.2f})")
        print(f"  Edge %     : {res['edge_min_val']*100:.2f}% to {res['edge_max_val']*100:.2f}%")
        print(f"  Variance   : {res['var_min_val']:.1f} to {res['var_max_val']:.1f}")

    # Generate text report
    print("\n" + "-" * 75)
    print(f"Generating validation report: {REPORT_TXT}")
    report_text = build_text_report(results)
    with open(REPORT_TXT, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"Saved: {REPORT_TXT}")

    # Generate comparison plot
    print(f"Generating comparison visualization: {COMPARISON_PNG}")
    generate_comparison_plot(results, COMPARISON_PNG)
    print(f"Saved: {COMPARISON_PNG}")

    print("\n" + "=" * 75)
    print("Multi-image validation complete.")
    print("=" * 75)


if __name__ == "__main__":
    main()
