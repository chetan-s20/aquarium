import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ml" / "fish_disease"


def main():
    parser = argparse.ArgumentParser(description="Train fish-disease image classifier (optional module).")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--epochs", type=int, default=5)
    args = parser.parse_args()

    if not args.data_dir.exists():
        print(f"Dataset not found at {args.data_dir}. Download from Kaggle and extract here first.")
        print("See ml/README.md. Training not run.")
        sys.exit(1)

    try:
        import torchvision  # noqa: F401
    except ImportError:
        print("torchvision is not installed. Install it manually, then rerun.")
        sys.exit(1)

    print("Dependencies and dataset present. Training entry point is a scaffold; implement model/training loop here.")
    print("Do not claim diagnostic accuracy without a held-out evaluation report.")


if __name__ == "__main__":
    main()
