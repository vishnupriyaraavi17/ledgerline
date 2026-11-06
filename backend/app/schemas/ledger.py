import uuid
from datetime import datetime
from decimal import Decimal
from typing import List
from pydantic import BaseModel, ConfigDict

from backend.app.models.ledger import EntryType, TransactionType


class LedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    transaction_id: uuid.UUID
    account_id: uuid.UUID
    entry_type: EntryType
    amount: Decimal
    sequence: int
    created_at: datetime


class LedgerTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    transaction_type: TransactionType
    description: str
    posted_at: datetime
    entries: List[LedgerEntryResponse] = []


class LedgerEntryListResponse(BaseModel):
    items: List[LedgerEntryResponse]
    total: int
    skip: int
    limit: int
