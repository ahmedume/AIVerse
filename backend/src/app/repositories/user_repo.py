# src/app/repositories/user_repo.py
# Purpose: data access for users + user_settings.
# Exports: get_by_id, get_by_email, create, count_users, get_settings, ensure_settings

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings_model import UserSetting
from app.models.user_model import User


async def get_by_id(session: AsyncSession, user_id: str) -> User | None:
    return await session.get(User, user_id)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    email: str,
    password_hash: str,
    role: str,
    name: str | None = None,
) -> User:
    user = User(email=email, password_hash=password_hash, role=role, name=name)
    session.add(user)
    await session.flush()
    session.add(UserSetting(user_id=user.id))
    return user


async def count_users(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(User.id)))
    return int(result.scalar_one())


async def get_settings(session: AsyncSession, user_id: str) -> UserSetting | None:
    return await session.get(UserSetting, user_id)


async def ensure_settings(session: AsyncSession, user_id: str) -> UserSetting:
    existing = await get_settings(session, user_id)
    if existing:
        return existing
    row = UserSetting(user_id=user_id)
    session.add(row)
    await session.flush()
    return row