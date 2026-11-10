from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import OperationalError

from backend.app.main import app
from backend.app.db.session import get_db
from backend.app.services.health import health_service


def test_liveness_endpoint_returns_200_without_database(client: TestClient):
    """
    Verifies that /api/v1/health/live and /health/live confirm process liveness
    and return HTTP 200 without requiring any database or Redis interaction.
    """
    # Test router endpoint
    resp = client.get("/api/v1/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"
    assert data["app_name"] == "LedgerLine"
    assert "version" in data
    assert "timestamp" in data

    # Test root orchestrator alias
    root_resp = client.get("/health/live")
    assert root_resp.status_code == 200
    assert root_resp.json()["status"] == "alive"


def test_liveness_succeeds_even_when_database_is_broken(client: TestClient):
    """
    Verifies liveness probe is completely decoupled from database health:
    even if database connectivity is completely down, liveness probe remains HTTP 200.
    """
    def broken_db():
        raise OperationalError("Connection dropped", {}, None)

    app.dependency_overrides[get_db] = broken_db
    try:
        resp = client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"
    finally:
        app.dependency_overrides.clear()


def test_readiness_endpoint_returns_200_when_dependencies_healthy(client: TestClient):
    """
    Verifies /api/v1/health/ready returns HTTP 200 when both PostgreSQL and Redis are responsive.
    """
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["app_name"] == "LedgerLine"
    assert data["dependencies"]["database"]["status"] == "connected"
    assert data["dependencies"]["redis"]["status"] == "connected"
    assert data["dependencies"]["database"]["details"] == "Database connection responsive"
    assert data["dependencies"]["redis"]["details"] == "Redis connection responsive"

    # Test root orchestrator alias /health/ready
    root_resp = client.get("/health/ready")
    assert root_resp.status_code == 200
    assert root_resp.json()["status"] == "ready"


def test_readiness_returns_503_when_database_unavailable(client: TestClient):
    """
    Verifies /api/v1/health/ready returns HTTP 503 when PostgreSQL is disconnected,
    while masking all internal errors and credentials.
    """
    mock_db = MagicMock()
    mock_db.execute.side_effect = OperationalError("connection to postgres://secret_pass@10.0.0.1:5432 failed", {}, None)

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"
        assert data["dependencies"]["database"]["status"] == "disconnected"
        assert data["dependencies"]["redis"]["status"] == "connected"
        # Security masking verification: credentials, connection strings and tracebacks never leaked
        assert "secret_pass" not in str(data)
        assert "10.0.0.1" not in str(data)
        assert "OperationalError" not in str(data)
        assert data["dependencies"]["database"]["details"] == "Database connection unavailable or rejected"
    finally:
        app.dependency_overrides.clear()


def test_readiness_returns_503_when_redis_unavailable(client: TestClient, monkeypatch):
    """
    Verifies /api/v1/health/ready returns HTTP 503 when Redis is unavailable,
    even though PostgreSQL database is responsive.
    """
    from backend.app.repositories.health import HealthRepository

    monkeypatch.setattr(
        HealthRepository,
        "ping_redis",
        staticmethod(lambda timeout=2.0: (False, "Redis connection unavailable or timed out")),
    )

    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "not_ready"
    assert data["dependencies"]["database"]["status"] == "connected"
    assert data["dependencies"]["redis"]["status"] == "disconnected"
    assert data["dependencies"]["redis"]["details"] == "Redis connection unavailable or timed out"


def test_readiness_returns_503_when_both_dependencies_unavailable(client: TestClient, monkeypatch):
    """
    Verifies /api/v1/health/ready returns HTTP 503 when both PostgreSQL and Redis are offline.
    """
    from backend.app.repositories.health import HealthRepository

    mock_db = MagicMock()
    mock_db.execute.side_effect = OperationalError("db offline", {}, None)

    monkeypatch.setattr(
        HealthRepository,
        "ping_redis",
        staticmethod(lambda timeout=2.0: (False, "Redis connection unavailable or timed out")),
    )

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"
        assert data["dependencies"]["database"]["status"] == "disconnected"
        assert data["dependencies"]["redis"]["status"] == "disconnected"
    finally:
        app.dependency_overrides.clear()


def test_general_health_endpoint_reflects_subsystems(client: TestClient, monkeypatch):
    """
    Verifies /api/v1/health backward compatibility and dual subsystem inspection.
    """
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"]["status"] == "connected"
    assert data["redis"]["status"] == "connected"

    # Simulate redis degraded
    from backend.app.repositories.health import HealthRepository
    monkeypatch.setattr(
        HealthRepository,
        "ping_redis",
        staticmethod(lambda timeout=2.0: (False, "Redis connection unavailable")),
    )

    resp_degraded = client.get("/api/v1/health")
    assert resp_degraded.status_code == 503
    data_degraded = resp_degraded.json()
    assert data_degraded["status"] == "degraded"
    assert data_degraded["redis"]["status"] == "disconnected"
