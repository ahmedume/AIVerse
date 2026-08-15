# backend/tests/conftest.py
# Purpose: test isolation — in-memory DB per test, fresh app per test, env pinned
#          BEFORE any app import so Settings picks them up.
# Exports: db_engine, client (fixtures)

import os
import tempfile
from pathlib import Path

os.environ["APP_ENV"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef-0123456789"
os.environ["AUTH_RATE_LIMIT"] = "1000/minute"
os.environ["REFRESH_RATE_LIMIT"] = "1000/minute"
os.environ["CHAT_RATE_LIMIT"] = "1000/minute"
os.environ["DOCUMENT_RATE_LIMIT"] = "1000/hour"
os.environ["MAX_UPLOAD_BYTES"] = "2048"
os.environ["DATA_DIR"] = str(Path(tempfile.gettempdir()) / "nexus-tests-data")
os.environ["CORS_ORIGINS"] = "http://localhost:3000"

import pytest  # noqa: E402
from fastapi import Depends  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import Base, get_session  # noqa: E402
from app.dependencies import require_admin  # noqa: E402
from app.main import create_app  # noqa: E402

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_engine():
    engine = create_async_engine(
        TEST_DB_URL,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def client(db_engine):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    app = create_app()

    app.get("/_test_admin", dependencies=[Depends(require_admin)])(
        lambda: {"ok": True}
    )

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c