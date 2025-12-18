from uuid import UUID

from fastapi_users import schemas
from pydantic import BaseModel, EmailStr, Field, computed_field, field_validator

from app.core.config import get_settings


class UserRead(schemas.BaseUser[UUID]):
    username: str
    daily_message_limit: int | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def email_verification_required(self) -> bool:
        return get_settings().REQUIRE_EMAIL_VERIFICATION


class UserCreate(schemas.BaseUserCreate):
    username: str
    password: str = Field(..., min_length=8)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not v:
            raise ValueError("Username is required")
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters long")
        if len(v) > 30:
            raise ValueError("Username must be less than 30 characters long")
        if not v.replace("_", "").isalnum():
            raise ValueError(
                "Username can only contain letters, numbers, and underscores"
            )
        if v.startswith("_") or v.endswith("_"):
            raise ValueError("Username cannot start or end with underscore")
        return v


class UserUpdate(schemas.BaseUserUpdate):
    username: str | None = None
    daily_message_limit: int | None = None


class UserBase(BaseModel):
    email: EmailStr
    username: str


class UserOut(UserBase):
    id: UUID
    is_verified: bool
    daily_message_limit: int | None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class TokenData(BaseModel):
    email: str | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class SignupResponse(BaseModel):
    message: str
    email: str
    verification_required: bool
    access_token: str | None = None


class VerifyEmailRequest(BaseModel):
    token: str
    email: str


class VerifyEmailResponse(BaseModel):
    message: str
    access_token: str | None = None


class ResendVerificationRequest(BaseModel):
    email: str


class ResendVerificationResponse(BaseModel):
    message: str


class UserUsage(BaseModel):
    messages_used_today: int
    daily_message_limit: int | None
    messages_remaining: int


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    success: bool
    message: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)


class ResetPasswordResponse(BaseModel):
    success: bool
    message: str
