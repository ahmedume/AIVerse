# src/app/routers/templates_router.py
# Purpose: template CRUD — per-user unique name, {input} placeholder enforced.
# Exports: router

import structlog
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionDep
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.dependencies import get_current_user
from app.models.user_model import User
from app.repositories import template_repo
from app.schemas.common import Envelope
from app.schemas.template_schema import (
    TEMPLATE_PLACEHOLDER,
    TemplateIn,
    TemplateOut,
    TemplateUpdateIn,
)

logger = structlog.get_logger()

router = APIRouter(tags=["templates"])


def _validate_placeholder(content: str) -> None:
    if TEMPLATE_PLACEHOLDER not in content:
        raise ValidationError(
            "Template content must contain {input}", "TEMPLATE_MISSING_PLACEHOLDER"
        )


async def _ensure_unique_name(
    session: AsyncSession, user_id: str, name: str, exclude_id: str | None = None
) -> None:
    existing = await template_repo.get_by_name(session, user_id, name)
    if existing is not None and existing.id != exclude_id:
        raise ConflictError("A template with this name already exists")


@router.post("/templates", status_code=201, response_model=Envelope[TemplateOut])
async def create_template(
    payload: TemplateIn,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> Envelope[TemplateOut]:
    _validate_placeholder(payload.content)
    await _ensure_unique_name(session, current_user.id, payload.name)
    template = await template_repo.create(
        session, current_user.id, name=payload.name, content=payload.content
    )
    await session.commit()
    logger.info("template.created", user_id=current_user.id, template_id=template.id)
    return Envelope(data=TemplateOut.model_validate(template))


@router.get("/templates", response_model=Envelope[list[TemplateOut]])
async def list_templates(
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> Envelope[list[TemplateOut]]:
    templates = await template_repo.list_by_user(session, current_user.id)
    return Envelope(data=[TemplateOut.model_validate(t) for t in templates])


@router.put("/templates/{template_id}", response_model=Envelope[TemplateOut])
async def update_template(
    template_id: str,
    payload: TemplateUpdateIn,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> Envelope[TemplateOut]:
    template = await template_repo.get_owned(session, template_id, current_user.id)
    if template is None:
        raise NotFoundError("Template not found")
    _validate_placeholder(payload.content)
    await _ensure_unique_name(session, current_user.id, payload.name, exclude_id=template.id)
    await template_repo.update(
        session, template, name=payload.name, content=payload.content
    )
    await session.commit()
    return Envelope(data=TemplateOut.model_validate(template))


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
) -> Response:
    template = await template_repo.get_owned(session, template_id, current_user.id)
    if template is None:
        raise NotFoundError("Template not found")
    await template_repo.remove(session, template)
    await session.commit()
    logger.info("template.deleted", user_id=current_user.id, template_id=template_id)
    return Response(status_code=204)