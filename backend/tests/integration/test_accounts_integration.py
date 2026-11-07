import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal, engine as app_engine
from backend.app.models.user import User, UserRole
from backend.app.models.account import Account, AccountType, AccountStatus


@pytest.fixture(scope="function")
def db_session():
    """Live application database session (running as ledgerline_app)."""
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


# ==============================================================================
# GROUP A: Application Runtime Role Tests (Restricted Permissions)
# ==============================================================================

def test_group_a_runtime_role_active_session_and_security_attributes(db_session: Session):
    # 1. Verify active connection is under the resolved canonical runtime role
    current_user = db_session.execute(text("SELECT current_user")).scalar()
    assert current_user == settings.RUNTIME_POSTGRES_USER
    assert current_user == "ledgerline_app"

    # 2. Verify all 6 security attributes in pg_roles are strictly False
    role_row = db_session.execute(
        text(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolinherit, rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname = :rolname"
        ),
        {"rolname": current_user},
    ).fetchone()
    assert role_row is not None
    rolsuper, rolcreaterole, rolcreatedb, rolinherit, rolreplication, rolbypassrls = role_row
    assert rolsuper is False
    assert rolcreaterole is False
    assert rolcreatedb is False
    assert rolinherit is False
    assert rolreplication is False
    assert rolbypassrls is False

    # 3. Verify zero role memberships in pg_auth_members
    membership_count = db_session.execute(
        text(
            "SELECT count(*) FROM pg_auth_members "
            "WHERE member = (SELECT oid FROM pg_roles WHERE rolname = :rolname)"
        ),
        {"rolname": current_user},
    ).scalar()
    assert membership_count == 0


def test_group_a_effective_postgresql_privileges(db_session: Session):
    app_user = settings.RUNTIME_POSTGRES_USER

    # 1. Effective table privileges: ledger tables are strictly read-only
    for priv in ["INSERT", "UPDATE", "DELETE", "TRUNCATE"]:
        has_ledger_priv = db_session.execute(
            text(f"SELECT has_table_privilege('{app_user}', 'ledger_entries', '{priv}')")
        ).scalar()
        assert has_ledger_priv is False, f"Expected no {priv} on ledger_entries for {app_user}"

        has_txn_priv = db_session.execute(
            text(f"SELECT has_table_privilege('{app_user}', 'ledger_transactions', '{priv}')")
        ).scalar()
        assert has_txn_priv is False, f"Expected no {priv} on ledger_transactions for {app_user}"

    # 2. Accounts table: DELETE and TRUNCATE are revoked
    for priv in ["DELETE", "TRUNCATE"]:
        has_acc_priv = db_session.execute(
            text(f"SELECT has_table_privilege('{app_user}', 'accounts', '{priv}')")
        ).scalar()
        assert has_acc_priv is False, f"Expected no {priv} on accounts for {app_user}"

    # 3. Column-level privileges on accounts
    # balance cannot be inserted or updated
    assert db_session.execute(
        text(f"SELECT has_column_privilege('{app_user}', 'accounts', 'balance', 'INSERT')")
    ).scalar() is False
    assert db_session.execute(
        text(f"SELECT has_column_privilege('{app_user}', 'accounts', 'balance', 'UPDATE')")
    ).scalar() is False

    # name cannot be updated
    assert db_session.execute(
        text(f"SELECT has_column_privilege('{app_user}', 'accounts', 'name', 'UPDATE')")
    ).scalar() is False

    # status and updated_at can be updated
    assert db_session.execute(
        text(f"SELECT has_column_privilege('{app_user}', 'accounts', 'status', 'UPDATE')")
    ).scalar() is True
    assert db_session.execute(
        text(f"SELECT has_column_privilege('{app_user}', 'accounts', 'updated_at', 'UPDATE')")
    ).scalar() is True


