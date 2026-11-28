# FISHUT datasets

Every dataset FISHUT trains or tests on: where it comes from, its licence, how it is split, and what
is wrong with it. Downloads go to `data/` and trained models to `ml/models/`; both are gitignored.

| Dataset | Used for | Licence | Split |
|---|---|---|---|
| Fish disease images (Kaggle) | Disease classifiers: SVM, Random Forest, Logistic Regression, CNN | See the Kaggle page; check it before sharing models | De-duplicated; stratified 80% fit / 20% test (CNN: 10% of fit for validation) |
| 3D-ZeF20 zebrafish | Tracker benchmark; YOLO fish detector | CC BY-NC-SA 3.0: internal testing only | YOLO trains on videos 01, 03, 04 (last 15% of each = validation); video 02 is the unseen test |
| USGS continuous water-quality monitor | Early warning of low oxygen (Logistic Regression, Random Forest, SVM) | Public domain | By time: earlier years train, most recent years test |
| FISHUT simulator | Dashboard demo and software tests only | Ours | Never used to train or score a model |

## Fish disease images

- **Source:** Kaggle, "Freshwater Fish Disease Aquaculture in South Asia" (`subirbiswas19`), downloaded
  with `ml/download_dataset.py` (no Kaggle login needed).
- **Content:** 7 classes: Bacterial Red disease, Aeromoniasis, Bacterial gill disease, Saprolegniasis
  (fungal), Healthy, Parasitic, White tail disease (viral). 250 Train and 100 Test images per class,
  collected from websites and fisheries institutes.
- **Problems found:**
  - **All 700 Test images are byte-identical copies of Train images.** Scoring on them gives a fake 100%.
  - Train has 3 exact duplicates and 1 image filed under two diseases.
  - Train also has **near-copies**: the same photo resized, mirrored, rotated or recompressed. With a
    plain random split, 37 of 350 test images (11%) had a near-copy in the training set, which made
    the CNN look better than it is (94.9% on that split).
- **Split** (`ml/disease_data.py`, shared by every model so their scores compare): exact copies are
  removed; near-copies are grouped by perceptual hash (any flip or 90° turn, at most 4 of 64 bits
  different), and a group filed under two diseases is dropped (13 images removed in total). 209
  images sit in near-copy groups, and each group stays on one side of the split. 1,389 fit and 348
  test images, stratified by class and grouped (`StratifiedGroupKFold`, `random_state=0`). After the
  fix, no test image has a near-copy in the training set at that threshold. The CNN holds 10% of the
  fit set back as a validation set to pick its best epoch. The test set is scored once, at the end.
- **Limit:** web photos do not look like the farm's camera, lighting or species. Results here show
  which method learns best, not how well it will work on the farm. That needs the farm's own photos,
  labelled by a fish-health expert.

## 3D-ZeF20 (zebrafish tracking benchmark)

- **Source:** MOTChallenge 3D-ZeF20 (`https://motchallenge.net/data/3DZeF20.zip` and the labels zip).
  Only the needed front-camera frames are fetched (HTTP range requests), not the 14 GB archive.
- **Content:** 4 labelled training videos of zebrafish in a tank at 60 fps, 2704×1520, with a box and
  an identity for every fish in every frame.
- **Licence:** CC BY-NC-SA 3.0 (non-commercial). Use it for internal testing only. Never commit the
  data, and never ship a model trained on it.
- **Use:**
  - `ml/benchmark_tracker.py` scores the tracker on the first 900 frames (15 s) of ZebraFish-02 (5 fish).
  - `ml/train_fish_detector.py` trains YOLO on 300 frames spread over each of ZebraFish-01, -03 and
    -04: 779 train and 121 validation frames (the last 15% of each video). ZebraFish-02 is never seen
    in training, so the benchmark is a fair test.
- **Limit:** zebrafish in a clear lab tank, not carp in a farm tank. A farm detector needs boxes drawn
  on the farm's own video.

## USGS continuous water-quality monitor

- **Source:** U.S. Geological Survey, Water Data API (`api.waterdata.usgs.gov`, "continuous"
  collection). Public domain. Fetched with `ml/fetch_usgs.py --site <number>` into
  `data/usgs/<site>.csv` (hourly: oxygen, temperature, pH, turbidity where measured).
- **Why this one:** calibrated monitors with approved records, and real night-time oxygen crashes,
  which is exactly what an early warning has to catch. No public fish-pond dataset we found had both
  (see Rejected).
- **Station used:** 421401121480900, Upper Klamath Lake at Link River Dam, Oregon: 121,794 hours of
  oxygen, temperature and pH, 2012–2025 (no turbidity at this site). Checks passed: oxygen 0.65–18
  mg/L (1st–99th percentile 4.8–13.8), a strong daily cycle (24-hour autocorrelation 0.89 in summer)
  with the low around 08:00 and the high around 19:00 local time, the same shape as a fish pond's
  dawn low, and 1,322 hours below 5 mg/L spread over the years (0 in 2017, 590 in 2013).
- **Use:** `ml/train_water_model.py` predicts whether oxygen will fall below 5 mg/L in the next 3 hours
  while it is still safe now. The label comes from future readings, so it is not circular.
- **Split:** by time: earlier years train and tune (time-series cross-validation), the most recent years
  test, so no model ever sees the future.
- **Limit:** a lake or river, not a fish tank. It shows whether early warning works from these sensors;
  FISHUT's own calibrated sensor data is needed before it can be trusted on the farm.

## Rejected

- **Mendeley "IoT Monitoring Dataset of Water Quality and Tilapia Health… Montería, Colombia (2024)"
  (doi:10.17632/3g2b4sh65m.1, CC BY 4.0):** checked file by SHA-256, then profiled. Not an hourly
  sensor log: dissolved oxygen is one value per month repeated for every hour (6 values cover 4,030 of
  4,383 rows; the value repeats from one hour to the next 92% of the time), it never drops below
  6.34 mg/L, and the "Low Oxygen Alert" column is "Safe" in every row. The columns that do vary by the
  hour are engineered (`oxigeno_scaled` has no daily cycle and does not correlate with oxygen, r = 0.04),
  and `day` / `hour` contradict the timestamps. There is no low-oxygen event to learn from.
- **Kaggle "Sensor based aquaponics fish pond datasets" (Nsukka, Nigeria, 2021):** real ESP32 sensor
  output, but the oxygen sensor reads 0 to 45 mg/L (water at 25–30 °C holds about 8 mg/L; above ~20 is
  not physical) with pond medians from 0 to 18 mg/L, the temperature sensor logs its "disconnected"
  code −127, timestamps come in four formats, and the authors report the ammonia and nitrate gas sensors
  (MQ-135 / MQ-137) misread. Its "low oxygen" hours are mostly sensor faults.
- **Mendeley "Aquaculture – Water Quality Dataset" (`y78ty2g293`):** "prepared based on the threshold
  values" of each feature, so its quality classes are generated from rules; a model would only learn
  the rules back.
- **FISHUT's simulated readings:** a model trained on them learns the simulator, not fish or water.
