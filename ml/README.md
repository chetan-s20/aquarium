# ml/: camera behaviour and fish-disease model

Everything here uses OpenCV. Install with `python -m pip install -r ml/requirements.txt` plus CPU
PyTorch, or use the Docker image, which needs nothing installed on the machine:

```bash
docker build -t fishut-ml ml
docker run --rm --user "$(id -u):$(id -g)" --shm-size=1g -v "$PWD:/work:z" fishut-ml python ml/train_disease_cnn.py
```

Datasets, pretrained weights and trained models stay under `data/` and `ml/models/` (both gitignored).

| File | Purpose |
|---|---|
| `vision.py` | Shared OpenCV code: image features (CLAHE, HSV histograms, HOG) and `ActivityMeter` (MOG2 motion) |
| `track_fish.py` | Tracks every fish (OpenCV detection + ByteTrack + re-linking) and posts each fish's positions to the API |
| `fish_activity.py` | Video or camera to `fish_activity` and `surface_activity` readings, posted to the API and/or a CSV |
| `download_dataset.py` | Downloads the Kaggle fish-disease images with `kagglehub.dataset_download()` |
| `disease_data.py` | One cleaned, de-duplicated split of the disease images, shared by every model so scores compare |
| `train_disease_classifier.py` | OpenCV features + SVM, Random Forest and Logistic Regression, compared on the same hold-out; deploys the best by cross-validation as `models/disease_model.joblib`; all three in `models/disease_report.json` |
| `train_disease_cnn.py` | CNN: MobileNetV3 (ImageNet) fine-tuned with train / validation / test splits; writes `models/disease_cnn.pt` and `models/disease_cnn_report.json` |
| `train_fish_detector.py` | YOLO11n fish detector trained on 3D-ZeF20 (internal testing only); `benchmark_tracker.py --yolo` scores it against the OpenCV detector |
| `predict_disease.py` | Ranks the likely conditions for one or more photos |
| `disease_service.py` | Small HTTP service around the CNN for the dashboard's photo check (`docker compose --profile ml`) |
| `fetch_usgs.py` | Downloads a USGS continuous water-quality record (oxygen, temperature, pH, turbidity) into an hourly CSV |
| `train_water_model.py` | Early warning: will oxygen fall below 5 mg/L in the next 3 h? Logistic Regression, Random Forest and SVM vs a cut-off baseline; writes `models/water_report.json` |
| `benchmark_tracker.py` | Scores `track_fish.py` on the 3D-ZeF20 zebrafish benchmark (IDF1, id switches) with py-motmetrics. Data is CC BY-NC-SA 3.0: internal testing only |
| `test_ml.py` | Self-checks on synthetic frames: `python -m pytest ml` |

## Results (28 Nov 2026)

Fish-disease images, 7 classes. The official Test images are all copies of Train images, and Train
holds near-copies (resized, mirrored, rotated) of the same photo, so every model is scored on one
shared 20% test set in which no photo also appears in training (`disease_data.py`,
`docs/DATASETS.md`): 1,389 fit, 348 test. Random guessing scores 14%.

| Model | Test accuracy | Cross-validation (fit set) |
|---|---|---|
| CNN: MobileNetV3, ImageNet weights, fine-tuned | **92.8%** | validation 93.5% (best epoch 5 of 12) |
| Random Forest on OpenCV features | 74.4% | 70.2% |
| Logistic Regression on OpenCV features | 46.0% | 49.2% |
| SVM (RBF) on OpenCV features | 43.4% | 47.7% |

- CNN: 10 of 298 sick fish (3.4%) were called healthy; 1 of 50 healthy fish was flagged. Lowest
  recall: parasitic diseases, 86%. Per-class results: `models/disease_cnn_report.json`.
- With a plain random split the same models scored higher (CNN 94.9%, SVM 53.1%) because near-copies
  leaked into the test set. The numbers above are the honest ones.
- These are web photos. The results rank the methods; they do not say how well any of them works on
  the farm's camera. That needs the farm's own photos labelled by a fish-health expert (`docs/PLAN.md §6`).
  Any output is a hint for staff to inspect a fish, not a diagnosis.

**Fish tracking** (`benchmark_tracker.py`): ZebraFish-02 front camera, 5 fish, 900 frames, same
tracker (ByteTrack + re-linking), only the detector differs. YOLO11n was trained for 6 epochs on CPU
(about an hour) on ZebraFish-01, -03 and -04 and never saw ZebraFish-02.

| Detector | IDF1 | Recall | Precision | MOTA | Mostly tracked | ID switches |
|---|---|---|---|---|---|---|
| OpenCV background subtraction | 58% | 69% | ~100% | 69% | 2 of 5 | 12 |
| YOLO11n (`train_fish_detector.py`) | **76%** | **93%** | 99% | **92%** | **5 of 5** | 15 |

YOLO separates touching fish, which the background method sees as one blob (misses fall from 1,400
to 299). It does swap ids slightly more often, because it now sees both fish while they overlap.
YOLO validation: precision 98.6%, recall 97.4%, mAP50 0.989. The weights are trained on CC BY-NC-SA
data, so they are for internal testing only; a farm detector needs boxes drawn on the farm's video.

**Low-oxygen early warning** (`train_water_model.py`): will dissolved oxygen fall below 5 mg/L in
the next 3 hours, while it is still safe now? Data: USGS monitor 421401121480900, Upper Klamath Lake
at Link River Dam (Oregon), hourly oxygen, temperature and pH, 2012–2025, a lake full of algae
with the same dawn oxygen low a fish pond has. Trained on 2012–2021 (85,124 hours), tested on
2022–2025 (34,310 hours, 85 of them 1–3 h before a crash). Each alarm threshold was set on 2020–21 and
then left unchanged for the test years.

| Model | Crashes warned (recall) | Alarms that were real (precision) | F1 | Average precision |
|---|---|---|---|---|
| **Logistic Regression** | **92%** | 43% | **0.59** | **0.74** |
| Random Forest | 53% | 65% | 0.58 | 0.58 |
| Baseline: oxygen below 5.3 mg/L now | 40% | 29% | 0.34 | 0.25 |
| SVM (RBF, 6,000-row subsample) | 94% | 8% | 0.16 | 0.28 |

Logistic Regression warns before 78 of the 85 crash hours, more than twice what the plain cut-off
catches, at the cost of a bit more than one false alarm per real one. The most useful signals
(Random Forest importance) are current oxygen, temperature and how fast both are changing. The
validation period held only 45 crash hours, so the thresholds are rough; the SVM's did not carry
over at all. Two public fish-pond datasets were rejected before this one (`docs/DATASETS.md`).
FISHUT's own sensors are needed before the farm can rely on it.

## Camera notes

- Use a fixed camera with no pan or zoom. The first 3 seconds are used to learn the empty background.
- Motion % depends on the camera set-up, so compare it over time for the same camera, not between tanks.
- Night monitoring needs IR lighting.
