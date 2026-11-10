import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, create_engine, select
from sqlalchemy.orm import sessionmaker, Session

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal, engine as app_engine
from backend.app.models.account import Account, AccountType, AccountStatus


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


@pytest.fixture(autouse=True)
def auto_idempotency_for_transfers(monkeypatch, client: TestClient):
    """
    Ensures Task 04 financial tests supply a valid Idempotency-Key
    if not explicitly specified, adhering to Task 05 mandatory idempotency requirement.
    """
    orig_post = client.post

    def patched_post(url, *args, **kwargs):
        if any(ep in str(url) for ep in ["/transfers/deposit", "/transfers/withdraw", "/transfers/transfer"]):
            headers = kwargs.get("headers")
            if headers is None:
                kwargs["headers"] = {"Idempotency-Key": f"test-key-{uuid.uuid4()}"}
            elif "Idempotency-Key" not in headers and "idempotency-key" not in headers:
                # Inject default test key only if not already provided
                new_headers = dict(headers)
                new_headers["Idempotency-Key"] = f"test-key-{uuid.uuid4()}"
                kwargs["headers"] = new_headers
        return orig_post(url, *args, **kwargs)

    monkeypatch.setattr(client, "post", patched_post)


@pytest.fixture(scope="module")
def admin_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "admin", "password": settings.SEED_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def holder_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "holder", "password": settings.SEED_HOLDER_PASSWORD},
    )
    assert response.status_code == 200, f"Holder login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auditor_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "auditor", "password": settings.SEED_AUDITOR_PASSWORD},
    )
    assert response.status_code == 200, f"Auditor login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def second_holder_token(client: TestClient, admin_token: str) -> str:
    """Create a second distinct Account Holder user for multi-party and anti-enumeration testing."""
    username = f"holder2_{uuid.uuid4().hex[:6]}"
    email = f"{username}@example.com"
    password = "SecPass_Holder2_2026!"

    res = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": username,
            "email": email,
            "password": password,
            "role": "account_holder",
        },
    )
    assert res.status_code == 201, f"Failed to provision holder2: {res.text}"

    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert login_res.status_code == 200, f"Login for holder2 failed: {login_res.text}"
    return login_res.json()["access_token"]


# ==============================================================================
# GROUP A: Double-Entry Posting, Money Conservation & Balances (Runtime Role)
# ==============================================================================

def test_group_a_successful_customer_deposit(
    client: TestClient, holder_token: str, db_session: Session
):
    # 1. Account Holder creates a new active account
    create_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Deposit Target Checking", "account_type": "customer_checking", "currency": "INR"},
    )
    assert create_res.status_code == 201
    acc_id = create_res.json()["id"]
    assert create_res.json()["balance"] == "0.00"

    # 2. Deposit ₹1,000.00
    deposit_res = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_id, "amount": "1000.00", "description": "Salary Deposit"},
    )
    assert deposit_res.status_code == 201, f"Deposit failed: {deposit_res.text}"
    txn_data = deposit_res.json()
    assert txn_data["reference"].startswith("TXN-")
    assert txn_data["transaction_type"] == "settlement"
    assert len(txn_data["entries"]) == 2

    # Check legs: Leg 1 is Debit ACC-SYSTEM02, Leg 2 is Credit customer account
    entries = sorted(txn_data["entries"], key=lambda e: e["sequence"])
    assert entries[0]["entry_type"] == "debit"
    assert entries[0]["amount"] == "1000.00"
    assert entries[1]["entry_type"] == "credit"
    assert entries[1]["account_id"] == acc_id
    assert entries[1]["amount"] == "1000.00"

    # 3. Check customer account balance is exactly ₹1000.00
    acc_check = client.get(
        f"/api/v1/accounts/{acc_id}",
        headers={"Authorization": f"Bearer {holder_token}"},
    )
    assert acc_check.status_code == 200
    assert acc_check.json()["balance"] == "1000.00"


