import cv2
import numpy as np
import os
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# Use the non-interactive Agg backend so matplotlib does not
# try to open a display window. We only want to save files.
matplotlib.use("Agg")


# ============================================================
# PHASE 2 -- PAGE REGION INVESTIGATION
# ============================================================
#
# PURPOSE:
#   Estimate whether the usable page region can be found even
#   when four visible page corners are absent.
#
#   We use sliding-window analysis rather than contour/line
#   detection. A sliding window divides the image into small
#   overlapping strips and measures a signal in each strip.
#   Sudden changes in the signal reveal structural transitions.
#
# WHAT WE INVESTIGATE:
#   1. Horizontal intensity profile   (left-to-right brightness)
#   2. Vertical intensity profile     (top-to-bottom brightness)
#   3. Horizontal edge-density profile
#   4. Vertical edge-density profile
#   5. Local variance / texture heatmap
#   6. Combined page-region evidence summary
#
# IMPORTANT CONSTRAINTS:
#   - Do NOT assume A4 or any fixed paper size.
#   - Do NOT declare a boundary or crop the image.
#   - Do NOT hard-code thresholds.
#   - This is an investigation tool only.
# ============================================================


# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------

IMAGE_PATH  = "images/answer_sheet.jpg"
OUTPUT_DIR  = "phase2/output"
WINDOW_SIZE = 32   # width/height of each sliding window (pixels)
STEP_SIZE   = 8    # how far the window moves each step (pixels)

# WINDOW_SIZE and STEP_SIZE are not calibrated thresholds --
# they are diagnostic resolution controls.
# Smaller values = more granular profile but noisier.
# Larger values  = smoother profile but coarser transitions.


# ============================================================
# HELPER: create output directory
# ============================================================

def ensure_output_dir(path):
    """Create directory if it does not exist."""
    os.makedirs(path, exist_ok=True)
    print(f"Output directory ready: {path}")


# ============================================================
# HELPER: save a matplotlib figure and close it
# ============================================================

