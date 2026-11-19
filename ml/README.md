# ml/: camera behaviour and fish-disease model

Everything here uses OpenCV. Install with `python -m pip install -r ml/requirements.txt`.

| File | Purpose |
|---|---|
| `vision.py` | Shared OpenCV code: image features (CLAHE, HSV histograms, HOG) and `ActivityMeter` (MOG2 motion) |
| `fish_activity.py` | Video or camera to `fish_activity` and `surface_activity` readings, posted to the API and/or a CSV |
| `download_dataset.py` | Downloads the Kaggle fish-disease images with `kagglehub.dataset_download()` |
| `train_disease_classifier.py` | Trains OpenCV features + SVM; writes `models/disease_svm.joblib` and `models/disease_report.json` |
| `predict_disease.py` | Ranks the likely conditions for one or more photos |
| `test_ml.py` | Self-checks on synthetic frames: `python -m pytest ml` |

## Results (19 Nov 2026)

- The dataset has 1,750 Train and 700 Test images across 7 classes. **All 700 Test images are copies of
  Train images**, so the official split is not used for scoring.
- On a de-duplicated, stratified 20% hold-out the baseline scores **53% accuracy** (random guessing:
  14%). Per-class results are in `models/disease_report.json`.
- This is an assistive hint, not a veterinary diagnosis. See `docs/PLAN.md §6` for the plan to reach
  a usable model (transfer learning plus the farm's own labelled photos).

## Camera notes

- Use a fixed camera with no pan or zoom. The first 3 seconds are used to learn the empty background.
- Motion % depends on the camera set-up, so compare it over time for the same camera, not between tanks.
- Night monitoring needs IR lighting.
