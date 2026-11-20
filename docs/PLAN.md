# Pond monitor: project plan

Status as of 19 Nov 2026. This replaces `docs/phase1.md`.

## 1. The problem

Fish in ponds and tanks die mostly from **water going bad**, and it happens fast. The main cause is
dissolved oxygen (DO):

- Algae make oxygen by day and every living thing uses it all night, so DO falls overnight and is lowest
  **just before dawn**. On cloudy days, or after heavy feeding, the dawn low can drop below what fish
  survive (warm-water fish are stressed below about 3 mg/L; good practice keeps DO above 5 mg/L).
- By the time staff see fish gasping at the surface in the morning, fish are already being lost.
- Disease shows up later as visible skin, fin and gill symptoms. In South Asian carp farming that means
  bacterial red disease, aeromoniasis, gill disease, fungal infections, parasites and white-tail disease.

Today, farms check water by hand once or twice a day, so the dangerous pre-dawn hours go unwatched.
Nothing records the data in a form that can be analysed later.

**What this software does:** it reads pond sensors and a tank camera around the clock. It warns staff
before oxygen reaches a dangerous level, keeps every reading with its quality and source, and lets the
farm's analysts download the whole history to study how fish behaviour relates to water quality. A
separate model flags possible disease from fish photos.

## 2. Who uses it

| User | Needs | Where in the product |
|---|---|---|
| Farm operator (on shift) | "Is any tank in trouble right now? What do I do?" | Dashboard: oxygen panel, alerts, "Mark as seen" |
| Farm manager | Trends over days, which ponds dip at dawn, alert history | 7-day view, resolved alerts |
| Analyst / employer staff | All raw data, joined across sensors, for behaviour analysis and model training | **Download data** panel / `GET /export/readings.csv` |
| Device (probe gateway, camera PC) | A simple authenticated way to post readings | `POST /readings` with `X-Device-Key` |

## 3. Measurements

**Change from Phase 1:** TDS is dropped. Dissolved oxygen is the primary sensor.

| Metric | Unit | Source | Why it matters | Provisional limits (warn / critical) |
|---|---|---|---|---|
| Dissolved oxygen | mg/L | DO probe | Main cause of sudden fish deaths; lowest at dawn | below 5 / below 3 |
| Temperature | °C | probe | Warmer water holds less oxygen; carp grow best at ~25–32 °C | outside 24–32 / outside 20–35 |
| pH | pH | probe | Swings with algae photosynthesis; extremes stress fish | outside 6.5–8.5 / outside 6–9 |
| Turbidity | NTU | probe | Plankton bloom or silt; affects light and oxygen production | above 50 / above 100 (**placeholder**) |
| Fish activity | % of frame moving | camera + OpenCV | Fish move less when stressed or sick | recorded, no alert yet |
| Surface activity | % of motion in top 20% of frame | camera + OpenCV | Fish gasping at the surface is a classic low-oxygen sign | recorded, no alert yet |

The limits come from general warm-water pond guidance: Boyd (1982) as quoted in pond-culture
literature, and ICAR pond-management guidance. They have **not** been validated for the farm's species
or life stages. Each limit is stored in the `thresholds` table with its reference text. The farm's
fisheries officer must confirm them, and they can be set per tank.

Camera metrics have no alert limits on purpose. Published work (see Sources) shows behaviour responds
to hypoxia, but no validated activity threshold exists. The plan is to collect paired data first and
set limits from that (Phase 4).

## 4. Architecture

```
 Pond probes ──► ESP32/RPi gateway ──┐
 (DO, temp, pH, NTU)                 │  HTTPS POST /readings  (X-Device-Key)
                                     ▼
 Tank camera ──► PC running ──► FastAPI backend ──► PostgreSQL (SQLite in dev)
                 ml/fish_activity.py   │  quality check → store → alert rules
                 (OpenCV)              │
                                       ├──► React dashboard (live, 60 s refresh)
                                       └──► CSV export for analysts (long / wide)

 Fish photos ──► ml/predict_disease.py (OpenCV features + SVM)   [offline, assistive]
```

### Data model

These tables already exist in the migration:

- `tanks`, `devices`, `sensors`, `calibrations`: what is installed where. Each sensor has a physical
  range, and a reading outside that range is marked invalid, not alarming.
- `readings`: every value with `observed_at` (when measured) and `received_at` (when the server got
  it), plus `quality_status` (valid / invalid / missing), `quality_rule_version`, `source`
  (sensor / camera / simulator / import), `raw_value` and `raw_payload`. Simulated data can never be
  mistaken for real data.
- `thresholds`: limits per metric, global or per tank, with hysteresis and a reference.
- `alerts`: one alert per sensor at a time. It opens on a breach, escalates from warning to critical,
  and **resolves itself** once the value recovers past the limit plus hysteresis, so values hovering
  near a limit don't flood staff. Staff can mark an alert as seen.
- `import_runs`: audit trail for bulk CSV imports, with a SHA-256 of the file.
- `media_assets`, `labels`: reserved for camera clips and expert disease labels (Phase 4).

### Key design rules

1. **The server decides quality and context.** A device sends only `sensor_id`, `value` and
   `observed_at`. The server takes tank, metric and unit from the registered sensor, so a misconfigured
   device can't file oxygen readings under pH.
2. **UTC everywhere.** The dashboard shows the viewer's local time. CSV exports use ISO-8601 with `Z`.
3. **No duplicates.** The same sensor and timestamp is rejected with 409. Re-runs of the camera script,
   imports and the simulator are all safe.
4. **Everything is labelled.** Simulated readings carry `source=simulator`, and the dashboard shows a
   "Demo data" banner while `SIMULATION_MODE=true`.

## 5. Behaviour analysis (OpenCV)

`ml/fish_activity.py` works on a fixed camera, from either a video file or a live feed:

1. MOG2 background subtraction learns the empty tank and marks moving pixels as fish. Blur and a
   morphological opening suppress ripples and sensor noise.
2. For each window (default 60 s) it reports:
   - `fish_activity`: the average % of the frame that is moving
   - `surface_activity`: the % of that motion in the top 20% of the frame
3. It posts both values to `/readings` as the tank's camera sensors, and can also write a CSV.

Because camera metrics are stored as ordinary readings, they show up in the dashboard's **Oxygen and
fish behaviour** panel (time-aligned with DO) and in the **wide** CSV export, which has one row per
timestamp with a column per metric. An analyst can load that file and correlate behaviour with DO
straight away.

**Limits of this approach.** Motion % depends on camera height, lighting, stocking density and water
clarity. Compare it within the same camera over time, not between tanks. Night-time needs IR
lighting. Identifying individual fish (counting, trajectories, YOLO-style detection) is a Phase 5
upgrade.

## 6. Disease model

**Dataset:** Kaggle "Freshwater Fish Disease Aquaculture in South Asia" (subirbiswas19). It has 7
classes (Aeromoniasis, Bacterial gill disease, Bacterial red disease, Saprolegniasis, Healthy,
Parasitic, White-tail), with 250 Train and 100 Test images per class. The images come from websites
and fisheries institutes.

**How to load it.** The dataset is a folder of images. kagglehub's `PANDAS` adapter only reads table
files such as CSV, JSON and Parquet. The only CSV in this dataset, `Train.csv`, is a list of image
filenames, so the adapter can't load the images. `ml/download_dataset.py` uses
`kagglehub.dataset_download()` instead, which needs no Kaggle login.

**What we found in the data:**

- **All 700 Test images are byte-identical copies of Train images.** Scoring on the official Test split
  gives a meaningless 100%.
- Train has 3 exact duplicates, and 1 image is filed under two different diseases.

