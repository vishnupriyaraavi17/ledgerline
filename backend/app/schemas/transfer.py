import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.models.ledger import TransactionType
from backend.app.schemas.ledger import LedgerEntryResponse


def validate_monetary_amount(v: Decimal) -> Decimal:
    if v <= Decimal("0.00"):
        raise ValueError("Amount must be strictly greater than 0.00 INR")
    # Enforce maximum 2 decimal places (exact paise precision)
    # as_tuple().exponent gives negative of decimal places
    exponent = v.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValueError("Amount cannot have more than 2 decimal places (exact paise precision)")
    return v


class DepositRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: uuid.UUID = Field(..., description="Target customer account ID to credit")
    amount: Decimal = Field(..., description="Deposit amount in INR (positive, max 2 decimal places)")
    description: Optional[str] = Field(default=None, max_length=255, description="Optional transaction memo")

    @field_validator("amount")
    @classmethod
    def check_amount(cls, v: Decimal) -> Decimal:
        return validate_monetary_amount(v)


class WithdrawRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: uuid.UUID = Field(..., description="Source customer account ID to debit")
    amount: Decimal = Field(..., description="Withdrawal amount in INR (positive, max 2 decimal places)")
    description: Optional[str] = Field(default=None, max_length=255, description="Optional transaction memo")

    @field_validator("amount")
    @classmethod
    def check_amount(cls, v: Decimal) -> Decimal:
        return validate_monetary_amount(v)


class TransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_account_id: uuid.UUID = Field(..., description="Source customer account ID to debit")
    destination_account_id: uuid.UUID = Field(..., description="Destination customer account ID to credit")
    amount: Decimal = Field(..., description="Transfer amount in INR (positive, max 2 decimal places)")
    description: Optional[str] = Field(default=None, max_length=255, description="Optional transaction memo")

    @field_validator("amount")
    @classmethod
    def check_amount(cls, v: Decimal) -> Decimal:
        return validate_monetary_amount(v)

    @model_validator(mode="after")
    def check_distinct_accounts(self) -> "TransferRequest":
        if self.source_account_id == self.destination_account_id:
            raise ValueError("Source and destination accounts must be distinct. Self-transfers are prohibited.")
        return self


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    transaction_type: TransactionType
    description: str
    posted_at: datetime
    entries: List[LedgerEntryResponse] = []


class TransactionListResponse(BaseModel):
    items: List[TransactionResponse]
    total: int
    skip: int
    limit: int
