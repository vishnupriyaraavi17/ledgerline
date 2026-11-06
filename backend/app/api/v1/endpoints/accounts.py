import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.user import User, UserRole
from backend.app.schemas.account import (
    AccountCreate,
    AccountResponse,
    AccountStatusUpdate,
    AccountListResponse,
)
from backend.app.schemas.ledger import LedgerEntryListResponse
from backend.app.services.account import account_service
from backend.app.security.dependencies import get_current_user, require_role

router = APIRouter()


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create New Customer Account",
    description=(
        "Provisions a new customer account (checking or savings) with initial ₹0.00 balance. "
        "Account Holders can create accounts for themselves. "
        "Administrators can create accounts for any registered customer. "
        "Auditors are rejected with HTTP 403 Forbidden."
    ),
    responses={
        201: {"description": "Account successfully created.", "model": AccountResponse},
        403: {"description": "Forbidden: Auditors cannot create accounts."},
        422: {"description": "Unprocessable Entity: Invalid account type or currency."},
    },
)
def create_account(
    account_in: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = account_service.create_account(db, current_user, account_in)
    return account


@router.get(
    "",
    response_model=AccountListResponse,
    summary="List Accounts",
    description=(
        "Retrieves a paginated list of accounts. "
        "Account Holders receive only their own accounts. "
        "Administrators and Auditors receive all accounts system-wide."
    ),
    responses={
        200: {"description": "Paginated list of accounts.", "model": AccountListResponse},
    },
)
def list_accounts(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = account_service.list_accounts_for_user(
        db, current_user, skip=skip, limit=limit
    )
    return AccountListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get(
    "/{id}",
    response_model=AccountResponse,
    summary="Get Account Details",
    description=(
        "Retrieves details for a specific account. "
        "Account Holders can only view their own accounts; attempting to view another "
        "user's account returns HTTP 404 Not Found (anti-enumeration protection). "
        "Administrators and Auditors can view any account."
    ),
    responses={
        200: {"description": "Account details.", "model": AccountResponse},
        404: {"description": "Not Found: Account does not exist or user does not own it."},
    },
)
def get_account(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return account_service.get_account_for_user(db, current_user, id)


@router.patch(
    "/{id}/status",
    response_model=AccountResponse,
    summary="Update Account Lifecycle Status (Admin Only)",
    description=(
        "Transitions account lifecycle status (Active <-> Frozen, Active/Frozen -> Closed). "
        "Closing an account strictly requires a balance of exactly ₹0.00. "
        "Closed accounts are terminal and cannot be reopened. "
        "Account Holders and Auditors are rejected with HTTP 403 Forbidden."
    ),
    responses={
        200: {"description": "Status successfully updated.", "model": AccountResponse},
        400: {"description": "Bad Request: Invalid lifecycle transition or non-zero balance closure."},
        403: {"description": "Forbidden: Requires Administrator role."},
        404: {"description": "Not Found: Account does not exist."},
    },
)
def update_account_status(
    id: uuid.UUID,
    status_in: AccountStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
):
    return account_service.update_account_status(db, admin, id, status_in.status)


@router.get(
    "/{id}/ledger",
    response_model=LedgerEntryListResponse,
    summary="Get Account Ledger Entries",
    description=(
        "Retrieves paginated ledger entries for a specific account. "
        "Account Holders can view ledger entries for their own accounts only; "
        "viewing non-owned accounts returns HTTP 404 Not Found (anti-enumeration). "
        "Administrators and Auditors can view ledger entries for any account."
    ),
    responses={
        200: {"description": "Paginated list of ledger entries.", "model": LedgerEntryListResponse},
        404: {"description": "Not Found: Account does not exist or user does not own it."},
    },
)
def get_account_ledger(
    id: uuid.UUID,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = account_service.get_account_ledger(
        db, current_user, id, skip=skip, limit=limit
    )
    return LedgerEntryListResponse(items=items, total=total, skip=skip, limit=limit)
