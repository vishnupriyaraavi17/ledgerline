import concurrent.futures
import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal


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
def user_a_token(client: TestClient, admin_token: str) -> str:
    username = f"user_a_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    pw = "StrongPass123!"

    client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": username,
            "email": email,
            "password": pw,
            "full_name": "User Alpha",
            "role": "account_holder",
        },
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": pw},
    )
    return login_res.json()["access_token"]


@pytest.fixture(scope="module")
def user_b_token(client: TestClient, admin_token: str) -> str:
    username = f"user_b_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    pw = "StrongPass123!"

    client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": username,
            "email": email,
            "password": pw,
            "full_name": "User Beta",
            "role": "account_holder",
        },
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": pw},
    )
    return login_res.json()["access_token"]


# ==============================================================================
# GROUP A: CORE REPLAY & DEDUPLICATION
# ==============================================================================


def test_group_a_successful_deposit_replay(client: TestClient, user_a_token: str, db_session: Session):
    # 1. Create account
    create_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"name": "Replay Checking", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_id = create_res.json()["id"]

    idem_key = f"dep-key-{uuid.uuid4()}"
    payload = {"account_id": acc_id, "amount": "1500.00", "description": "Consulting Fee"}

    # 2. First execution: should post transaction
    res1 = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json=payload,
    )
    assert res1.status_code == 201
    assert "Idempotent-Replay" not in res1.headers
    txn1 = res1.json()

    # 3. Second execution (replay): identical key and identical payload
    res2 = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json=payload,
    )
    assert res2.status_code == 201
    assert res2.headers.get("Idempotent-Replay") == "true"
    txn2 = res2.json()

    # Result data matches exactly
    assert txn1["id"] == txn2["id"]
    assert txn1["reference"] == txn2["reference"]

    # 4. Direct DB verification: exactly 1 transaction and 2 entries exist for this reference
    txn_count = db_session.execute(
        text("SELECT count(*) FROM public.ledger_transactions WHERE reference = :ref"),
        {"ref": txn1["reference"]},
    ).scalar()
    assert txn_count == 1

    entry_count = db_session.execute(
        text("SELECT count(*) FROM public.ledger_entries WHERE transaction_id = :tid"),
        {"tid": txn1["id"]},
    ).scalar()
    assert entry_count == 2

    # Account balance was credited exactly ONCE
    acc_balance = db_session.execute(
        text("SELECT balance FROM public.accounts WHERE id = :aid"),
        {"aid": acc_id},
    ).scalar()
    assert acc_balance == Decimal("1500.00")


def test_group_a_successful_withdrawal_replay(client: TestClient, user_a_token: str, db_session: Session):
    # Create and fund account
    acc = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"name": "Withdraw Replay", "account_type": "customer_checking", "currency": "INR"},
    ).json()
    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": f"fund-{uuid.uuid4()}"},
        json={"account_id": acc["id"], "amount": "2000.00"},
    )

    idem_key = f"wd-key-{uuid.uuid4()}"
    payload = {"account_id": acc["id"], "amount": "500.00", "description": "ATM"}

    # 1. Primary withdrawal
    res1 = client.post(
        "/api/v1/transfers/withdraw",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json=payload,
    )
    assert res1.status_code == 201
    assert "Idempotent-Replay" not in res1.headers

    # 2. Replay identical withdrawal
    res2 = client.post(
        "/api/v1/transfers/withdraw",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json=payload,
    )
    assert res2.status_code == 201
    assert res2.headers.get("Idempotent-Replay") == "true"
    assert res1.json()["reference"] == res2.json()["reference"]

    # Balance debited exactly ONCE (2000 - 500 = 1500)
    acc_balance = db_session.execute(
        text("SELECT balance FROM public.accounts WHERE id = :aid"),
        {"aid": acc["id"]},
    ).scalar()
    assert acc_balance == Decimal("1500.00")


def test_group_a_successful_transfer_replay(
    client: TestClient, user_a_token: str, user_b_token: str, db_session: Session
):
    acc_src = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"name": "Src Checking", "account_type": "customer_checking", "currency": "INR"},
    ).json()
    acc_dst = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_b_token}"},
        json={"name": "Dst Checking", "account_type": "customer_checking", "currency": "INR"},
    ).json()

    # Fund source with ₹1,000.00
    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": f"fund-{uuid.uuid4()}"},
        json={"account_id": acc_src["id"], "amount": "1000.00"},
    )

    idem_key = f"xfer-key-{uuid.uuid4()}"
    payload = {
        "source_account_id": acc_src["id"],
        "destination_account_id": acc_dst["id"],
        "amount": "300.00",
        "description": "Lunch split",
    }

    # Primary transfer
    res1 = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json=payload,
    )
    assert res1.status_code == 201

    # Replay transfer
    res2 = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json=payload,
    )
    assert res2.status_code == 201
    assert res2.headers.get("Idempotent-Replay") == "true"
    assert res1.json()["reference"] == res2.json()["reference"]

    # Verify balances: Source ₹700.00, Destination ₹300.00
    bal_src = db_session.execute(
        text("SELECT balance FROM public.accounts WHERE id = :aid"), {"aid": acc_src["id"]}
    ).scalar()
    bal_dst = db_session.execute(
        text("SELECT balance FROM public.accounts WHERE id = :aid"), {"aid": acc_dst["id"]}
    ).scalar()
    assert bal_src == Decimal("700.00")
    assert bal_dst == Decimal("300.00")