**Current model (baseline):** OpenCV features (CLAHE lighting correction, HSV colour histograms,
HOG shape and texture, edge density) fed into an RBF support vector machine. On a de-duplicated,
stratified 20% hold-out it scores **53% accuracy across 7 classes** (random guessing gives 14%).
That is useful only as an "inspect this fish" hint. It is **not** a diagnosis. The full per-class
report is written to `ml/models/disease_report.json`.

**How to make it good (Phase 4):**

1. Transfer learning (EfficientNet or MobileNet via torchvision), keeping OpenCV for preprocessing.
   Typically this gives a large jump on small image sets. PyTorch with CUDA is already on the dev
   machine.
2. Collect the farm's own photos, labelled by a fish health expert, using the `media_assets` and
   `labels` tables. A web-scraped dataset won't match the farm's camera, lighting or species.
3. Report per-class recall. Missing a sick fish costs more than a false alarm.

## 7. Roadmap

| Phase | Scope | Done when |
|---|---|---|
| **1–2 (done)** | Data model, migrations, API, quality rules, alert lifecycle, simulator, CSV import, CSV export, dashboard, OpenCV activity meter, baseline disease model, tests | `pytest` passes for backend and ml; the dashboard runs on simulated data |
| **3: real sensors** | Choose and install probes (an optical DO probe is preferred for low upkeep), ESP32/RPi gateway posting every 1–5 min, calibration records, offline buffering on the gateway, device-offline alert | One pond streams real data for 2 weeks; manual check readings agree within probe spec |
| **3b: notifications** | SMS / WhatsApp / phone call for critical DO, especially 02:00–07:00; escalation if nobody marks it seen | A test alert reaches the on-call phone in under 1 minute |
| **4: behaviour + disease** | Camera on one tank; collect paired DO and behaviour data; derive data-driven activity limits; CNN disease model with farm photos | Activity limit validated against at least 5 real low-DO events; disease model recall ≥ 80% on farm photos |
| **5: prediction** | Forecast tonight's dawn DO from the afternoon trend, temperature and weather, so aerators can start early | Forecast error under 1 mg/L on held-out nights |
| **6: hardening** | User login and roles (replacing shared keys), HTTPS, PostgreSQL in production, backups, retention policy, audit log | Security review passes |

## 8. Risks and open questions for the farm

- **Species, life stage and stocking density** per tank are still unconfirmed, so the limits stay
  provisional until then.
- **Turbidity limit** is a placeholder. Pond turbidity from plankton is normal; turbidity from silt is not.
- **Power and connectivity** at the ponds: gateways need battery backup and must store readings while
  offline. The API already accepts late readings, because `observed_at` is kept separate from
  `received_at`.
- **Probe fouling.** DO and pH probes drift. A cleaning and calibration schedule has to be followed,
  and the `calibrations` table is there to record it.
- **Shared API keys** are fine for a prototype only. In the current setup the operator key ships inside
  the dashboard bundle (`VITE_OPERATOR_KEY`), so anyone who can open the dashboard can act as an
  operator. Put the dashboard behind a login before exposing it outside the farm network.

## Sources

