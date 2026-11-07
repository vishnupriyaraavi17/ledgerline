from datetime import datetime, timezone, timedelta
from decimal import Decimal
import uuid
import pytest
from pydantic import ValidationError

from backend.app.schemas.statement import (
    StatementPeriod,
    StatementSummary,
    StatementTransactionItem,
    RefusedAttemptItem,
)


def test_statement_period_rejects_naive_datetime():
    """
    StatementPeriod must fail closed when provided timezone-naive timestamps.
    """
    naive_start = datetime(2026, 11, 1, 0, 0)
    aware_end = datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError) as exc:
        StatementPeriod(start_date=naive_start, end_date=aware_end)
    assert "Timestamp must be timezone-aware" in str(exc.value)


def test_statement_period_rejects_inverted_dates():
    """
    start_date must be strictly earlier than end_date.
    """
    t_early = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
    t_late = datetime(2026, 11, 5, 0, 0, tzinfo=timezone.utc)

    # Inverted: start > end
    with pytest.raises(ValidationError) as exc:
        StatementPeriod(start_date=t_late, end_date=t_early)
    assert "must be strictly earlier than end_date" in str(exc.value)

    # Identical: start == end
    with pytest.raises(ValidationError) as exc:
        StatementPeriod(start_date=t_early, end_date=t_early)
    assert "must be strictly earlier than end_date" in str(exc.value)


def test_statement_period_valid_utc():
    """
    Valid timezone-aware dates are accepted and converted to UTC.
    """
    t_start = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
    t_end = datetime(2026, 11, 5, 0, 0, tzinfo=timezone.utc)
    p = StatementPeriod(start_date=t_start, end_date=t_end)
    assert p.start_date == t_start
    assert p.end_date == t_end


def test_statement_summary_exact_decimals():
    """
    StatementSummary accepts exact Decimal values without float corruption.
    """
    summary = StatementSummary(
        opening_balance=Decimal("1234.56"),
        closing_balance=Decimal("2345.67"),
        total_credits=Decimal("2000.00"),
        total_debits=Decimal("888.89"),
        net_change=Decimal("1111.11"),
        total_posted_transactions=15,
        total_refused_attempts=2,
    )
    assert summary.opening_balance == Decimal("1234.56")
    assert summary.closing_balance == Decimal("2345.67")
    assert summary.net_change == Decimal("1111.11")
    assert summary.total_posted_transactions == 15
    assert summary.total_refused_attempts == 2
