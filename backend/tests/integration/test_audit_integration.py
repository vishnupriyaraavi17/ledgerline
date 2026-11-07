import concurrent.futures
import hashlib
import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import ProgrammingError

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal, engine as app_engine
from backend.app.models.user import UserRole
from backend.app.repositories.audit import canonicalize_payload


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
    email = f"{username}@example.com"
    pw = "AuditOfficer123!"

    res = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": username,
            "email": email,
            "password": pw,
            "full_name": "Audit Officer",
            "role": "auditor",
        },
    )
    assert res.status_code == 201, f"Auditor creation failed: {res.text}"

    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": pw},
    )
    assert login_res.status_code == 200, f"Auditor login failed: {login_res.text}"
    return login_res.json()["access_token"]


@pytest.fixture(scope="module")
def user_a(client: TestClient, admin_token: str):
    username = f"audit_user_a_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    pw = "StrongPass123!"

    create_res = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": username,
            "email": email,
            "password": pw,
            "full_name": "Audit User A",
            "role": "account_holder",
        },
    )
    assert create_res.status_code == 201, f"User creation failed: {create_res.text}"
    user_data = create_res.json()

    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": pw},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    return {
        "id": user_data["id"],
        "username": username,
        "token": token,
    }


@pytest.fixture(scope="module")
def user_b(client: TestClient, admin_token: str):
    username = f"audit_user_b_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    pw = "StrongPass123!"

    create_res = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": username,
            "email": email,
            "password": pw,
            "full_name": "Audit User B",
            "role": "account_holder",
        },
    )
    assert create_res.status_code == 201, f"User B creation failed: {create_res.text}"
    user_data = create_res.json()

    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": pw},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    return {
        "id": user_data["id"],
        "username": username,
        "token": token,
    }


# ==============================================================================
# GROUP A: AUDIT RECORDING ACROSS CORE OPERATIONS
# ==============================================================================


def test_group_a_financial_deposit_audit_event(client: TestClient, user_a: dict, db_session: Session):
    """
    Verifies that a deposit transaction atomically appends a financial.deposit
    audit event with idempotency_key_hash and canonical payload.
    """
    # 1. Create account
    create_acc = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a['token']}"},
        json={"name": "Audit Deposit Acc", "account_type": "customer_checking", "currency": "INR"},
    )
    assert create_acc.status_code == 201
    acc_id = create_acc.json()["id"]

    # 2. Issue deposit
    idem_key = f"dep-audit-{uuid.uuid4()}"
    dep_res = client.post(
        "/api/v1/transfers/deposit",
        headers={
            "Authorization": f"Bearer {user_a['token']}",
            "Idempotency-Key": idem_key,
        },
        json={
            "account_id": acc_id,
            "amount": 500.00,
            "description": "Initial test deposit",
        },
    )
    assert dep_res.status_code == 201
    tx_id = dep_res.json()["id"]
    tx_ref = dep_res.json()["reference"]

    # 3. Query audit events for this transaction
    event_row = db_session.execute(
        text("SELECT * FROM public.audit_events WHERE entity_id = :tx_ref AND event_type = 'financial.deposit'"),
        {"tx_ref": tx_ref},
    ).mappings().first()

    assert event_row is not None, "Audit event for deposit not found"
    assert event_row["actor_id"] == uuid.UUID(user_a["id"])
    assert event_row["actor_role"] == "account_holder"
    assert event_row["entity_type"] == "transaction"
    assert event_row["sequence_number"] > 0

    # Payload checks
    payload = event_row["payload"]
    expected_idem_hash = hashlib.sha256(idem_key.encode("utf-8")).hexdigest()
    assert payload["idempotency_key_hash"] == expected_idem_hash
    assert payload["amount"] == "500.00"
    assert payload["currency"] == "INR"
    assert payload["account_id"] == acc_id
    assert payload["transaction_id"] == tx_id


