import concurrent.futures
from unittest.mock import MagicMock
import uuid
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.redis import get_redis_client, set_redis_client
from backend.app.db.session import SessionLocal
from backend.app.models.user import User, UserRole
from backend.app.repositories.user import user_repository
from backend.app.services.auth import auth_service
from backend.app.schemas.user import UserCreate
from backend.app.security.tokens import create_access_token


@pytest.fixture(scope="module")
def db_session():
    """Live database session for integration test teardown and verification."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


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


# ------------------------------------------------------------------------------
# 1. Authentication & Login Tests
# ------------------------------------------------------------------------------

def test_login_success_admin(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "admin", "password": settings.SEED_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "admin"
    assert data["user"]["role"] == "admin"
    assert data["user"]["is_active"] is True
    # Password hash must NEVER appear in response
    assert "hashed_password" not in data
    assert "password" not in data["user"]
    assert "hashed_password" not in data["user"]


def test_login_success_with_email(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "ADMIN@LEDGERLINE.INTERNAL", "password": settings.SEED_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["username"] == "admin"


def test_login_wrong_password_returns_generic_401(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "admin", "password": "CompletelyWrongPassword123!"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_login_nonexistent_user_returns_generic_401(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "nonexistent_ghost_user", "password": "AnyPassword123!"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_swagger_oauth2_token_endpoint(client: TestClient):
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "holder", "password": settings.SEED_HOLDER_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["role"] == "account_holder"
    assert settings.REFRESH_COOKIE_NAME in response.cookies


def test_login_sets_httponly_refresh_cookie(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "admin", "password": settings.SEED_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    assert settings.REFRESH_COOKIE_NAME in response.cookies
    refresh_token = response.cookies[settings.REFRESH_COOKIE_NAME]
    assert len(refresh_token) > 20


def test_refresh_session_restores_tokens_and_rotates(client: TestClient):
    # 1. Login
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "holder", "password": settings.SEED_HOLDER_PASSWORD},
    )
    assert login_res.status_code == 200
    initial_cookie = login_res.cookies[settings.REFRESH_COOKIE_NAME]

    # 2. Refresh session using the cookie
    refresh_res = client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE_NAME: initial_cookie},
    )
    assert refresh_res.status_code == 200
    data = refresh_res.json()
    assert "access_token" in data
    assert data["user"]["username"] == "holder"
    assert data["user"]["role"] == "account_holder"

    # 3. Verify token rotation: new cookie issued
    rotated_cookie = refresh_res.cookies[settings.REFRESH_COOKIE_NAME]
    assert rotated_cookie != initial_cookie

    # 4. Old refresh token cannot be reused (rotation invalidated it)
    replay_res = client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE_NAME: initial_cookie},
    )
    assert replay_res.status_code == 401


def test_logout_revokes_session_and_clears_cookie(client: TestClient):
    # 1. Login
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "auditor", "password": settings.SEED_AUDITOR_PASSWORD},
    )
    assert login_res.status_code == 200
    cookie = login_res.cookies[settings.REFRESH_COOKIE_NAME]

    # 2. Logout
    logout_res = client.post(
        "/api/v1/auth/logout",
        cookies={settings.REFRESH_COOKIE_NAME: cookie},
    )
    assert logout_res.status_code == 200
    assert logout_res.json()["detail"] == "Successfully logged out"

    # 3. Attempting to refresh with the revoked cookie must fail with 401
    refresh_res = client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE_NAME: cookie},
    )
    assert refresh_res.status_code == 401


def test_refresh_without_cookie_rejected(client: TestClient):
    res = client.post("/api/v1/auth/refresh")
    assert res.status_code == 401
    assert "Active refresh session not found" in res.json()["detail"]


def test_first_refresh_succeeds(client: TestClient):
    """Verifies that an initial refresh request with a valid cookie succeeds and rotates token."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "holder", "password": settings.SEED_HOLDER_PASSWORD},
    )
    assert login_res.status_code == 200
    initial_cookie = login_res.cookies[settings.REFRESH_COOKIE_NAME]

    refresh_res = client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE_NAME: initial_cookie},
    )
    assert refresh_res.status_code == 200
    data = refresh_res.json()
    assert "access_token" in data
    assert data["user"]["username"] == "holder"
    assert refresh_res.cookies[settings.REFRESH_COOKIE_NAME] != initial_cookie


