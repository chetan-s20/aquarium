# Aquarium Monitoring System (Phase 1)

Backend foundation for an aquaculture water-quality monitoring product. Phase 1 provides the canonical data model, migrations, health check, and clearly labeled simulated seed data. No real hardware is connected.

## Quick start (backend)
```powershell
cd backend
python -m pip install -r requirements.txt
copy ..\.env.example ..\.env
python -m alembic upgrade head
python scripts/seed_demo.py
python scripts/seed_thresholds.py
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs and http://127.0.0.1:8000/health

## Security (prototype)
- Device writes require `X-Device-Key`.
- Operator actions (simulate, import commit, alert ack) require `X-Operator-Key`.
- Replace default keys in `.env` before any shared deployment.
- Use HTTPS/TLS in production and restrict CORS origins.

## Configuration
Copy `.env.example` to `.env`. Key variables: `DATABASE_URL`, `SIMULATION_MODE`, `DEFAULT_TIMEZONE`.

## Tests
```powershell
cd backend
python -m pytest -q
```

## Notes
- All seed readings are `source=simulator` and are not real measurements.
- Thresholds are provisional placeholders; replace with species-specific values before operational use.
- PostgreSQL is supported via `DATABASE_URL`; local dev defaults to SQLite.
