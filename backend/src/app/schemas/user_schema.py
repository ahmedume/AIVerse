# src/app/schemas/user_schema.py
# Purpose: auth request/response DTOs (Pydantic v2).
# Exports: RegisterIn, LoginIn, UserOut, SettingsOut, MeOut

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_EMAIL_MAX = 254
_PASSWORD_MIN = 8
_PASSWORD_MAX = 128
# bcrypt only uses the first 72 bytes — reject anything longer outright.
_BCRYPT_MAX_BYTES = 72


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=_EMAIL_MAX)
    password: str = Field(min_length=_PASSWORD_MIN, max_length=_PASSWORD_MAX)
    name: str | None = Field(default=None, max_length=100)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return value.strip() if value else None

    @field_validator("password")
    @classmethod
    def enforce_bcrypt_max(cls, value: str) -> str:
        if len(value.encode("utf-8")) > _BCRYPT_MAX_BYTES:
            raise ValueError("Password must be at most 72 bytes")
        return value


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=_EMAIL_MAX)
    password: str = Field(min_length=1, max_length=_PASSWORD_MAX)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str | None
    role: str
    is_active: bool
    created_at: datetime


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    default_provider: str
    default_model: str
    temperature: float


class MeOut(BaseModel):
    user: UserOut
    settings: SettingsOut
    providers: dict[str, bool]