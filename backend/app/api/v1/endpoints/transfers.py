from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.schemas.transfer import (
    DepositRequest,
    WithdrawRequest,
    TransferRequest,
    TransactionResponse,
    TransactionListResponse,
)
from backend.app.services.transfer import transfer_service
from backend.app.security.dependencies import get_current_user

router = APIRouter()


def validate_idempotency_key(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
) -> str:
    """
    Validates the client-supplied Idempotency-Key HTTP header:
    - Must be provided and non-empty.
    - Length must be between 8 and 128 characters.
    - Must contain only printable ASCII characters without whitespace (ASCII 33 to 126).
    Rejects violations with HTTP 400 Bad Request.
    """
    if idempotency_key is None or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required and cannot be empty",
        )
    key = idempotency_key.strip()
    if len(key) < 8 or len(key) > 128:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must be between 8 and 128 characters in length",
        )
    if not all(32 < ord(c) <= 126 for c in key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must consist of printable ASCII characters without whitespace",
        )
    return key


@router.post(
    "/deposit",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Deposit Funds (Simulated External Settlement)",
    description=(
        "Deposits simulated funds in INR into a customer checking or savings account. "
        "Creates a balanced double-entry settlement transaction: "
        "DEBIT ACC-SYSTEM02 (Internal Clearing), CREDIT Customer Account. "
        "Account Holders can only deposit into accounts they own. "
        "Administrators can deposit into any customer account. "
        "Auditors are rejected with HTTP 403 Forbidden. "
        "Guarded by database-backed idempotency."
    ),
    responses={
        201: {"description": "Deposit successful.", "model": TransactionResponse},
        400: {"description": "Bad Request: Account not active, invalid account type, or missing/invalid Idempotency-Key."},
        403: {"description": "Forbidden: Auditors cannot perform deposits."},
        404: {"description": "Not Found: Account does not exist or user does not own it."},
        409: {"description": "Conflict: Idempotency key previously used with different parameters."},
    },
)
def deposit(
    req: DepositRequest,
    response: Response,
    idempotency_key: str = Depends(validate_idempotency_key),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result, is_replay = transfer_service.deposit(
        db, current_user, req, idempotency_key=idempotency_key
    )
    if is_replay:
        response.headers["Idempotent-Replay"] = "true"
    return result


@router.post(
    "/withdraw",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Withdraw Funds (Simulated External Settlement)",
    description=(
        "Disburses funds in INR from a customer checking or savings account. "
        "Creates a balanced double-entry settlement transaction: "
        "DEBIT Customer Account, CREDIT ACC-SYSTEM02 (Internal Clearing). "
        "Guarded by deterministic row locking, balance sufficiency check, and idempotency deduplication. "
        "Account Holders can only withdraw from accounts they own. "
        "Administrators can withdraw from any customer account. "
        "Auditors are rejected with HTTP 403 Forbidden."
    ),
    responses={
        201: {"description": "Withdrawal successful.", "model": TransactionResponse},
        400: {"description": "Bad Request: Insufficient funds, account not active, or missing/invalid Idempotency-Key."},
        403: {"description": "Forbidden: Auditors cannot perform withdrawals."},
        404: {"description": "Not Found: Account does not exist or user does not own it."},
        409: {"description": "Conflict: Idempotency key previously used with different parameters."},
    },
)
def withdraw(
    req: WithdrawRequest,
    response: Response,
    idempotency_key: str = Depends(validate_idempotency_key),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result, is_replay = transfer_service.withdraw(
        db, current_user, req, idempotency_key=idempotency_key
    )
    if is_replay:
        response.headers["Idempotent-Replay"] = "true"
    return result


@router.post(
    "/transfer",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Transfer Funds (Customer to Customer)",
    description=(
        "Transfers funds in INR between two distinct customer accounts with zero-sum money conservation. "
        "Creates a balanced double-entry transfer transaction: "
        "DEBIT Source Account, CREDIT Destination Account. "
        "Guarded by deterministic row locking to prevent deadlocks and race conditions. "
        "Account Holders can only transfer from accounts they own. "
        "Administrators can transfer between any customer accounts. "
        "Auditors are rejected with HTTP 403 Forbidden. "
        "Guarded by database-backed idempotency."
    ),
    responses={
        201: {"description": "Transfer successful.", "model": TransactionResponse},
        400: {"description": "Bad Request: Insufficient funds, identical accounts, inactive account, or missing/invalid Idempotency-Key."},
        403: {"description": "Forbidden: Auditors cannot perform transfers."},
        404: {"description": "Not Found: Sourcing or destination account not found or unowned."},
        409: {"description": "Conflict: Idempotency key previously used with different parameters."},
    },
)
def transfer(
    req: TransferRequest,
    response: Response,
    idempotency_key: str = Depends(validate_idempotency_key),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result, is_replay = transfer_service.transfer(
        db, current_user, req, idempotency_key=idempotency_key
    )
    if is_replay:
        response.headers["Idempotent-Replay"] = "true"
    return result


@router.get(
    "/{reference}",
    response_model=TransactionResponse,
    summary="Get Transaction Details by Reference",
    description=(
        "Retrieves transaction header and double-entry legs for a given transaction reference. "
        "Account Holders can view transactions only if they own at least one involved account "
        "(returns HTTP 404 Not Found otherwise as anti-enumeration defense). "
        "Administrators and Auditors can view any transaction."
    ),
    responses={
        200: {"description": "Transaction details with entries.", "model": TransactionResponse},
        404: {"description": "Not Found: Transaction does not exist or user lacks access."},
    },
)
def get_transaction(
    reference: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return transfer_service.get_transaction(db, current_user, reference)


@router.get(
    "",
    response_model=TransactionListResponse,
    summary="List Transactions Journal",
    description=(
        "Retrieves a paginated list of double-entry ledger transactions. "
        "Account Holders receive transactions involving their own accounts. "
        "Administrators and Auditors receive all transactions system-wide."
    ),
    responses={
        200: {"description": "Paginated list of transactions.", "model": TransactionListResponse},
    },
)
def list_transactions(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = transfer_service.list_transactions(db, current_user, skip=skip, limit=limit)
    return TransactionListResponse(items=items, total=total, skip=skip, limit=limit)
