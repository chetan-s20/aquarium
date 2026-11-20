"""Apply the retention policy: delete readings older than RETENTION_DAYS.

Run after setting RETENTION_DAYS (0 = disabled):  python scripts/retain.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.services.retention import delete_expired_readings


if __name__ == "__main__":
    with SessionLocal() as db:
        n = delete_expired_readings(db)
    print(f"Deleted {n} reading(s) older than RETENTION_DAYS.")