def test_reusing_same_refresh_token_rejected(client: TestClient):
    """Verifies that an already-consumed refresh token cannot be reused."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "holder", "password": settings.SEED_HOLDER_PASSWORD},
    )
    assert login_res.status_code == 200
    initial_cookie = login_res.cookies[settings.REFRESH_COOKIE_NAME]

    # First consumption succeeds
    first_refresh = client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE_NAME: initial_cookie},
    )
    assert first_refresh.status_code == 200

    # Second consumption of the same token is rejected
    replay_refresh = client.post(
        "/api/v1/auth/refresh",
        cookies={settings.REFRESH_COOKIE_NAME: initial_cookie},
    )
    assert replay_refresh.status_code == 401
    assert "revoked, expired, or already consumed" in replay_refresh.json()["detail"]


def test_concurrent_refresh_attempts_cannot_both_succeed(client: TestClient):
    """
    Verifies race-condition protection: two simultaneous refresh requests using the exact same
    refresh token cannot both succeed. Exactly one must succeed (200) and the other must be rejected (401).
    """
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "holder", "password": settings.SEED_HOLDER_PASSWORD},
    )
    assert login_res.status_code == 200
    cookie = login_res.cookies[settings.REFRESH_COOKIE_NAME]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(lambda: client.post("/api/v1/auth/refresh", cookies={settings.REFRESH_COOKIE_NAME: cookie}))
        f2 = executor.submit(lambda: client.post("/api/v1/auth/refresh", cookies={settings.REFRESH_COOKIE_NAME: cookie}))
        r1, r2 = f1.result(), f2.result()

    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 401], f"Expected exactly one 200 and one 401, but received: {[r1.status_code, r2.status_code]}"


def test_refresh_rejected_when_redis_returns_zero(client: TestClient):
    """Verifies that when Redis delete returns 0 (consumed/absent session), refresh is rejected with 401."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "holder", "password": settings.SEED_HOLDER_PASSWORD},
    )
    assert login_res.status_code == 200
    cookie = login_res.cookies[settings.REFRESH_COOKIE_NAME]

    original_client = get_redis_client()
    mock_redis = MagicMock()
    mock_redis.delete.return_value = 0
    set_redis_client(mock_redis)

    try:
        res = client.post(
            "/api/v1/auth/refresh",
            cookies={settings.REFRESH_COOKIE_NAME: cookie},
        )
        assert res.status_code == 401
        assert "Session has been revoked, expired, or already consumed" in res.json()["detail"]
    finally:
        set_redis_client(original_client)


def test_refresh_fails_closed_on_redis_connection_failure(client: TestClient):
    """
    Verifies that a Redis connection failure fails closed with HTTP 503 Service Unavailable,
    guaranteeing no unverified refresh request can authenticate.
    """
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "holder", "password": settings.SEED_HOLDER_PASSWORD},
    )
    assert login_res.status_code == 200
    cookie = login_res.cookies[settings.REFRESH_COOKIE_NAME]

    original_client = get_redis_client()
    failing_redis = MagicMock()
    failing_redis.delete.side_effect = ConnectionError("Redis cluster connection failed")
    set_redis_client(failing_redis)

    try:
        res = client.post(
            "/api/v1/auth/refresh",
            cookies={settings.REFRESH_COOKIE_NAME: cookie},
        )
        assert res.status_code == 503
        assert "Authentication service temporarily unavailable" in res.json()["detail"]
    finally:
        set_redis_client(original_client)


# ------------------------------------------------------------------------------
# 2. Inactive User Security Checks (Token Invalidation & Login Rejection)
# ------------------------------------------------------------------------------

