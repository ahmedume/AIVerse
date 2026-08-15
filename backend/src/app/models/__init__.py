# src/app/models/__init__.py
# Purpose: model registry — imported by alembic autogenerate via app models metadata.
# Exports: User, UserSetting

from app.models.settings_model import UserSetting
from app.models.user_model import User

__all__ = ["User", "UserSetting"]