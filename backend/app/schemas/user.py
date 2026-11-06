import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from backend.app.models.user import UserRole


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, description="Unique username")
    email: EmailStr = Field(..., description="Unique email address")

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not cleaned:
            raise ValueError("Username cannot be empty")
        if not cleaned.isalnum() and not all(c.isalnum() or c in "_-" for c in cleaned):
            raise ValueError("Username can only contain alphanumeric characters, underscores, and hyphens")
        return cleaned

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128, description="Plaintext password")
    role: UserRole = Field(default=UserRole.ACCOUNT_HOLDER, description="Assigned authorization role")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: UserRole
    is_active: bool
    created_at: datetime


class UserListResponse(BaseModel):
    items: List[UserResponse]
    total: int
    skip: int
    limit: int


class LoginRequest(BaseModel):
    username_or_email: str = Field(..., description="Username or email address")
    password: str = Field(..., description="Password")

    @field_validator("username_or_email")
    @classmethod
    def normalize_identifier(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="Signed JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    user: UserResponse = Field(..., description="Authenticated user profile")
