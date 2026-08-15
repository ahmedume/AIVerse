# src/app/core/database.py
# Purpose: async SQLAlchemy engine (SQLite WAL by default; Postgres-ready via DATABASE_URL).
# Exports: Base, engine, AsyncSessionFactory, get_session, SessionDep

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_connect_args: dict[str, object] = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}


class _WALEmitter:
    """Enables SQLite WAL mode at connect time (engine-level via SQLAlchemy event)."""

    def __init__(self, engine_url: str) -> None:
        if engine_url.startswith("sqlite"):
            from sqlalchemy import event

            event.listen(engine.sync_engine, "connect", self._set_wal)

    @staticmethod
    def _set_wal(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=_connect_args,
    pool_pre_ping=True,
)
_WALEmitter(settings.DATABASE_URL)

AsyncSessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]