# src/app/schemas/template_schema.py
# Purpose: template request/response contracts.
# Exports: TemplateIn, TemplateUpdateIn, TemplateOut

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

TEMPLATE_PLACEHOLDER = "{input}"


class TemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=4000)


class TemplateUpdateIn(TemplateIn):
    pass


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    content: str
    created_at: datetime
    updated_at: datetime