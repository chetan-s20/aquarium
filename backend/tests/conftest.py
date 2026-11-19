import os
import tempfile

# Must run before `app` is imported: point the app at a throwaway database.
_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["SIMULATION_MODE"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from scripts.seed import seed  # noqa: E402

DEVICE = {"X-Device-Key": "dev-device-key-change-me"}
OPERATOR = {"X-Operator-Key": "dev-operator-key-change-me"}


@pytest.fixture(scope="session")
def client():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db, hours=24)
    with TestClient(app) as c:
        yield c