def test_group_a_financial_withdraw_audit_event(client: TestClient, user_a: dict, db_session: Session):
    """
    Verifies that a withdrawal transaction atomically appends a financial.withdraw
    audit event with idempotency_key_hash.
    """
    # 1. Create account & deposit funds
    acc_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a['token']}"},
        json={"name": "Audit Withdraw Acc", "account_type": "customer_checking", "currency": "INR"},
    )
    acc_id = acc_res.json()["id"]

    client.post(
        "/api/v1/transfers/deposit",
        headers={
            "Authorization": f"Bearer {user_a['token']}",
            "Idempotency-Key": f"dep-pre-{uuid.uuid4()}",
        },
        json={"account_id": acc_id, "amount": 1000.00, "description": "Pre-funding"},
    )

    # 2. Issue withdrawal
    idem_key = f"with-audit-{uuid.uuid4()}"
    with_res = client.post(
        "/api/v1/transfers/withdraw",
        headers={
            "Authorization": f"Bearer {user_a['token']}",
            "Idempotency-Key": idem_key,
        },
        json={
            "account_id": acc_id,
            "amount": 350.00,
            "description": "ATM withdrawal",
        },
    )
    assert with_res.status_code == 201
    tx_id = with_res.json()["id"]
    tx_ref = with_res.json()["reference"]

    # 3. Query audit event
    event_row = db_session.execute(
        text("SELECT * FROM public.audit_events WHERE entity_id = :tx_ref AND event_type = 'financial.withdraw'"),
        {"tx_ref": tx_ref},
    ).mappings().first()

    assert event_row is not None
    assert event_row["actor_id"] == uuid.UUID(user_a["id"])
    assert event_row["entity_type"] == "transaction"

    payload = event_row["payload"]
    expected_idem_hash = hashlib.sha256(idem_key.encode("utf-8")).hexdigest()
    assert payload["idempotency_key_hash"] == expected_idem_hash
    assert payload["amount"] == "350.00"
    assert payload["currency"] == "INR"
    assert payload["transaction_id"] == tx_id


def test_group_a_financial_transfer_audit_event(
    client: TestClient, user_a: dict, user_b: dict, db_session: Session
):
    """
    Verifies that a transfer transaction atomically appends a financial.transfer
    audit event linking source and destination accounts.
    """
    # 1. Accounts setup
    acc_a = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a['token']}"},
        json={"name": "Source Checking", "account_type": "customer_checking", "currency": "INR"},
    ).json()["id"]

    acc_b = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_b['token']}"},
        json={"name": "Dest Checking", "account_type": "customer_checking", "currency": "INR"},
    ).json()["id"]

    client.post(
        "/api/v1/transfers/deposit",
        headers={
            "Authorization": f"Bearer {user_a['token']}",
            "Idempotency-Key": f"dep-{uuid.uuid4()}",
        },
        json={"account_id": acc_a, "amount": 800.00, "description": "Pre-funding transfer"},
    )

    # 2. Transfer
    idem_key = f"xfer-audit-{uuid.uuid4()}"
    xfer_res = client.post(
        "/api/v1/transfers/transfer",
        headers={
            "Authorization": f"Bearer {user_a['token']}",
            "Idempotency-Key": idem_key,
        },
        json={
            "source_account_id": acc_a,
            "destination_account_id": acc_b,
            "amount": 275.50,
            "description": "P2P Payment",
        },
    )
    assert xfer_res.status_code == 201
    tx_id = xfer_res.json()["id"]
    tx_ref = xfer_res.json()["reference"]

    # 3. Query audit event
    event_row = db_session.execute(
        text("SELECT * FROM public.audit_events WHERE entity_id = :tx_ref AND event_type = 'financial.transfer'"),
        {"tx_ref": tx_ref},
    ).mappings().first()

    assert event_row is not None
    assert event_row["actor_id"] == uuid.UUID(user_a["id"])

    payload = event_row["payload"]
    expected_idem_hash = hashlib.sha256(idem_key.encode("utf-8")).hexdigest()
    assert payload["idempotency_key_hash"] == expected_idem_hash
    assert payload["amount"] == "275.50"
    assert payload["source_account_id"] == acc_a
    assert payload["destination_account_id"] == acc_b
    assert payload["transaction_id"] == tx_id


