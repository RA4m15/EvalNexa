import cv2
import numpy as np
import os
import math


# ============================================================
# PHASE 2 - PAGE BOUNDARY INVESTIGATION
# ============================================================
#
# PURPOSE:
#   This script is a visual investigation tool.
#   We are NOT building the final page detector yet.
#   We are gathering visual evidence about where the page
#   boundaries might be in the answer sheet image.
#
# OUTPUT:
#   All images are saved to phase2/output/
#
# KEY RULES:
#   - Do NOT assume A4 paper size.
#   - Do NOT assume the largest contour is the page.
#   - Do NOT hardcode thresholds from this single image.
#   - Lines detected by Hough are candidates only — they are
#     not declared as page boundaries automatically.
# ============================================================


# ------------------------------------------------------------
# STEP 0: Setup output folder
# ------------------------------------------------------------

# Create the output folder if it does not exist.
# os.makedirs with exist_ok=True means: if the folder already
# exists, do nothing; if it does not exist, create it.

output_dir = "phase2/output"
os.makedirs(output_dir, exist_ok=True)

print("Output folder ready:", output_dir)


# ------------------------------------------------------------
# STEP 1: Load the original image
# ------------------------------------------------------------

# cv2.imread loads the image from disk.
# The result is a NumPy array with shape (height, width, 3).
# The 3 channels are Blue, Green, Red (BGR) — not RGB.

image_path = "images/answer_sheet.jpg"
image = cv2.imread(image_path)

if image is None:
    print("ERROR: Could not load image.")
    print("Check path:", image_path)
    exit(1)

image_height, image_width = image.shape[:2]

print(f"\nOriginal image shape: {image.shape}")
print(f"  Width : {image_width} pixels")
print(f"  Height: {image_height} pixels")

# Save original image as Output 1
output_path = os.path.join(output_dir, "01_original.jpg")
cv2.imwrite(output_path, image)
print(f"\nSaved: {output_path}")


# ------------------------------------------------------------
# STEP 2: Convert to grayscale
# ------------------------------------------------------------

# Most OpenCV processing works on single-channel images.
# cv2.cvtColor converts the BGR image to grayscale.
# Result shape: (height, width) — one brightness value per pixel.

gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

print(f"\nGrayscale shape: {gray.shape}")

# Save grayscale image as Output 2
output_path = os.path.join(output_dir, "02_grayscale.jpg")
cv2.imwrite(output_path, gray)
print(f"Saved: {output_path}")


# ------------------------------------------------------------
# STEP 3: Gaussian blur
# ------------------------------------------------------------

# Gaussian blur reduces noise in the image.
# Without blur, Canny edge detection picks up many tiny
# imperfections that are not real structure.
#
# Parameters:
#   (5, 5)  = kernel size (both dimensions must be odd)
#   0       = standard deviation (let OpenCV compute it)

blurred = cv2.GaussianBlur(gray, (5, 5), 0)

print(f"\nBlurred shape: {blurred.shape}")

# Save blurred image as Output 3
output_path = os.path.join(output_dir, "03_blurred.jpg")
cv2.imwrite(output_path, blurred)
print(f"Saved: {output_path}")


# ------------------------------------------------------------
# STEP 4: Canny edge detection
# ------------------------------------------------------------

# Canny edge detection finds sharp transitions in brightness.
# These transitions often correspond to object boundaries.
#
# Parameters:
#   threshold1 = lower threshold for the hysteresis step
#   threshold2 = upper threshold for the hysteresis step
#
# Pixels with gradient above threshold2 are definitely edges.
# Pixels with gradient below threshold1 are definitely not edges.
# Pixels in between are edges only if connected to a strong edge.

canny_edges = cv2.Canny(blurred, threshold1=50, threshold2=150)

print(f"\nCanny edges shape: {canny_edges.shape}")

# Count how many edge pixels were detected
edge_pixel_count = cv2.countNonZero(canny_edges)
total_pixels = image_height * image_width
edge_density_overall = edge_pixel_count / total_pixels

print(f"Edge pixels detected: {edge_pixel_count}")
print(f"Total image pixels:   {total_pixels}")
print(f"Overall edge density: {edge_density_overall:.4f}")

# Save Canny edges image as Output 4
output_path = os.path.join(output_dir, "04_canny_edges.jpg")
cv2.imwrite(output_path, canny_edges)
print(f"Saved: {output_path}")


# ------------------------------------------------------------
# STEP 5: Hough line detection
# ------------------------------------------------------------

# cv2.HoughLinesP detects straight line segments in an edge image.
#
# It works by voting in a parameter space (rho, theta).
# Long, straight edges accumulate many votes and are returned.
#
# Parameters:
#   image         = the edge image (output of Canny)
#   rho           = distance resolution in pixels (1 = high res)
#   theta         = angle resolution in radians (pi/180 = 1 degree)
#   threshold     = minimum number of votes to be a line
#   minLineLength = minimum length of a line segment (in pixels)
#   maxLineGap    = maximum gap between two points of a line (pixels)
#
# NOTE: We are looking for LONG lines only.
# Short lines are likely printed table borders, not page edges.
#
# We choose minLineLength as a fraction of the image dimension
# so that we do not hardcode a pixel value from this one image.

min_line_length = int(min(image_width, image_height) * 0.3)
max_line_gap = 20
hough_threshold = 80

print("\n--- Hough Line Detection ---")
print(f"  minLineLength : {min_line_length} px")
print(f"  maxLineGap    : {max_line_gap} px")
print(f"  threshold     : {hough_threshold}")

lines = cv2.HoughLinesP(
    canny_edges,
    rho=1,
    theta=np.pi / 180,
    threshold=hough_threshold,
    minLineLength=min_line_length,
    maxLineGap=max_line_gap
)

# Create a colour copy of the original image to draw lines on.
# np.copy makes an independent copy (changes to it do not affect
# the original array).
hough_image = np.copy(image)

# Separate storage for horizontal and vertical lines.
# We will use these to build per-side evidence images later.
horizontal_lines = []
vertical_lines   = []

if lines is None:

    print("\nNo Hough lines detected with current parameters.")

