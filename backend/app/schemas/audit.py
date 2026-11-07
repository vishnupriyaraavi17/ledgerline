import uuid
from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict


class TamperFailureType(str, Enum):
    HASH_MISMATCH = "HASH_MISMATCH"
    BROKEN_CHAIN = "BROKEN_CHAIN"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    HEAD_DESYNC = "HEAD_DESYNC"


class TamperDetail(BaseModel):
    failure_type: TamperFailureType
    sequence_number: int
    event_id: Optional[str] = None
    expected_value: str
    actual_value: str
    message: str


class VerificationResult(BaseModel):
    is_valid: bool
    total_events: int
    verified_at: datetime
    head_sequence: int
    head_hash: str
    tamper_details: Optional[TamperDetail] = None


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence_number: int
    event_type: str
    actor_id: Optional[uuid.UUID] = None
    actor_role: Optional[str] = None
    entity_type: str
    entity_id: str
    payload: Dict[str, Any]
    prev_hash: str
    current_hash: str
    created_at: datetime


class AuditListResponse(BaseModel):
    items: List[AuditEventResponse]
    total: int
    limit: int
    offset: int


class AuditHeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence_number: int
    current_hash: str
    updated_at: datetime