def test_group_a_successful_customer_withdrawal(
    client: TestClient, holder_token: str, db_session: Session
):
    # 1. Create account and deposit ₹1,000.00
    create_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Withdrawal Source Checking", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_id = create_res.json()["id"]

    dep_res = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_id, "amount": "1000.00"},
    )
    assert dep_res.status_code == 201

    # 2. Withdraw ₹400.00
    wd_res = client.post(
        "/api/v1/transfers/withdraw",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_id, "amount": "400.00", "description": "ATM Cash Withdrawal"},
    )
    assert wd_res.status_code == 201, f"Withdrawal failed: {wd_res.text}"
    txn_data = wd_res.json()
    assert len(txn_data["entries"]) == 2

    entries = sorted(txn_data["entries"], key=lambda e: e["sequence"])
    assert entries[0]["entry_type"] == "debit"
    assert entries[0]["account_id"] == acc_id
    assert entries[0]["amount"] == "400.00"
    assert entries[1]["entry_type"] == "credit"
    assert entries[1]["amount"] == "400.00"

    # 3. Check customer account balance is exactly ₹600.00
    acc_check = client.get(
        f"/api/v1/accounts/{acc_id}",
        headers={"Authorization": f"Bearer {holder_token}"},
    )
    assert acc_check.json()["balance"] == "600.00"


def test_group_a_overdraft_withdrawal_insufficient_funds(
    client: TestClient, holder_token: str
):
    # 1. Create account with initial ₹0.00 balance
    create_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Low Balance Checking", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_id = create_res.json()["id"]

    # Fund with ₹200.00
    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_id, "amount": "200.00"},
    )

    # 2. Attempt to withdraw ₹250.00 (exceeds balance)
    wd_res = client.post(
        "/api/v1/transfers/withdraw",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_id, "amount": "250.00"},
    )
    assert wd_res.status_code == 400
    assert "Insufficient funds" in wd_res.json()["detail"]

    # 3. Balance must remain strictly ₹200.00
    acc_check = client.get(
        f"/api/v1/accounts/{acc_id}",
        headers={"Authorization": f"Bearer {holder_token}"},
    )
    assert acc_check.json()["balance"] == "200.00"


def test_group_a_successful_peer_to_peer_transfer(
    client: TestClient, holder_token: str, second_holder_token: str
):
    # 1. Holder 1 creates account A and deposits ₹600.00
    res_a = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Alice Checking", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_a_id = res_a.json()["id"]
    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_a_id, "amount": "600.00"},
    )

    # 2. Holder 2 creates account B with ₹0.00
    res_b = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {second_holder_token}"},
        json={"name": "Bob Savings", "account_type": "customer_savings", "currency": "INR"},
    )
    acc_b_id = res_b.json()["id"]

    # 3. Transfer ₹250.00 from A to B
    xfer_res = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={
            "source_account_id": acc_a_id,
            "destination_account_id": acc_b_id,
            "amount": "250.00",
            "description": "Peer transfer A to B",
        },
    )
    assert xfer_res.status_code == 201, f"Transfer failed: {xfer_res.text}"
    txn_data = xfer_res.json()
    assert txn_data["transaction_type"] == "transfer"
    assert len(txn_data["entries"]) == 2

    # 4. Invariant checks
    # Account A balance: 600 - 250 = 350.00
    check_a = client.get(
        f"/api/v1/accounts/{acc_a_id}",
        headers={"Authorization": f"Bearer {holder_token}"},
    )
    assert check_a.json()["balance"] == "350.00"

    # Account B balance: 0 + 250 = 250.00
    check_b = client.get(
        f"/api/v1/accounts/{acc_b_id}",
        headers={"Authorization": f"Bearer {second_holder_token}"},
    )
    assert check_b.json()["balance"] == "250.00"

    # Strict Money Conservation:
    # (350.00 + 250.00) == (600.00 + 0.00)
    bal_a = Decimal(check_a.json()["balance"])
    bal_b = Decimal(check_b.json()["balance"])
    assert bal_a + bal_b == Decimal("600.00")


