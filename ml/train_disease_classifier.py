"""Train the fish-disease image classifiers on OpenCV features and compare them honestly.

    python ml/train_disease_classifier.py            # downloads the dataset if needed
    python ml/train_disease_classifier.py --data-dir path/with/Train_and_Test

Compares an RBF SVM, a Random Forest and Logistic Regression on the same features and the same
de-duplicated hold-out (see disease_data.py). Each is tuned with 5-fold cross-validation on the fit
set only; the hold-out is scored once. The best by cross-validation (never by hold-out score) is refit
on every clean image and saved as ml/models/disease_model.joblib for predict_disease.py; all three
are in ml/models/disease_report.json.
"""
import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

sys.path.insert(0, str(Path(__file__).parent))
from disease_data import clean_split, image_files  # noqa: E402
from vision import FEATURE_VERSION, image_features, load_image  # noqa: E402

MODEL_DIR = Path(__file__).parent / "models"

CANDIDATES = {
    "svm_rbf": (  # calibrated for probabilities: SVC(probability=True) is deprecated in scikit-learn 1.9
        make_pipeline(StandardScaler(), CalibratedClassifierCV(SVC(kernel="rbf", class_weight="balanced"), ensemble=False)),
        {"calibratedclassifiercv__estimator__C": [1, 10, 30], "calibratedclassifiercv__estimator__gamma": ["scale", 1e-4]},
    ),
    "random_forest": (
        RandomForestClassifier(n_estimators=400, class_weight="balanced", random_state=0, n_jobs=-1),
        {"max_features": ["sqrt", 0.05], "min_samples_leaf": [1, 3]},
    ),
    "logistic_regression": (
        make_pipeline(StandardScaler(), LogisticRegression(max_iter=5000, class_weight="balanced")),
        {"logisticregression__C": [0.001, 0.01, 0.1]},
    ),
}


def features(paths) -> np.ndarray:
    return np.array([image_features(load_image(p)) for p in paths])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", type=Path, help="folder containing Train/ and Test/")
    args = ap.parse_args()
    if args.data_dir is None:
        from download_dataset import dataset_root
        args.data_dir = dataset_root()

    split = clean_split(args.data_dir)
    (fit_paths, y_fit), (hold_paths, y_hold) = split["fit"], split["hold"]
    print(f"fit {len(y_fit)}  hold-out {len(y_hold)}  (removed {split['removed']} duplicates/conflicts)")
    print("Extracting OpenCV features ...")
    X_fit, X_hold = features(fit_paths), features(hold_paths)
    y_fit, y_hold = np.array(y_fit), np.array(y_hold)

    # official Test images that are NOT copies of Train images (there may be none)
    test_paths, y_test, test_md5, test_skipped = image_files(args.data_dir / "Test")
    clean_test = [i for i, d in enumerate(test_md5) if d not in split["train_digests"]]

    classes = sorted(set(y_fit))
    cv = StratifiedKFold(5, shuffle=True, random_state=0)
    results, best = {}, {}
    for name, (estimator, grid) in CANDIDATES.items():
        search = GridSearchCV(estimator, grid, cv=cv, n_jobs=-1).fit(X_fit, y_fit)
        pred = search.best_estimator_.predict(X_hold)
        best[name] = search.best_estimator_
        results[name] = {
            "best_params": search.best_params_,
            "cv_accuracy": round(search.best_score_, 4),
            "holdout_accuracy": round(accuracy_score(y_hold, pred), 4),
            "holdout_balanced_accuracy": round(balanced_accuracy_score(y_hold, pred), 4),
            "per_class": classification_report(y_hold, pred, output_dict=True, zero_division=0),
            "confusion_matrix": confusion_matrix(y_hold, pred, labels=classes).tolist(),
        }
        if clean_test:
            t_pred = search.best_estimator_.predict(features([test_paths[i] for i in clean_test]))
            results[name]["official_clean_test_accuracy"] = round(accuracy_score([y_test[i] for i in clean_test], t_pred), 4)
        print(f"{name:20s} cv {search.best_score_:.3f}  hold-out {results[name]['holdout_accuracy']:.3f}  {search.best_params_}")

    chosen = max(results, key=lambda n: results[n]["cv_accuracy"])
    print(f"deployed: {chosen} (best cross-validation accuracy)")
    print(classification_report(y_hold, best[chosen].predict(X_hold), zero_division=0))
    model = best[chosen].fit(np.concatenate([X_fit, X_hold]), np.concatenate([y_fit, y_hold]))
    report = {
        "feature_version": FEATURE_VERSION,
        "deployed_model": chosen,
        "classes": classes,
        "fit_images": int(len(y_fit)),
        "holdout_images": int(len(y_hold)),
        "removed_duplicates_or_conflicts": split["removed"],
        "near_copy_images_kept_on_one_side": split["near_copy_images"],
        "official_test_images": len(test_md5),
        "official_test_images_copied_from_train": len(test_md5) - len(clean_test),
        "chance_accuracy": round(1 / len(classes), 4),
        "models": results,
        "unreadable_files": split["skipped"] + test_skipped,
    }
    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump({"model": model, "name": chosen, "classes": classes, "feature_version": FEATURE_VERSION},
                MODEL_DIR / "disease_model.joblib")
    (MODEL_DIR / "disease_report.json").write_text(json.dumps(report, indent=2))
    print(f"saved {MODEL_DIR / 'disease_model.joblib'} ({chosen}) and disease_report.json")


if __name__ == "__main__":
    main()
