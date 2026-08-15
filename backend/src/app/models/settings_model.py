# src/app/models/settings_model.py
# Purpose: per-user preference row (1:1 with users, cascade delete).
# Exports: UserSetting

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.core.database import Base

settings = get_settings()


def utcnow() -> datetime:
    return datetime.now(UTC)


class UserSetting(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    default_provider: Mapped[str] = mapped_column(
        String(16), nullable=False, default=settings.DEFAULT_PROVIDER
    )
    default_model: Mapped[str] = mapped_column(
        String(64), nullable=False, default=settings.DEFAULT_MODEL
    )
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )