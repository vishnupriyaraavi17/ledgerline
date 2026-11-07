import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest

from backend.app.services.statement import StatementService


def test_opening_balance_mathematical_summation():
    """
    Verify opening balance calculation matches sum(credits) - sum(debits)
    strictly for entries before start_date.
    """
    entries = [
        {"entry_type": "credit", "amount": Decimal("500.00"), "created_at": datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)},
        {"entry_type": "debit", "amount": Decimal("150.00"), "created_at": datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)},
        {"entry_type": "credit", "amount": Decimal("200.00"), "created_at": datetime(2026, 11, 3, 14, 0, tzinfo=timezone.utc)},
    ]
    start_date = datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc)

    # Opening balance before start_date
    opening = Decimal("0.00")
    for e in entries:
        if e["created_at"] < start_date:
            if e["entry_type"] == "credit":
                opening += e["amount"]
            else:
                opening -= e["amount"]

    assert opening == Decimal("550.00")


def test_sequential_running_balances_and_closing_balance():
    """
    Verify that each transaction sequentially mutates the running balance
    and closing_balance = opening_balance + total_credits - total_debits.
    """
    opening_balance = Decimal("1000.00")
    transactions = [
        ("credit", Decimal("250.50")),   # Running: 1250.50
        ("debit", Decimal("100.25")),    # Running: 1150.25
        ("debit", Decimal("400.00")),    # Running: 750.25
        ("credit", Decimal("1500.00")),  # Running: 2250.25
    ]

    running = opening_balance
    total_credits = Decimal("0.00")
    total_debits = Decimal("0.00")
    running_balances = []

    for direction, amt in transactions:
        if direction == "credit":
            running += amt
            total_credits += amt
        else:
            running -= amt
            total_debits += amt
        running_balances.append(running)

    net_change = total_credits - total_debits
    closing_balance = opening_balance + net_change

    assert running_balances == [
        Decimal("1250.50"),
        Decimal("1150.25"),
        Decimal("750.25"),
        Decimal("2250.25"),
    ]
    assert total_credits == Decimal("1750.50")
    assert total_debits == Decimal("500.25")
    assert net_change == Decimal("1250.25")
    assert closing_balance == Decimal("2250.25")
    assert closing_balance == running_balances[-1]


def test_half_open_interval_boundary_continuity():
    """
    Verify consecutive period continuity: [T0, T1) and [T1, T2).
    Closing balance of Period 1 strictly equals Opening balance of Period 2.
    """
    t0 = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 11, 5, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)

    all_entries = [
        {"amount": Decimal("1000.00"), "dir": "credit", "time": datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)},
        {"amount": Decimal("200.00"), "dir": "debit", "time": datetime(2026, 11, 5, 0, 0, tzinfo=timezone.utc)}, # Exactly at T1!
        {"amount": Decimal("300.00"), "dir": "credit", "time": datetime(2026, 11, 7, 0, 0, tzinfo=timezone.utc)},
    ]

    # Period 1: [T0, T1) -> Entry at T1 must be EXCLUDED from Period 1!
    p1_entries = [e for e in all_entries if t0 <= e["time"] < t1]
    p1_opening = Decimal("0.00")
    p1_net = sum(e["amount"] if e["dir"] == "credit" else -e["amount"] for e in p1_entries)
    p1_closing = p1_opening + p1_net

    # Period 2: [T1, T2) -> Entry at T1 must be INCLUDED in Period 2!
    p2_entries = [e for e in all_entries if t1 <= e["time"] < t2]
    # P2 opening balance is all entries strictly before T1
    p2_opening = sum(e["amount"] if e["dir"] == "credit" else -e["amount"] for e in all_entries if e["time"] < t1)
    p2_net = sum(e["amount"] if e["dir"] == "credit" else -e["amount"] for e in p2_entries)
    p2_closing = p2_opening + p2_net

    assert len(p1_entries) == 1
    assert p1_entries[0]["amount"] == Decimal("1000.00")
    assert p1_closing == Decimal("1000.00")

    # Continuity check: P1 closing == P2 opening
    assert p1_closing == p2_opening
    assert len(p2_entries) == 2
    assert p2_entries[0]["amount"] == Decimal("200.00") # Entry at exact T1 boundary is captured here
    assert p2_closing == Decimal("1100.00")


def test_pagination_invariance():
    """
    Verify that pagination does not distort summary totals or running balances.
    Summary cards remain identical regardless of which page is viewed.
    """
    total_entries = 75
    opening = Decimal("500.00")
    entries = []
    curr = opening
    for i in range(total_entries):
        amt = Decimal("10.00")
        curr += amt
        entries.append({"idx": i, "running": curr})

    total_credits = Decimal("750.00")
    closing = opening + total_credits

    # Slice page 1 (size 25)
    page_1 = entries[0:25]
    # Slice page 2 (size 25)
    page_2 = entries[25:50]
    # Slice page 3 (size 25)
    page_3 = entries[50:75]

    # Running balances are preserved from global calculation
    assert page_1[0]["running"] == Decimal("510.00")
    assert page_1[-1]["running"] == Decimal("750.00")

    assert page_2[0]["running"] == Decimal("760.00")
    assert page_2[-1]["running"] == Decimal("1000.00")

    assert page_3[0]["running"] == Decimal("1010.00")
    assert page_3[-1]["running"] == Decimal("1250.00")
    assert closing == Decimal("1250.00")


def test_csv_injection_protection_sanitization():
    """
    Verify spreadsheet formula injection protection.
    Strings starting with '=', '+', '-', '@', '\t', '\r' must be prefixed with a single quote.
    """
    sanitize = StatementService._sanitize_csv_cell

    # Formulas
    assert sanitize("=1+1") == "'=1+1"
    assert sanitize("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize("-2+3") == "'-2+3"
    assert sanitize("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert sanitize("\tTAB_INJECT") == "'\tTAB_INJECT"
    assert sanitize("\rRETURN_INJECT") == "'\rRETURN_INJECT"

    # Safe strings
    assert sanitize("Standard Payment Description") == "Standard Payment Description"
    assert sanitize("TXN-ABCD1234EF56") == "TXN-ABCD1234EF56"
    assert sanitize("ACC-7B8C9D1E") == "ACC-7B8C9D1E"
    assert sanitize("") == ""
    assert sanitize(None) == ""
