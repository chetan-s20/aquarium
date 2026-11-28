# FISHUT

Water-quality monitoring and **individual fish tracking** for fish farms. Water sensors and a tank camera
report around the clock. Staff see each tank's water in plain words, every fish in the tank, and a profile
for each fish: where it swam through the day, how active it was, and whether it behaves differently from
its tankmates (a sign it may be unwell). Analysts can download all water readings and every fish position.

The full problem statement, design, research and roadmap are in **[docs/PLAN.md](docs/PLAN.md)**; every
dataset used for training and testing (source, licence, split, known problems) is in **[docs/DATASETS.md](docs/DATASETS.md)**.

## What's in the repo

| Folder | What it is |
|---|---|
| `backend/` | FastAPI + SQLAlchemy + Alembic. Readings ingestion, quality checks, alert rules, CSV export, simulator |
| `frontend/` | React + Vite dashboard: tank page (water check + fish in the tank), fish profile pages, data download |
| `ml/` | OpenCV + ByteTrack fish tracker, tank activity meter, fish-disease image classifier |
| `docs/PLAN.md` | Plan, sources, roadmap |

Measured: **dissolved oxygen**, temperature, pH, turbidity, ammonium, plus camera-based fish activity and surface
activity. TDS is not used.

## Run it locally

You need Python 3.11+ and Node 20+.

```powershell
# 1. Backend  (http://127.0.0.1:8000, API docs at /docs)
cd backend
python -m pip install -r requirements.txt
copy ..\.env.example ..\.env          # optional: defaults work for local dev
python -m alembic upgrade head
python scripts/seed.py                # 2 demo tanks, 12 fish each, SIMULATED data
python -m uvicorn app.main:app --reload

# 2. Dashboard  (http://localhost:5173), in a second terminal
cd frontend
npm install
npm run dev
```

The dashboard shows a "Demo data" banner while `SIMULATION_MODE=true`. **Update demo data to now**
fills in simulated readings and fish movements since the last ones. Set `SIMULATION_MODE=false` once real sensors are
connected.

If you have an older `aquarium.db` (Phase 1 TDS sensors, or the `pond-a` / `nursery-b` demo tanks), delete or
rename it before running `alembic upgrade head` and the seed.

## Tracking individual fish

The tank camera watches the tank from the side. `ml/track_fish.py` finds every fish with OpenCV, follows
it from frame to frame with ByteTrack (Roboflow `trackers` library), keeps one id per fish through short
hides and crossings, and posts each fish's position every few seconds:

```powershell
# photo of the EMPTY tank from the same camera makes resting fish visible (recommended)
python ml/track_fish.py --source tank.mp4 --start 2026-11-19T06:00:00Z --tank tank-a --max-fish 12 `
    --background empty_tank.jpg --api http://127.0.0.1:8000 --csv tracks.csv
python ml/track_fish.py --source 0 --tank tank-a --max-fish 12 --background empty_tank.jpg --api http://127.0.0.1:8000
```

From those positions the server works out, per fish and per day: distance swum, time moving, time at
the surface and on the bottom, distance to the nearest fish, favourite area, size, and activity by
hour. **Health is judged by comparing each fish with its tankmates on the same day**, so it works for
any species without tuning: much less active, resting on the bottom, staying at the surface, keeping
apart from the group, or not seen for 2 hours. Each finding comes with a plain-language suggestion.
It is a prompt to look at the fish, not a diagnosis.

Known limit: when two similar fish cross, the tracker can swap their ids. If identity must be
guaranteed all day, run [TRex](https://trex.run) or [idtracker.ai](https://idtracker.ai) on the video
and post their per-fish trajectories to the same endpoint (below).

## Getting data out (for analysts)

Use the **Download data** panel in the dashboard, or call the API directly:

```
GET /export/readings.csv?tank_id=tank-a&start=2026-11-12T00:00:00Z&layout=wide&valid_only=true
GET /export/fish-positions.csv?tank_id=tank-a&start=2026-11-19T00:00:00Z
```

`fish-positions.csv` has one row per fish per sample: time, fish, `x`/`y` (0 to 1; `y` 0 = surface),
the same in cm, and body length.

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
`/readings?tank_id=&metric=&start=&end=`, `/alerts?tank_id=&status=`,
`/tanks/{id}/fish?day=YYYY-MM-DD` (every fish with behaviour and health),
`/fish/{id}?day=` (one fish with its route, favourite spots and hourly activity).

## Sending data in (devices)

```http
POST /readings
X-Device-Key: <DEVICE_API_KEY>
{"sensor_id": "tank-a-dissolved_oxygen", "value": 6.4, "observed_at": "2026-11-19T00:10:00Z"}

POST /tanks/tank-a/fish-positions
X-Device-Key: <DEVICE_API_KEY>
{"positions": [{"track_key": "7", "observed_at": "2026-11-19T00:10:00Z", "x": 0.42, "y": 0.18, "size": 0.07}]}
```

A new `track_key` becomes a new fish (named "Fish N"; staff can rename it, add notes, or mark it removed).

The server fills in tank, metric and unit from the registered sensor. It also marks out-of-range values
as invalid, rejects duplicates (409) and opens or resolves alerts. To bulk-load history, use
`POST /imports/preview` and then `/imports/commit` while logged in as an operator (session cookie).

**Over MQTT (ESP32 gateways).** `docker compose up` also starts a Mosquitto broker on port 1883 and
`scripts/mqtt_bridge.py`, which stores each message through `POST /readings`. A device logs in with
`MQTT_USER` / `MQTT_PASSWORD` and publishes one reading, or a JSON list of them, in the same JSON as
above, with QoS 1, to `fishut/readings/<device>`. Nothing is lost if the API is down: the bridge
acknowledges a message only after the API has stored it. To try it without hardware:

```powershell
docker compose run --rm --no-deps mqtt-bridge python scripts/fake_esp32.py --tank tank-a --every 60
```

## Camera and ML (`ml/`)

Install with `python -m pip install -r ml/requirements.txt` plus CPU PyTorch, or use the Docker image
(`docker build -t fishut-ml ml`; see [ml/README.md](ml/README.md)).

```powershell
# Fish behaviour from a fixed tank camera (OpenCV), posted to the dashboard:
python ml/fish_activity.py --source 0 --tank tank-a --api http://127.0.0.1:8000
python ml/fish_activity.py --source tank.mp4 --start 2026-11-19T05:00:00Z --csv activity.csv

# Fish-disease models (download the Kaggle images automatically, no login needed):
python ml/train_disease_classifier.py   # SVM vs Random Forest vs Logistic Regression
python ml/train_disease_cnn.py          # CNN (MobileNetV3), ~30 min on a 4-core CPU
python ml/predict_disease.py photo.jpg

# Early warning of low oxygen (3 h ahead), on real calibrated monitor data from USGS (public domain):
python ml/fetch_usgs.py --site 421401121480900
python ml/train_water_model.py --csv data/usgs/421401121480900.csv

# YOLO fish detector, then score it against the OpenCV detector on unseen fish:
python ml/train_fish_detector.py
python ml/benchmark_tracker.py --seq ZebraFish-02 --yolo ml/models/fish_yolo.pt
```

The disease CNN scores **92.8% over 7 classes** (random guessing: 14%) on test photos that never
appear in training; results for every model are in [ml/README.md](ml/README.md). These are web photos,
so treat any prediction as a hint to inspect a fish, not a diagnosis
([docs/PLAN.md §6](docs/PLAN.md#6-disease-model)).

**Photo check on the dashboard.** With a trained CNN, `docker compose --profile ml up` also starts
`ml/disease_service.py`. Logged-in staff can then take or upload a photo on a fish's page and see the
three most likely conditions.

## Tests

```powershell
cd backend; python -m pytest -q     # API, alerts, simulator, import, export, fish behaviour + health
cd ..; python -m pytest -q ml       # OpenCV tracker, activity meter and features

# Score the fish tracker on real zebrafish with hand-labelled identities (3D-ZeF20, front camera).
# Downloads ~0.5 GB of one sequence into data/zef/. Data is CC BY-NC-SA: internal testing only.
python ml/benchmark_tracker.py --seq ZebraFish-02
cd frontend; npm run build          # type-check and build
```

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./aquarium.db` | Use `postgresql+psycopg://...` in production |
| `SIMULATION_MODE` | `true` | Allows the simulator and shows the demo banner |
| `FARM_UTC_OFFSET_HOURS` | `5.5` | Puts the simulated dawn oxygen low at local dawn |
| `DEVICE_API_KEY` | dev value | Devices post readings with `X-Device-Key` |
| `OPERATOR_PASSWORD` | `letmein` | Password of the seeded `operator` account |
| `SECRET_KEY` | dev value | Signs operator session cookies |
| `CORS_ORIGINS` | localhost:5173 | Comma-separated dashboard origins |
| `MQTT_USER` / `MQTT_PASSWORD` | `fishut` / dev value | Broker login for devices and the bridge (docker compose) |
| `DISEASE_URL` | empty (off) | Photo checker service (`ml/disease_service.py`); compose sets it |

The frontend reads `VITE_API_BASE` and calls the API with the operator's session cookie, set on
login (the seeded `operator` account, password from `OPERATOR_PASSWORD`). Anyone can view the
dashboard; **Log in** (top right) is needed to mark alerts as seen, rename fish, save notes or update
demo data. Devices keep using `X-Device-Key`.

## Important caveats

- Alert limits are general warm-water pond guidance (Boyd 1982 / ICAR). Confirm them for your species.
- All demo readings are `source=simulator`. They are not measurements.
- `docker compose up` starts PostgreSQL, the API with the built dashboard (http://127.0.0.1:8000; it
  runs migrations and the demo seed on start), the MQTT broker and the bridge.
- Run the backend tests on PostgreSQL with `TEST_DATABASE_URL=postgresql+psycopg://...` pointing at an
  empty database; SQLite does not enforce foreign keys, so it misses insert-order bugs.
