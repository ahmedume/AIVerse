# src/app/schemas/conversation_schema.py
# Purpose: conversation/message request + response contracts.
# Exports: ChatIn, ConversationCreateIn, ConversationUpdateIn, ConversationOut,
#          ConversationDetailOut, MessageOut

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AgentType = Literal["chat", "rag", "agent", "textgen"]


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = None
    message: str = Field(default="", max_length=10_000)
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None
    regenerate: bool = False


class ConversationCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_type: AgentType = "chat"
    provider: str | None = None
    model: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)


class ConversationUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    token_count: int
    created_at: datetime


class ConversationOut(BaseModel):
    id: str
    title: str
    agent_type: str
    provider: str
    model: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]