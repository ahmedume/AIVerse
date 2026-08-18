# tests/conftest.py
# Purpose: shared fixtures — isolated DATA_DIR, FastAPI TestClient.

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="aiverse_test_")
os.environ["DATA_DIR"] = _TMP
os.environ["APP_ENV"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c