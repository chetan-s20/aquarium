# Phase 1 - Repository, Dataset, and Foundation

## Repository state
- The repository was empty at start (no commits, no files).
- `Fishut_Dataset/` was not present on this machine. No CSVs found. This is a documented gap; no dataset fields were invented.
- Development environment: Python 3.11.9, Node 24.18.0, PostgreSQL 18.4 installed (auth not available to this user), no Docker.

## Provisional assumptions
1. Five candidate sensors only (temperature, pH, TDS, turbidity, dissolved oxygen) are unconfirmed candidates.
2. No real hardware connected; all seed readings are `source=simulator` and are not measurements.
3. SQLite is used for local development because PostgreSQL credentials are unavailable in this environment. SQLAlchemy models and Alembic migrations are written to be PostgreSQL-compatible; `DATABASE_URL` can be switched to PostgreSQL without model changes.
4. Thresholds in `config/sensors.example.yaml` are placeholders, not operational limits.
5. Species/life stage/tank count unconfirmed.
6. Timezone: UTC internally; display timezone configurable.

## Architecture (text)
Sensors -> Edge gateway -> (MQTT/HTTPS) -> FastAPI ingestion -> (SQLite/PostgreSQL) -> React dashboard + alerts
Optional camera/ML module is separate and not implemented.

## Canonical schema
Tables: tanks, devices, sensors, calibrations, readings, thresholds, alerts, import_runs, media_assets, labels.
Readings keep observed_at (event time), received_at (ingestion time), value, unit, quality_status, quality_rule_version, calibration_id, source, raw_value, raw_payload, import_run_id.

## Phase 1 acceptance criteria
- Backend starts and `/health` returns ok.
- Database migration creates all tables.
- Seed script inserts clearly labeled SIMULATED readings.
- No source data overwritten (none present).
- Tests pass.
- Assumptions documented.

## Dataset note (camera/ML, optional)
- User provided Kaggle dataset: "Freshwater Fish Disease Aquaculture in South Asia" (subirbiswas19).
- 7 classes, ~2,444 images; image classification of fish disease, not sensor telemetry.
- No download performed (no Kaggle credentials in this environment); no model trained or evaluated.
- See `ml/README.md` and `ml/train_image_classifier.py`.

## Risks / open items
- Dataset not available; CSV import contract deferred.
- PostgreSQL not exercised locally; migration syntax should be validated when credentials are available.
- No authentication or real device connectivity implemented yet.
- Camera/ML not implemented.