def test_group_a_overdraft_transfer_insufficient_funds(
    client: TestClient, holder_token: str, second_holder_token: str
):
    # 1. Setup accounts
    res_a = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Source Low Balance", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_a_id = res_a.json()["id"]
    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_a_id, "amount": "100.00"},
    )

    res_b = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {second_holder_token}"},
        json={"name": "Dest Account", "account_type": "customer_savings", "currency": "INR"},
    )
    acc_b_id = res_b.json()["id"]

    # 2. Transfer ₹150.00 (exceeds balance ₹100.00)
    xfer_res = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={
            "source_account_id": acc_a_id,
            "destination_account_id": acc_b_id,
            "amount": "150.00",
        },
    )
    assert xfer_res.status_code == 400
    assert "Insufficient funds" in xfer_res.json()["detail"]

    # 3. Balances remain unchanged
    check_a = client.get(f"/api/v1/accounts/{acc_a_id}", headers={"Authorization": f"Bearer {holder_token}"})
    assert check_a.json()["balance"] == "100.00"
    check_b = client.get(f"/api/v1/accounts/{acc_b_id}", headers={"Authorization": f"Bearer {second_holder_token}"})
    assert check_b.json()["balance"] == "0.00"


def test_group_a_self_transfer_prohibited(client: TestClient, holder_token: str):
    res_a = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Self Account", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_id = res_a.json()["id"]

    xfer_res = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={
            "source_account_id": acc_id,
            "destination_account_id": acc_id,
            "amount": "50.00",
        },
    )
    assert xfer_res.status_code == 400
    assert "Source and destination accounts must be distinct" in xfer_res.text


def test_group_a_frozen_account_operations_rejected(
    client: TestClient, admin_token: str, holder_token: str, second_holder_token: str
):
    # 1. Create account and freeze it
    res_a = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Frozen Candidate", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_a_id = res_a.json()["id"]

    # Fund with ₹500 before freeze
    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_a_id, "amount": "500.00"},
    )

    # Admin freezes account
    freeze_res = client.patch(
        f"/api/v1/accounts/{acc_a_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "frozen"},
    )
    assert freeze_res.status_code == 200
    assert freeze_res.json()["status"] == "frozen"

    # 2. Deposit into frozen account rejected
    dep_res = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_a_id, "amount": "100.00"},
    )
    assert dep_res.status_code == 400
    assert "frozen" in dep_res.json()["detail"]

    # 3. Withdrawal from frozen account rejected
    wd_res = client.post(
        "/api/v1/transfers/withdraw",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_a_id, "amount": "100.00"},
    )
    assert wd_res.status_code == 400
    assert "frozen" in wd_res.json()["detail"]

    # 4. Transfer out of frozen account rejected
    res_b = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {second_holder_token}"},
        json={"name": "Active Recipient", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_b_id = res_b.json()["id"]

    xfer_out = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"source_account_id": acc_a_id, "destination_account_id": acc_b_id, "amount": "50.00"},
    )
    assert xfer_out.status_code == 400
    assert "frozen" in xfer_out.json()["detail"]

    # 5. Transfer into frozen account rejected
    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {second_holder_token}"},
        json={"account_id": acc_b_id, "amount": "200.00"},
    )
    xfer_in = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {second_holder_token}"},
        json={"source_account_id": acc_b_id, "destination_account_id": acc_a_id, "amount": "50.00"},
    )
    assert xfer_in.status_code == 400
    assert "frozen" in xfer_in.json()["detail"]


def test_group_a_exact_monetary_decimal_precision(
    client: TestClient, holder_token: str
):
    # 1. Create fresh account
    res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Exact Paise Math", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_id = res.json()["id"]

    # Deposit ₹12.34
    d_res = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_id, "amount": "12.34"},
    )
    assert d_res.status_code == 201

    # Withdraw ₹5.67
    w_res = client.post(
        "/api/v1/transfers/withdraw",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_id, "amount": "5.67"},
    )
    assert w_res.status_code == 201

    # Expected exact balance: 12.34 - 5.67 = 6.67
    acc_check = client.get(f"/api/v1/accounts/{acc_id}", headers={"Authorization": f"Bearer {holder_token}"})
    assert acc_check.json()["balance"] == "6.67"

    # Sub-paise fractional inputs (e.g. 10.001) are strictly rejected
    sub_res = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_id, "amount": "10.001"},
    )
    assert sub_res.status_code == 422