def save_figure(fig, filename):
    """
    Save a matplotlib Figure to disk and close it.

    Closing is important: matplotlib accumulates open figures
    in memory. If we never close them the script leaks memory.
    """
    filepath = os.path.join(OUTPUT_DIR, filename)
    fig.savefig(filepath, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {filepath}")
    return filepath


# ============================================================
# HELPER: save an OpenCV image
# ============================================================

def save_cv_image(cv_image, filename):
    """Save an OpenCV (NumPy) image to the output directory."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    cv2.imwrite(filepath, cv_image)
    print(f"  Saved: {filepath}")
    return filepath


# ============================================================
# STEP 1: Load image and build processing pipeline
# ============================================================

def load_and_prepare(image_path):
    """
    Load the original image and produce grayscale, blurred,
    and Canny-edge versions.

    We prepare all derived images here so every analysis
    function can operate on the same consistent data.

    Returns a dict with keys:
        original, gray, blurred, edges
    """

    image = cv2.imread(image_path)

    if image is None:
        raise FileNotFoundError(
            f"Cannot load image: {image_path}"
        )

    # Convert BGR -> grayscale.
    # Grayscale reduces 3 channels to 1, making intensity
    # analysis straightforward.
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Gaussian blur to reduce high-frequency noise before
    # Canny edge detection.
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Canny edges. We use the same thresholds as the
    # earlier investigation scripts for consistency.
    edges = cv2.Canny(blurred, threshold1=50, threshold2=150)

    h, w = image.shape[:2]

    print(f"\nImage loaded: {image_path}")
    print(f"  Size : {w} x {h} pixels (width x height)")
    print(f"  Shape: {image.shape}")

    return {
        "original": image,
        "gray"    : gray,
        "blurred" : blurred,
        "edges"   : edges,
        "width"   : w,
        "height"  : h,
    }


# ============================================================
# STEP 2: Horizontal intensity profile
# ============================================================

def horizontal_intensity_profile(data, window_size, step_size):
    """
    Measure mean brightness in each vertical strip of the image.

    We slide a window from left to right across the image width.
    For each window position we compute the mean pixel value of
    the grayscale strip at that column range.

    WHY: A page lying on a dark background will show a sharp
    brightness rise at the left page edge and a sharp drop at
    the right page edge. Even without explicit corners, this
    step change tells us where the page content starts/ends
    horizontally.

    If brightness is uniformly high all the way to the edges
    the page likely fills the full width (no visible margin).

    Returns:
        positions : list of x-coordinates (window centers)
        means     : list of mean intensity values
    """

    gray   = data["gray"]
    width  = data["width"]
    height = data["height"]

    positions = []
    means     = []
    stds      = []

    x = 0
    while x + window_size <= width:

        # Extract the vertical strip at column range [x, x+window_size)
        # All rows are included (:) -- we want the full-height strip.
        strip = gray[:, x : x + window_size]

        mean_val = float(np.mean(strip))
        std_val  = float(np.std(strip))

        # Window center is a more natural x coordinate than the left edge
        center_x = x + window_size // 2

        positions.append(center_x)
        means.append(mean_val)
        stds.append(std_val)

        x += step_size

    # ----------------------------------------------------------
    # Visualisation: intensity profile + std band
    # ----------------------------------------------------------

    fig, axes = plt.subplots(2, 1, figsize=(12, 7))
    fig.suptitle(
        "Horizontal Intensity Profile\n"
        "(left-to-right brightness and texture variation)",
        fontsize=13
    )

    # Top subplot: mean intensity with +/-1 std band
    ax = axes[0]
    means_arr = np.array(means)
    stds_arr  = np.array(stds)

    ax.plot(positions, means_arr, color="steelblue", linewidth=1.5,
            label="Mean intensity")
    ax.fill_between(positions,
                    means_arr - stds_arr,
                    means_arr + stds_arr,
                    alpha=0.25, color="steelblue", label="+/-1 std")
    ax.set_xlim(0, width)
    ax.set_ylim(0, 270)
    ax.set_xlabel("Column position (pixels)")
    ax.set_ylabel("Mean pixel value (0=black, 255=white)")
    ax.set_title("Mean brightness per vertical strip")
    ax.axhline(y=np.mean(means_arr), color="orange", linestyle="--",
               linewidth=1, label=f"Overall mean={np.mean(means_arr):.1f}")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # Annotate min and max brightness column
    min_idx = int(np.argmin(means_arr))
    max_idx = int(np.argmax(means_arr))
    ax.axvline(x=positions[min_idx], color="red", linestyle=":",
               linewidth=1, label=f"Darkest x={positions[min_idx]}")
    ax.axvline(x=positions[max_idx], color="green", linestyle=":",
               linewidth=1, label=f"Brightest x={positions[max_idx]}")
    ax.legend(fontsize=9)

    # Bottom subplot: standard deviation profile
    # High std = textured/content-rich region (text, lines)
    # Low std  = uniform region (background or blank paper)
    ax2 = axes[1]
    ax2.plot(positions, stds_arr, color="darkorange", linewidth=1.5)
    ax2.fill_between(positions, 0, stds_arr, alpha=0.2, color="darkorange")
    ax2.set_xlim(0, width)
    ax2.set_xlabel("Column position (pixels)")
    ax2.set_ylabel("Std deviation (texture level)")
    ax2.set_title(
        "Texture variation per vertical strip\n"
        "(high = content-rich, low = uniform background)"
    )
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    save_figure(fig, "09_horizontal_intensity_profile.png")

    # Print key statistics
    print(f"\n  Horizontal intensity profile:")
    print(f"    Window size   : {window_size} px,  Step : {step_size} px")
    print(f"    Windows total : {len(positions)}")
    print(f"    Overall range : {min(means):.1f} – {max(means):.1f}")
    print(f"    Darkest strip : x={positions[min_idx]}  "
          f"mean={means[min_idx]:.1f}")
    print(f"    Brightest strip: x={positions[max_idx]}  "
          f"mean={means[max_idx]:.1f}")
    print(f"    Max brightness drop (left->right): "
          f"{max(means) - min(means):.1f}")

    return {
        "positions"     : positions,
        "means"         : means,
        "stds"          : stds,
        "min_mean"      : min(means),
        "max_mean"      : max(means),
        "range"         : max(means) - min(means),
        "darkest_x"     : positions[min_idx],
        "brightest_x"   : positions[max_idx],
    }


# ============================================================
# STEP 3: Vertical intensity profile
# ============================================================

def vertical_intensity_profile(data, window_size, step_size):
    """
    Measure mean brightness in each horizontal strip of the image.

    We slide a window from top to bottom across the image height.
    For each window position we compute the mean pixel value of
    the full-width horizontal strip.

    WHY: A page on a desk will show a brightness transition
    at the top/bottom edges. Additionally, the header region
    of an answer sheet often has dense printed lines that
    create a distinctive high-texture zone near the top.

    Returns:
        positions : list of y-coordinates (window centers)
        means     : list of mean intensity values
    """

    gray   = data["gray"]
    width  = data["width"]
    height = data["height"]

    positions = []
    means     = []
    stds      = []

    y = 0
    while y + window_size <= height:

        # Extract the horizontal strip at row range [y, y+window_size)
        # All columns are included (:) for the full-width strip.
        strip = gray[y : y + window_size, :]

        mean_val = float(np.mean(strip))
        std_val  = float(np.std(strip))

        center_y = y + window_size // 2

        positions.append(center_y)
        means.append(mean_val)
        stds.append(std_val)

        y += step_size

    # ----------------------------------------------------------
    # Visualisation
    # ----------------------------------------------------------

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(
        "Vertical Intensity Profile\n"
        "(top-to-bottom brightness and texture variation)",
        fontsize=13
    )

    means_arr = np.array(means)
    stds_arr  = np.array(stds)

    min_idx = int(np.argmin(means_arr))
    max_idx = int(np.argmax(means_arr))

    # Left subplot: horizontal bar chart shows top->bottom brightness
    # We plot row index on Y-axis so it matches image orientation.
    ax = axes[0]
    ax.barh(positions, means_arr, height=step_size * 0.8,
            color="steelblue", alpha=0.7)
    ax.set_xlabel("Mean pixel value (0=black, 255=white)")
    ax.set_ylabel("Row position (pixels, top=0)")
    ax.set_title("Mean brightness per horizontal strip")
    ax.set_xlim(0, 270)
    ax.invert_yaxis()   # top of chart = top of image
    ax.axvline(x=np.mean(means_arr), color="orange", linestyle="--",
               linewidth=1.5, label=f"Mean={np.mean(means_arr):.1f}")
    ax.axhline(y=positions[min_idx], color="red", linestyle=":",
               linewidth=1, label=f"Darkest row y={positions[min_idx]}")
    ax.axhline(y=positions[max_idx], color="green", linestyle=":",
               linewidth=1, label=f"Brightest row y={positions[max_idx]}")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="x")

    # Right subplot: std deviation profile
    ax2 = axes[1]
    ax2.barh(positions, stds_arr, height=step_size * 0.8,
             color="darkorange", alpha=0.7)
    ax2.set_xlabel("Std deviation (texture level)")
    ax2.set_ylabel("Row position (pixels, top=0)")
    ax2.set_title(
        "Texture variation per horizontal strip\n"
        "(high = content-rich or edge-heavy)"
    )
    ax2.invert_yaxis()
    ax2.grid(True, alpha=0.3, axis="x")

    plt.tight_layout()
    save_figure(fig, "10_vertical_intensity_profile.png")

    print(f"\n  Vertical intensity profile:")
    print(f"    Window size   : {window_size} px,  Step : {step_size} px")
    print(f"    Windows total : {len(positions)}")
    print(f"    Overall range : {min(means):.1f} – {max(means):.1f}")
    print(f"    Darkest strip : y={positions[min_idx]}  "
          f"mean={means[min_idx]:.1f}")
    print(f"    Brightest strip: y={positions[max_idx]}  "
          f"mean={means[max_idx]:.1f}")
    print(f"    Max brightness drop (top->bottom): "
          f"{max(means) - min(means):.1f}")

    return {
        "positions"   : positions,
        "means"       : means,
        "stds"        : stds,
        "min_mean"    : min(means),
        "max_mean"    : max(means),
        "range"       : max(means) - min(means),
        "darkest_y"   : positions[min_idx],
        "brightest_y" : positions[max_idx],
    }


# ============================================================
# STEP 4: Horizontal edge-density profile
# ============================================================

def horizontal_edge_density_profile(data, window_size, step_size):
    """
    Measure Canny edge density in each vertical strip.

    Edge density = (edge pixels in strip) / (total pixels in strip).

    WHY: Page boundaries produce strong, consistent edges.
    A spike in edge density near the left or right side of the
    image could indicate a page edge -- but it could also be
    shadow or printed content. Comparing this profile with the
    intensity profile helps separate the two possibilities:
    - A page edge shows HIGH edge density + sharp brightness change.
    - Shadow shows brightness change but possibly lower edge density.
    - Printed content shows HIGH edge density + stable brightness.

    Returns:
        positions      : list of x-coordinates
        edge_densities : list of edge density values (0.0 – 1.0)
    """

    edges  = data["edges"]
    width  = data["width"]
    height = data["height"]

    positions      = []
    edge_densities = []

    x = 0
    while x + window_size <= width:

        strip = edges[:, x : x + window_size]

        # countNonZero counts edge pixels (value > 0 in Canny output).
        # Dividing by strip.size gives a fraction between 0 and 1.
        density = cv2.countNonZero(strip) / strip.size

        center_x = x + window_size // 2
        positions.append(center_x)
        edge_densities.append(density)

        x += step_size

    # ----------------------------------------------------------
    # Visualisation
    # ----------------------------------------------------------

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle(
        "Horizontal Edge Density Profile\n"
        "(left-to-right edge concentration)",
        fontsize=13
    )

    densities_arr = np.array(edge_densities)
    min_idx = int(np.argmin(densities_arr))
    max_idx = int(np.argmax(densities_arr))

    ax.plot(positions, densities_arr, color="crimson",
            linewidth=1.5, label="Edge density")
    ax.fill_between(positions, 0, densities_arr,
                    alpha=0.2, color="crimson")
    ax.set_xlim(0, width)
    ax.set_ylim(0, max(densities_arr) * 1.3 + 0.001)
    ax.set_xlabel("Column position (pixels)")
    ax.set_ylabel("Edge density (0=no edges, 1=all edges)")
    ax.set_title(
        "Edge density per vertical strip\n"
        "Spikes may indicate page edges, shadows, or dense content"
    )
    ax.axhline(y=float(np.mean(densities_arr)), color="orange",
               linestyle="--", linewidth=1,
               label=f"Mean density={np.mean(densities_arr):.4f}")
    ax.axvline(x=positions[max_idx], color="green", linestyle=":",
               linewidth=1.5, label=f"Highest edge x={positions[max_idx]}")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    save_figure(fig, "11_horizontal_edge_density.png")

    print(f"\n  Horizontal edge density profile:")
    print(f"    Min density : {min(edge_densities):.4f}  "
          f"at x={positions[min_idx]}")
    print(f"    Max density : {max(edge_densities):.4f}  "
          f"at x={positions[max_idx]}")
    print(f"    Mean density: {float(np.mean(densities_arr)):.4f}")
    print(f"    Density range (max-min): "
          f"{max(edge_densities) - min(edge_densities):.4f}")

    return {
        "positions"      : positions,
        "edge_densities" : edge_densities,
        "min_density"    : min(edge_densities),
        "max_density"    : max(edge_densities),
        "mean_density"   : float(np.mean(densities_arr)),
        "range"          : max(edge_densities) - min(edge_densities),
        "peak_x"         : positions[max_idx],
    }


# ============================================================
# STEP 5: Vertical edge-density profile
# ============================================================

def vertical_edge_density_profile(data, window_size, step_size):
    """
    Measure Canny edge density in each horizontal strip.

    WHY: Printed answer sheets typically have dense horizontal
    lines (ruled lines, table borders) in the answer area. A
    high vertical-strip edge density concentrated in the middle
    of the image suggests printed structure. A spike specifically
    at the top or bottom suggests a page boundary or header.

    Returns:
        positions      : list of y-coordinates
        edge_densities : list of edge density values (0.0 – 1.0)
    """

    edges  = data["edges"]
    width  = data["width"]
    height = data["height"]

    positions      = []
    edge_densities = []

    y = 0
    while y + window_size <= height:

        strip = edges[y : y + window_size, :]
        density = cv2.countNonZero(strip) / strip.size

        center_y = y + window_size // 2
        positions.append(center_y)
        edge_densities.append(density)

        y += step_size

    # ----------------------------------------------------------
    # Visualisation: horizontal bar chart (matches image orientation)
    # ----------------------------------------------------------

    fig, ax = plt.subplots(figsize=(8, 10))
    fig.suptitle(
        "Vertical Edge Density Profile\n"
        "(top-to-bottom edge concentration)",
        fontsize=13
    )

    densities_arr = np.array(edge_densities)
    min_idx = int(np.argmin(densities_arr))
    max_idx = int(np.argmax(densities_arr))

    ax.barh(positions, densities_arr, height=step_size * 0.8,
            color="crimson", alpha=0.75)
    ax.set_xlabel("Edge density (0=no edges, 1=all edges)")
    ax.set_ylabel("Row position (pixels, top=0)")
    ax.set_title(
        "Edge density per horizontal strip\n"
        "Peaks suggest dense content or structural lines"
    )
    ax.invert_yaxis()
    ax.axvline(x=float(np.mean(densities_arr)), color="orange",
               linestyle="--", linewidth=1.5,
               label=f"Mean={np.mean(densities_arr):.4f}")
    ax.axhline(y=positions[max_idx], color="green", linestyle=":",
               linewidth=1.5,
               label=f"Peak at y={positions[max_idx]}")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="x")

    plt.tight_layout()
    save_figure(fig, "12_vertical_edge_density.png")

    print(f"\n  Vertical edge density profile:")
    print(f"    Min density : {min(edge_densities):.4f}  "
          f"at y={positions[min_idx]}")
    print(f"    Max density : {max(edge_densities):.4f}  "
          f"at y={positions[max_idx]}")
    print(f"    Mean density: {float(np.mean(densities_arr)):.4f}")
    print(f"    Density range (max-min): "
          f"{max(edge_densities) - min(edge_densities):.4f}")

    return {
        "positions"      : positions,
        "edge_densities" : edge_densities,
        "min_density"    : min(edge_densities),
        "max_density"    : max(edge_densities),
        "mean_density"   : float(np.mean(densities_arr)),
        "range"          : max(edge_densities) - min(edge_densities),
        "peak_y"         : positions[max_idx],
    }


# ============================================================
# STEP 6: Local variance heatmap
# ============================================================

def local_variance_heatmap(data, window_size, step_size):
    """
    Calculate local standard deviation in a grid of windows
    and visualise the result as a heatmap overlaid on the image.

    WHY: Local variance (measured as std dev) reveals texture.
    - High variance areas: text, printed lines, complex patterns.
    - Low variance areas:  blank paper or smooth background.
    This helps distinguish content regions from non-content
    regions without requiring visible page edges.

    We build a 2D grid of variance values and display it as a
    colour-mapped heatmap. Blending it with the original image
    makes it easy to see which spatial regions are content-rich.

    Returns:
        variance_map   : 2D NumPy array of std values (full size)
        grid_stds      : 2D list of per-window std values
        grid_rows      : number of rows in the variance grid
        grid_cols      : number of cols in the variance grid
    """

    gray   = data["gray"]
    width  = data["width"]
    height = data["height"]

    # Build a list of (row_center, col_center, std_value) triples.
    # We will later assemble these into a 2D array for the heatmap.

    row_centers = []
    col_centers = []
    std_values  = []

    y = 0
    while y + window_size <= height:

        row_stds = []
        row_cx   = []
        row_cy   = []

        x = 0
        while x + window_size <= width:

            patch = gray[y : y + window_size, x : x + window_size]
            std   = float(np.std(patch))

            row_stds.append(std)
            row_cx.append(x + window_size // 2)
            row_cy.append(y + window_size // 2)

            x += step_size

        col_centers.append(row_cx)
        row_centers.append(row_cy)
        std_values.append(row_stds)

        y += step_size

    std_array = np.array(std_values, dtype=np.float32)

    # Resize the small grid to the full image size so we can
    # overlay it on the original image. cv2.resize with
    # INTER_LINEAR produces smooth interpolation -- appropriate
    # for a heatmap display.
    variance_map = cv2.resize(
        std_array,
        (width, height),
        interpolation=cv2.INTER_LINEAR
    )

    # Normalise to 0–255 for display
    variance_map_norm = cv2.normalize(
        variance_map, None, 0, 255, cv2.NORM_MINMAX
    ).astype(np.uint8)

    # Apply a colour map. COLORMAP_JET: blue=low variance, red=high.
    heatmap_coloured = cv2.applyColorMap(
        variance_map_norm, cv2.COLORMAP_JET
    )

    # Blend heatmap with the original image so content is visible.
    # alpha=0.55 means 55% heatmap, 45% original.
    blended = cv2.addWeighted(
        heatmap_coloured, 0.55,
        data["original"], 0.45,
        0
    )

    save_cv_image(blended, "13_local_variance_heatmap.png")

    # ----------------------------------------------------------
    # Additional matplotlib version: side-by-side comparison
    # ----------------------------------------------------------

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(
        "Local Variance (Standard Deviation) Heatmap\n"
        "Blue = low texture (uniform), Red = high texture (content-rich)",
        fontsize=12
    )

    # Left: raw std-dev grid as heatmap
    ax = axes[0]
    im = ax.imshow(std_array, cmap="jet", aspect="auto",
                   extent=[0, width, height, 0])
    ax.set_title("Variance grid (window-level resolution)")
    ax.set_xlabel("Image width (pixels)")
    ax.set_ylabel("Image height (pixels, top=0)")
    plt.colorbar(im, ax=ax, label="Std deviation")

    # Right: original image for reference
    ax2 = axes[1]
    rgb = cv2.cvtColor(data["original"], cv2.COLOR_BGR2RGB)
    ax2.imshow(rgb)
    ax2.set_title("Original image (reference)")
    ax2.set_xlabel("Image width (pixels)")
    ax2.set_ylabel("Image height (pixels, top=0)")
    ax2.axis("off")

    plt.tight_layout()
    save_figure(fig, "13b_local_variance_grid.png")

    grid_rows = std_array.shape[0]
    grid_cols = std_array.shape[1]
    global_mean_std = float(np.mean(std_array))
    global_max_std  = float(np.max(std_array))

    print(f"\n  Local variance heatmap:")
    print(f"    Grid size : {grid_rows} rows x {grid_cols} cols")
    print(f"    Mean std  : {global_mean_std:.2f}")
    print(f"    Max std   : {global_max_std:.2f}")

    # Find which row and column has highest variance
    peak_row, peak_col = np.unravel_index(
        np.argmax(std_array), std_array.shape
    )
    # Convert back to approximate pixel coordinates
    peak_y_px = peak_row * step_size + window_size // 2
    peak_x_px = peak_col * step_size + window_size // 2
    print(f"    Highest-variance window: "
          f"approx x={peak_x_px}, y={peak_y_px}  "
          f"std={global_max_std:.2f}")

    return {
        "variance_map"    : variance_map,
        "std_array"       : std_array,
        "grid_rows"       : grid_rows,
        "grid_cols"       : grid_cols,
        "global_mean_std" : global_mean_std,
        "global_max_std"  : global_max_std,
        "peak_x_px"       : peak_x_px,
        "peak_y_px"       : peak_y_px,
    }


# ============================================================
# STEP 7: Combined page-region evidence image
# ============================================================

def combined_evidence_image(data, h_intensity, v_intensity,
                             h_edge, v_edge):
    """
    Draw a composite diagnostic image that overlays:
    - Vertical indicator lines for horizontal intensity transitions
    - Horizontal indicator lines for vertical intensity transitions
    - Edge-density peaks as coloured bands

    WHY: All individual profiles are meaningful in isolation, but
    page-region estimation depends on convergence of signals.
    If the intensity transition AND the edge-density spike align
    at the same column/row, that is stronger evidence of a real
    structural boundary than either signal alone.

    The combined image lets us check spatial alignment visually.
    """

    img = np.copy(data["original"])
    height, width = img.shape[:2]

    # ----------------------------------------------------------
    # Mark horizontal intensity transition candidates.
    # We compute the gradient (difference between adjacent means)
    # of the horizontal intensity profile. Large gradients suggest
    # brightness transitions worth investigating.
    # ----------------------------------------------------------

    h_means   = np.array(h_intensity["means"])
    h_pos     = h_intensity["positions"]
    h_grad    = np.abs(np.diff(h_means))

    # Keep only the top-3 gradient positions as transition candidates
    top_h_idx = np.argsort(h_grad)[-3:][::-1]

    for rank, idx in enumerate(top_h_idx):
        x_pos = h_pos[idx]
        # Yellow line = strongest horizontal transition candidate
        colour = (0, 255, 255) if rank == 0 else (0, 200, 200)
        cv2.line(img, (x_pos, 0), (x_pos, height - 1), colour, 2)
        cv2.putText(img, f"H{rank+1}", (x_pos + 3, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)

    # ----------------------------------------------------------
    # Mark vertical intensity transition candidates.
    # Same logic applied top-to-bottom.
    # ----------------------------------------------------------

    v_means = np.array(v_intensity["means"])
    v_pos   = v_intensity["positions"]
    v_grad  = np.abs(np.diff(v_means))

    top_v_idx = np.argsort(v_grad)[-3:][::-1]

    for rank, idx in enumerate(top_v_idx):
        y_pos = v_pos[idx]
        colour = (255, 0, 255) if rank == 0 else (200, 0, 200)
        cv2.line(img, (0, y_pos), (width - 1, y_pos), colour, 2)
        cv2.putText(img, f"V{rank+1}", (5, y_pos - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)

    # ----------------------------------------------------------
    # Mark horizontal edge-density peak (green vertical line)
    # ----------------------------------------------------------

    peak_x = h_edge["peak_x"]
    cv2.line(img, (peak_x, 0), (peak_x, height - 1), (0, 255, 0), 2)
    cv2.putText(img, "EdgePeakH", (peak_x + 3, height - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

    # ----------------------------------------------------------
    # Mark vertical edge-density peak (blue horizontal line)
    # ----------------------------------------------------------

    peak_y = v_edge["peak_y"]
    cv2.line(img, (0, peak_y), (width - 1, peak_y), (255, 100, 0), 2)
    cv2.putText(img, "EdgePeakV", (5, peak_y - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 100, 0), 2)

    # ----------------------------------------------------------
    # Legend
    # ----------------------------------------------------------

    legend_items = [
        ((0, 255, 255),  "H1/H2/H3 = horizontal intensity transitions"),
        ((255, 0, 255),  "V1/V2/V3 = vertical intensity transitions"),
        ((0, 255, 0),    "EdgePeakH = horizontal edge-density peak"),
        ((255, 100, 0),  "EdgePeakV = vertical edge-density peak"),
    ]

    for i, (colour, text) in enumerate(legend_items):
        y_text = 20 + i * 22
        cv2.rectangle(img, (width - 400, y_text - 14),
                      (width - 385, y_text), colour, -1)
        cv2.putText(img, text, (width - 380, y_text),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, colour, 1)

    save_cv_image(img, "14_page_region_evidence.png")

    return img


# ============================================================
# STEP 8: Final summary
# ============================================================

def print_summary(data, h_intensity, v_intensity,
                  h_edge, v_edge, variance):
    """
    Print a structured numerical summary and qualitative
    interpretation hints.

    These are observations, NOT final decisions.
    """

    width  = data["width"]
    height = data["height"]

    # ----------------------------------------------------------
    # Interpret horizontal intensity
    # ----------------------------------------------------------

    h_range = h_intensity["range"]
    h_darkest_x   = h_intensity["darkest_x"]
    h_brightest_x = h_intensity["brightest_x"]

    # Relative position of the dark/bright extremes
    dark_x_frac   = h_darkest_x   / width
    bright_x_frac = h_brightest_x / width

    # Is the darkest column close to either edge? (within 20%)
    dark_near_edge = dark_x_frac < 0.20 or dark_x_frac > 0.80

    # ----------------------------------------------------------
    # Interpret vertical intensity
    # ----------------------------------------------------------

    v_range = v_intensity["range"]
    v_darkest_y   = v_intensity["darkest_y"]
    v_brightest_y = v_intensity["brightest_y"]

    dark_y_frac   = v_darkest_y   / height
    bright_y_frac = v_brightest_y / height

    dark_near_top_bottom = (
        dark_y_frac < 0.20 or dark_y_frac > 0.80
    )

    # ----------------------------------------------------------
    # Overall edge density context
    # ----------------------------------------------------------

    edges = data["edges"]
    overall_edge_density = (
        cv2.countNonZero(edges) / edges.size
    )

    h_edge_range = h_edge["range"]
    v_edge_range = v_edge["range"]

    print()
    print("=" * 65)
    print("PHASE 2 PAGE REGION INVESTIGATION SUMMARY")
    print("=" * 65)

    print(f"\nImage: {width} x {height} px  "
          f"(overall edge density: {overall_edge_density:.4f})")

    # ----------------------------------------------------------
    # Horizontal intensity
    # ----------------------------------------------------------

    print()
    print("Horizontal intensity (left -> right):")
    print(f"  Brightness range across columns : {h_range:.1f}")
    print(f"  Darkest column  : x={h_darkest_x}  "
          f"({dark_x_frac*100:.0f}% from left)  "
          f"mean={h_intensity['min_mean']:.1f}")
    print(f"  Brightest column: x={h_brightest_x}  "
          f"({bright_x_frac*100:.0f}% from left)  "
          f"mean={h_intensity['max_mean']:.1f}")

    if h_range > 60:
        print("  OBSERVATION: Strong brightness variation left->right.")
        if dark_near_edge:
            print("    Darkest strip is near an image edge -- possible "
                  "background visible on one side.")
        else:
            print("    Darkest strip is in the interior -- may be "
                  "shadow or a printed dark region.")
    elif h_range > 20:
        print("  OBSERVATION: Moderate brightness variation left->right.")
        print("    Could be shadow gradient rather than a page edge.")
    else:
        print("  OBSERVATION: Brightness is relatively uniform left->right.")
        print("    Page likely fills the full width, or lighting is even.")

    # ----------------------------------------------------------
    # Vertical intensity
    # ----------------------------------------------------------

    print()
    print("Vertical intensity (top -> bottom):")
    print(f"  Brightness range across rows : {v_range:.1f}")
    print(f"  Darkest row  : y={v_darkest_y}  "
          f"({dark_y_frac*100:.0f}% from top)  "
          f"mean={v_intensity['min_mean']:.1f}")
    print(f"  Brightest row: y={v_brightest_y}  "
          f"({bright_y_frac*100:.0f}% from top)  "
          f"mean={v_intensity['max_mean']:.1f}")

    if v_range > 60:
        print("  OBSERVATION: Strong brightness variation top->bottom.")
        if dark_near_top_bottom:
            print("    Darkest strip is near the top or bottom -- possible "
                  "page edge or margin visible.")
        else:
            print("    Darkest strip is in the middle rows -- likely a "
                  "shadow or dark printed zone.")
    elif v_range > 20:
        print("  OBSERVATION: Moderate brightness variation top->bottom.")
    else:
        print("  OBSERVATION: Brightness relatively uniform top->bottom.")
        print("    Page likely fills the full height.")

    # ----------------------------------------------------------
    # Horizontal edge density
    # ----------------------------------------------------------

    print()
    print("Horizontal edge density (left -> right):")
    print(f"  Mean edge density : {h_edge['mean_density']:.4f}")
    print(f"  Min / Max density : "
          f"{h_edge['min_density']:.4f} / {h_edge['max_density']:.4f}")
    print(f"  Density range     : {h_edge_range:.4f}")
    print(f"  Peak edge column  : x={h_edge['peak_x']}")

    if h_edge_range > 0.05:
        print("  OBSERVATION: Edge density varies noticeably left->right.")
        print("    Some columns are structurally richer than others.")
    else:
        print("  OBSERVATION: Edge density is relatively uniform "
              "left->right.")
        print("    No strong horizontal structural boundary signal.")

    # ----------------------------------------------------------
    # Vertical edge density
    # ----------------------------------------------------------

    print()
    print("Vertical edge density (top -> bottom):")
    print(f"  Mean edge density : {v_edge['mean_density']:.4f}")
    print(f"  Min / Max density : "
          f"{v_edge['min_density']:.4f} / {v_edge['max_density']:.4f}")
    print(f"  Density range     : {v_edge_range:.4f}")
    print(f"  Peak edge row     : y={v_edge['peak_y']}")

    if v_edge_range > 0.05:
        print("  OBSERVATION: Edge density varies noticeably top->bottom.")
        print("    Some rows contain much more structural content.")
    else:
        print("  OBSERVATION: Edge density is relatively uniform "
              "top->bottom.")

    # ----------------------------------------------------------
    # Local variance
    # ----------------------------------------------------------

    print()
    print("Local variance (texture):")
    print(f"  Mean local std : {variance['global_mean_std']:.2f}")
    print(f"  Max local std  : {variance['global_max_std']:.2f}")
    print(f"  Peak-variance location: "
          f"x={variance['peak_x_px']}, y={variance['peak_y_px']}")

    if variance["global_mean_std"] > 40:
        print("  OBSERVATION: Image is texture-rich overall.")
        print("    Consistent with a page full of printed content.")
    elif variance["global_mean_std"] > 20:
        print("  OBSERVATION: Moderate texture -- mix of content "
              "and uniform regions.")
    else:
        print("  OBSERVATION: Low texture -- image may be mostly "
              "uniform background with little content.")

    # ----------------------------------------------------------
    # Page-region estimation feasibility
    # ----------------------------------------------------------

    print()
    print("Page-region estimation -- feasibility assessment:")

    signals_present = 0

    if h_range > 30:
        print("  [+] Horizontal brightness variation present "
              "(useful signal)")
        signals_present += 1
    else:
        print("  [-] Horizontal brightness variation low "
              "(weak horizontal signal)")

    if v_range > 30:
        print("  [+] Vertical brightness variation present "
              "(useful signal)")
        signals_present += 1
    else:
        print("  [-] Vertical brightness variation low "
              "(weak vertical signal)")

    if h_edge_range > 0.03:
        print("  [+] Horizontal edge-density variation present")
        signals_present += 1
    else:
        print("  [-] Horizontal edge-density variation low")

    if v_edge_range > 0.03:
        print("  [+] Vertical edge-density variation present")
        signals_present += 1
    else:
        print("  [-] Vertical edge-density variation low")

    print()
    print(f"  Signals with useful variation: {signals_present} / 4")

    if signals_present >= 3:
        print("  CONCLUSION: Multiple consistent signals available.")
        print("  Page-region estimation from sliding-window analysis")
        print("  appears PROMISING for this image.")
    elif signals_present >= 2:
        print("  CONCLUSION: Some useful signals present.")
        print("  Estimation may be possible but will need care.")
    else:
        print("  CONCLUSION: Few strong signals found.")
        print("  The page likely fills the frame -- boundary may not "
              "be estimable from this image without additional context.")

    # ----------------------------------------------------------
    # Limitations
    # ----------------------------------------------------------

    print()
    print("Known limitations of this investigation:")
    print("  1. Sliding-window analysis cannot distinguish a "
          "page edge from a shadow edge without additional context.")
    print("  2. Intensity and edge signals can both be caused by "
          "printed content, not just physical page boundaries.")
    print("  3. The current script uses a single image -- no "
          "multi-image calibration has been done.")
    print("  4. No perspective correction has been applied -- "
          "a tilted page would distort all profiles.")
    print("  5. Window size and step are fixed parameters -- "
          "they affect profile resolution but are not thresholds.")

    print()
    print("=" * 65)
    print("END OF PHASE 2 PAGE REGION INVESTIGATION")
    print("=" * 65)


# ============================================================
# MAIN PROGRAM
# ============================================================

if __name__ == "__main__":

    ensure_output_dir(OUTPUT_DIR)

    print("\n" + "=" * 65)
    print("PHASE 2 -- PAGE REGION INVESTIGATION")
    print("=" * 65)

    # --------------------------------------------------------
    # Load and prepare images
    # --------------------------------------------------------

    data = load_and_prepare(IMAGE_PATH)

    # Save the canonical copies to output so outputs 09-14
    # are self-contained (viewer does not need the original).
    save_cv_image(data["original"], "09a_source_original.png")
    save_cv_image(data["gray"],     "09b_source_grayscale.png")

    # --------------------------------------------------------
    # Run all analysis passes
    # --------------------------------------------------------

    print("\n--- Running horizontal intensity profile ---")
    h_intensity = horizontal_intensity_profile(
        data, WINDOW_SIZE, STEP_SIZE
    )

    print("\n--- Running vertical intensity profile ---")
    v_intensity = vertical_intensity_profile(
        data, WINDOW_SIZE, STEP_SIZE
    )

    print("\n--- Running horizontal edge density profile ---")
    h_edge = horizontal_edge_density_profile(
        data, WINDOW_SIZE, STEP_SIZE
    )

    print("\n--- Running vertical edge density profile ---")
    v_edge = vertical_edge_density_profile(
        data, WINDOW_SIZE, STEP_SIZE
    )

    print("\n--- Generating local variance heatmap ---")
    variance = local_variance_heatmap(
        data, WINDOW_SIZE, STEP_SIZE
    )

    print("\n--- Generating combined evidence image ---")
    combined_evidence_image(
        data, h_intensity, v_intensity, h_edge, v_edge
    )

    # --------------------------------------------------------
    # Print final summary
    # --------------------------------------------------------

    print_summary(
        data, h_intensity, v_intensity,
        h_edge, v_edge, variance
    )
