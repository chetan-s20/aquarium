# Pond monitor

Water-quality and fish-behaviour monitoring for fish farms. Sensors and a tank camera report around the
clock. Staff are warned before dissolved oxygen falls to dangerous levels, usually just before dawn,
and analysts can download the full history to study how fish behaviour relates to water quality.

The full problem statement, design, research and roadmap are in **[docs/PLAN.md](docs/PLAN.md)**.

## What's in the repo

| Folder | What it is |
|---|---|
| `backend/` | FastAPI + SQLAlchemy + Alembic. Readings ingestion, quality checks, alert rules, CSV export, simulator |
| `frontend/` | React + Vite dashboard: oxygen panel, alerts, sensor readouts, behaviour view, data download |
| `ml/` | OpenCV fish-activity meter for the tank camera, plus the fish-disease image classifier |
| `docs/PLAN.md` | Plan, sources, roadmap |

Measured: **dissolved oxygen**, temperature, pH, turbidity, plus camera-based fish activity and surface
activity. TDS is not used.

## Run it locally

You need Python 3.11+ and Node 20+.

```powershell
# 1. Backend  (http://127.0.0.1:8000, API docs at /docs)
cd backend
python -m pip install -r requirements.txt
copy ..\.env.example ..\.env          # optional: defaults work for local dev
python -m alembic upgrade head
python scripts/seed.py                # 2 demo ponds + 7 days of SIMULATED data
python -m uvicorn app.main:app --reload

# 2. Dashboard  (http://localhost:5173), in a second terminal
cd frontend
npm install
npm run dev
```

The dashboard shows a "Demo data" banner while `SIMULATION_MODE=true`. **Generate readings up to now**
fills in simulated readings since the last one. Set `SIMULATION_MODE=false` once real sensors are
connected.

If you have an `aquarium.db` from the old Phase 1 code (it contains TDS sensors), delete or rename it
before running `alembic upgrade head`.

## Getting data out (for analysts)

Use the **Download data** panel in the dashboard, or call the API directly:

```
GET /export/readings.csv?tank_id=pond-a&start=2026-11-12T00:00:00Z&layout=wide&valid_only=true
```

- `layout=wide`: one row per tank and time, with a column per measurement. Best for comparing oxygen
  with fish behaviour.
- `layout=long`: one row per reading, including `quality_status` and `source`.
- Filters: `tank_id` and `metric` (both repeatable), `start`, `end`, `valid_only`.

```python
import pandas as pd
df = pd.read_csv("http://127.0.0.1:8000/export/readings.csv?layout=wide&valid_only=true", parse_dates=["observed_at"])
df.groupby("tank_name")[["dissolved_oxygen", "surface_activity"]].corr()
```

Other read endpoints: `GET /tanks`, `/tanks/{id}/sensors`, `/tanks/{id}/thresholds`,
`/readings?tank_id=&metric=&start=&end=`, `/alerts?tank_id=&status=`.

## Sending data in (devices)

```http
POST /readings
X-Device-Key: <DEVICE_API_KEY>
{"sensor_id": "pond-a-dissolved_oxygen", "value": 6.4, "observed_at": "2026-11-19T00:10:00Z"}
```

The server fills in tank, metric and unit from the registered sensor. It also marks out-of-range values
as invalid, rejects duplicates (409) and opens or resolves alerts. To bulk-load history, use
`POST /imports/preview` and then `/imports/commit` with an `X-Operator-Key` header.

## Camera and ML (`ml/`)

```powershell
python -m pip install -r ml/requirements.txt

# Fish behaviour from a fixed tank camera (OpenCV), posted to the dashboard:
python ml/fish_activity.py --source 0 --tank pond-a --api http://127.0.0.1:8000
python ml/fish_activity.py --source tank.mp4 --start 2026-11-19T05:00:00Z --csv activity.csv

# Fish-disease classifier (downloads the Kaggle dataset automatically, no login needed):
python ml/download_dataset.py
python ml/train_disease_classifier.py
python ml/predict_disease.py photo.jpg
```

About the dataset: it is a folder of images, so it is loaded with `kagglehub.dataset_download()`, not
the `PANDAS` adapter, which only reads table files. Every image in its official Test split is an exact
copy of a Train image, so the training script scores the model on a de-duplicated hold-out instead.
The current OpenCV + SVM baseline reaches **53% accuracy over 7 classes** (random guessing gives 14%).
Treat it as a hint to inspect a fish, not a diagnosis. The path to a usable model is in
[docs/PLAN.md §6](docs/PLAN.md#6-disease-model).

## Tests

```powershell
cd backend; python -m pytest -q     # API, alerts, simulator, import, export
cd ..; python -m pytest -q ml       # OpenCV activity meter and features
cd frontend; npm run build          # type-check and build
```

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./aquarium.db` | Use `postgresql+psycopg://...` in production |
| `SIMULATION_MODE` | `true` | Allows the simulator and shows the demo banner |
| `FARM_UTC_OFFSET_HOURS` | `5.5` | Puts the simulated dawn oxygen low at local dawn |
| `DEVICE_API_KEY` / `OPERATOR_API_KEY` | dev values | **Change before any shared deployment** |
| `CORS_ORIGINS` | localhost:5173 | Comma-separated dashboard origins |

The frontend reads `VITE_API_BASE` and `VITE_OPERATOR_KEY`. The operator key is built into the
dashboard bundle, so keep the dashboard on the farm network until login is added (Phase 6).

## Important caveats

- Alert limits are general warm-water pond guidance (Boyd 1982 / ICAR). Confirm them for your species.
- All demo readings are `source=simulator`. They are not measurements.
- `docker compose up` starts PostgreSQL and the API (it runs migrations on start); the dashboard is run
  separately.
