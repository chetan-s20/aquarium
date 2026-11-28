"""Classify fish photos with the trained model.  python ml/predict_disease.py photo1.jpg [photo2.jpg ...]

Output is an assistive signal for staff, not a veterinary diagnosis.
"""
import sys
from pathlib import Path

import joblib

sys.path.insert(0, str(Path(__file__).parent))
from vision import FEATURE_VERSION, image_features, load_image  # noqa: E402

MODEL = Path(__file__).parent / "models" / "disease_model.joblib"  # best of SVM / Random Forest / LogReg


def predict(paths: list[str], top: int = 3) -> list[dict]:
    if not MODEL.exists():
        sys.exit(f"No model at {MODEL}. Run: python ml/train_disease_classifier.py")
    bundle = joblib.load(MODEL)
    if bundle["feature_version"] != FEATURE_VERSION:
        sys.exit("Model was trained with different features; retrain it.")
    model = bundle["model"]
    out = []
    for p in paths:
        probs = model.predict_proba([image_features(load_image(p))])[0]
        ranked = sorted(zip(model.classes_, probs), key=lambda x: -x[1])[:top]
        out.append({"image": p, "predictions": [{"label": c, "probability": round(float(pr), 3)} for c, pr in ranked]})
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for result in predict(sys.argv[1:]):
        print(result["image"])
        for p in result["predictions"]:
            print(f"  {p['probability']:.0%}  {p['label']}")
