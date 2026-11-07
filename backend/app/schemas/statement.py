import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.schemas.account import AccountResponse


class StatementTransactionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entry_id: uuid.UUID
    transaction_id: uuid.UUID
    reference: str
    transaction_type: str = Field(..., description="Internal transaction type (settlement, transfer, adjustment)")
    display_label: str = Field(..., description="User-facing operation label (Deposit, Withdrawal, Transfer In, Transfer Out)")
    direction: str = Field(..., description="'credit' (inflow) or 'debit' (outflow) from this account's perspective")
    amount: Decimal = Field(..., description="Transaction amount in INR")
    currency: str = Field(default="INR", description="Single supported currency code, strictly INR")
    running_balance: Decimal = Field(..., description="Resulting account balance after this transaction")
    status: str = Field(default="posted", description="Ledger posting status")
    description: str
    posted_at: datetime
    counterparty_account_number: Optional[str] = None
    counterparty_name: Optional[str] = None


class RefusedAttemptItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    operation_type: str = Field(..., description="'deposit', 'withdraw', or 'transfer'")
    amount: Optional[Decimal] = None
    currency: str = Field(default="INR")
    refusal_reason: str = Field(..., description="Controlled machine-readable refusal code")
    error_message: str = Field(..., description="Sanitized client-safe description of the refusal")
    is_source: bool = Field(default=True, description="True if this account was the initiator/source; False if destination")
    counterparty_account_number: Optional[str] = None
    outcome: str = Field(default="refused")
    created_at: datetime


class StatementSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    opening_balance: Decimal = Field(..., description="Account balance immediately prior to start_date")
    closing_balance: Decimal = Field(..., description="Account balance at end_date (opening + net_change)")
    total_credits: Decimal = Field(..., description="Sum of all credit inflows during the period")
    total_debits: Decimal = Field(..., description="Sum of all debit outflows during the period")
    net_change: Decimal = Field(..., description="Net balance change during the period (total_credits - total_debits)")
    total_posted_transactions: int = Field(..., description="Total number of posted transactions in the requested period")
    total_refused_attempts: int = Field(..., description="Total number of refused operation attempts in the requested period")


class StatementPeriod(BaseModel):
    start_date: datetime
    end_date: datetime

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC required)")
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_interval(self) -> "StatementPeriod":
        if self.start_date >= self.end_date:
            raise ValueError(f"start_date ({self.start_date.isoformat()}) must be strictly earlier than end_date ({self.end_date.isoformat()})")
        return self


class AccountStatementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account: AccountResponse
    period: StatementPeriod
    summary: StatementSummary
    transactions: List[StatementTransactionItem]
    refused_attempts: List[RefusedAttemptItem]
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    total_pages: int = Field(..., ge=1)