def test_inactive_user_cannot_login(client: TestClient, db_session: Session):
    # Provision a test user
    deactivated_uname = f"deact_{uuid.uuid4().hex[:6]}"
    user_in = UserCreate(
        username=deactivated_uname,
        email=f"{deactivated_uname}@ledgerline.internal",
        password="ValidPassword_2026!",
        role=UserRole.ACCOUNT_HOLDER,
    )
    auth_service.create_user(db_session, user_in)
    
    # Deactivate the user in the database
    db_user = db_session.query(User).filter(User.username == deactivated_uname).first()
    assert db_user is not None
    db_user.is_active = False
    db_session.commit()

    # Attempt login
    response = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": deactivated_uname, "password": "ValidPassword_2026!"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_inactive_user_with_previously_issued_token_rejected_server_side(client: TestClient, db_session: Session):
    """
    Simulates a user holding a valid JWT whose account is subsequently deactivated in DB.
    Server-side dependency must check is_active on every request and return 401.
    """
    uname = f"revoked_{uuid.uuid4().hex[:6]}"
    user_in = UserCreate(
        username=uname,
        email=f"{uname}@ledgerline.internal",
        password="ValidPassword_2026!",
        role=UserRole.ACCOUNT_HOLDER,
    )
    created = auth_service.create_user(db_session, user_in)
    user_id = str(created.id)

    # Issue a valid token for this user
    token = create_access_token({"sub": user_id, "username": uname, "role": "account_holder"})

    # Verify token works while active
    headers = {"Authorization": f"Bearer {token}"}
    resp1 = client.get("/api/v1/auth/me", headers=headers)
    assert resp1.status_code == 200

    # Deactivate the user directly in DB
    db_user = db_session.query(User).filter(User.id == created.id).first()
    assert db_user is not None
    db_user.is_active = False
    db_session.commit()

    # Now verify the same token is rejected
    resp2 = client.get("/api/v1/auth/me", headers=headers)
    assert resp2.status_code == 401
    assert resp2.json()["detail"] == "User account is inactive"


# ------------------------------------------------------------------------------
# 3. /auth/me Endpoint
# ------------------------------------------------------------------------------