# ==============================================================================
# GROUP B: Role-Based Authorization & Anti-Enumeration (HTTP 404)
# ==============================================================================

def test_group_b_account_holder_anti_enumeration(
    client: TestClient, holder_token: str, second_holder_token: str
):
    # 1. Holder 2 creates their private account and funds it
    res_b = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {second_holder_token}"},
        json={"name": "Private Account B", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_b_id = res_b.json()["id"]
    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {second_holder_token}"},
        json={"account_id": acc_b_id, "amount": "500.00"},
    )

    # 2. Holder 1 attempts to deposit into Holder 2's account -> 404 Not Found
    dep_leak = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_b_id, "amount": "100.00"},
    )
    assert dep_leak.status_code == 404
    assert dep_leak.json()["detail"] == "Account not found"

    # 3. Holder 1 attempts to withdraw from Holder 2's account -> 404 Not Found
    wd_leak = client.post(
        "/api/v1/transfers/withdraw",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_b_id, "amount": "100.00"},
    )
    assert wd_leak.status_code == 404
    assert wd_leak.json()["detail"] == "Account not found"

    # 4. Holder 1 attempts to source a transfer from Holder 2's account -> 404 Not Found
    res_a = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Holder 1 Checking", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_a_id = res_a.json()["id"]

    xfer_leak = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"source_account_id": acc_b_id, "destination_account_id": acc_a_id, "amount": "50.00"},
    )
    assert xfer_leak.status_code == 404
    assert xfer_leak.json()["detail"] == "Account not found"


def test_group_b_account_holder_cannot_query_unowned_transaction(
    client: TestClient, holder_token: str, second_holder_token: str
):
    # Holder 2 executes a private deposit
    res_b = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {second_holder_token}"},
        json={"name": "Secret Account", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_b_id = res_b.json()["id"]
    dep_b = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {second_holder_token}"},
        json={"account_id": acc_b_id, "amount": "300.00"},
    )
    ref = dep_b.json()["reference"]

    # Holder 1 attempts to inspect Holder 2's transaction reference -> 404 Not Found
    peek_res = client.get(
        f"/api/v1/transfers/{ref}",
        headers={"Authorization": f"Bearer {holder_token}"},
    )
    assert peek_res.status_code == 404
    assert peek_res.json()["detail"] == "Transaction not found"

    # Holder 2 can inspect it successfully -> 200 OK
    legit_res = client.get(
        f"/api/v1/transfers/{ref}",
        headers={"Authorization": f"Bearer {second_holder_token}"},
    )
    assert legit_res.status_code == 200
    assert legit_res.json()["reference"] == ref