def test_group_a_zero_balance_account_creation_api(
    client: TestClient, admin_token: str, holder_token: str, db_session: Session
):
    # 1. Admin creates account
    res_admin = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Admin Managed Checking", "account_type": "customer_checking", "currency": "INR"},
    )
    assert res_admin.status_code == 201, f"Create failed: {res_admin.text}"
    admin_acc_data = res_admin.json()
    assert admin_acc_data["balance"] == "0.00"
    assert admin_acc_data["currency"] == "INR"
    assert admin_acc_data["status"] == "active"
    assert admin_acc_data["account_number"].startswith("ACC-")

    # 2. Account Holder creates self-owned account
    res_holder = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"name": "Holder Personal Savings", "account_type": "customer_savings", "currency": "INR"},
    )
    assert res_holder.status_code == 201, f"Create failed: {res_holder.text}"
    holder_acc_data = res_holder.json()
    assert holder_acc_data["balance"] == "0.00"
    assert holder_acc_data["currency"] == "INR"
    assert holder_acc_data["status"] == "active"

    # Verify directly in DB
    acc_id = uuid.UUID(holder_acc_data["id"])
    db_acc = db_session.scalar(text("SELECT balance FROM accounts WHERE id = :id"), {"id": acc_id})
    assert db_acc == Decimal("0.00")

    # Verify zero ledger postings exist
    entry_count = db_session.scalar(
        text("SELECT count(*) FROM ledger_entries WHERE account_id = :id"), {"id": acc_id}
    )
    assert entry_count == 0


def test_group_a_ownership_isolation_and_404_anti_enumeration(
    client: TestClient, admin_token: str, holder_token: str
):
    # Create another user and an account for that user
    user_b_res = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": f"user_b_{uuid.uuid4().hex[:6]}",
            "email": f"user_b_{uuid.uuid4().hex[:6]}@example.com",
            "password": "SecurePassword123!",
            "role": "account_holder",
        },
    )
    assert user_b_res.status_code == 201
    user_b_id = user_b_res.json()["id"]

    acc_b_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "User B Primary",
            "account_type": "customer_checking",
            "currency": "INR",
            "owner_id": user_b_id,
        },
    )
    assert acc_b_res.status_code == 201
    acc_b_id = acc_b_res.json()["id"]

    # User A (Account Holder) lists accounts -> must NOT see User B's account
    holder_list_res = client.get(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {holder_token}"},
    )
    assert holder_list_res.status_code == 200
    holder_account_ids = [acc["id"] for acc in holder_list_res.json()["items"]]
    assert acc_b_id not in holder_account_ids

    # User A directly queries User B's account -> strictly HTTP 404 (Anti-Enumeration)
    get_res = client.get(
        f"/api/v1/accounts/{acc_b_id}",
        headers={"Authorization": f"Bearer {holder_token}"},
    )
    assert get_res.status_code == 404, f"Expected 404 anti-enumeration, got {get_res.status_code}"

    # User A queries ledger for User B's account -> strictly HTTP 404 (Anti-Enumeration)
    ledger_res = client.get(
        f"/api/v1/accounts/{acc_b_id}/ledger",
        headers={"Authorization": f"Bearer {holder_token}"},
    )
    assert ledger_res.status_code == 404, f"Expected 404 anti-enumeration, got {ledger_res.status_code}"

    # Non-existent account ID returns 404
    non_existent_id = uuid.uuid4()
    assert client.get(
        f"/api/v1/accounts/{non_existent_id}",
        headers={"Authorization": f"Bearer {holder_token}"},
    ).status_code == 404


def test_group_a_role_based_restrictions_and_lifecycle(
    client: TestClient, admin_token: str, holder_token: str, auditor_token: str
):
    # Auditor cannot create accounts (403)
    auditor_create_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {auditor_token}"},
        json={"name": "Auditor Account", "account_type": "customer_checking", "currency": "INR"},
    )
    assert auditor_create_res.status_code == 403

    # Create account to test lifecycle
    create_res = client.post(
        "/api/v1/accounts",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Lifecycle Test Account", "account_type": "customer_checking", "currency": "INR"},
    )
    assert create_res.status_code == 201
    account_id = create_res.json()["id"]

    # Holder cannot update account status (403)
    assert client.patch(
        f"/api/v1/accounts/{account_id}/status",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"status": "frozen"},
    ).status_code == 403

    # Auditor cannot update account status (403)
    assert client.patch(
        f"/api/v1/accounts/{account_id}/status",
        headers={"Authorization": f"Bearer {auditor_token}"},
        json={"status": "frozen"},
    ).status_code == 403

    # Admin freezes account (200)
    freeze_res = client.patch(
        f"/api/v1/accounts/{account_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "frozen"},
    )
    assert freeze_res.status_code == 200
    assert freeze_res.json()["status"] == "frozen"

    # Admin unfreezes account (200)
    unfreeze_res = client.patch(
        f"/api/v1/accounts/{account_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "active"},
    )
    assert unfreeze_res.status_code == 200
    assert unfreeze_res.json()["status"] == "active"

    # Admin closes account with ₹0.00 balance (200)
    close_res = client.patch(
        f"/api/v1/accounts/{account_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "closed"},
    )
    assert close_res.status_code == 200
    assert close_res.json()["status"] == "closed"

    # Reopening closed account is rejected (400)
    reopen_res = client.patch(
        f"/api/v1/accounts/{account_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "active"},
    )
    assert reopen_res.status_code == 400
    assert "Closed accounts cannot be reopened" in reopen_res.json()["detail"]


