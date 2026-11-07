import csv
import io
import math
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.models.user import User, UserRole
from backend.app.models.account import Account, AccountType
from backend.app.models.ledger import EntryType, TransactionType
from backend.app.schemas.account import AccountResponse
from backend.app.schemas.statement import (
    StatementTransactionItem,
    RefusedAttemptItem,
    StatementSummary,
    StatementPeriod,
    AccountStatementResponse,
)
from backend.app.repositories.statement import statement_repository
from backend.app.repositories.refusal import refusal_repository


class StatementService:
    """
    Business orchestration for Account Statements and CSV Exports.
    Executes under a consistent PostgreSQL REPEATABLE READ READ ONLY snapshot.
    Guarantees exact paise arithmetic, full-period calculations before pagination,
    and protection against spreadsheet formula injection.
    """

    @staticmethod
    def _sanitize_csv_cell(value: Optional[str]) -> str:
        """
        Protect CSV exports against spreadsheet formula injection (CSV Injection / Formula Injection).
        If a text field begins with '=', '+', '-', '@', '\t', or '\r', prefix with a single quote.
        """
        if not value:
            return ""
        s = str(value)
        if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
            return f"'{s}"
        return s

    @staticmethod
    def generate_statement(
        db: Session,
        current_user: User,
        account_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
        page: int = 1,
        page_size: int = 50,
    ) -> AccountStatementResponse:
        # Validate timezone awareness (Fail closed on naive datetimes)
        if start_date.tzinfo is None or end_date.tzinfo is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date and end_date must be timezone-aware UTC timestamps",
            )
        start_utc = start_date.astimezone(timezone.utc)
        end_utc = end_date.astimezone(timezone.utc)

        if start_utc >= end_utc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"start_date ({start_utc.isoformat()}) must be strictly earlier than end_date ({end_utc.isoformat()})",
            )

        # Set transaction isolation level for this session to REPEATABLE READ READ ONLY
        try:
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        except Exception:
            # If transaction is already active, rollback first to allow isolation setting
            db.rollback()
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))

        account = statement_repository.get_account_under_snapshot(db, account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found",
            )

        # Anti-Enumeration: Account Holder can only query their own accounts
        if current_user.role == UserRole.ACCOUNT_HOLDER:
            if account.owner_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Account not found",
                )

        # Implementation Safeguard 1: Statements are available strictly for customer accounts
        if account.account_type not in (AccountType.CUSTOMER_CHECKING, AccountType.CUSTOMER_SAVINGS):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Statements are only available for customer accounts (checking or savings)",
            )

        # 1. Compute opening balance across all time before start_utc
        opening_bal = statement_repository.compute_opening_balance(db, account.id, start_utc)

        # 2. Fetch all entries in interval [start_utc, end_utc) with deterministic ordering
        entries = statement_repository.fetch_period_entries(db, account.id, start_utc, end_utc)

        # 3. Resolve counterparties
        counterparty_map = statement_repository.resolve_counterparties(db, entries, account.id)

        # 4. Fetch refused operations in interval [start_utc, end_utc)
        refusal_rows = refusal_repository.list_refusals_for_account(db, account.id, start_utc, end_utc)

        # 5. Calculate sequential running balances and totals over the COMPLETE period
        running_bal = opening_bal
        total_credits = Decimal("0.00")
        total_debits = Decimal("0.00")
        all_transactions = []

        for entry, txn in entries:
            if entry.entry_type == EntryType.CREDIT:
                running_bal += entry.amount
                total_credits += entry.amount
                direction = "credit"
            else:
                running_bal -= entry.amount
                total_debits += entry.amount
                direction = "debit"

            # Map actual database transaction types deterministically to display labels
            if txn.transaction_type == TransactionType.SETTLEMENT:
                if entry.entry_type == EntryType.CREDIT:
                    tx_type_str = "deposit"
                    display_label = "Deposit"
                else:
                    tx_type_str = "withdraw"
                    display_label = "Withdrawal"
            elif txn.transaction_type == TransactionType.TRANSFER:
                tx_type_str = "transfer"
                display_label = "Transfer In" if entry.entry_type == EntryType.CREDIT else "Transfer Out"
            else:
                tx_type_str = "adjustment"
                display_label = "Adjustment"

            c_num, c_name = counterparty_map.get(txn.id, (None, None))

            all_transactions.append(
                StatementTransactionItem(
                    entry_id=entry.id,
                    transaction_id=txn.id,
                    reference=txn.reference,
                    transaction_type=tx_type_str,
                    display_label=display_label,
                    direction=direction,
                    amount=entry.amount,
                    currency=account.currency,
                    running_balance=running_bal,
                    status="posted",
                    description=txn.description,
                    posted_at=txn.posted_at,
                    counterparty_account_number=c_num,
                    counterparty_name=c_name,
                )
            )

        net_change = total_credits - total_debits
        closing_bal = opening_bal + net_change

        refused_items = [
            RefusedAttemptItem(
                id=rec.id,
                operation_type=rec.operation_type,
                amount=rec.amount,
                currency=rec.currency,
                refusal_reason=rec.refusal_reason,
                error_message=rec.error_message,
                is_source=is_src,
                counterparty_account_number=c_acc_num,
                outcome="refused",
                created_at=rec.created_at,
            )
            for rec, is_src, c_acc_num in refusal_rows
        ]

        # 6. Apply pagination strictly AFTER complete-period calculations
        total_posted = len(all_transactions)
        total_refusals = len(refused_items)
        total_pages = max(1, math.ceil(total_posted / page_size))
        offset = (page - 1) * page_size
        paginated_transactions = all_transactions[offset : offset + page_size]

        summary = StatementSummary(
            opening_balance=opening_bal,
            closing_balance=closing_bal,
            total_credits=total_credits,
            total_debits=total_debits,
            net_change=net_change,
            total_posted_transactions=total_posted,
            total_refused_attempts=total_refusals,
        )

        period = StatementPeriod(
            start_date=start_utc,
            end_date=end_utc,
        )

        return AccountStatementResponse(
            account=AccountResponse.model_validate(account),
            period=period,
            summary=summary,
            transactions=paginated_transactions,
            refused_attempts=refused_items,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @staticmethod
    def export_statement_csv(
        db: Session,
        current_user: User,
        account_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> str:
        """
        Generate RFC 4180 compliant CSV export protected against spreadsheet formula injection.
        Includes complete period transactions with running balances and metadata summary headers.
        """
        # Call generate_statement with page=1, page_size=100000 to get full period
        stmt_data = StatementService.generate_statement(
            db=db,
            current_user=current_user,
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            page=1,
            page_size=100000,
        )

        output = io.StringIO()
        writer = csv.writer(output, dialect="excel", quoting=csv.QUOTE_MINIMAL)

        # Metadata Header
        writer.writerow(["LEDGERLINE ACCOUNT STATEMENT"])
        writer.writerow(["Account Number", stmt_data.account.account_number])
        writer.writerow(["Account Name", StatementService._sanitize_csv_cell(stmt_data.account.name)])
        writer.writerow(["Account Type", stmt_data.account.account_type.value])
        writer.writerow(["Currency", stmt_data.account.currency])
        writer.writerow(["Period Start (UTC)", stmt_data.period.start_date.isoformat()])
        writer.writerow(["Period End (UTC)", stmt_data.period.end_date.isoformat()])
        writer.writerow(["Opening Balance (INR)", f"{stmt_data.summary.opening_balance:.2f}"])
        writer.writerow(["Total Credits (INR)", f"{stmt_data.summary.total_credits:.2f}"])
        writer.writerow(["Total Debits (INR)", f"{stmt_data.summary.total_debits:.2f}"])
        writer.writerow(["Net Change (INR)", f"{stmt_data.summary.net_change:.2f}"])
        writer.writerow(["Closing Balance (INR)", f"{stmt_data.summary.closing_balance:.2f}"])
        writer.writerow([])

        # Table Column Headers
        writer.writerow([
            "Transaction Reference",
            "Posted At (UTC)",
            "Operation",
            "Direction",
            "Amount (INR)",
            "Running Balance (INR)",
            "Counterparty Account",
            "Description",
            "Status",
        ])

        for tx in stmt_data.transactions:
            writer.writerow([
                StatementService._sanitize_csv_cell(tx.reference),
                tx.posted_at.isoformat(),
                StatementService._sanitize_csv_cell(tx.display_label),
                tx.direction.upper(),
                f"{tx.amount:.2f}",
                f"{tx.running_balance:.2f}",
                StatementService._sanitize_csv_cell(tx.counterparty_account_number or "External Clearing (ACC-SYSTEM02)"),
                StatementService._sanitize_csv_cell(tx.description),
                StatementService._sanitize_csv_cell(tx.status.upper()),
            ])

        return output.getvalue()


statement_service = StatementService()
