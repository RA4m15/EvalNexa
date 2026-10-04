import cv2


# ============================================================
# PHASE 2 - ANSWER SHEET / PAGE DETECTION
# ============================================================


def detect_page_candidates(image, edges):
    """
    Detect possible page-like contours.

    Important:
    We do NOT assume that the largest contour is the page.
    """

    contours, hierarchy = cv2.findContours(
        edges,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    print("Number of contours:", len(contours))

    # --------------------------------------------------------
    # Sort contours by area
    # --------------------------------------------------------

    contours_by_area = sorted(
        contours,
        key=cv2.contourArea,
        reverse=True
    )

    print("\nTop 5 contour areas:")

    for i, contour in enumerate(
        contours_by_area[:5]
    ):

        area = cv2.contourArea(
            contour
        )

        print(
            f"Contour {i}: {area:.1f}"
        )

    # --------------------------------------------------------
    # Find approximately four-corner contours
    # --------------------------------------------------------

    four_corner_contours = []

    for i, contour in enumerate(
        contours_by_area
    ):

        perimeter = cv2.arcLength(
            contour,
            True
        )

        epsilon = 0.02 * perimeter

        approx = cv2.approxPolyDP(
            contour,
            epsilon,
            True
        )

        if len(approx) == 4:

            area = cv2.contourArea(
                contour
            )

            four_corner_contours.append(
                (
                    i,
                    contour,
                    approx,
                    area
                )
            )

    print("\n4-corner contours:")

    for (
        i,
        contour,
        approx,
        area
    ) in four_corner_contours[:10]:

        print(
            f"Contour {i}: "
            f"Area={area:.1f}, "
            f"Corners={len(approx)}"
        )

    # --------------------------------------------------------
    # Analyse page candidates
    # --------------------------------------------------------

    page_candidates = []

    image_height, image_width = image.shape[:2]

    image_area = (
        image_height *
        image_width
    )

    for (
        i,
        contour,
        approx,
        area
    ) in four_corner_contours:

        x, y, w, h = cv2.boundingRect(
            approx
        )

        if w == 0 or h == 0:
            continue

        width_ratio = (
            w /
            image_width
        )

        height_ratio = (
            h /
            image_height
        )

        area_ratio = (
            area /
            image_area
        )

        bounding_box_area = (
            w * h
        )

        if bounding_box_area == 0:
            continue

        fill_ratio = (
            area /
            bounding_box_area
        )

        aspect_ratio = (
            w /
            h
        )

        # ----------------------------------------------------
        # Basic geometric score
        # ----------------------------------------------------

        score = 0

        if width_ratio > 0.40:
            score += 1

        if height_ratio > 0.30:
            score += 1

        if area_ratio > 0.05:
            score += 1

        if 0.2 < aspect_ratio < 5:
            score += 1

        page_candidates.append(
            (
                i,
                contour,
                approx,
                area,
                w,
                h,
                width_ratio,
                height_ratio,
                area_ratio,
                aspect_ratio,
                fill_ratio,
                score
            )
        )

    print("\nPage Candidate Scores:")

    if len(page_candidates) == 0:

        print(
            "No page-like contour found."
        )

    else:

        for candidate in page_candidates:

            (
                i,
                contour,
                approx,
                area,
                w,
                h,
                width_ratio,
                height_ratio,
                area_ratio,
                aspect_ratio,
                fill_ratio,
                score
            ) = candidate

            print(
                f"Contour {i}: "
                f"Score={score}/4, "
                f"Width={w}, "
                f"Height={h}, "
                f"Width Ratio={width_ratio:.2f}, "
                f"Height Ratio={height_ratio:.2f}, "
                f"Area Ratio={area_ratio:.3f}, "
                f"Aspect={aspect_ratio:.2f}, "
                f"Fill={fill_ratio:.3f}"
            )

    return page_candidates


# ============================================================
# PAGE CONFIDENCE ANALYSIS
# ============================================================


def calculate_page_confidence(
    page_candidates,
    gray,
    edges
):
    """
    Analyse page candidate and border features.

    No final hard threshold is applied yet.
    """

    print(
        "\nPage Confidence Analysis:"
    )

    # --------------------------------------------------------
    # 1. Filter meaningless candidates
    # --------------------------------------------------------

    meaningful_candidates = []

    for candidate in page_candidates:

        (
            i,
            contour,
            approx,
            area,
            w,
            h,
            width_ratio,
            height_ratio,
            area_ratio,
            aspect_ratio,
            fill_ratio,
            score
        ) = candidate

        # Reject very small regions
        if w < 150:
            continue

        if h < 100:
            continue

        # Reject extremely thin rectangles
        if aspect_ratio > 5:
            continue

        if aspect_ratio < 0.2:
            continue

        meaningful_candidates.append(
            candidate
        )

    # --------------------------------------------------------
    # 2. Select best meaningful candidate
    # --------------------------------------------------------

    if len(meaningful_candidates) > 0:

        best_candidate = max(
            meaningful_candidates,
            key=lambda candidate: (
                candidate[-1],
                candidate[8]
            )
        )

        (
            i,
            contour,
            approx,
            area,
            w,
            h,
            width_ratio,
            height_ratio,
            area_ratio,
            aspect_ratio,
            fill_ratio,
            score
        ) = best_candidate

        print(
            "\nBest meaningful page candidate:"
        )

        print(
            f"Contour index: {i}"
        )

        print(
            f"Candidate score: {score}/4"
        )

        print(
            f"Width: {w}"
        )

        print(
            f"Height: {h}"
        )

        print(
            f"Width ratio: {width_ratio:.3f}"
        )

        print(
            f"Height ratio: {height_ratio:.3f}"
        )

        print(
            f"Area ratio: {area_ratio:.3f}"
        )

        print(
            f"Aspect ratio: {aspect_ratio:.3f}"
        )

        print(
            f"Fill ratio: {fill_ratio:.3f}"
        )

        candidate_found = True

    else:

        print(
            "\nNo meaningful page candidate available."
        )

        best_candidate = None

        candidate_found = False

    # --------------------------------------------------------
    # 3. Border analysis
    # --------------------------------------------------------

    height, width = gray.shape

    border_size = 20

    top_border = gray[
        :border_size,
        :
    ]

    bottom_border = gray[
        -border_size:,
        :
    ]

    left_border = gray[
        :,
        :border_size
    ]

    right_border = gray[
        :,
        -border_size:
    ]

    # --------------------------------------------------------
    # 4. Border brightness
    # --------------------------------------------------------

    top_mean = top_border.mean()

    bottom_mean = bottom_border.mean()

    left_mean = left_border.mean()

    right_mean = right_border.mean()

    horizontal_difference = abs(
        top_mean -
        bottom_mean
    )

    vertical_difference = abs(
        left_mean -
        right_mean
    )

    # --------------------------------------------------------
    # 5. Border standard deviation
    # --------------------------------------------------------

    top_std = top_border.std()

    bottom_std = bottom_border.std()

    left_std = left_border.std()

    right_std = right_border.std()

    average_border_std = (
        top_std +
        bottom_std +
        left_std +
        right_std
    ) / 4

    # --------------------------------------------------------
    # 6. Border edge density
    # --------------------------------------------------------

    top_edges = edges[
        :border_size,
        :
    ]

    bottom_edges = edges[
        -border_size:,
        :
    ]

    left_edges = edges[
        :,
        :border_size
    ]

    right_edges = edges[
        :,
        -border_size:
    ]

    top_edge_density = (
        cv2.countNonZero(
            top_edges
        ) /
        top_edges.size
    )

    bottom_edge_density = (
        cv2.countNonZero(
            bottom_edges
        ) /
        bottom_edges.size
    )

    left_edge_density = (
        cv2.countNonZero(
            left_edges
        ) /
        left_edges.size
    )

    right_edge_density = (
        cv2.countNonZero(
            right_edges
        ) /
        right_edges.size
    )

    average_edge_density = (
        top_edge_density +
        bottom_edge_density +
        left_edge_density +
        right_edge_density
    ) / 4

    # --------------------------------------------------------
    # 7. Print border features
    # --------------------------------------------------------

    print(
        "\nBorder features:"
    )

    print(
        f"Horizontal brightness difference: "
        f"{horizontal_difference:.3f}"
    )

    print(
        f"Vertical brightness difference: "
        f"{vertical_difference:.3f}"
    )

    print(
        f"Average border std: "
        f"{average_border_std:.3f}"
    )

    print(
        f"Average border edge density: "
        f"{average_edge_density:.4f}"
    )

    # --------------------------------------------------------
    # 8. Return confidence features
    # --------------------------------------------------------

    confidence_features = {
        "candidate_found": candidate_found,
        "horizontal_brightness_difference":
            horizontal_difference,
        "vertical_brightness_difference":
            vertical_difference,
        "average_border_std":
            average_border_std,
        "average_edge_density":
            average_edge_density
    }

    return confidence_features


# ============================================================
# FALLBACK BORDER ANALYSIS
# ============================================================


def analyze_borders(
    gray,
    edges
):
    """
    Analyse image borders when page boundary
    is not clearly detected.
    """

    height, width = gray.shape

    border_size = 20

    top_border = gray[
        :border_size,
        :
    ]

    bottom_border = gray[
        -border_size:,
        :
    ]

    left_border = gray[
        :,
        :border_size
    ]

    right_border = gray[
        :,
        -border_size:
    ]

    # --------------------------------------------------------
    # Border means
    # --------------------------------------------------------

    top_mean = top_border.mean()

    bottom_mean = bottom_border.mean()

    left_mean = left_border.mean()

    right_mean = right_border.mean()

    print(
        "\nFallback Border Analysis:"
    )

    print(
        f"Top border mean: "
        f"{top_mean:.2f}"
    )

    print(
        f"Bottom border mean: "
        f"{bottom_mean:.2f}"
    )

    print(
        f"Left border mean: "
        f"{left_mean:.2f}"
    )

    print(
        f"Right border mean: "
        f"{right_mean:.2f}"
    )

    # --------------------------------------------------------
    # Border differences
    # --------------------------------------------------------

    horizontal_difference = abs(
        top_mean -
        bottom_mean
    )

    vertical_difference = abs(
        left_mean -
        right_mean
    )

    print(
        "\nBorder Differences:"
    )

    print(
        f"Horizontal difference: "
        f"{horizontal_difference:.2f}"
    )

    print(
        f"Vertical difference: "
        f"{vertical_difference:.2f}"
    )

    # --------------------------------------------------------
    # Border standard deviation
    # --------------------------------------------------------

    top_std = top_border.std()

    bottom_std = bottom_border.std()

    left_std = left_border.std()

    right_std = right_border.std()

    print(
        "\nBorder Standard Deviation:"
    )

    print(
        f"Top border std: "
        f"{top_std:.2f}"
    )

    print(
        f"Bottom border std: "
        f"{bottom_std:.2f}"
    )

    print(
        f"Left border std: "
        f"{left_std:.2f}"
    )

    print(
        f"Right border std: "
        f"{right_std:.2f}"
    )

    # --------------------------------------------------------
    # Border edge density
    # --------------------------------------------------------

    top_edges = edges[
        :border_size,
        :
    ]

    bottom_edges = edges[
        -border_size:,
        :
    ]

    left_edges = edges[
        :,
        :border_size
    ]

    right_edges = edges[
        :,
        -border_size:
    ]

    top_edge_density = (
        cv2.countNonZero(
            top_edges
        ) /
        top_edges.size
    )

    bottom_edge_density = (
        cv2.countNonZero(
            bottom_edges
        ) /
        bottom_edges.size
    )

    left_edge_density = (
        cv2.countNonZero(
            left_edges
        ) /
        left_edges.size
    )

    right_edge_density = (
        cv2.countNonZero(
            right_edges
        ) /
        right_edges.size
    )

    print(
        "\nBorder Edge Density:"
    )

    print(
        f"Top border edge density: "
        f"{top_edge_density:.4f}"
    )

    print(
        f"Bottom border edge density: "
        f"{bottom_edge_density:.4f}"
    )

    print(
        f"Left border edge density: "
        f"{left_edge_density:.4f}"
    )

    print(
        f"Right border edge density: "
        f"{right_edge_density:.4f}"
    )


# ============================================================
# MAIN PROGRAM
# ============================================================


# ------------------------------------------------------------
# 1. Image path
# ------------------------------------------------------------

image_path = (
    "images/answer_sheet.jpg"
)


# ------------------------------------------------------------
# 2. Load image
# ------------------------------------------------------------

image = cv2.imread(
    image_path
)

if image is None:

    print(
        "ERROR: Image could not be loaded."
    )

    print(
        f"Check image path: {image_path}"
    )

    raise SystemExit


# ------------------------------------------------------------
# 3. Original image
# ------------------------------------------------------------

print(
    "Original shape:",
    image.shape
)


# ------------------------------------------------------------
# 4. Grayscale
# ------------------------------------------------------------

gray = cv2.cvtColor(
    image,
    cv2.COLOR_BGR2GRAY
)

print(
    "Grayscale shape:",
    gray.shape
)


# ------------------------------------------------------------
# 5. Gaussian blur
# ------------------------------------------------------------

blur = cv2.GaussianBlur(
    gray,
    (5, 5),
    0
)

print(
    "Blur shape:",
    blur.shape
)


# ------------------------------------------------------------
# 6. Adaptive threshold
# ------------------------------------------------------------

adaptive_threshold = cv2.adaptiveThreshold(
    blur,
    255,
    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
    cv2.THRESH_BINARY,
    11,
    2
)

print(
    "Adaptive threshold shape:",
    adaptive_threshold.shape
)


# ------------------------------------------------------------
# 7. Canny edges
# ------------------------------------------------------------

edges = cv2.Canny(
    blur,
    50,
    150
)

print(
    "Edges shape:",
    edges.shape
)


# ------------------------------------------------------------
# 8. Detect page candidates
# ------------------------------------------------------------

page_candidates = detect_page_candidates(
    image,
    edges
)


# ------------------------------------------------------------
# 9. Calculate confidence
# ------------------------------------------------------------

confidence_features = calculate_page_confidence(
    page_candidates,
    gray,
    edges
)


# ------------------------------------------------------------
# 10. Fallback border analysis
# ------------------------------------------------------------

analyze_borders(
    gray,
    edges
)


# ------------------------------------------------------------
# 11. Final summary
# ------------------------------------------------------------

print(
    "\n================================================"
)

print(
    "PHASE 2 IMAGE ANALYSIS SUMMARY"
)

print(
    "================================================"
)

if confidence_features["candidate_found"]:

    print(
        "Meaningful page candidate: FOUND"
    )

else:

    print(
        "Meaningful page candidate: NOT FOUND"
    )

print(
    "Confidence feature analysis: COMPLETE"
)

print(
    "Border analysis: COMPLETE"
)

print(
    "No final hard rejection threshold applied yet."
)

print(
    "================================================"
)