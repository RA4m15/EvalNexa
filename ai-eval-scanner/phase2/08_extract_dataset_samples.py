from pathlib import Path
import random
import shutil


DATASET_ROOT = Path("dataset/AnswerScripts/Handwriting224")
OUTPUT_DIR = Path("images/dataset_samples")

SAMPLE_COUNT = 30
SEED = 42


def main():
    random.seed(SEED)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Remove previous extracted samples
    for old_file in OUTPUT_DIR.glob("*.jpg"):
        old_file.unlink()

    student_folders = sorted(
        folder for folder in DATASET_ROOT.iterdir()
        if folder.is_dir()
    )

    print(f"Student folders found: {len(student_folders)}")

    selected = []

    # First: select one image from every student
    for folder in student_folders:
        images = sorted(folder.glob("*.jpg"))

        if images:
            selected.append(
                (folder.name, random.choice(images))
            )

    # Add more images until we reach SAMPLE_COUNT
    remaining_needed = SAMPLE_COUNT - len(selected)

    if remaining_needed > 0:
        candidates = []

        for folder in student_folders:
            images = sorted(folder.glob("*.jpg"))

            for image in images:
                candidates.append((folder.name, image))

        already_selected = {
            image_path for _, image_path in selected
        }

        candidates = [
            item
            for item in candidates
            if item[1] not in already_selected
        ]

        random.shuffle(candidates)

        selected.extend(
            candidates[:remaining_needed]
        )

    selected = selected[:SAMPLE_COUNT]

    # Copy selected images
    for index, (student, image_path) in enumerate(
        selected,
        start=1
    ):
        output_name = (
            f"{index:02d}_{student}_{image_path.name}"
        )

        shutil.copy2(
            image_path,
            OUTPUT_DIR / output_name
        )

    print(f"\nExtracted: {len(selected)} images")
    print(f"Output: {OUTPUT_DIR.resolve()}")

    print("\nSelected samples:")

    for index, (student, image_path) in enumerate(
        selected,
        start=1
    ):
        print(
            f"{index:02d}. "
            f"{student} -> {image_path.name}"
        )


if __name__ == "__main__":
    main()