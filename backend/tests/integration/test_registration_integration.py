import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.user import UserRole
from backend.app.repositories.audit import audit_repository
from backend.app.repositories.user import user_repository
from backend.app.security.rate_limiter import registration_limiter


@pytest.fixture(scope="module")
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def reset_limiter():
    registration_limiter.reset()
    yield
    registration_limiter.reset()


def test_public_registration_success(client: TestClient, db_session: Session):
    unique_suffix = uuid.uuid4().hex[:8]
    username = f"cust_{unique_suffix}"
    email = f"cust_{unique_suffix}@example.com"
    password = f"SecurePass123_{unique_suffix}"

    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 201, f"Registration failed: {response.text}"
    data = response.json()
    assert data["username"] == username
    assert data["email"] == email
    assert data["role"] == UserRole.ACCOUNT_HOLDER.value
    assert data["is_active"] is True
    assert "access_token" not in data

    # Verify user can log in after registration
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()

    # Verify audit event was logged
    audit_events, _ = audit_repository.list_events(
        db=db_session, event_type="security.user_registered", limit=5
    )
    matching = [e for e in audit_events if e.payload.get("username") == username]
    assert len(matching) >= 1
    assert matching[0].payload.get("role") == UserRole.ACCOUNT_HOLDER.value


def test_public_registration_role_tampering_ignored(client: TestClient):
    """Clients attempting to pass role='admin' must be forced to account_holder."""
    unique_suffix = uuid.uuid4().hex[:8]
    username = f"hacker_{unique_suffix}"
    email = f"hacker_{unique_suffix}@example.com"
    password = "HackerPass123!"

    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
            "role": "admin",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == UserRole.ACCOUNT_HOLDER.value


def test_public_registration_duplicate_username(client: TestClient):
    unique_suffix = uuid.uuid4().hex[:8]
    username = f"dup_{unique_suffix}"
    email1 = f"dup1_{unique_suffix}@example.com"
    email2 = f"dup2_{unique_suffix}@example.com"
    password = "ValidPass123!"

    resp1 = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email1, "password": password},
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email2, "password": password},
    )
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"]


def test_public_registration_weak_password(client: TestClient):
    unique_suffix = uuid.uuid4().hex[:8]
    username = f"weak_{unique_suffix}"
    email = f"weak_{unique_suffix}@example.com"

    # Too short
    resp_short = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": "abc"},
    )
    assert resp_short.status_code == 422

    # All letters, no digits/special
    resp_letters = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": "onlylettershere"},
    )
    assert resp_letters.status_code == 422


def test_public_registration_rate_limiting(client: TestClient):
    # Set a small limit for test
    registration_limiter.requests_limit = 3
    registration_limiter.window_seconds = 60

    for i in range(3):
        suffix = uuid.uuid4().hex[:6]
        res = client.post(
            "/api/v1/auth/register",
            json={"username": f"rate_{suffix}", "email": f"rate_{suffix}@example.com", "password": "ValidPass123!"},
        )
        assert res.status_code == 201

    # 4th request must hit 429
    res_blocked = client.post(
        "/api/v1/auth/register",
        json={"username": "blocked_user", "email": "blocked@example.com", "password": "ValidPass123!"},
    )
    assert res_blocked.status_code == 429
    assert "Retry-After" in res_blocked.headers