def test_group_a_privilege_and_trigger_enforcement_under_runtime_role(db_session: Session):
    # 1. Reserved Account Number Pattern INSERT rejected by trigger
    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(
                text(
                    "INSERT INTO accounts (id, account_number, owner_id, name, account_type, currency, status) "
                    "VALUES (gen_random_uuid(), 'ACC-SYSTEM99', NULL, 'Reserved Hack', 'customer_checking', 'INR', 'active')"
                )
            )
        assert "Reserved system account numbers" in str(exc_info.value)
    finally:
        sp.rollback()

    # 2. Account Number Format Constraint Enforced
    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(
                text(
                    "INSERT INTO accounts (id, account_number, owner_id, name, account_type, currency, status) "
                    "VALUES (gen_random_uuid(), 'INVALID_ACC', NULL, 'Invalid', 'customer_checking', 'INR', 'active')"
                )
            )
        assert "chk_account_number_format" in str(exc_info.value)
    finally:
        sp.rollback()

    # 3. Direct Balance Column INSERT rejected by column-level privilege
    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(
                text(
                    "INSERT INTO accounts (id, account_number, owner_id, name, account_type, currency, balance, status) "
                    "VALUES (gen_random_uuid(), 'ACC-HACK0001', NULL, 'Balance Hack', 'customer_checking', 'INR', 500.00, 'active')"
                )
            )
        assert "permission denied" in str(exc_info.value)
        assert ("column balance" in str(exc_info.value) or "table accounts" in str(exc_info.value))
    finally:
        sp.rollback()

    # 4. System Account Type INSERT rejected by trigger
    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(
                text(
                    "INSERT INTO accounts (id, account_number, owner_id, name, account_type, currency, status) "
                    "VALUES (gen_random_uuid(), 'ACC-HACK0002', NULL, 'System Hack', 'system_reserve', 'INR', 'active')"
                )
            )
        assert "System account types can only be provisioned by the migration owner role" in str(exc_info.value)
    finally:
        sp.rollback()

    # Create a legitimate test account under runtime role for update tests
    test_acc_id = uuid.uuid4()
    unique_acc_num = f"ACC-V{uuid.uuid4().hex[:7].upper()}"
    db_session.execute(
        text(
            "INSERT INTO accounts (id, account_number, owner_id, name, account_type, currency, status) "
            "VALUES (:id, :acc_num, NULL, 'Valid Account', 'customer_checking', 'INR', 'active')"
        ),
        {"id": test_acc_id, "acc_num": unique_acc_num},
    )
    db_session.commit()

    # 5. Operational Column UPDATE on accounts.name rejected by column privilege
    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(
                text("UPDATE accounts SET name = 'Tampered' WHERE id = :id"),
                {"id": test_acc_id},
            )
        assert "permission denied" in str(exc_info.value)
    finally:
        sp.rollback()

    # 6. Operational Column UPDATE on accounts.balance rejected by column privilege
    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(
                text("UPDATE accounts SET balance = 1000.00 WHERE id = :id"),
                {"id": test_acc_id},
            )
        assert "permission denied" in str(exc_info.value)
    finally:
        sp.rollback()

    # 7. Operational Column UPDATE on accounts.status and updated_at succeeds
    db_session.execute(
        text("UPDATE accounts SET status = 'frozen', updated_at = now() WHERE id = :id"),
        {"id": test_acc_id},
    )
    db_session.commit()

    # 8. Ledger Tables INSERT is permitted under Task 04, but empty transactions are rejected by trigger
    sp = db_session.begin_nested()
    try:
        db_session.execute(
            text(
                "INSERT INTO ledger_transactions (id, reference, transaction_type, description, posted_at) "
                "VALUES (gen_random_uuid(), :ref, 'transfer', 'Task 04 Allowed Insert', now())"
            ),
            {"ref": f"TXN-T04-{uuid.uuid4().hex[:6].upper()}"},
        )
        with pytest.raises(Exception) as exc_info:
            db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        assert "has zero ledger entries and cannot be committed" in str(exc_info.value)
    finally:
        sp.rollback()


    # 9. Ledger Tables UPDATE, DELETE, TRUNCATE rejected by table privilege
    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(text("UPDATE ledger_entries SET amount = 999.00"))
        assert "permission denied for table ledger_entries" in str(exc_info.value)
    finally:
        sp.rollback()

    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(text("DELETE FROM ledger_entries"))
        assert "permission denied for table ledger_entries" in str(exc_info.value)
    finally:
        sp.rollback()

    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(text("TRUNCATE TABLE ledger_entries"))
        assert "permission denied for table ledger_entries" in str(exc_info.value)
    finally:
        sp.rollback()

    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(text("TRUNCATE TABLE ledger_transactions"))
        assert "permission denied for table ledger_transactions" in str(exc_info.value)
    finally:
        sp.rollback()

    # 10. Accounts Table DELETE and TRUNCATE rejected
    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(text("DELETE FROM accounts WHERE id = :id"), {"id": test_acc_id})
        assert "permission denied for table accounts" in str(exc_info.value)
    finally:
        sp.rollback()

    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(text("TRUNCATE TABLE accounts"))
        assert "permission denied for table accounts" in str(exc_info.value)
    finally:
        sp.rollback()

    # 11. Trigger Disabling Rejected (must be table owner)
    sp = db_session.begin_nested()
    try:
        with pytest.raises(Exception) as exc_info:
            db_session.execute(text("ALTER TABLE ledger_entries DISABLE TRIGGER ALL"))
        assert "must be owner of table ledger_entries" in str(exc_info.value)
    finally:
        sp.rollback()


