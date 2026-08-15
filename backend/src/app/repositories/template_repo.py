# src/app/repositories/template_repo.py
# Purpose: data access for templates, always scoped by user_id.
# Exports: create, list_by_user, get_owned, get_by_name, update, remove

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template_model import Template


async def create(
    session: AsyncSession, user_id: str, *, name: str, content: str
) -> Template:
    template = Template(user_id=user_id, name=name, content=content)
    session.add(template)
    await session.flush()
    return template


async def list_by_user(session: AsyncSession, user_id: str) -> list[Template]:
    result = await session.execute(
        select(Template)
        .where(Template.user_id == user_id)
        .order_by(Template.name, Template.id)
    )
    return list(result.scalars())


async def get_owned(
    session: AsyncSession, template_id: str, user_id: str
) -> Template | None:
    result = await session.execute(
        select(Template).where(Template.id == template_id, Template.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_by_name(
    session: AsyncSession, user_id: str, name: str
) -> Template | None:
    result = await session.execute(
        select(Template).where(Template.user_id == user_id, Template.name == name)
    )
    return result.scalar_one_or_none()


async def update(
    session: AsyncSession, template: Template, *, name: str, content: str
) -> None:
    template.name = name
    template.content = content
    await session.flush()


async def remove(session: AsyncSession, template: Template) -> None:
    await session.delete(template)
    await session.flush()