- Water-quality guidance: Boyd (1982) ranges as cited in pond-culture literature
  ([SciELO](https://scielo.br/j/bjb/a/cmKqrbqsf9p68MhYbztndvb/abstract/?lang=pt));
  ICAR Indian Journal of Fisheries, pond water quality
  ([ICAR ePubs](https://epubs.icar.org.in/index.php/IJF/article/view/13339)).
- Dataset description: [GTS listing](https://gts.ai/dataset-download/freshwater-fish-disease-aquaculture-in-south-asia/);
  [Indian Journal of Animal Research](https://arccjournals.com/journal/indian-journal-of-animal-research/bf-1946).
- kagglehub adapters: [kagglehub README](https://raw.githubusercontent.com/Kaggle/kagglehub/main/README.md).
- Fish behaviour and computer vision: [Fish tracking & behaviour survey (arXiv 2406.17800)](https://arxiv.org/html/2406.17800v1);
  [Hypoxia stress behaviour detection](https://chaoweifang.github.io/publication/aquaculture25real-time);
  [Computer vision fish-behaviour monitoring review (PMC5903295)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5903295/).

## 9. Work log — done vs. left (status as of 20 Nov 2026, commit 2bb3b29 on main)

### Done

- **Phase 3 server-side — device-offline alert.** Devices post readings every 1–5 min;
  `evaluate_device_offline` (`backend/app/services/alerts.py`) sweeps on every `GET /alerts` and
  opens one warning alert per device that has not reported for `DEVICE_OFFLINE_MINUTES` (default
  10). The alert resolves when the device posts a reading again. `alerts.device_id` column added
  (migration `4d52c4042583`). Tests: `tests/test_device_offline.py` (3).

- **Phase 4 server-side — data-driven activity limits.** `derive_activity_limits`
  (`backend/app/services/activity_limits.py`) pairs valid activity readings with nearby (±30 min)
  valid dissolved-oxygen readings; DO below the tank's warning limit is a "low-DO event"; returns
  a proposal (`low_warning` = the activity level typically reached during low-DO events) only when
  at least 5 such events have activity. Tests: `tests/test_activity_limits.py` (3).

- **Phase 5 — dawn DO forecast.** `dawn_do_forecast` (`backend/app/services/forecast.py`) fits DO
  vs local hour over the last readings before the next local dawn (farm offset, hour 4.0) and
  extrapolates. Tests: `tests/test_forecast.py` (3).

- **Phase 6 — login/roles, audit, retention, backup.**
  - Login/roles: `users` table + migration `ea191d344f70`; `app/auth.py` (pbkdf2 password hashing,
    HMAC-signed `aquarium_session` cookie, `require_user`); `POST /auth/login`, `POST /auth/logout`,
    `GET /auth/me` (`app/api/auth.py`). Operator endpoints (create tank, acknowledge, simulate,
    imports commit, fish rename) now require a session; devices keep `X-Device-Key`. CORS allows
    credentials. Seed creates the `operator` account (password from `OPERATOR_PASSWORD`, default
    `letmein`). Frontend: cookie auth + operator-login form in `App.tsx`. Tests:
    `tests/test_auth.py` (3).
  - Audit log: `audit_log` table + migration `92be7bbac19c`; write-through `audit()`
    (`app/services/audit.py`) on `create_tank`, `update_fish`, `acknowledge`, `import_commit`.
    Tests: `tests/test_audit.py`.
  - Retention: `RETENTION_DAYS` setting (0 = off) + `delete_expired_readings`
    (`app/services/retention.py`) + `scripts/retain.py`. Tests: `tests/test_retention.py`.
  - Backup: `scripts/backup.sh` (copies the SQLite file, `pg_dump` for PostgreSQL).

All 33 backend tests pass; `npm run build` passes.

### Left

- **Phase 3 install — probes + gateway.** The gateway must post readings every 1–5 min to
  `POST /readings` with `X-Device-Key`; each device must be registered in `devices`. Farm
  decisions: which DO probe and which gateway (ESP32/RPi).
- **Phase 3b — SMS/phone-call notifications.** The treg catalog has no SMS-send or phone-call
  provider (`catalog_request`s filed: #3856 `sms.send`, #3855 `phone.call`). Needs the team to add
  a provider or use their own SMS bridge.
- **Phase 4 — CNN + farm photos.** The farm-scraped baseline doesn't match the farm's camera,
  lighting and species; needs the farm's own labelled photos (per class, e.g. healthy + the
  South-Asian carp diseases).
- **Phase 5 — validation on held-out nights.** Forecast error on real pre-dawn events; needs real
  sensors and watching actual overnight DO vs the forecast.