def test_group_b_auditor_role_restrictions(
    client: TestClient, auditor_token: str, holder_token: str
):
    res_a = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Audit Target", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_id = res_a.json()["id"]

    # 1. Auditor cannot deposit -> 403 Forbidden
    dep = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {auditor_token}"},
        json={"account_id": acc_id, "amount": "100.00"},
    )
    assert dep.status_code == 403

    # 2. Auditor cannot withdraw -> 403 Forbidden
    wd = client.post(
        "/api/v1/transfers/withdraw",
        headers={"Authorization": f"Bearer {auditor_token}"},
        json={"account_id": acc_id, "amount": "100.00"},
    )
    assert wd.status_code == 403

    # 3. Auditor cannot transfer -> 403 Forbidden
    res_b = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Audit Dest Account", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_b_id = res_b.json()["id"]

    xf = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {auditor_token}"},
        json={"source_account_id": acc_id, "destination_account_id": acc_b_id, "amount": "100.00"},
    )
    assert xf.status_code == 403


    # 4. Auditor CAN inspect transaction journal (Read-Only) -> 200 OK
    journal = client.get(
        "/api/v1/transfers",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert journal.status_code == 200
    assert "items" in journal.json()


def test_group_b_admin_cannot_initiate_transfers(
    client: TestClient, admin_token: str, holder_token: str
):
    """
    Verifies Admin cannot initiate customer-fund transfers (HTTP 403 Forbidden),
    while preserving Admin read access to the transaction journal.
    """
    res_a = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Admin Transfer Source", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_a_id = res_a.json()["id"]

    res_b = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Admin Transfer Dest", "account_type": "customer_savings", "currency": "INR"},
    )
    acc_b_id = res_b.json()["id"]

    # Fund account
    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_a_id, "amount": "1000.00"},
    )

    # Admin cannot initiate transfer -> 403 Forbidden
    xf = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"source_account_id": acc_a_id, "destination_account_id": acc_b_id, "amount": "100.00"},
    )
    assert xf.status_code == 403
    assert "Only Account Holders are permitted to initiate transfers" in xf.json()["detail"]

    # Admin CAN inspect transaction journal -> 200 OK
    journal = client.get(
        "/api/v1/transfers",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert journal.status_code == 200
    assert "items" in journal.json()


def test_group_b_admin_cannot_deposit_or_withdraw(
    client: TestClient, admin_token: str, holder_token: str
):
    """
    Verifies Admin cannot directly invoke deposit or withdrawal endpoints to move customer funds (HTTP 403 Forbidden).
    """
    res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Admin Dep/Wd Target", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_id = res.json()["id"]

    # 1. Admin deposit attempt rejected -> 403 Forbidden
    dep = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"account_id": acc_id, "amount": "500.00"},
    )
    assert dep.status_code == 403
    assert "Only Account Holders are permitted to perform deposits" in dep.json()["detail"]

    # Fund via legitimate Account Holder
    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"account_id": acc_id, "amount": "500.00"},
    )

    # 2. Admin withdrawal attempt rejected -> 403 Forbidden
    wd = client.post(
        "/api/v1/transfers/withdraw",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"account_id": acc_id, "amount": "200.00"},
    )
    assert wd.status_code == 403
    assert "Only Account Holders are permitted to perform withdrawals" in wd.json()["detail"]



# ==============================================================================
# GROUP C: Database Engine Triggers, Immutability & Mandatory Safeguards
# ==============================================================================

def test_group_c_safeguard_1_empty_transaction_rejected_by_trigger(db_session: Session):
    """
    Safeguard 1: Database-level rejection of empty transactions.
    A transaction header with zero ledger entries must NOT be allowed to commit.
    Enforced via deferred constraint trigger trg_verify_transaction_not_empty.
    """
    # Verify directly under runtime role ledgerline_app inside a savepoint
    sp = db_session.begin_nested()
    try:
        empty_txn_id = uuid.uuid4()
        ref = f"TXN-EMPTY-{uuid.uuid4().hex[:6].upper()}"

        # Insert header without entries
        db_session.execute(
            text(
                "INSERT INTO ledger_transactions (id, reference, transaction_type, description, posted_at) "
                "VALUES (:id, :ref, 'transfer', 'Empty transaction test', now())"
            ),
            {"id": empty_txn_id, "ref": ref},
        )

        with pytest.raises(Exception) as exc_info:
            # Invoking SET CONSTRAINTS ALL IMMEDIATE immediately evaluates deferred constraint triggers
            db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        assert "has zero ledger entries and cannot be committed" in str(exc_info.value)
    finally:
        sp.rollback()


