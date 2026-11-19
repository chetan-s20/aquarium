"""Download the fish-disease image dataset and print where it is.

The dataset is a folder of images (Train/<class>/*.jpg, Test/<class>/*.jpg).
kagglehub's PANDAS adapter only loads tabular files (csv/json/parquet...), so for
images we use dataset_download(), which returns the local folder path.
No Kaggle credentials are needed for this public dataset.
"""
from collections import Counter
from pathlib import Path

import kagglehub

DATASET = "subirbiswas19/freshwater-fish-disease-aquaculture-in-south-asia"


def dataset_root() -> Path:
    """Folder that contains Train/ and Test/ (downloads once, then uses the cache)."""
    base = Path(kagglehub.dataset_download(DATASET))
    return next(p.parent for p in base.rglob("Train") if p.is_dir())


if __name__ == "__main__":
    root = dataset_root()
    print(f"Dataset at: {root}")
    for split in ("Train", "Test"):
        counts = Counter(p.parent.name for p in (root / split).rglob("*") if p.is_file())
        print(f"\n{split}: {sum(counts.values())} images")
        for cls, n in sorted(counts.items()):
            print(f"  {n:4d}  {cls}")
