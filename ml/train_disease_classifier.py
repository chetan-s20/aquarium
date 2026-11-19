"""Train the fish-disease image classifier (OpenCV features + SVM) and evaluate it honestly.

    python ml/train_disease_classifier.py            # downloads the dataset if needed
    python ml/train_disease_classifier.py --data-dir path/with/Train_and_Test

Writes ml/models/disease_svm.joblib and ml/models/disease_report.json.
Honest evaluation: in the Kaggle download every Test image is a byte-identical copy of a
Train image, so the official Test split would report a fake 100%. We therefore drop exact
duplicates and label conflicts from Train, hold out a stratified 20% of it as the test set,
and score the official Test split only on images that are NOT copies of Train images.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

sys.path.insert(0, str(Path(__file__).parent))
from vision import FEATURE_VERSION, IMAGE_EXTS, image_features, load_image  # noqa: E402

MODEL_DIR = Path(__file__).parent / "models"


def load_split(folder: Path):
    X, y, digests, skipped = [], [], [], []
    for path in sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMAGE_EXTS):
        try:
            X.append(image_features(load_image(path)))
        except ValueError:
            skipped.append(str(path))
            continue
        y.append(path.parent.name)
        digests.append(hashlib.md5(path.read_bytes()).hexdigest())
    return np.array(X), np.array(y), digests, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", type=Path, help="folder containing Train/ and Test/")
    args = ap.parse_args()
    if args.data_dir is None:
        from download_dataset import dataset_root
        args.data_dir = dataset_root()

    print(f"Extracting OpenCV features from {args.data_dir} ...")
    X_train, y_train, train_md5, skip_a = load_split(args.data_dir / "Train")
    X_test, y_test, test_md5, skip_b = load_split(args.data_dir / "Test")
    print(f"train {len(y_train)}  test {len(y_test)}  unreadable {len(skip_a) + len(skip_b)}")

    # drop exact duplicates; drop images filed under two different classes
    labels_by_md5: dict[str, set] = {}
    for d, label in zip(train_md5, y_train):
        labels_by_md5.setdefault(d, set()).add(label)
    keep, seen = [], set()
    for i, d in enumerate(train_md5):
        if d not in seen and len(labels_by_md5[d]) == 1:
            keep.append(i)
        seen.add(d)
    X, y = X_train[keep], y_train[keep]
    print(f"train after removing duplicates/conflicts: {len(y)} (removed {len(y_train) - len(y)})")

    X_fit, X_hold, y_fit, y_hold = train_test_split(X, y, test_size=0.2, stratify=y, random_state=0)
    search = GridSearchCV(
        make_pipeline(StandardScaler(), SVC(kernel="rbf", class_weight="balanced", probability=True)),
        {"svc__C": [1, 10, 30], "svc__gamma": ["scale", 1e-4]},
        cv=StratifiedKFold(5, shuffle=True, random_state=0), n_jobs=-1,
    )
    search.fit(X_fit, y_fit)
    print(f"best params {search.best_params_}  cv accuracy {search.best_score_:.3f}")

    pred = search.best_estimator_.predict(X_hold)
    classes = sorted(set(y))
    leaked = np.array([d in labels_by_md5 for d in test_md5])
    clean_test = None
    if (~leaked).any():
        clean_pred = search.best_estimator_.predict(X_test[~leaked])
        clean_test = round(accuracy_score(y_test[~leaked], clean_pred), 4)

    # final model: same settings, all clean training images
    model = search.best_estimator_.fit(X, y)
    report = {
        "feature_version": FEATURE_VERSION,
        "best_params": search.best_params_,
        "cv_accuracy": round(search.best_score_, 4),
        "holdout_accuracy": round(accuracy_score(y_hold, pred), 4),
        "holdout_images": int(len(y_hold)),
        "official_test_images": int(len(y_test)),
        "official_test_images_copied_from_train": int(leaked.sum()),
        "official_clean_test_accuracy": clean_test,
        "chance_accuracy": round(1 / len(classes), 4),
        "classes": classes,
        "per_class": classification_report(y_hold, pred, output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(y_hold, pred, labels=classes).tolist(),
        "unreadable_files": skip_a + skip_b,
    }
    print(classification_report(y_hold, pred, zero_division=0))
    print(f"held-out accuracy {report['holdout_accuracy']} (chance {report['chance_accuracy']})  |  "
          f"{report['official_test_images_copied_from_train']}/{len(y_test)} official Test images are copies of Train")

    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump({"model": model, "classes": classes, "feature_version": FEATURE_VERSION}, MODEL_DIR / "disease_svm.joblib")
    (MODEL_DIR / "disease_report.json").write_text(json.dumps(report, indent=2))
    print(f"saved {MODEL_DIR / 'disease_svm.joblib'}")


if __name__ == "__main__":
    main()
