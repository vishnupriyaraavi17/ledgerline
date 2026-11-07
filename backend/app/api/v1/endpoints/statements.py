import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.schemas.statement import AccountStatementResponse, RefusedAttemptItem
from backend.app.services.statement import statement_service
from backend.app.security.dependencies import get_current_user

router = APIRouter()


@router.get(
    "/{id}/statement",
    response_model=AccountStatementResponse,
    summary="Get Account Statement",
    description=(
        "Generates a complete, mathematically verified account statement for the specified account "
        "over the half-open interval [start_date, end_date) in UTC. "
        "Opening balance, closing balance, running balances, and totals are computed across the complete period. "
        "Pagination is applied strictly after complete calculations. "
        "Account Holders can access statements only for self-owned accounts (anti-enumeration 404). "
        "Administrators and Auditors can access statements for all customer accounts."
    ),
    responses={
        200: {"description": "Account statement successfully generated.", "model": AccountStatementResponse},
        400: {"description": "Bad Request: Invalid date interval or non-customer account."},
        404: {"description": "Not Found: Account does not exist or user does not own it."},
    },
)
def get_account_statement(
    id: uuid.UUID,
    start_date: Optional[datetime] = Query(
        None,
        description="UTC start datetime (inclusive). Defaults to 30 days prior (00:00:00 UTC)."
    ),
    end_date: Optional[datetime] = Query(
        None,
        description="UTC end datetime (exclusive). Defaults to current time in UTC."
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now_utc = datetime.now(timezone.utc)
    if end_date is None:
        end_date = now_utc
    elif end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    if start_date is None:
        start_date = end_date - timedelta(days=30)
    elif start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)

    return statement_service.generate_statement(
        db=db,
        current_user=current_user,
        account_id=id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{id}/statement/export",
    summary="Export Account Statement (CSV)",
    description=(
        "Exports an account statement as an RFC 4180 CSV file. "
        "Protected against spreadsheet formula injection (CSV injection). "
        "Includes complete unpaginated period transactions, running balances, and metadata summary header."
    ),
    responses={
        200: {"description": "CSV statement file download.", "content": {"text/csv": {}}},
        400: {"description": "Bad Request: Invalid date interval or non-customer account."},
        404: {"description": "Not Found: Account does not exist or user does not own it."},
    },
)
def export_account_statement_csv(
    id: uuid.UUID,
    start_date: Optional[datetime] = Query(None, description="UTC start datetime (inclusive)"),
    end_date: Optional[datetime] = Query(None, description="UTC end datetime (exclusive)"),
    format: str = Query("csv", pattern="^(csv)$", description="Export format (strictly csv)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now_utc = datetime.now(timezone.utc)
    if end_date is None:
        end_date = now_utc
    elif end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    if start_date is None:
        start_date = end_date - timedelta(days=30)
    elif start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)

    csv_data = statement_service.export_statement_csv(
        db=db,
        current_user=current_user,
        account_id=id,
        start_date=start_date,
        end_date=end_date,
    )

    filename = f"statement_{id}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )
