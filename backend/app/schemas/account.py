import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models.account import AccountType, AccountStatus


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=3, max_length=128, description="Account display name")
    account_type: AccountType = Field(..., description="Customer checking or savings account type")
    currency: str = Field(default="INR", description="Single supported currency code, strictly INR")
    owner_id: Optional[uuid.UUID] = Field(default=None, description="Owner user ID (Admin only)")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 3 or len(cleaned) > 128:
            raise ValueError("Account name must be between 3 and 128 characters")
        return cleaned

    @field_validator("account_type")
    @classmethod
    def validate_customer_account_type(cls, v: AccountType) -> AccountType:
        if v not in (AccountType.CUSTOMER_CHECKING, AccountType.CUSTOMER_SAVINGS):
            raise ValueError(
                f"Cannot create account with type '{v.value}'. Only customer accounts "
                f"('customer_checking', 'customer_savings') can be created via API."
            )
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if v.strip().upper() != "INR":
            raise ValueError("Only INR currency is supported")
        return "INR"


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_number: str
    owner_id: Optional[uuid.UUID]
    name: str
    account_type: AccountType
    currency: str
    balance: Decimal
    status: AccountStatus
    created_at: datetime
    updated_at: datetime


class AccountStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AccountStatus = Field(..., description="Target lifecycle status")


class AccountListResponse(BaseModel):
    items: List[AccountResponse]
    total: int
    skip: int
    limit: int