# ==============================================================================
# GROUP B: CONFLICT DETECTION (HTTP 409)
# ==============================================================================


def test_group_b_conflict_same_key_different_amount(client: TestClient, user_a_token: str):
    acc = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"name": "Conflict Acc", "account_type": "customer_checking", "currency": "INR"},
    ).json()

    idem_key = f"conflict-{uuid.uuid4()}"

    # Request 1: Deposit ₹500.00
    res1 = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json={"account_id": acc["id"], "amount": "500.00"},
    )
    assert res1.status_code == 201

    # Request 2: Same key, Deposit ₹600.00
    res2 = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json={"account_id": acc["id"], "amount": "600.00"},
    )
    assert res2.status_code == 409
    assert "different request payload" in res2.json()["detail"]


def test_group_b_conflict_same_key_different_destination(
    client: TestClient, user_a_token: str, user_b_token: str
):
    src = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"name": "Src Acc", "account_type": "customer_checking", "currency": "INR"},
    ).json()
    dst1 = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_b_token}"},
        json={"name": "Dst 1", "account_type": "customer_checking", "currency": "INR"},
    ).json()
    dst2 = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_b_token}"},
        json={"name": "Dst 2", "account_type": "customer_checking", "currency": "INR"},
    ).json()

    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": f"fund-{uuid.uuid4()}"},
        json={"account_id": src["id"], "amount": "1000.00"},
    )

    idem_key = f"xfer-conflict-{uuid.uuid4()}"

    # Transfer to Dst1
    res1 = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json={"source_account_id": src["id"], "destination_account_id": dst1["id"], "amount": "100.00"},
    )
    assert res1.status_code == 201

    # Same key, Transfer to Dst2
    res2 = client.post(
        "/api/v1/transfers/transfer",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json={"source_account_id": src["id"], "destination_account_id": dst2["id"], "amount": "100.00"},
    )
    assert res2.status_code == 409
    assert "different request payload" in res2.json()["detail"]


def test_group_b_conflict_same_key_different_operation(client: TestClient, user_a_token: str):
    acc = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"name": "Op Conflict", "account_type": "customer_checking", "currency": "INR"},
    ).json()

    idem_key = f"op-conflict-{uuid.uuid4()}"

    # Deposit ₹200.00
    res1 = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json={"account_id": acc["id"], "amount": "200.00"},
    )
    assert res1.status_code == 201

    # Attempt Withdrawal with same key
    res2 = client.post(
        "/api/v1/transfers/withdraw",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json={"account_id": acc["id"], "amount": "200.00"},
    )
    assert res2.status_code == 409
    assert "different request payload" in res2.json()["detail"]


# ==============================================================================
# GROUP C: MULTI-TENANT ISOLATION
# ==============================================================================


def test_group_c_multi_tenant_isolation_shared_key(
    client: TestClient, user_a_token: str, user_b_token: str
):
    acc_a = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"name": "A Acc", "account_type": "customer_checking", "currency": "INR"},
    ).json()
    acc_b = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_b_token}"},
        json={"name": "B Acc", "account_type": "customer_checking", "currency": "INR"},
    ).json()

    shared_key = f"shared-idempotency-key-{uuid.uuid4()}"

    # User A uses key
    res_a = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": shared_key},
        json={"account_id": acc_a["id"], "amount": "100.00"},
    )
    assert res_a.status_code == 201

    # User B uses identical key independently
    res_b = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {user_b_token}", "Idempotency-Key": shared_key},
        json={"account_id": acc_b["id"], "amount": "100.00"},
    )
    assert res_b.status_code == 201

    # Different transactions generated
    assert res_a.json()["id"] != res_b.json()["id"]
    assert res_a.json()["reference"] != res_b.json()["reference"]


# ==============================================================================
# GROUP D: CONCURRENCY, ROLLBACK & INTEGRITY
# ==============================================================================


def test_group_d_concurrent_identical_requests_deduplicated(
    client: TestClient, user_a_token: str, db_session: Session
):
    acc = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"name": "Concurrent Race Acc", "account_type": "customer_checking", "currency": "INR"},
    ).json()

    idem_key = f"race-{uuid.uuid4()}"
    payload = {"account_id": acc["id"], "amount": "400.00", "description": "Concurrent deposit"}

    def submit_request():
        # Create fresh TestClient per thread
        from backend.app.main import app
        with TestClient(app) as thread_client:
            return thread_client.post(
                "/api/v1/transfers/deposit",
                headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
                json=payload,
            )

    # Launch 5 concurrent requests with identical key and payload
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(submit_request) for _ in range(5)]
        results = [f.result() for f in futures]

    # All 5 requests must succeed with HTTP 201
    status_codes = [r.status_code for r in results]
    assert status_codes == [201, 201, 201, 201, 201]

    # Exactly one transaction was created; all return identical reference
    references = {r.json()["reference"] for r in results}
    assert len(references) == 1

    # At least some requests should have the Idempotent-Replay header
    replay_headers = [r.headers.get("Idempotent-Replay") for r in results]
    assert "true" in replay_headers

    # Account balance credited exactly once (₹400.00, NOT ₹2000.00)
    acc_balance = db_session.execute(
        text("SELECT balance FROM public.accounts WHERE id = :aid"), {"aid": acc["id"]}
    ).scalar()
    assert acc_balance == Decimal("400.00")


def test_group_d_failed_transaction_rollback_allows_retry(client: TestClient, user_a_token: str, db_session: Session):
    acc = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"name": "Rollback Test", "account_type": "customer_checking", "currency": "INR"},
    ).json()

    idem_key = f"rollback-{uuid.uuid4()}"

    # Attempt withdrawal on ₹0.00 balance
    res_fail = client.post(
        "/api/v1/transfers/withdraw",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json={"account_id": acc["id"], "amount": "500.00"},
    )
    assert res_fail.status_code == 400
    assert "Insufficient funds" in res_fail.json()["detail"]

    # Verify no completed or processing record remains in DB
    record_count = db_session.execute(
        text("SELECT count(*) FROM public.idempotency_records WHERE idempotency_key = :k"),
        {"k": idem_key},
    ).scalar()
    assert record_count == 0

    # Fund account with ₹1,000.00
    client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": f"fund-{uuid.uuid4()}"},
        json={"account_id": acc["id"], "amount": "1000.00"},
    )

    # Retry the withdrawal with the SAME key: now succeeds cleanly!
    res_retry = client.post(
        "/api/v1/transfers/withdraw",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json={"account_id": acc["id"], "amount": "500.00"},
    )
    assert res_retry.status_code == 201


def test_group_d_foreign_key_on_delete_restrict_enforced(
    client: TestClient, user_a_token: str, owner_session: Session, db_session: Session
):
    """
    Asserts ON DELETE RESTRICT prevents deleting users or transactions that have idempotency records.
    """
    acc = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"name": "Restrict Acc", "account_type": "customer_checking", "currency": "INR"},
    ).json()

    idem_key = f"restrict-{uuid.uuid4()}"
    res = client.post(
        "/api/v1/transfers/deposit",
        headers={"Authorization": f"Bearer {user_a_token}", "Idempotency-Key": idem_key},
        json={"account_id": acc["id"], "amount": "100.00"},
    )
    assert res.status_code == 201
    txn_id = res.json()["id"]

    # Lookup user_id
    user_id = db_session.execute(
        text("SELECT user_id FROM public.idempotency_records WHERE idempotency_key = :k"),
        {"k": idem_key},
    ).scalar()

    # Attempt to delete user under owner session -> rejected by ON DELETE RESTRICT
    with pytest.raises(Exception) as exc_user:
        owner_session.execute(
            text("DELETE FROM public.users WHERE id = :uid"),
            {"uid": user_id},
        )
        owner_session.flush()
    assert "violates foreign key constraint" in str(exc_user.value).lower()
    owner_session.rollback()

    # Attempt to delete transaction under owner session -> rejected by immutability trigger and ON DELETE RESTRICT
    with pytest.raises(Exception) as exc_txn:
        owner_session.execute(
            text("DELETE FROM public.ledger_transactions WHERE id = :tid"),
            {"tid": txn_id},
        )
        owner_session.flush()
    err_txn = str(exc_txn.value).lower()
    assert "ledger records are strictly immutable" in err_txn or "violates foreign key constraint" in err_txn
    owner_session.rollback()


# ==============================================================================
# GROUP E: RUNTIME DATABASE PRIVILEGE ENFORCEMENT
# ==============================================================================


def test_group_e_runtime_role_denied_delete_on_idempotency_records(db_session: Session):
    """
    Asserts ledgerline_app has SELECT, INSERT, UPDATE, but CANNOT DELETE from idempotency_records.
    """
    # Verify current runtime user
    current_user = db_session.execute(text("SELECT current_user")).scalar()
    assert current_user == "ledgerline_app"

    # Attempt DELETE on idempotency_records -> MUST fail closed
    with pytest.raises(Exception) as exc_info:
        db_session.execute(text("DELETE FROM public.idempotency_records;"))
        db_session.flush()

    err_str = str(exc_info.value).lower()
    assert "permission denied" in err_str or "insufficient privilege" in err_str
    db_session.rollback()