# ==============================================================================
# GROUP B: Migration / Owner Role Tests (Trigger Enforcement & System Accounts)
# ==============================================================================

def test_group_b_migration_seed_verification(owner_session: Session):
    # 1. Verify root system account ACC-SYSTEM01 seeded during migration exists exactly once
    seed_acc = owner_session.execute(
        text("SELECT account_number, account_type, currency, balance, status FROM accounts WHERE account_number = 'ACC-SYSTEM01'")
    ).fetchone()
    assert seed_acc is not None
    acc_num, acc_type, currency, balance, status = seed_acc
    assert acc_num == "ACC-SYSTEM01"
    assert acc_type == "system_reserve"
    assert currency == "INR"
    assert balance == Decimal("0.00")
    assert status == "active"


def test_group_b_owner_role_system_account_creation_trigger(owner_session: Session):
    # Verify database trigger trg_enforce_account_creation_permissions permits migration owner
    # to provision a system account. Executed in a nested savepoint and rolled back immediately.
    sp = owner_session.begin_nested()
    try:
        owner_session.execute(
            text(
                "INSERT INTO accounts (id, account_number, owner_id, name, account_type, currency, balance, status) "
                "VALUES (gen_random_uuid(), 'ACC-SYSTEM03', NULL, 'Test Reserve', 'system_reserve', 'INR', 0.00, 'active')"
            )
        )
        created = owner_session.execute(
            text("SELECT account_number FROM accounts WHERE account_number = 'ACC-SYSTEM03'")
        ).scalar()
        assert created == "ACC-SYSTEM03"
    finally:
        sp.rollback()

    # Ensure rollback cleaned up the temporary system account
    assert owner_session.execute(
        text("SELECT count(*) FROM accounts WHERE account_number = 'ACC-SYSTEM03'")
    ).scalar() == 0



def test_group_b_immutability_triggers_on_actual_rows(owner_session: Session):
    """
    Sets up temporary fixture rows in an isolated transaction under ledgerline_owner,
    verifies that row-level and statement-level triggers intercept and reject modifications,
    and rolls back savepoints and the outer transaction cleanly.
    """
    fixture_txn_id = uuid.uuid4()
    fixture_entry_id = uuid.uuid4()

    # 1. Setup temporary fixture rows
    # Owner role possesses table INSERT privileges
    owner_session.execute(
        text(
            "INSERT INTO ledger_transactions (id, reference, transaction_type, description) "
            "VALUES (:id, 'TXN-FIXTURE001', 'transfer', 'Temporary Fixture Transaction')"
        ),
        {"id": fixture_txn_id},
    )

    # Use existing ACC-SYSTEM01 for entry fixture
    system_acc_id = owner_session.scalar(
        text("SELECT id FROM accounts WHERE account_number = 'ACC-SYSTEM01'")
    )
    assert system_acc_id is not None

    owner_session.execute(
        text(
            "INSERT INTO ledger_entries (id, transaction_id, account_id, entry_type, amount, sequence) "
            "VALUES (:id, :txn_id, :acc_id, 'credit', 100.00, 1)"
        ),
        {"id": fixture_entry_id, "txn_id": fixture_txn_id, "acc_id": system_acc_id},
    )

    try:
        # 2. Row-level trigger on ledger_entries UPDATE
        sp = owner_session.begin_nested()
        try:
            with pytest.raises(Exception) as exc_info:
                owner_session.execute(
                    text("UPDATE ledger_entries SET amount = 999.00 WHERE id = :id"),
                    {"id": fixture_entry_id},
                )
            assert "Ledger records are strictly immutable" in str(exc_info.value)
        finally:
            sp.rollback()

        # 3. Row-level trigger on ledger_entries DELETE
        sp = owner_session.begin_nested()
        try:
            with pytest.raises(Exception) as exc_info:
                owner_session.execute(
                    text("DELETE FROM ledger_entries WHERE id = :id"),
                    {"id": fixture_entry_id},
                )
            assert "Ledger records are strictly immutable" in str(exc_info.value)
        finally:
            sp.rollback()

        # 4. Row-level trigger on ledger_transactions UPDATE
        sp = owner_session.begin_nested()
        try:
            with pytest.raises(Exception) as exc_info:
                owner_session.execute(
                    text("UPDATE ledger_transactions SET description = 'tampered' WHERE id = :id"),
                    {"id": fixture_txn_id},
                )
            assert "Ledger records are strictly immutable" in str(exc_info.value)
        finally:
            sp.rollback()

        # 5. Row-level trigger on ledger_transactions DELETE
        sp = owner_session.begin_nested()
        try:
            with pytest.raises(Exception) as exc_info:
                owner_session.execute(
                    text("DELETE FROM ledger_transactions WHERE id = :id"),
                    {"id": fixture_txn_id},
                )
            assert "Ledger records are strictly immutable" in str(exc_info.value)
        finally:
            sp.rollback()

        # 6. Statement-level trigger on ledger_entries TRUNCATE
        sp = owner_session.begin_nested()
        try:
            with pytest.raises(Exception) as exc_info:
                owner_session.execute(text("TRUNCATE TABLE ledger_entries"))
            assert (
                "Ledger records are strictly immutable" in str(exc_info.value)
                or "cannot TRUNCATE" in str(exc_info.value)
            )
        finally:

            sp.rollback()

        # 7. Statement-level trigger on ledger_transactions TRUNCATE
        sp = owner_session.begin_nested()
        try:
            with pytest.raises(Exception) as exc_info:
                owner_session.execute(text("TRUNCATE TABLE ledger_transactions CASCADE"))
            assert (
                "Ledger records are strictly immutable" in str(exc_info.value)
                or "cannot TRUNCATE" in str(exc_info.value)
            )
        finally:
            sp.rollback()


    finally:
        # Roll back outer fixture transaction cleanly
        owner_session.rollback()

    # Confirm fixture rows were completely rolled back
    assert owner_session.scalar(
        text("SELECT count(*) FROM ledger_transactions WHERE id = :id"),
        {"id": fixture_txn_id},
    ) == 0


# ==============================================================================
# GROUP C: Alembic Migration Reversibility
# ==============================================================================

def test_group_c_alembic_migration_reversibility():
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
