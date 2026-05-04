import os
import shutil
import tempfile

# IMPORTANT: configure env vars before importing the app, so settings pick them up.
_TMPDIR = tempfile.mkdtemp(prefix="webstalker-test-")
os.environ["WEBSTALKER_DATA_DIR"] = _TMPDIR
os.environ["WEBSTALKER_ENABLE_SCHEDULER"] = "false"

import pytest
from fastapi.testclient import TestClient

from webstalker.db import Base, engine, SessionLocal
from webstalker.main import app


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # Wipe blob dir between tests too.
    blob_dir = os.path.join(_TMPDIR, "blobs")
    if os.path.exists(blob_dir):
        shutil.rmtree(blob_dir, ignore_errors=True)
    os.makedirs(blob_dir, exist_ok=True)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
