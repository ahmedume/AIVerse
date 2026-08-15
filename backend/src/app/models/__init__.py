# src/app/models/__init__.py
# Purpose: model registry — imported by alembic autogenerate via app models metadata.
# Exports: User, UserSetting, Conversation, Message, Document, Template

from app.models.conversation_model import Conversation
from app.models.document_model import Document
from app.models.message_model import Message
from app.models.settings_model import UserSetting
from app.models.template_model import Template
from app.models.user_model import User

__all__ = ["User", "UserSetting", "Conversation", "Message", "Document", "Template"]