def test_group_a_account_lifecycle_audit_events(
    client: TestClient, admin_token: str, user_a: dict, db_session: Session
):
    """
    Verifies that account creation and status modification log account.created
    and account.status_updated events.
    """
    # 1. Create account
    create_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a['token']}"},
        json={"name": "Lifecycle Account", "account_type": "customer_savings", "currency": "INR"},
    )
    assert create_res.status_code == 201
    acc_id = create_res.json()["id"]
    acc_num = create_res.json()["account_number"]

    # Verify account.created audit record
    created_event = db_session.execute(
        text("SELECT * FROM public.audit_events WHERE entity_id = :acc_num AND event_type = 'account.created'"),
        {"acc_num": acc_num},
    ).mappings().first()
    assert created_event is not None
    assert created_event["payload"]["name"] == "Lifecycle Account"
    assert created_event["payload"]["account_type"] == "customer_savings"

    # 2. Admin freezes account
    freeze_res = client.patch(
        f"/api/v1/accounts/{acc_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "frozen"},
    )
    assert freeze_res.status_code == 200

    # Verify account.status_updated audit record
    status_event = db_session.execute(
        text("SELECT * FROM public.audit_events WHERE entity_id = :acc_num AND event_type = 'account.status_updated'"),
        {"acc_num": acc_num},
    ).mappings().first()
    assert status_event is not None
    assert status_event["payload"]["previous_status"] == "active"
    assert status_event["payload"]["new_status"] == "frozen"


def test_group_a_security_user_registration_audit_event(
    client: TestClient, admin_token: str, db_session: Session
):
    """
    Verifies that user creation generates a security.user_registered event.
    """
    uname = f"reg_user_{uuid.uuid4().hex[:8]}"
    create_res = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": uname,
            "email": f"{uname}@example.com",
            "password": "RegistrationPass123!",
            "full_name": "Registered User",
            "role": "account_holder",
        },
    )
    assert create_res.status_code == 201
    user_id = create_res.json()["id"]

    reg_event = db_session.execute(
        text("SELECT * FROM public.audit_events WHERE entity_id = :user_id AND event_type = 'security.user_registered'"),
        {"user_id": user_id},
    ).mappings().first()
    assert reg_event is not None
    assert reg_event["payload"]["username"] == uname
    assert reg_event["payload"]["role"] == "account_holder"


def test_group_a_security_login_success_audit_event(client: TestClient, user_a: dict, db_session: Session):
    """
    Verifies that successful login records security.login_success without client IP.
    """
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": user_a["username"], "password": "StrongPass123!"},
    )
    assert login_res.status_code == 200

    success_event = db_session.execute(
        text("""
            SELECT * FROM public.audit_events
            WHERE entity_id = :user_id AND event_type = 'security.login_success'
            ORDER BY sequence_number DESC LIMIT 1
        """),
        {"user_id": user_a["id"]},
    ).mappings().first()

    assert success_event is not None
    assert success_event["actor_id"] == uuid.UUID(user_a["id"])
    assert "client_ip" not in success_event["payload"]
    assert "ip" not in success_event["payload"]
    assert success_event["payload"]["status"] == "success"


def test_group_a_security_login_failure_isolated_audit_event(client: TestClient, db_session: Session):
    """
    Verifies that failed login:
    1. Returns HTTP 401 with generic error.
    2. Records security.login_failure with actor_id = NULL.
    3. entity_type = 'auth', entity_id = 'login_attempt'.
    4. Payload contains attempted_identifier (truncated to 64 chars) and reason = 'invalid_credentials'.
    5. No client IP, password, or token is stored.
    """
    attempted_user = f"fake_user_{uuid.uuid4().hex[:12]}"

    res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": attempted_user, "password": "WrongPassword123!"},
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid credentials"

    fail_event = db_session.execute(
        text("""
            SELECT * FROM public.audit_events
            WHERE entity_type = 'auth' AND entity_id = 'login_attempt'
              AND event_type = 'security.login_failure'
            ORDER BY sequence_number DESC LIMIT 1
        """)
    ).mappings().first()

    assert fail_event is not None
    assert fail_event["actor_id"] is None, "actor_id must be strictly NULL for failed login"
    assert fail_event["actor_role"] is None

    payload = fail_event["payload"]
    assert payload["attempted_identifier"] == attempted_user[:64]
    assert payload["reason"] == "invalid_credentials"
    assert "password" not in payload
    assert "client_ip" not in payload
    assert "ip" not in payload


