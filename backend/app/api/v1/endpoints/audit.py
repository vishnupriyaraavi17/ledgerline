import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.user import User, UserRole
from backend.app.schemas.audit import (
    VerificationResult,
    AuditListResponse,
    AuditHeadResponse,
)
from backend.app.services.audit import audit_service
from backend.app.security.dependencies import require_role

router = APIRouter()


@router.get(
    "/verify",
    response_model=VerificationResult,
    summary="Cryptographic Chain Verification",
    description=(
        "Executes full mathematical verification of the SHA-256 linear hash chain. "
        "Streams all events from genesis to head holding a shared read lock (FOR SHARE), "
        "validating sequence continuity, parent hash linkage, and content integrity. "
        "Strictly restricted to Administrator and Auditor roles."
    ),
    responses={
        200: {"description": "Verification report successfully generated.", "model": VerificationResult},
        403: {"description": "Forbidden: Requires Administrator or Auditor role."},
    },
)
def verify_audit_chain(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role([UserRole.ADMIN, UserRole.AUDITOR])),
):
    return audit_service.verify_chain(db)


@router.get(
    "/events",
    response_model=AuditListResponse,
    summary="List Audit Events",
    description=(
        "Retrieves a paginated chronological list of immutable cryptographic audit records. "
        "Supports filtering by event type, entity type, entity ID, and actor ID. "
        "Strictly restricted to Administrator and Auditor roles."
    ),
    responses={
        200: {"description": "Paginated list of audit events.", "model": AuditListResponse},
        403: {"description": "Forbidden: Requires Administrator or Auditor role."},
    },
)
def list_audit_events(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    actor_id: Optional[uuid.UUID] = Query(None, description="Filter by actor user ID"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Offset"),
    db: Session = Depends(get_db),
    _user: User = Depends(require_role([UserRole.ADMIN, UserRole.AUDITOR])),
):
    return audit_service.list_events(
        db=db,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/head",
    response_model=AuditHeadResponse,
    summary="Get Chain Head Pointer",
    description=(
        "Retrieves the latest cryptographic chain head sequence number, hash, and timestamp. "
        "Strictly restricted to Administrator and Auditor roles."
    ),
    responses={
        200: {"description": "Current chain head metadata.", "model": AuditHeadResponse},
        403: {"description": "Forbidden: Requires Administrator or Auditor role."},
    },
)
def get_audit_head(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role([UserRole.ADMIN, UserRole.AUDITOR])),
):
    return audit_service.get_head(db)