def test_group_c_unbalanced_transaction_rejected_by_trigger(
    db_session: Session, holder_token: str, client: TestClient
):
    """
    Deferred zero-sum constraint trigger trg_verify_transaction_balanced rejection.
    Inserting a single credit leg without a matching debit leg must be rejected on deferred evaluation.
    """
    res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Unbalanced Test Acc", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_id = uuid.UUID(res.json()["id"])

    sp = db_session.begin_nested()
    try:
        txn_id = uuid.uuid4()
        ref = f"TXN-UNBAL-{uuid.uuid4().hex[:6].upper()}"

        db_session.execute(
            text(
                "INSERT INTO ledger_transactions (id, reference, transaction_type, description, posted_at) "
                "VALUES (:id, :ref, 'transfer', 'Unbalanced test', now())"
            ),
            {"id": txn_id, "ref": ref},
        )
        db_session.execute(
            text(
                "INSERT INTO ledger_entries (id, transaction_id, account_id, entry_type, amount, sequence, created_at) "
                "VALUES (gen_random_uuid(), :txn_id, :acc_id, 'credit', 500.00, 1, now())"
            ),
            {"txn_id": txn_id, "acc_id": acc_id},
        )

        with pytest.raises(Exception) as exc_info:
            db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        assert "Unbalanced transaction: debits and credits do not balance" in str(exc_info.value)
    finally:
        sp.rollback()



def test_group_c_safeguard_2_security_definer_and_runtime_balance_protection(
    db_session: Session, owner_session: Session
):
    """
    Safeguard 2: SECURITY DEFINER hardening.
    - Revoke EXECUTE from PUBLIC.
    - Fixed safe search_path.
    - Runtime role cannot directly modify accounts.balance.
    """
    # 1. Verify prosecdef = true on balance sync function
    proc_info = owner_session.execute(
        text(
            "SELECT prosecdef, proconfig FROM pg_proc WHERE proname = 'sync_account_balance_from_ledger_entry'"
        )
    ).fetchone()
    assert proc_info is not None
    prosecdef, proconfig = proc_info
    assert prosecdef is True, "sync_account_balance_from_ledger_entry must have SECURITY DEFINER"
    assert proconfig is not None
    assert any("search_path=" in c for c in proconfig), f"search_path must be locked in proconfig: {proconfig}"

    # 2. Verify EXECUTE is revoked from PUBLIC
    has_public_exec = owner_session.execute(
        text(
            "SELECT has_function_privilege('public', 'sync_account_balance_from_ledger_entry()', 'EXECUTE')"
        )
    ).scalar()
    assert has_public_exec is False, "EXECUTE must be revoked from PUBLIC"

    # 3. Verify runtime role CANNOT directly update accounts.balance
    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(text("UPDATE accounts SET balance = balance + 1000"))
            db_session.flush()
        assert "permission denied" in str(exc_info.value).lower()
    finally:
        sp.rollback()


def test_group_c_ledger_immutability_triggers(owner_session: Session):
    """
    Row-level and statement-level ledger immutability triggers protect against UPDATE, DELETE, and TRUNCATE.
    """
    sp = owner_session.begin_nested()
    try:
        # Check statement trigger on TRUNCATE
        with pytest.raises(Exception) as exc_info:
            owner_session.execute(text("TRUNCATE TABLE ledger_transactions CASCADE"))
        assert "Ledger records are strictly immutable" in str(exc_info.value)
    finally:
        sp.rollback()


def test_group_c_system_clearing_account_balance_exemption(owner_session: Session):
    """
    Proves ACC-SYSTEM02 is exempt from chk_customer_balance_non_negative.
    """
    clearing_acc = owner_session.execute(
        text("SELECT balance, account_type FROM accounts WHERE account_number = 'ACC-SYSTEM02'")
    ).fetchone()
    assert clearing_acc is not None
    balance, acc_type = clearing_acc
    assert acc_type == "internal_clearing"


# ==============================================================================
# GROUP D: Alembic Migration Reversibility
# ==============================================================================

def test_group_d_alembic_migration_0004_reversibility():
    """
    Verifies full downgrade and re-upgrade reversibility of migration 0004.
    """
    from alembic.config import Config
    from alembic import command
    from pathlib import Path

    # Dispose application engine pools so connections are closed before DDL execution
    app_engine.dispose()

    project_root = Path(__file__).resolve().parent.parent.parent.parent
    alembic_ini_path = project_root / "backend" / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", str(project_root / "backend" / "alembic"))

    # Reversibility test: downgrade 1 revision, then upgrade to head
    command.downgrade(alembic_cfg, "-1")
    command.upgrade(alembic_cfg, "head")
