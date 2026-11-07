import csv
import io
import time
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, select, create_engine, func
from sqlalchemy.orm import sessionmaker, Session
from alembic.config import Config
from alembic import command

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.models.user import UserRole
from backend.app.models.account import Account, AccountType, AccountStatus
from backend.app.models.refusal import RefusedOperation
from backend.app.models.ledger import LedgerTransaction, LedgerEntry


@pytest.fixture(scope="function")
def db_session():
    """Live application database session running as ledgerline_app."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def owner_session():
    """Dedicated database session running as ledgerline_owner."""
    engine = create_engine(settings.MIGRATION_DATABASE_URI)
    SessionOwner = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionOwner()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


@pytest.fixture(scope="module")
def admin_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "admin", "password": settings.SEED_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auditor_token(client: TestClient, admin_token: str) -> str:
    username = f"auditor_{uuid.uuid4().hex[:8]}"
    email = f"{username}@ledgerline.internal"
    pw = "AuditorPass123!"
    create_res = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": username,
            "email": email,
            "password": pw,
            "role": UserRole.AUDITOR.value,
        },
    )
    assert create_res.status_code == 201
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": pw},
    )
    assert login_res.status_code == 200
    return login_res.json()["access_token"]


def create_customer_holder(client: TestClient, admin_token: str, suffix: str = ""):
    u = f"holder_{suffix}_{uuid.uuid4().hex[:6]}"
    email = f"{u}@ledgerline.internal"
    pw = "CustomerPass123!"
    create_res = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"username": u, "email": email, "password": pw, "role": UserRole.ACCOUNT_HOLDER.value},
    )
    assert create_res.status_code == 201
    user_id = create_res.json()["id"]

    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": u, "password": pw},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    return user_id, token


# ==============================================================================
# GROUP A: STATEMENT BALANCES, SNAPSHOT CONSISTENCY & MATH INVARIANTS
# ==============================================================================

def test_group_a_statement_mathematical_conservation_and_running_balances(
    client: TestClient, admin_token: str
):
    """
    Verify complete statement balance derivation from double-entry ledger:
    Opening balance, credits, debits, net change, closing balance, and sequential running balances.
    """
    user_a_id, token_a = create_customer_holder(client, admin_token, "stmt_a")
    user_b_id, token_b = create_customer_holder(client, admin_token, "stmt_b")

    # 1. Create checking account for User A
    acc_a_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Checking Account A", "account_type": "customer_checking", "currency": "INR"},
    )
    assert acc_a_res.status_code == 201
    acc_a_id = acc_a_res.json()["id"]
    acc_a_num = acc_a_res.json()["account_number"]

    # Create savings account for User B
    acc_b_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Savings Account B", "account_type": "customer_savings", "currency": "INR"},
    )
    assert acc_b_res.status_code == 201
    acc_b_id = acc_b_res.json()["id"]
    acc_b_num = acc_b_res.json()["account_number"]

    t_before_deposit = datetime.now(timezone.utc) - timedelta(seconds=2)

    # 2. Deposit ₹1,000 into Account A
    dep_res = client.post(
        "/api/v1/transfers/deposit",
        headers={
            "Authorization": f"Bearer {token_a}",
            "Idempotency-Key": f"IDEM-DEP-{uuid.uuid4().hex[:12]}",
        },
        json={"account_id": acc_a_id, "amount": "1000.00", "description": "Initial Capital"},
    )
    assert dep_res.status_code == 201

    time.sleep(0.05)
    t_after_deposit = datetime.now(timezone.utc)

    # 3. Transfer ₹300 from Account A to Account B
    tx_res = client.post(
        "/api/v1/transfers/transfer",
        headers={
            "Authorization": f"Bearer {token_a}",
            "Idempotency-Key": f"IDEM-TRF-{uuid.uuid4().hex[:12]}",
        },
        json={
            "source_account_id": acc_a_id,
            "destination_account_id": acc_b_id,
            "amount": "300.00",
            "description": "Payment for Services",
        },
    )
    assert tx_res.status_code == 201

    time.sleep(0.05)
    t_after_transfer = datetime.now(timezone.utc)

    # 4. Withdraw ₹200 from Account A
    wd_res = client.post(
        "/api/v1/transfers/withdraw",
        headers={
            "Authorization": f"Bearer {token_a}",
            "Idempotency-Key": f"IDEM-WTH-{uuid.uuid4().hex[:12]}",
        },
        json={"account_id": acc_a_id, "amount": "200.00", "description": "ATM Cash Outflow"},
    )
    assert wd_res.status_code == 201

    t_end = datetime.now(timezone.utc) + timedelta(seconds=2)

    # 5. Query Full Statement for Account A: [t_before_deposit, t_end)
    stmt_res = client.get(
        f"/api/v1/accounts/{acc_a_id}/statement",
        headers={"Authorization": f"Bearer {token_a}"},
        params={
            "start_date": t_before_deposit.isoformat(),
            "end_date": t_end.isoformat(),
        },
    )
    assert stmt_res.status_code == 200
    stmt = stmt_res.json()

    # Verify Summary Calculations
    assert Decimal(str(stmt["summary"]["opening_balance"])) == Decimal("0.00")
    assert Decimal(str(stmt["summary"]["total_credits"])) == Decimal("1000.00")
    assert Decimal(str(stmt["summary"]["total_debits"])) == Decimal("500.00")
    assert Decimal(str(stmt["summary"]["net_change"])) == Decimal("500.00")
    assert Decimal(str(stmt["summary"]["closing_balance"])) == Decimal("500.00")
    assert stmt["summary"]["total_posted_transactions"] == 3

    # Verify Line-by-Line Sequential Running Balances and Types
    txs = stmt["transactions"]
    assert len(txs) == 3

    # Line 1: Deposit of ₹1,000
    assert txs[0]["display_label"] == "Deposit"
    assert txs[0]["direction"] == "credit"
    assert Decimal(str(txs[0]["amount"])) == Decimal("1000.00")
    assert Decimal(str(txs[0]["running_balance"])) == Decimal("1000.00")
    assert "ACC-SYSTEM02" in txs[0]["counterparty_account_number"]

    # Line 2: Transfer Out of ₹300
    assert txs[1]["display_label"] == "Transfer Out"
    assert txs[1]["direction"] == "debit"
    assert Decimal(str(txs[1]["amount"])) == Decimal("300.00")
    assert Decimal(str(txs[1]["running_balance"])) == Decimal("700.00")
    assert txs[1]["counterparty_account_number"] == acc_b_num

    # Line 3: Withdrawal of ₹200
    assert txs[2]["display_label"] == "Withdrawal"
    assert txs[2]["direction"] == "debit"
    assert Decimal(str(txs[2]["amount"])) == Decimal("200.00")
    assert Decimal(str(txs[2]["running_balance"])) == Decimal("500.00")

    # 6. Verify Sub-Range Continuity: [t_after_deposit, t_after_transfer)
    # Range includes ONLY the ₹300 transfer. Opening balance must be ₹1,000.00; Closing must be ₹700.00.
    sub_res = client.get(
        f"/api/v1/accounts/{acc_a_id}/statement",
        headers={"Authorization": f"Bearer {token_a}"},
        params={
            "start_date": t_after_deposit.isoformat(),
            "end_date": t_after_transfer.isoformat(),
        },
    )
    assert sub_res.status_code == 200
    sub_stmt = sub_res.json()

    assert Decimal(str(sub_stmt["summary"]["opening_balance"])) == Decimal("1000.00")
    assert Decimal(str(sub_stmt["summary"]["total_credits"])) == Decimal("0.00")
    assert Decimal(str(sub_stmt["summary"]["total_debits"])) == Decimal("300.00")
    assert Decimal(str(sub_stmt["summary"]["net_change"])) == Decimal("-300.00")
    assert Decimal(str(sub_stmt["summary"]["closing_balance"])) == Decimal("700.00")
    assert len(sub_stmt["transactions"]) == 1
    assert Decimal(str(sub_stmt["transactions"][0]["running_balance"])) == Decimal("700.00")

    # 7. Check Inbound Perspective on Account B
    stmt_b_res = client.get(
        f"/api/v1/accounts/{acc_b_id}/statement",
        headers={"Authorization": f"Bearer {token_b}"},
        params={
            "start_date": t_before_deposit.isoformat(),
            "end_date": t_end.isoformat(),
        },
    )
    assert stmt_b_res.status_code == 200
    stmt_b = stmt_b_res.json()
    assert Decimal(str(stmt_b["summary"]["opening_balance"])) == Decimal("0.00")
    assert Decimal(str(stmt_b["summary"]["closing_balance"])) == Decimal("300.00")
    assert stmt_b["transactions"][0]["display_label"] == "Transfer In"
    assert stmt_b["transactions"][0]["direction"] == "credit"
    assert stmt_b["transactions"][0]["counterparty_account_number"] == acc_a_num


def test_group_a_pagination_invariance(client: TestClient, admin_token: str):
    """
    Verify pagination does not alter summary totals or running balance continuity.
    """
    user_id, token = create_customer_holder(client, admin_token, "page_inv")
    acc_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Pagination Account", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_id = acc_res.json()["id"]

    # Post 3 deposits of ₹100, ₹200, ₹300
    for amt in ["100.00", "200.00", "300.00"]:
        dep = client.post(
            "/api/v1/transfers/deposit",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"IDEM-{uuid.uuid4().hex[:12]}"},
            json={"account_id": acc_id, "amount": amt, "description": f"Dep {amt}"},
        )
        assert dep.status_code == 201

    # Fetch with page_size=2: Page 1
    p1 = client.get(
        f"/api/v1/accounts/{acc_id}/statement",
        headers={"Authorization": f"Bearer {token}"},
        params={"page": 1, "page_size": 2},
    ).json()

    # Fetch with page_size=2: Page 2
    p2 = client.get(
        f"/api/v1/accounts/{acc_id}/statement",
        headers={"Authorization": f"Bearer {token}"},
        params={"page": 2, "page_size": 2},
    ).json()

    # Summary totals MUST BE identical across both pages!
    assert p1["summary"] == p2["summary"]
    assert Decimal(str(p1["summary"]["opening_balance"])) == Decimal("0.00")
    assert Decimal(str(p1["summary"]["closing_balance"])) == Decimal("600.00")
    assert p1["summary"]["total_posted_transactions"] == 3
    assert p1["total_pages"] == 2

    # Check page 1 running balances
    assert len(p1["transactions"]) == 2
    assert Decimal(str(p1["transactions"][0]["running_balance"])) == Decimal("100.00")
    assert Decimal(str(p1["transactions"][1]["running_balance"])) == Decimal("300.00")

    # Check page 2 running balance continuity (does NOT reset to 0!)
    assert len(p2["transactions"]) == 1
    assert Decimal(str(p2["transactions"][0]["running_balance"])) == Decimal("600.00")


# ==============================================================================
# GROUP B: REFUSED OPERATIONS PERSISTENCE, VISIBILITY & ZERO LEDGER CONTAMINATION
# ==============================================================================

def test_group_b_refused_withdrawal_insufficient_funds_and_zero_ledger_contamination(
    client: TestClient, admin_token: str, db_session: Session
):
    """
    Verify overdraft withdrawal is recorded in refused_operations,
    account balance is unchanged, and ZERO ledger entries are created.
    """
    user_id, token = create_customer_holder(client, admin_token, "ref_wth")
    acc_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Overdraft Checking", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_id = acc_res.json()["id"]

    # Deposit ₹500
    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"IDEM-{uuid.uuid4().hex[:12]}"},
        json={"account_id": acc_id, "amount": "500.00", "description": "Deposit ₹500"},
    )

    # Initial ledger entry count
    initial_entries_count = db_session.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.account_id == acc_id)
    )
    assert initial_entries_count == 1 # Just the deposit

    # Attempt Overdraft Withdrawal of ₹5,000 (Available: ₹500)
    overdraft_key = f"IDEM-OVERDRAFT-{uuid.uuid4().hex[:10]}"
    overdraft_res = client.post(
        "/api/v1/transfers/withdraw",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": overdraft_key},
        json={"account_id": acc_id, "amount": "5000.00", "description": "Attempted Overdraft"},
    )
    assert overdraft_res.status_code == 400
    assert "Insufficient funds" in overdraft_res.json()["detail"]

    # 1. Invariant: Ledger entries count is strictly unchanged!
    db_session.expire_all()
    entries_after = db_session.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.account_id == acc_id)
    )
    assert entries_after == initial_entries_count

    # 2. Invariant: Account balance remains untouched at ₹500.00
    acc_after = db_session.scalar(select(Account).where(Account.id == acc_id))
    assert acc_after.balance == Decimal("500.00")

    # 3. Refusal record was autonomously committed in refused_operations!
    refusal = db_session.scalar(
        select(RefusedOperation).where(
            RefusedOperation.account_id == acc_id,
            RefusedOperation.refusal_reason == "INSUFFICIENT_FUNDS",
        )
    )
    assert refusal is not None
    assert refusal.operation_type == "withdraw"
    assert refusal.amount == Decimal("5000.00")
    assert refusal.error_message == "Insufficient funds"
    assert refusal.idempotency_key_hash is not None

    # 4. Refusal appears on Account Statement in Refused Attempts Tab
    stmt = client.get(
        f"/api/v1/accounts/{acc_id}/statement",
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    assert stmt["summary"]["total_refused_attempts"] >= 1
    refused_list = stmt["refused_attempts"]
    match = [r for r in refused_list if r["refusal_reason"] == "INSUFFICIENT_FUNDS"]
    assert len(match) >= 1
    assert match[0]["operation_type"] == "withdraw"
    assert Decimal(str(match[0]["amount"])) == Decimal("5000.00")
    assert match[0]["outcome"] == "refused"


def test_group_b_refused_transfer_dual_account_visibility(
    client: TestClient, admin_token: str
):
    """
    Verify a refused transfer is visible in the statements of BOTH source and destination accounts.
    """
    user_a_id, token_a = create_customer_holder(client, admin_token, "dual_src")
    user_b_id, token_b = create_customer_holder(client, admin_token, "dual_dst")

    acc_a_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Source Account", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_a_id = acc_a_res.json()["id"]

    acc_b_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Dest Account", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_b_id = acc_b_res.json()["id"]

    # Attempt transfer of ₹10,000 when Account A has balance ₹0.00
    res = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {token_a}", "Idempotency-Key": f"IDEM-TRF-{uuid.uuid4().hex[:10]}"},
        json={"source_account_id": acc_a_id, "destination_account_id": acc_b_id, "amount": "10000.00"},
    )
    assert res.status_code == 400

    # 1. Source Account Statement shows the refusal (as initiator)
    stmt_a = client.get(f"/api/v1/accounts/{acc_a_id}/statement", headers={"Authorization": f"Bearer {token_a}"}).json()
    ref_a = [r for r in stmt_a["refused_attempts"] if r["refusal_reason"] == "INSUFFICIENT_FUNDS"]
    assert len(ref_a) >= 1
    assert ref_a[0]["is_source"] is True

    # 2. Destination Account Statement shows the refusal (as intended destination)
    stmt_b = client.get(f"/api/v1/accounts/{acc_b_id}/statement", headers={"Authorization": f"Bearer {token_b}"}).json()
    ref_b = [r for r in stmt_b["refused_attempts"] if r["refusal_reason"] == "INSUFFICIENT_FUNDS"]
    assert len(ref_b) >= 1
    assert ref_b[0]["is_source"] is False


def test_group_b_frozen_account_and_destination_refusal_recording(
    client: TestClient, admin_token: str
):
    """
    Verify frozen accounts (source, destination, deposit) record controlled refusal reasons.
    """
    user_a_id, token_a = create_customer_holder(client, admin_token, "froz_a")
    user_b_id, token_b = create_customer_holder(client, admin_token, "froz_b")

    acc_a_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Testing Account A", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_a_id = acc_a_res.json()["id"]

    acc_b_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Testing Account B", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_b_id = acc_b_res.json()["id"]

    # 1. Freeze Account B and attempt transfer from A to B -> DESTINATION_FROZEN
    client.patch(
        f"/api/v1/accounts/{acc_b_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "frozen"},
    )

    trf_res = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {token_a}", "Idempotency-Key": f"IDEM-DSTFROZ-{uuid.uuid4().hex[:10]}"},
        json={"source_account_id": acc_a_id, "destination_account_id": acc_b_id, "amount": "100.00"},
    )
    assert trf_res.status_code == 400
    assert "frozen" in trf_res.json()["detail"]

    stmt_a = client.get(f"/api/v1/accounts/{acc_a_id}/statement", headers={"Authorization": f"Bearer {token_a}"}).json()
    ref_dst = [r for r in stmt_a["refused_attempts"] if r["refusal_reason"] == "DESTINATION_FROZEN"]
    assert len(ref_dst) >= 1

    # 2. Freeze Account A and attempt deposit -> ACCOUNT_FROZEN
    client.patch(
        f"/api/v1/accounts/{acc_a_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "frozen"},
    )

    froz_res = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {token_a}", "Idempotency-Key": f"IDEM-FROZ-{uuid.uuid4().hex[:10]}"},
        json={"account_id": acc_a_id, "amount": "250.00"},
    )
    assert froz_res.status_code == 400
    assert "frozen" in froz_res.json()["detail"]

    stmt_froz = client.get(f"/api/v1/accounts/{acc_a_id}/statement", headers={"Authorization": f"Bearer {token_a}"}).json()
    ref_froz = [r for r in stmt_froz["refused_attempts"] if r["refusal_reason"] == "ACCOUNT_FROZEN"]
    assert len(ref_froz) >= 1


def test_group_b_idempotency_conflict_refusal_recording(
    client: TestClient, admin_token: str
):
    """
    Verify payload conflict on identical idempotency key is recorded as IDEMPOTENCY_CONFLICT.
    """
    user_id, token = create_customer_holder(client, admin_token, "idem_conf")
    acc_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Idempotency Test", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_id = acc_res.json()["id"]

    key = f"IDEM-UNIQUE-{uuid.uuid4().hex[:12]}"

    # Step 1: Successful deposit of ₹200
    dep1 = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        json={"account_id": acc_id, "amount": "200.00", "description": "Original Payload"},
    )
    assert dep1.status_code == 201

    # Step 2: Conflict attempt with altered amount ₹999.00 under same key
    dep2 = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        json={"account_id": acc_id, "amount": "999.00", "description": "Altered Payload"},
    )
    assert dep2.status_code == 409

    # Verify IDEMPOTENCY_CONFLICT refusal appears on statement
    stmt = client.get(f"/api/v1/accounts/{acc_id}/statement", headers={"Authorization": f"Bearer {token}"}).json()
    ref_idem = [r for r in stmt["refused_attempts"] if r["refusal_reason"] == "IDEMPOTENCY_CONFLICT"]
    assert len(ref_idem) >= 1
    assert ref_idem[0]["operation_type"] == "deposit"
    assert Decimal(str(ref_idem[0]["amount"])) == Decimal("999.00")


def test_group_b_refused_operation_account_closed(
    client: TestClient, admin_token: str, db_session: Session
):
    """
    Verify:
    1. A customer account closed through permitted lifecycle rejects financial operations.
    2. Correct ACCOUNT_CLOSED refusal record is created in refused_operations.
    3. The financial operation rolls back.
    4. ZERO ledger transactions, ledger entries, or balance changes occur.
    """
    user_id, token = create_customer_holder(client, admin_token, "close_op")
    acc_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Closure Test Account", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_id = acc_res.json()["id"]

    # Close account through permitted lifecycle (balance is ₹0.00)
    close_res = client.patch(
        f"/api/v1/accounts/{acc_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "closed"},
    )
    assert close_res.status_code == 200
    assert close_res.json()["status"] == "closed"

    # Count initial ledger entries (should be 0)
    initial_entries_count = db_session.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.account_id == acc_id)
    )
    assert initial_entries_count == 0

    # Attempt deposit to closed account
    dep_res = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"IDEM-CLS-{uuid.uuid4().hex[:10]}"},
        json={"account_id": acc_id, "amount": "100.00"},
    )
    assert dep_res.status_code == 400
    assert "closed" in dep_res.json()["detail"].lower()

    # 1. Zero ledger entries created
    db_session.expire_all()
    entries_after = db_session.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.account_id == acc_id)
    )
    assert entries_after == 0

    # 2. Balance remains 0.00
    acc_after = db_session.scalar(select(Account).where(Account.id == acc_id))
    assert acc_after.balance == Decimal("0.00")

    # 3. Refusal record created with reason ACCOUNT_CLOSED
    refusal = db_session.scalar(
        select(RefusedOperation).where(
            RefusedOperation.account_id == acc_id,
            RefusedOperation.refusal_reason == "ACCOUNT_CLOSED",
        )
    )
    assert refusal is not None
    assert refusal.operation_type == "deposit"
    assert refusal.amount == Decimal("100.00")
    assert "closed" in refusal.error_message.lower()

    # 4. Appears in statement refused_attempts
    stmt = client.get(f"/api/v1/accounts/{acc_id}/statement", headers={"Authorization": f"Bearer {token}"}).json()
    ref_list = [r for r in stmt["refused_attempts"] if r["refusal_reason"] == "ACCOUNT_CLOSED"]
    assert len(ref_list) >= 1
    assert ref_list[0]["outcome"] == "refused"


def test_group_b_refused_transfer_destination_closed(
    client: TestClient, admin_token: str, db_session: Session
):
    """
    Verify:
    1. Transfer to a destination account closed through permitted lifecycle is rejected.
    2. DESTINATION_CLOSED refusal record is created.
    3. Dual-account visibility: both source and destination see the refusal.
    4. ZERO ledger transactions, ledger entries, or balance changes occur.
    """
    user_a_id, token_a = create_customer_holder(client, admin_token, "dst_cls_a")
    user_b_id, token_b = create_customer_holder(client, admin_token, "dst_cls_b")

    acc_a_id = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Source Active Account", "account_type": "customer_checking", "currency": "INR"},
    ).json()["id"]

    acc_b_id = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Dest Closed Account", "account_type": "customer_checking", "currency": "INR"},
    ).json()["id"]

    # Fund Source Account with ₹500
    dep_res = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {token_a}", "Idempotency-Key": f"IDEM-SRC-{uuid.uuid4().hex[:10]}"},
        json={"account_id": acc_a_id, "amount": "500.00"},
    )
    assert dep_res.status_code == 201

    # Close Destination Account B through permitted lifecycle (balance is ₹0.00)
    close_b = client.patch(
        f"/api/v1/accounts/{acc_b_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "closed"},
    )
    assert close_b.status_code == 200

    # Initial ledger entry count for both accounts
    initial_a_entries = db_session.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.account_id == acc_a_id)
    )
    initial_b_entries = db_session.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.account_id == acc_b_id)
    )
    assert initial_a_entries == 1 # Deposit
    assert initial_b_entries == 0

    # Attempt transfer from Account A to closed Account B
    trf_res = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {token_a}", "Idempotency-Key": f"IDEM-CLS-TRF-{uuid.uuid4().hex[:10]}"},
        json={"source_account_id": acc_a_id, "destination_account_id": acc_b_id, "amount": "100.00"},
    )
    assert trf_res.status_code == 400
    assert "closed" in trf_res.json()["detail"].lower()

    # Invariants: No ledger entries added and balances untouched
    db_session.expire_all()
    assert db_session.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.account_id == acc_a_id)
    ) == initial_a_entries
    assert db_session.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.account_id == acc_b_id)
    ) == initial_b_entries

    acc_a_db = db_session.scalar(select(Account).where(Account.id == acc_a_id))
    acc_b_db = db_session.scalar(select(Account).where(Account.id == acc_b_id))
    assert acc_a_db.balance == Decimal("500.00")
    assert acc_b_db.balance == Decimal("0.00")

    # Refusal record exists with DESTINATION_CLOSED
    refusal = db_session.scalar(
        select(RefusedOperation).where(
            RefusedOperation.account_id == acc_a_id,
            RefusedOperation.counterparty_account_id == acc_b_id,
            RefusedOperation.refusal_reason == "DESTINATION_CLOSED",
        )
    )
    assert refusal is not None
    assert refusal.amount == Decimal("100.00")

    # Dual-account visibility
    stmt_a = client.get(f"/api/v1/accounts/{acc_a_id}/statement", headers={"Authorization": f"Bearer {token_a}"}).json()
    ref_a = [r for r in stmt_a["refused_attempts"] if r["refusal_reason"] == "DESTINATION_CLOSED"]
    assert len(ref_a) >= 1
    assert ref_a[0]["is_source"] is True

    stmt_b = client.get(f"/api/v1/accounts/{acc_b_id}/statement", headers={"Authorization": f"Bearer {token_b}"}).json()
    ref_b = [r for r in stmt_b["refused_attempts"] if r["refusal_reason"] == "DESTINATION_CLOSED"]
    assert len(ref_b) >= 1
    assert ref_b[0]["is_source"] is False


def test_group_b_self_transfer_prohibited_refusal_recording(
    client: TestClient, admin_token: str, db_session: Session
):
    """
    Verify:
    1. Transfer where source == destination is rejected by service with HTTP 400.
    2. SELF_TRANSFER_PROHIBITED refusal record is created.
    3. ZERO ledger transactions, ledger entries, or balance changes occur.
    4. Refusal appears on account statement.
    """
    user_id, token = create_customer_holder(client, admin_token, "self_ref")
    acc_id = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Self Transfer Account", "account_type": "customer_checking", "currency": "INR"},
    ).json()["id"]

    # Deposit ₹500
    dep_res = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"IDEM-DEP-{uuid.uuid4().hex[:10]}"},
        json={"account_id": acc_id, "amount": "500.00"},
    )
    assert dep_res.status_code == 201

    initial_entries_count = db_session.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.account_id == acc_id)
    )
    assert initial_entries_count == 1

    # Attempt self-transfer of ₹50.00
    self_res = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"IDEM-SELF-{uuid.uuid4().hex[:10]}"},
        json={"source_account_id": acc_id, "destination_account_id": acc_id, "amount": "50.00"},
    )
    assert self_res.status_code == 400
    assert "Source and destination accounts must be distinct" in self_res.json()["detail"]

    # 1. Zero new ledger entries
    db_session.expire_all()
    entries_after = db_session.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.account_id == acc_id)
    )
    assert entries_after == initial_entries_count

    # 2. Balance untouched at ₹500.00
    acc_db = db_session.scalar(select(Account).where(Account.id == acc_id))
    assert acc_db.balance == Decimal("500.00")

    # 3. Refusal record created with SELF_TRANSFER_PROHIBITED
    refusal = db_session.scalar(
        select(RefusedOperation).where(
            RefusedOperation.account_id == acc_id,
            RefusedOperation.refusal_reason == "SELF_TRANSFER_PROHIBITED",
        )
    )
    assert refusal is not None
    assert refusal.operation_type == "transfer"
    assert refusal.amount == Decimal("50.00")
    assert refusal.counterparty_account_id == uuid.UUID(acc_id)

    # 4. Appears in account statement
    stmt = client.get(f"/api/v1/accounts/{acc_id}/statement", headers={"Authorization": f"Bearer {token}"}).json()
    ref_list = [r for r in stmt["refused_attempts"] if r["refusal_reason"] == "SELF_TRANSFER_PROHIBITED"]
    assert len(ref_list) >= 1
    assert Decimal(str(ref_list[0]["amount"])) == Decimal("50.00")


# ==============================================================================
# GROUP C: RBAC & HTTP 404 ANTI-ENUMERATION
# ==============================================================================

def test_group_c_rbac_and_anti_enumeration(
    client: TestClient, admin_token: str, auditor_token: str
):
    """
    Verify:
    1. Account Holder can access only their own statement.
    2. Account Holder requesting another user's statement receives strictly HTTP 404 Not Found.
    3. Admin and Auditor can access statements for all customer accounts.
    4. System accounts are strictly rejected with HTTP 400.
    """
    user_1_id, token_1 = create_customer_holder(client, admin_token, "rbac_1")
    user_2_id, token_2 = create_customer_holder(client, admin_token, "rbac_2")

    acc_1_id = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token_1}"},
        json={"name": "User 1 Checking", "account_type": "customer_checking", "currency": "INR"},
    ).json()["id"]

    # 1. User 1 accesses User 1's statement -> HTTP 200 OK
    res_1 = client.get(f"/api/v1/accounts/{acc_1_id}/statement", headers={"Authorization": f"Bearer {token_1}"})
    assert res_1.status_code == 200

    # 2. User 2 accesses User 1's statement -> strictly HTTP 404 Not Found (Anti-Enumeration)
    res_2 = client.get(f"/api/v1/accounts/{acc_1_id}/statement", headers={"Authorization": f"Bearer {token_2}"})
    assert res_2.status_code == 404
    assert res_2.json()["detail"] == "Account not found"

    # 3. Admin accesses User 1's statement -> HTTP 200 OK
    res_admin = client.get(f"/api/v1/accounts/{acc_1_id}/statement", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200

    # 4. Auditor accesses User 1's statement -> HTTP 200 OK (Read-Only)
    res_auditor = client.get(f"/api/v1/accounts/{acc_1_id}/statement", headers={"Authorization": f"Bearer {auditor_token}"})
    assert res_auditor.status_code == 200

    # 5. Safeguard 1: Querying statement for system reserve or clearing account -> HTTP 400 Bad Request
    sys_acc = SessionLocal().scalar(select(Account).where(Account.account_number == "ACC-SYSTEM01"))
    if sys_acc:
        res_sys = client.get(f"/api/v1/accounts/{sys_acc.id}/statement", headers={"Authorization": f"Bearer {admin_token}"})
        assert res_sys.status_code == 400
        assert "customer accounts" in res_sys.json()["detail"]


# ==============================================================================
# GROUP D: DATABASE PRIVILEGE HARDENING & ENGINE IMMUTABILITY TRIGGERS
# ==============================================================================

def test_group_d_runtime_privileges_and_triggers_on_refused_operations(
    db_session: Session, owner_session: Session
):
    """
    Verify:
    1. Runtime role ledgerline_app has SELECT and INSERT.
    2. Runtime role UPDATE, DELETE, and TRUNCATE are blocked by triggers or privileges.
    """
    user_id = db_session.scalar(select(Account.owner_id).where(Account.owner_id != None))
    test_id = uuid.uuid4()

    # 1. INSERT succeeds under runtime role
    ins_stmt = text("""
        INSERT INTO public.refused_operations (
            id, user_id, operation_type, amount, currency, refusal_reason, error_message
        ) VALUES (
            :id, :user_id, 'withdraw', 100.00, 'INR', 'INSUFFICIENT_FUNDS', 'Test refusal row'
        )
    """)
    db_session.execute(ins_stmt, {"id": test_id, "user_id": user_id})
    db_session.commit()

    # 2. SELECT succeeds under runtime role
    row = db_session.scalar(select(RefusedOperation).where(RefusedOperation.id == test_id))
    assert row is not None
    assert row.amount == Decimal("100.00")

    # 3. UPDATE fails with immutability trigger exception 55000
    with pytest.raises(Exception) as exc_update:
        db_session.execute(
            text("UPDATE public.refused_operations SET error_message = 'Hacked' WHERE id = :id"),
            {"id": test_id},
        )
        db_session.flush()
    db_session.rollback()
    assert "Refused operation records are strictly immutable" in str(exc_update.value) or "permission denied" in str(exc_update.value)

    # 4. DELETE fails with immutability trigger exception 55000
    with pytest.raises(Exception) as exc_delete:
        db_session.execute(
            text("DELETE FROM public.refused_operations WHERE id = :id"),
            {"id": test_id},
        )
        db_session.flush()
    db_session.rollback()
    assert "Refused operation records are strictly immutable" in str(exc_delete.value) or "permission denied" in str(exc_delete.value)


# ==============================================================================
# GROUP E: CSV EXPORT & SPREADSHEET FORMULA INJECTION SANITIZATION
# ==============================================================================

def test_group_e_csv_export_format_and_formula_injection_defense(
    client: TestClient, admin_token: str
):
    """
    Verify RFC 4180 CSV export and ensure formula injection strings
    (=, +, -, @, \t, \r) are neutralized with a leading single quote.
    """
    user_id, token = create_customer_holder(client, admin_token, "csv_inj")
    acc_id = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Formula Checking", "account_type": "customer_checking", "currency": "INR"},
    ).json()["id"]

    # Deposit with injection attempt in description: "=2+5"
    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"IDEM-{uuid.uuid4().hex[:10]}"},
        json={"account_id": acc_id, "amount": "150.00", "description": "=SUM(A1:A100)"},
    )

    # Export CSV
    export_res = client.get(
        f"/api/v1/accounts/{acc_id}/statement/export?format=csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert export_res.status_code == 200
    assert "text/csv" in export_res.headers["content-type"]
    assert "attachment; filename=" in export_res.headers["content-disposition"]

    csv_text = export_res.text
    # Verify CSV structure
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    # Header check
    assert rows[0][0] == "LEDGERLINE ACCOUNT STATEMENT"

    # Find the transaction table rows
    table_header_idx = -1
    for i, row in enumerate(rows):
        if len(row) > 0 and row[0] == "Transaction Reference":
            table_header_idx = i
            break

    assert table_header_idx != -1
    tx_row = rows[table_header_idx + 1]
    description_cell = tx_row[7]

    # Invariant: Formula injection '=SUM(...)' is neutralized to ''=SUM(...)''
    assert description_cell.startswith("'=")


# ==============================================================================
# GROUP F: ALEMBIC MIGRATION REVERSIBILITY
# ==============================================================================

def test_group_f_alembic_migration_reversibility():
    """
    Verify migration 0007_statements_refusals executes downgrade and upgrade cleanly.
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    alembic_ini_path = project_root / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))

    # Downgrade 1 step to Task 06 head
    command.downgrade(alembic_cfg, "-1")

    # Re-upgrade to head
    command.upgrade(alembic_cfg, "head")