# ==============================================================================
# GROUP B: CRYPTOGRAPHIC CHAIN VERIFICATION & HEAD SYNCHRONIZATION
# ==============================================================================


def test_group_b_audit_verification_healthy_chain_via_api(
    client: TestClient, auditor_token: str, admin_token: str, db_session: Session
):
    """
    Verifies that GET /api/v1/audit/verify returns is_valid: True across all accumulated events.
    """
    # 1. Auditor call
    res_auditor = client.get(
        "/api/v1/audit/verify",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert res_auditor.status_code == 200
    data = res_auditor.json()
    assert data["is_valid"] is True
    assert data["tamper_details"] is None
    assert data["total_events"] > 0

    # 2. Admin call
    res_admin = client.get(
        "/api/v1/audit/verify",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["is_valid"] is True


def test_group_b_audit_head_sync(client: TestClient, auditor_token: str, db_session: Session):
    """
    Verifies that GET /api/v1/audit/head strictly matches the latest event in audit_events.
    """
    res = client.get(
        "/api/v1/audit/head",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert res.status_code == 200
    head_data = res.json()

    # Query latest event from DB
    latest_event = db_session.execute(
        text("SELECT sequence_number, current_hash FROM public.audit_events ORDER BY sequence_number DESC LIMIT 1")
    ).mappings().first()

    if latest_event:
        assert head_data["sequence_number"] == latest_event["sequence_number"]
        assert head_data["current_hash"] == latest_event["current_hash"]
    else:
        assert head_data["sequence_number"] == 0
        assert head_data["current_hash"] == "0" * 64


def test_group_b_audit_events_filtering_and_pagination(
    client: TestClient, auditor_token: str
):
    """
    Verifies GET /api/v1/audit/events pagination and filtering by event_type.
    """
    # Filter by financial.deposit
    res = client.get(
        "/api/v1/audit/events?event_type=financial.deposit&limit=10",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert res.status_code == 200
    events = res.json()["items"]
    assert len(events) > 0
    for e in events:
        assert e["event_type"] == "financial.deposit"

    # Pagination check
    res_page = client.get(
        "/api/v1/audit/events?limit=2&offset=0",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert res_page.status_code == 200
    assert len(res_page.json()["items"]) <= 2


# ==============================================================================
# GROUP C: SIMULATED TAMPERING DETECTION
# ==============================================================================


def test_group_c_tamper_detection_hash_mismatch(
    client: TestClient, auditor_token: str, owner_session: Session
):
    """
    Simulates malicious payload modification on an existing event:
    1. Temporarily disable triggers using ledgerline_owner.
    2. Modify event payload in place.
    3. Re-enable triggers.
    4. Assert /api/v1/audit/verify detects HASH_MISMATCH.
    5. Restore original payload and assert verify succeeds again.
    """
    # 1. Select the latest event
    latest = owner_session.execute(
        text("SELECT id, sequence_number, payload FROM public.audit_events ORDER BY sequence_number DESC LIMIT 1")
    ).mappings().first()
    assert latest is not None

    seq_num = latest["sequence_number"]
    orig_payload = latest["payload"]
    tampered_payload = dict(orig_payload)
    tampered_payload["malicious_modification"] = "tampered_value"

    try:
        # Disable row trigger, tamper payload, re-enable trigger
        owner_session.execute(text("ALTER TABLE public.audit_events DISABLE TRIGGER trg_protect_audit_events_row;"))
        owner_session.execute(
            text("UPDATE public.audit_events SET payload = :p WHERE sequence_number = :seq"),
            {"p": json.dumps(tampered_payload), "seq": seq_num},
        )
        owner_session.commit()
        owner_session.execute(text("ALTER TABLE public.audit_events ENABLE TRIGGER trg_protect_audit_events_row;"))
        owner_session.commit()

        # Call verify API
        res = client.get(
            "/api/v1/audit/verify",
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["is_valid"] is False
        assert data["tamper_details"] is not None
        assert data["tamper_details"]["failure_type"] == "HASH_MISMATCH"
        assert data["tamper_details"]["sequence_number"] == seq_num

    finally:
        # Restore original payload
        owner_session.rollback()
        owner_session.execute(text("ALTER TABLE public.audit_events DISABLE TRIGGER trg_protect_audit_events_row;"))
        owner_session.execute(
            text("UPDATE public.audit_events SET payload = :p WHERE sequence_number = :seq"),
            {"p": json.dumps(orig_payload), "seq": seq_num},
        )
        owner_session.commit()
        owner_session.execute(text("ALTER TABLE public.audit_events ENABLE TRIGGER trg_protect_audit_events_row;"))
        owner_session.commit()

    # Confirm chain is healthy again
    healthy_res = client.get(
        "/api/v1/audit/verify",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert healthy_res.status_code == 200
    assert healthy_res.json()["is_valid"] is True


def test_group_c_tamper_detection_broken_chain(
    client: TestClient, auditor_token: str, owner_session: Session
):
    """
    Simulates broken parent hash link:
    1. Temporarily disable triggers using ledgerline_owner.
    2. Change prev_hash of latest event.
    3. Assert verify detects BROKEN_CHAIN.
    4. Restore original prev_hash.
    """
    latest = owner_session.execute(
        text("SELECT sequence_number, prev_hash FROM public.audit_events ORDER BY sequence_number DESC LIMIT 1")
    ).mappings().first()
    assert latest is not None

    seq_num = latest["sequence_number"]
    orig_prev_hash = latest["prev_hash"]
    corrupted_prev_hash = "f" * 64

    try:
        owner_session.execute(text("ALTER TABLE public.audit_events DISABLE TRIGGER trg_protect_audit_events_row;"))
        owner_session.execute(
            text("UPDATE public.audit_events SET prev_hash = :ph WHERE sequence_number = :seq"),
            {"ph": corrupted_prev_hash, "seq": seq_num},
        )
        owner_session.commit()
        owner_session.execute(text("ALTER TABLE public.audit_events ENABLE TRIGGER trg_protect_audit_events_row;"))
        owner_session.commit()

        res = client.get(
            "/api/v1/audit/verify",
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["is_valid"] is False
        assert data["tamper_details"] is not None
        assert data["tamper_details"]["failure_type"] == "BROKEN_CHAIN"
        assert data["tamper_details"]["sequence_number"] == seq_num

    finally:
        owner_session.rollback()
        owner_session.execute(text("ALTER TABLE public.audit_events DISABLE TRIGGER trg_protect_audit_events_row;"))
        owner_session.execute(
            text("UPDATE public.audit_events SET prev_hash = :ph WHERE sequence_number = :seq"),
            {"ph": orig_prev_hash, "seq": seq_num},
        )
        owner_session.commit()
        owner_session.execute(text("ALTER TABLE public.audit_events ENABLE TRIGGER trg_protect_audit_events_row;"))
        owner_session.commit()

    # Confirm restored
    res_restored = client.get(
        "/api/v1/audit/verify",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert res_restored.status_code == 200
    assert res_restored.json()["is_valid"] is True


def test_group_c_tamper_detection_sequence_gap(
    client: TestClient, auditor_token: str, owner_session: Session
):
    """
    Simulates deletion of an event producing a sequence gap:
    1. Temporarily advance sequence_number of latest event by +1.
    2. Assert verify detects SEQUENCE_GAP.
    3. Restore sequence_number.
    """
    latest = owner_session.execute(
        text("SELECT sequence_number FROM public.audit_events ORDER BY sequence_number DESC LIMIT 1")
    ).mappings().first()
    assert latest is not None

    orig_seq = latest["sequence_number"]
    gap_seq = orig_seq + 1

    try:
        owner_session.execute(text("ALTER TABLE public.audit_events DISABLE TRIGGER trg_protect_audit_events_row;"))
        owner_session.execute(
            text("UPDATE public.audit_events SET sequence_number = :gap WHERE sequence_number = :orig"),
            {"gap": gap_seq, "orig": orig_seq},
        )
        owner_session.commit()
        owner_session.execute(text("ALTER TABLE public.audit_events ENABLE TRIGGER trg_protect_audit_events_row;"))
        owner_session.commit()

        res = client.get(
            "/api/v1/audit/verify",
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["is_valid"] is False
        assert data["tamper_details"] is not None
        assert data["tamper_details"]["failure_type"] == "SEQUENCE_GAP"
        assert data["tamper_details"]["sequence_number"] == orig_seq

    finally:
        owner_session.rollback()
        owner_session.execute(text("ALTER TABLE public.audit_events DISABLE TRIGGER trg_protect_audit_events_row;"))
        owner_session.execute(
            text("UPDATE public.audit_events SET sequence_number = :orig WHERE sequence_number = :gap"),
            {"gap": gap_seq, "orig": orig_seq},
        )
        owner_session.commit()
        owner_session.execute(text("ALTER TABLE public.audit_events ENABLE TRIGGER trg_protect_audit_events_row;"))
        owner_session.commit()

    # Confirm restored
    res_restored = client.get(
        "/api/v1/audit/verify",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert res_restored.status_code == 200
    assert res_restored.json()["is_valid"] is True


# ==============================================================================
# GROUP D: CONCURRENCY, DATABASE PERMISSIONS & RBAC ENFORCEMENT
# ==============================================================================


def test_group_d_concurrency_stress_transfers(
    client: TestClient, admin_token: str, user_a: dict, user_b: dict, db_session: Session
):
    """
    Executes 10 concurrent transfer operations across threads:
    - Verifies zero deadlocks due to strict 3-stage lock hierarchy.
    - Verifies sequence numbers are contiguous with no gaps or duplicates.
    - Verifies chain remains mathematically valid.
    """
    # 1. Create accounts and pre-fund
    acc_a = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_a['token']}"},
        json={"name": "Concurrent Source", "account_type": "customer_checking", "currency": "INR"},
    ).json()["id"]

    acc_b = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {user_b['token']}"},
        json={"name": "Concurrent Dest", "account_type": "customer_checking", "currency": "INR"},
    ).json()["id"]

    client.post(
        "/api/v1/transfers/deposit",
        headers={
            "Authorization": f"Bearer {user_a['token']}",
            "Idempotency-Key": f"dep-conc-{uuid.uuid4()}",
        },
        json={"account_id": acc_a, "amount": 10000.00, "description": "Seed for concurrency"},
    )

    # 2. Record starting sequence number
    start_seq_row = db_session.execute(
        text("SELECT COALESCE(MAX(sequence_number), 0) AS max_seq FROM public.audit_events")
    ).mappings().first()
    start_seq = start_seq_row["max_seq"]

    # 3. Launch 10 concurrent transfers
    num_transfers = 10

    def execute_single_transfer(i: int):
        transfer_idem_key = f"concurrent-audit-key-{i}-{uuid.uuid4()}"
        res = client.post(
            "/api/v1/transfers/transfer",
            headers={
                "Authorization": f"Bearer {user_a['token']}",
                "Idempotency-Key": transfer_idem_key,
            },
            json={
                "source_account_id": acc_a,
                "destination_account_id": acc_b,
                "amount": 10.00,
                "description": f"Concurrent transfer {i}",
            },
        )
        return res.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(execute_single_transfer, range(num_transfers)))

    assert all(code == 201 for code in results), f"Some transfers failed: {results}"

    # 4. Check sequence continuity
    end_seq_row = db_session.execute(
        text("SELECT COALESCE(MAX(sequence_number), 0) AS max_seq FROM public.audit_events")
    ).mappings().first()
    end_seq = end_seq_row["max_seq"]
    assert end_seq == start_seq + num_transfers

    # 5. Verify the entire chain is cryptographically sound
    verify_res = client.get(
        "/api/v1/audit/verify",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["is_valid"] is True


def test_group_d_database_privileges_enforced(db_session: Session):
    """
    Verifies that ledgerline_app (runtime role) is strictly prohibited from
    direct INSERT, UPDATE, DELETE, TRUNCATE on audit tables and cannot CREATE
    objects in the public schema.
    """
    # 1. Attempt direct INSERT into audit_events
    with pytest.raises(ProgrammingError) as exc_info:
        db_session.execute(
            text("""
                INSERT INTO public.audit_events (
                    sequence_number, prev_hash, current_hash, event_type,
                    entity_type, entity_id, payload, created_at
                ) VALUES (
                    999999, '0000', '1111', 'malicious.event',
                    'fake', 'fake_id', '{}', NOW()
                )
            """)
        )
    assert "permission denied" in str(exc_info.value).lower()
    db_session.rollback()

    # 2. Attempt direct UPDATE on audit_events
    with pytest.raises(ProgrammingError) as exc_info:
        db_session.execute(text("UPDATE public.audit_events SET event_type = 'hacked'"))
    assert "permission denied" in str(exc_info.value).lower()
    db_session.rollback()

    # 3. Attempt direct DELETE from audit_events
    with pytest.raises(ProgrammingError) as exc_info:
        db_session.execute(text("DELETE FROM public.audit_events"))
    assert "permission denied" in str(exc_info.value).lower()
    db_session.rollback()

    # 4. Attempt direct TRUNCATE on audit_events
    with pytest.raises(ProgrammingError) as exc_info:
        db_session.execute(text("TRUNCATE TABLE public.audit_events"))
    assert "permission denied" in str(exc_info.value).lower()
    db_session.rollback()

    # 5. Attempt direct UPDATE on audit_chain_head
    with pytest.raises(ProgrammingError) as exc_info:
        db_session.execute(text("UPDATE public.audit_chain_head SET sequence_number = 999999 WHERE id = 1"))
    assert "permission denied" in str(exc_info.value).lower()
    db_session.rollback()

    # 6. Attempt CREATE table in public schema
    with pytest.raises(ProgrammingError) as exc_info:
        db_session.execute(text("CREATE TABLE public.malicious_test (id int)"))
    assert "permission denied" in str(exc_info.value).lower()
    db_session.rollback()


def test_group_d_rbac_access_control(
    client: TestClient, user_a: dict, auditor_token: str, admin_token: str
):
    """
    Verifies that Account Holder receives HTTP 403 Forbidden on all /api/v1/audit/* endpoints,
    while Auditor and Admin are authorized.
    """
    audit_endpoints = [
        "/api/v1/audit/verify",
        "/api/v1/audit/head",
        "/api/v1/audit/events",
    ]

    # Account holder -> 403 Forbidden
    for ep in audit_endpoints:
        res = client.get(ep, headers={"Authorization": f"Bearer {user_a['token']}"})
        assert res.status_code == 403, f"Expected 403 for account holder on {ep}, got {res.status_code}"

    # Auditor -> 200 OK
    for ep in audit_endpoints:
        res = client.get(ep, headers={"Authorization": f"Bearer {auditor_token}"})
        assert res.status_code == 200, f"Expected 200 for auditor on {ep}, got {res.status_code}"

    # Admin -> 200 OK
    for ep in audit_endpoints:
        res = client.get(ep, headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200, f"Expected 200 for admin on {ep}, got {res.status_code}"


# ==============================================================================
# GROUP E: ALEMBIC MIGRATION REVERSIBILITY
# ==============================================================================


def test_group_e_alembic_migration_0006_reversibility():
    """
    Verifies full downgrade and re-upgrade reversibility of migration 0006.
    """
    from alembic.config import Config
    from alembic import command

    # Dispose application engine pools so connections are closed before DDL execution
    app_engine.dispose()

    project_root = Path(__file__).resolve().parent.parent.parent.parent
    alembic_ini_path = project_root / "backend" / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", str(project_root / "backend" / "alembic"))

    # 1. Downgrade 1 revision (reverts 0006)
    command.downgrade(alembic_cfg, "-1")

    # 2. Upgrade back to head (re-applies 0006)
    command.upgrade(alembic_cfg, "head")

    # 3. Verify clean genesis state
    with SessionLocal() as db:
        head_row = db.execute(
            text("SELECT sequence_number, current_hash FROM public.audit_chain_head WHERE id = 1")
        ).mappings().first()
        assert head_row is not None
        assert head_row["sequence_number"] == 0
        assert head_row["current_hash"] == "0" * 64

        count_events = db.execute(
            text("SELECT COUNT(*) AS cnt FROM public.audit_events")
        ).scalar()
        assert count_events == 0