else:

    print(f"\nTotal Hough lines detected: {len(lines)}")
    print("\nDetailed line list:")
    print(f"{'No.':<5} {'x1':>6} {'y1':>6} {'x2':>6} {'y2':>6} "
          f"{'Length':>8} {'Angle deg':>10} {'Type':<12}")
    print("-" * 65)

    for line_index, line in enumerate(lines):

        # HoughLinesP returns an array of shape (N, 1, 4).
        # Each element is [[x1, y1, x2, y2]].
        # We use .flatten() to safely extract the four values
        # regardless of whether the array is 1-D or 2-D.
        x1, y1, x2, y2 = line.flatten()

        # ----------------------------------------------------
        # Calculate line length using Pythagoras' theorem:
        #   length = sqrt( (x2-x1)^2 + (y2-y1)^2 )
        # ----------------------------------------------------
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx * dx + dy * dy)

        # ----------------------------------------------------
        # Calculate line angle in degrees.
        # math.atan2(dy, dx) returns angle in radians from
        # the positive x-axis. We convert to degrees.
        # abs() is used because we care about orientation,
        # not direction (so -90 and +90 are both "vertical").
        # ----------------------------------------------------
        angle_rad = math.atan2(dy, dx)
        angle_deg = math.degrees(angle_rad)

        # Normalise angle to range [0, 180)
        # so that a line going left-to-right and right-to-left
        # both appear as the same angle.
        angle_deg = abs(angle_deg)
        if angle_deg > 90:
            angle_deg = 180 - angle_deg

        # ----------------------------------------------------
        # Classify as horizontal or vertical.
        # A line close to 0 deg is horizontal.
        # A line close to 90 deg is vertical.
        # We use a tolerance of 20 deg on each side.
        # This is lenient because real paper may be slightly tilted.
        # ----------------------------------------------------
        if angle_deg <= 20:
            line_type = "HORIZONTAL"
            horizontal_lines.append((x1, y1, x2, y2, length, angle_deg))

            # Draw horizontal lines in green
            cv2.line(hough_image, (x1, y1), (x2, y2), (0, 255, 0), 2)

        elif angle_deg >= 70:
            line_type = "VERTICAL"
            vertical_lines.append((x1, y1, x2, y2, length, angle_deg))

            # Draw vertical lines in blue
            cv2.line(hough_image, (x1, y1), (x2, y2), (255, 0, 0), 2)

        else:
            line_type = "DIAGONAL"

            # Draw diagonal lines in red
            cv2.line(hough_image, (x1, y1), (x2, y2), (0, 0, 255), 2)

        print(f"{line_index:<5} {x1:>6} {y1:>6} {x2:>6} {y2:>6} "
              f"{length:>8.1f} {angle_deg:>10.1f} {line_type:<12}")

    print(f"\nSummary of detected lines:")
    print(f"  Horizontal lines : {len(horizontal_lines)}")
    print(f"  Vertical lines   : {len(vertical_lines)}")
    diagonal_count = len(lines) - len(horizontal_lines) - len(vertical_lines)
    print(f"  Diagonal lines   : {diagonal_count}")

    # Add legend text to the Hough image
    cv2.putText(hough_image, "GREEN=Horizontal", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(hough_image, "BLUE=Vertical", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
    cv2.putText(hough_image, "RED=Diagonal", (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

# Save Hough lines image as Output 5
output_path = os.path.join(output_dir, "05_hough_lines.jpg")
cv2.imwrite(output_path, hough_image)
print(f"\nSaved: {output_path}")


# ------------------------------------------------------------
# STEP 6: Horizontal line evidence image
# ------------------------------------------------------------

# We draw ONLY horizontal lines on a fresh copy of the image.
# This lets us inspect them in isolation without diagonal /
# vertical lines cluttering the view.

horizontal_image = np.copy(image)

if len(horizontal_lines) == 0:
    print("\nNo horizontal lines to draw.")
else:
    for (x1, y1, x2, y2, length, angle_deg) in horizontal_lines:
        cv2.line(horizontal_image, (x1, y1), (x2, y2), (0, 255, 0), 2)

    cv2.putText(horizontal_image,
                f"Horizontal lines: {len(horizontal_lines)}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

# Save horizontal evidence image as Output 6
output_path = os.path.join(output_dir, "06_horizontal_lines.jpg")
cv2.imwrite(output_path, horizontal_image)
print(f"Saved: {output_path}")


# ------------------------------------------------------------
# STEP 7: Vertical line evidence image
# ------------------------------------------------------------

# Same idea — draw only vertical lines on a fresh copy.

vertical_image = np.copy(image)

if len(vertical_lines) == 0:
    print("No vertical lines to draw.")
else:
    for (x1, y1, x2, y2, length, angle_deg) in vertical_lines:
        cv2.line(vertical_image, (x1, y1), (x2, y2), (255, 0, 0), 2)

    cv2.putText(vertical_image,
                f"Vertical lines: {len(vertical_lines)}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)

# Save vertical evidence image as Output 7
output_path = os.path.join(output_dir, "07_vertical_lines.jpg")
cv2.imwrite(output_path, vertical_image)
print(f"Saved: {output_path}")


# ------------------------------------------------------------
# STEP 8: Combined page-boundary evidence image
# ------------------------------------------------------------

# We overlay all lines on the image AND add coloured rectangles
# to highlight the four border strips where we measure evidence.
# This gives a single image summarising everything.

combined_image = np.copy(image)

# Draw all detected lines (horizontal=green, vertical=blue)
for (x1, y1, x2, y2, length, angle_deg) in horizontal_lines:
    cv2.line(combined_image, (x1, y1), (x2, y2), (0, 255, 0), 2)

for (x1, y1, x2, y2, length, angle_deg) in vertical_lines:
    cv2.line(combined_image, (x1, y1), (x2, y2), (255, 0, 0), 2)

# Draw the border strips as coloured outlines.
# This shows which region we used for the border evidence analysis.
border_size = 30  # pixels wide (same strip we will measure below)

# Top border strip — yellow rectangle
cv2.rectangle(combined_image,
              (0, 0),
              (image_width - 1, border_size),
              (0, 255, 255), 2)

# Bottom border strip — cyan rectangle
cv2.rectangle(combined_image,
              (0, image_height - border_size),
              (image_width - 1, image_height - 1),
              (255, 255, 0), 2)

# Left border strip — magenta rectangle
cv2.rectangle(combined_image,
              (0, 0),
              (border_size, image_height - 1),
              (255, 0, 255), 2)

# Right border strip — orange rectangle
cv2.rectangle(combined_image,
              (image_width - border_size, 0),
              (image_width - 1, image_height - 1),
              (0, 165, 255), 2)

# Save combined evidence image as Output 8
output_path = os.path.join(output_dir, "08_combined_evidence.jpg")
cv2.imwrite(output_path, combined_image)
print(f"Saved: {output_path}")


# ============================================================
# STEP 9: Border evidence analysis
# ============================================================
#
# We divide the image into four border strips (top, bottom,
# left, right) and measure edge density in each strip.
#
# Edge density = (number of edge pixels) / (total pixels in strip)
#
# A high edge density in a border strip suggests that a real
# structural line (like a page edge) may be present there.
#
# We also measure brightness mean and standard deviation because:
#   - A dark border could mean background is visible beyond the page.
#   - A bright, uniform border may suggest the page fills that edge.
#
# IMPORTANT: We are only collecting evidence here.
# We do NOT declare a side to be the page boundary.
# ============================================================

print("\n" + "=" * 60)
print("BORDER EVIDENCE ANALYSIS")
print("=" * 60)

# Use a wider strip (30px) for richer evidence measurement
border_size = 30

# ------------------------------------------------------------
# Extract the four border strips from the edge image
# ------------------------------------------------------------

# Top strip: rows 0 to border_size-1, all columns
top_edges = canny_edges[:border_size, :]

# Bottom strip: last border_size rows, all columns
bottom_edges = canny_edges[-border_size:, :]

# Left strip: all rows, columns 0 to border_size-1
left_edges = canny_edges[:, :border_size]

# Right strip: all rows, last border_size columns
right_edges = canny_edges[:, -border_size:]

# ------------------------------------------------------------
# Extract matching strips from the grayscale image
# (for brightness and std analysis)
# ------------------------------------------------------------

top_gray    = gray[:border_size, :]
bottom_gray = gray[-border_size:, :]
left_gray   = gray[:, :border_size]
right_gray  = gray[:, -border_size:]


# ------------------------------------------------------------
# Helper function: compute evidence features for a strip
# ------------------------------------------------------------

def compute_strip_evidence(edge_strip, gray_strip, strip_name):
    """
    Compute and print evidence features for one border strip.

    Parameters:
        edge_strip  : 2D NumPy array (the Canny edge strip)
        gray_strip  : 2D NumPy array (the grayscale strip)
        strip_name  : string label for printing

    Returns:
        A dictionary of measured features.
    """

    # Edge density: what fraction of pixels in this strip are edges?
    # cv2.countNonZero counts all pixels with value > 0.
    # edge_strip.size is the total number of pixels.
    edge_count   = cv2.countNonZero(edge_strip)
    total_pixels = edge_strip.size
    edge_density = edge_count / total_pixels

    # Brightness mean: average pixel brightness in the strip.
    # 0 = black, 255 = white.
    brightness_mean = float(np.mean(gray_strip))

    # Brightness std: how much variation is in the strip?
    # Low std means the strip is uniform (possibly background).
    # High std means there is structure or texture (page content).
    brightness_std = float(np.std(gray_strip))

    # Print the evidence for this strip
    print(f"\n  {strip_name} border strip "
          f"({edge_strip.shape[0]} x {edge_strip.shape[1]} px):")
    print(f"    Edge density     : {edge_density:.4f}  "
          f"({edge_count} edge pixels / {total_pixels} total)")
    print(f"    Brightness mean  : {brightness_mean:.2f}  "
          f"(0=black, 255=white)")
    print(f"    Brightness std   : {brightness_std:.2f}  "
          f"(0=uniform, higher=more varied)")

    return {
        "edge_density"    : edge_density,
        "brightness_mean" : brightness_mean,
        "brightness_std"  : brightness_std,
    }


# Compute evidence for each side
print("\nMeasuring each border strip...")

top_evidence    = compute_strip_evidence(top_edges,    top_gray,    "TOP   ")
bottom_evidence = compute_strip_evidence(bottom_edges, bottom_gray, "BOTTOM")
left_evidence   = compute_strip_evidence(left_edges,   left_gray,   "LEFT  ")
right_evidence  = compute_strip_evidence(right_edges,  right_gray,  "RIGHT ")


# ============================================================
# STEP 10: Count how many Hough lines fall near each border
# ============================================================
#
# For each detected line, we check whether it lies near the
# top / bottom / left / right edge of the image.
#
# "Near" means within a threshold distance of that image edge.
# We use 10% of the image dimension as the threshold.
#
# This is NOT a definitive boundary detection — it is just
# counting evidence: "how many long lines are near each side?"
# ============================================================

print("\n" + "=" * 60)
print("HOUGH LINE PROXIMITY TO IMAGE SIDES")
print("=" * 60)

# Threshold: a line is "near" a side if its midpoint is within
# this many pixels of that side.
proximity_threshold_h = int(image_height * 0.10)  # 10% of height
proximity_threshold_w = int(image_width  * 0.10)  # 10% of width

print(f"\n  Proximity threshold (top/bottom) : {proximity_threshold_h} px")
print(f"  Proximity threshold (left/right) : {proximity_threshold_w} px")

near_top    = 0
near_bottom = 0
near_left   = 0
near_right  = 0

all_detected_lines = []

if lines is not None:
    for line in lines:
        x1, y1, x2, y2 = line.flatten()
        all_detected_lines.append((x1, y1, x2, y2))

for (x1, y1, x2, y2) in all_detected_lines:

    # The midpoint of the line gives a representative position
    mid_y = (y1 + y2) / 2
    mid_x = (x1 + x2) / 2

    # Near top: midpoint y is within threshold of row 0
    if mid_y < proximity_threshold_h:
        near_top += 1

    # Near bottom: midpoint y is within threshold of last row
    if mid_y > (image_height - proximity_threshold_h):
        near_bottom += 1

    # Near left: midpoint x is within threshold of column 0
    if mid_x < proximity_threshold_w:
        near_left += 1

    # Near right: midpoint x is within threshold of last column
    if mid_x > (image_width - proximity_threshold_w):
        near_right += 1

print(f"\n  Lines near TOP    : {near_top}")
print(f"  Lines near BOTTOM : {near_bottom}")
print(f"  Lines near LEFT   : {near_left}")
print(f"  Lines near RIGHT  : {near_right}")


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n")
print("=" * 60)
print("PAGE BOUNDARY INVESTIGATION SUMMARY")
print("=" * 60)

print(f"\nImage size: {image_width} x {image_height} pixels")
print(f"Overall edge density: {edge_density_overall:.4f}")

if lines is not None:
    print(f"Total Hough lines detected : {len(lines)}")
    print(f"  Horizontal : {len(horizontal_lines)}")
    print(f"  Vertical   : {len(vertical_lines)}")
else:
    print("Total Hough lines detected : 0")

print()
print("Top boundary evidence:")
print(f"  Edge density     = {top_evidence['edge_density']:.4f}")
print(f"  Brightness mean  = {top_evidence['brightness_mean']:.2f}")
print(f"  Brightness std   = {top_evidence['brightness_std']:.2f}")
print(f"  Hough lines near = {near_top}")

print()
print("Bottom boundary evidence:")
print(f"  Edge density     = {bottom_evidence['edge_density']:.4f}")
print(f"  Brightness mean  = {bottom_evidence['brightness_mean']:.2f}")
print(f"  Brightness std   = {bottom_evidence['brightness_std']:.2f}")
print(f"  Hough lines near = {near_bottom}")

print()
print("Left boundary evidence:")
print(f"  Edge density     = {left_evidence['edge_density']:.4f}")
print(f"  Brightness mean  = {left_evidence['brightness_mean']:.2f}")
print(f"  Brightness std   = {left_evidence['brightness_std']:.2f}")
print(f"  Hough lines near = {near_left}")

print()
print("Right boundary evidence:")
print(f"  Edge density     = {right_evidence['edge_density']:.4f}")
print(f"  Brightness mean  = {right_evidence['brightness_mean']:.2f}")
print(f"  Brightness std   = {right_evidence['brightness_std']:.2f}")
print(f"  Hough lines near = {near_right}")

print()
print("Saved images in phase2/output/:")
print("  01_original.jpg          -> original colour image")
print("  02_grayscale.jpg         -> single channel brightness")
print("  03_blurred.jpg           -> after Gaussian blur")
print("  04_canny_edges.jpg       -> Canny edge detection result")
print("  05_hough_lines.jpg       -> all Hough lines (colour coded)")
print("  06_horizontal_lines.jpg  -> horizontal Hough lines only")
print("  07_vertical_lines.jpg    -> vertical Hough lines only")
print("  08_combined_evidence.jpg -> lines + border strip overlays")
print()
print("NOTE: No page boundary decision has been made.")
print("This is an evidence-collection step only.")
print("=" * 60)
