import pytest
from decimal import Decimal, ROUND_HALF_UP
from pydantic import ValidationError
from backend.app.schemas.ledger import LedgerEntryResponse
from backend.app.schemas.account import AccountResponse
from backend.app.models.account import AccountType, AccountStatus
from backend.app.models.ledger import EntryType
import uuid
from datetime import datetime, timezone


def test_monetary_decimal_precision_and_exactness():
    """
    Asserts that Decimal arithmetic avoids IEEE-754 floating point inaccuracies.
    0.1 + 0.2 in binary float != 0.3, but in Decimal == Decimal('0.30').
    """
    float_sum = 0.1 + 0.2
    assert float_sum != 0.3

    d1 = Decimal("0.10")
    d2 = Decimal("0.20")
    d_sum = d1 + d2
    assert d_sum == Decimal("0.30")
    assert str(d_sum) == "0.30"


def test_monetary_decimal_rounding_and_quantization():
    """
    Tests that financial rounding to 2 decimal places is exact.
    """
    amount = Decimal("100.555")
    quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert quantized == Decimal("100.56")


def test_account_response_decimal_handling():
    """
    Asserts AccountResponse accepts and accurately parses Decimal balance.
    """
    now = datetime.now(timezone.utc)
    acc = AccountResponse(
        id=uuid.uuid4(),
        account_number="ACC-12345678",
        owner_id=uuid.uuid4(),
        name="Test Savings",
        account_type=AccountType.CUSTOMER_SAVINGS,
        currency="INR",
        balance=Decimal("0.00"),
        status=AccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    assert acc.balance == Decimal("0.00")
    assert isinstance(acc.balance, Decimal)


def test_ledger_entry_response_decimal_handling():
    """
    Asserts LedgerEntryResponse accepts and preserves Decimal amount.
    """
    entry = LedgerEntryResponse(
        id=uuid.uuid4(),
        transaction_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        entry_type=EntryType.CREDIT,
        amount=Decimal("5000.75"),
        sequence=1,
        created_at=datetime.now(timezone.utc),
    )
    assert entry.amount == Decimal("5000.75")
    assert isinstance(entry.amount, Decimal)