def test_get_me_unauthenticated(client: TestClient):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_get_me_authenticated(client: TestClient, holder_token: str):
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {holder_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "holder"
    assert data["role"] == "account_holder"
    assert "hashed_password" not in data


# ------------------------------------------------------------------------------
# 4. Role-Based Access Control (RBAC): User Provisioning (POST /users)
# ------------------------------------------------------------------------------

def test_admin_can_provision_new_user(client: TestClient, admin_token: str):
    new_uname = f"newuser_{uuid.uuid4().hex[:6]}"
    payload = {
        "username": new_uname,
        "email": f"{new_uname}@ledgerline.internal",
        "password": "StrongPassword_2026!",
        "role": "account_holder",
    }
    response = client.post(
        "/api/v1/users",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == new_uname
    assert data["email"] == f"{new_uname}@ledgerline.internal"
    assert data["role"] == "account_holder"
    assert data["is_active"] is True
    assert "id" in data
    assert "hashed_password" not in data


def test_duplicate_username_returns_409(client: TestClient, admin_token: str):
    # Attempt to create existing 'admin' username
    payload = {
        "username": "admin",
        "email": f"unique_{uuid.uuid4().hex[:6]}@ledgerline.internal",
        "password": "StrongPassword_2026!",
        "role": "account_holder",
    }
    response = client.post(
        "/api/v1/users",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


def test_duplicate_email_returns_409(client: TestClient, admin_token: str):
    # Attempt to create existing 'admin@ledgerline.internal' email
    payload = {
        "username": f"unique_{uuid.uuid4().hex[:6]}",
        "email": "admin@ledgerline.internal",
        "password": "StrongPassword_2026!",
        "role": "account_holder",
    }
    response = client.post(
        "/api/v1/users",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


def test_auditor_cannot_provision_user(client: TestClient, auditor_token: str):
    uname = f"audit_blocked_{uuid.uuid4().hex[:6]}"
    payload = {
        "username": uname,
        "email": f"{uname}@ledgerline.internal",
        "password": "StrongPassword_2026!",
        "role": "account_holder",
    }
    response = client.post(
        "/api/v1/users",
        json=payload,
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert response.status_code == 403


def test_account_holder_cannot_provision_user(client: TestClient, holder_token: str):
    uname = f"holder_blocked_{uuid.uuid4().hex[:6]}"
    payload = {
        "username": uname,
        "email": f"{uname}@ledgerline.internal",
        "password": "StrongPassword_2026!",
        "role": "account_holder",
    }
    response = client.post(
        "/api/v1/users",
        json=payload,
        headers={"Authorization": f"Bearer {holder_token}"},
    )
    assert response.status_code == 403


# ------------------------------------------------------------------------------
# 5. Role-Based Access Control (RBAC): User Listing (GET /users)
# ------------------------------------------------------------------------------

def test_admin_can_list_users(client: TestClient, admin_token: str):
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 3
    # Check that each item conforms to UserResponse schema
    for item in data["items"]:
        assert "id" in item
        assert "username" in item
        assert "role" in item
        assert "hashed_password" not in item


def test_auditor_can_list_users(client: TestClient, auditor_token: str):
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 3


def test_account_holder_cannot_list_users(client: TestClient, holder_token: str):
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {holder_token}"},
    )
    assert response.status_code == 403


# ------------------------------------------------------------------------------
# 6. Password Hash Exposure Audit
# ------------------------------------------------------------------------------

def test_password_hash_never_exposed_in_any_response(
    client: TestClient,
    admin_token: str,
    holder_token: str,
    auditor_token: str,
):
    """
    Exhaustively scans response bodies from all endpoints to guarantee no
    password or hash hashes leak to the client.
    """
    endpoints = [
        ("GET", "/api/v1/auth/me", {"Authorization": f"Bearer {admin_token}"}),
        ("GET", "/api/v1/auth/me", {"Authorization": f"Bearer {holder_token}"}),
        ("GET", "/api/v1/auth/me", {"Authorization": f"Bearer {auditor_token}"}),
        ("GET", "/api/v1/users", {"Authorization": f"Bearer {admin_token}"}),
        ("GET", "/api/v1/users", {"Authorization": f"Bearer {auditor_token}"}),
    ]
    for method, path, headers in endpoints:
        resp = client.request(method, path, headers=headers)
        assert resp.status_code == 200
        text = resp.text
        assert "hashed_password" not in text
        assert "$argon2id$" not in text
        assert "Admin_SecPass" not in text
        assert "Holder_SecPass" not in text
        assert "Auditor_SecPass" not in text


# ------------------------------------------------------------------------------
# 7. Runtime Role Users Table Privilege Audit
# ------------------------------------------------------------------------------

def test_runtime_role_users_table_permissions(db_session: Session):
    """
    Verifies that ledgerline_app holds strictly required SELECT and INSERT
    privileges on the users table, and that TRUNCATE is strictly withheld.
    """
    app_user = settings.RUNTIME_POSTGRES_USER

    # SELECT and INSERT are strictly required for authentication and registration
    assert db_session.execute(
        text(f"SELECT has_table_privilege('{app_user}', 'users', 'SELECT')")
    ).scalar() is True, f"Expected SELECT on users for {app_user}"

    assert db_session.execute(
        text(f"SELECT has_table_privilege('{app_user}', 'users', 'INSERT')")
    ).scalar() is True, f"Expected INSERT on users for {app_user}"

    # TRUNCATE must always be withheld
    assert db_session.execute(
        text(f"SELECT has_table_privilege('{app_user}', 'users', 'TRUNCATE')")
    ).scalar() is False, f"Expected TRUNCATE to be withheld on users for {app_user}"

