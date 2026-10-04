from pathlib import Path

import cv2
import numpy as np


IMAGE_DIR = Path("images/dataset_samples")


def calculate_metrics(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Brightness
    brightness = float(np.mean(gray))

    # Contrast
    contrast = float(np.std(gray))

    # Blur / sharpness
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # Edge density
    edges = cv2.Canny(gray, 50, 150)
    edge_density = float(np.mean(edges > 0))

    # Local texture
    texture = cv2.Laplacian(gray, cv2.CV_64F).var()

    return brightness, contrast, blur_score, edge_density, texture


def main():
    images = sorted(IMAGE_DIR.glob("*.jpg"))

    print("=" * 60)
    print("DATASET VALIDATION")
    print("=" * 60)

    print(f"Dataset directory : {IMAGE_DIR}")
    print(f"Images found      : {len(images)}")
    print()

    if not images:
        print("ERROR: No JPG images found.")
        return

    valid_count = 0
    invalid_count = 0

    brightness_values = []
    contrast_values = []
    blur_values = []
    edge_values = []
    texture_values = []

    print("Checking images...\n")

    for image_path in images:

        image = cv2.imread(str(image_path))

        if image is None:
            print(f"[INVALID] {image_path.name}")
            invalid_count += 1
            continue

        valid_count += 1

        height, width = image.shape[:2]

        brightness, contrast, blur_score, edge_density, texture = (
            calculate_metrics(image)
        )

        brightness_values.append(brightness)
        contrast_values.append(contrast)
        blur_values.append(blur_score)
        edge_values.append(edge_density)
        texture_values.append(texture)

        print(
            f"{image_path.name:50} "
            f"{width}x{height} | "
            f"Brightness={brightness:7.2f} | "
            f"Contrast={contrast:7.2f} | "
            f"Blur={blur_score:9.2f} | "
            f"Edges={edge_density:.4f}"
        )

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(f"Total images : {len(images)}")
    print(f"Valid images : {valid_count}")
    print(f"Invalid      : {invalid_count}")

    if valid_count == 0:
        return

    print("\nBrightness")
    print(f"  Min  : {min(brightness_values):.2f}")
    print(f"  Max  : {max(brightness_values):.2f}")
    print(f"  Mean : {np.mean(brightness_values):.2f}")

    print("\nContrast")
    print(f"  Min  : {min(contrast_values):.2f}")
    print(f"  Max  : {max(contrast_values):.2f}")
    print(f"  Mean : {np.mean(contrast_values):.2f}")

    print("\nBlur / Sharpness")
    print(f"  Min  : {min(blur_values):.2f}")
    print(f"  Max  : {max(blur_values):.2f}")
    print(f"  Mean : {np.mean(blur_values):.2f}")

    print("\nEdge Density")
    print(f"  Min  : {min(edge_values):.4f}")
    print(f"  Max  : {max(edge_values):.4f}")
    print(f"  Mean : {np.mean(edge_values):.4f}")

    print("\nTexture")
    print(f"  Min  : {min(texture_values):.2f}")
    print(f"  Max  : {max(texture_values):.2f}")
    print(f"  Mean : {np.mean(texture_values):.2f}")

    print("\nValidation completed successfully.")


if __name__ == "__main__":
    main()