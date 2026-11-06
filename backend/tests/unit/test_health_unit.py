from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from backend.app.main import app
from backend.app.db.session import get_db
from backend.app.repositories.health import HealthRepository
from backend.app.services.health import HealthService


def test_app_starts_and_docs_available(client: TestClient):
    """Verifies that the FastAPI application boots and exposes OpenAPI/docs endpoints."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "Swagger UI" in response.text or "swagger" in response.text.lower()

    openapi_res = client.get("/api/v1/openapi.json")
    assert openapi_res.status_code == 200
    data = openapi_res.json()
    assert data["info"]["title"] == "LedgerLine"


def test_health_unit_mocked_success():
    """Unit test: verifies health service returns healthy when db probe succeeds."""
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar.return_value = 1

    service = HealthService()
    is_healthy, response = service.check_health(mock_db)

    assert is_healthy is True
    assert response.status == "healthy"
    assert response.database.status == "connected"
    assert response.database.details == "Database connection responsive"


def test_health_unit_mocked_db_failure():
    """Unit test: verifies health service handles db operational failure safely without leaking internals."""
    mock_db = MagicMock()
    mock_db.execute.side_effect = OperationalError("connection refused", {}, None)

    service = HealthService()
    is_healthy, response = service.check_health(mock_db)

    assert is_healthy is False
    assert response.status == "degraded"
    assert response.database.status == "disconnected"
    # Ensure raw operational error string / connection string isn't dumped
    assert "connection refused" not in response.database.details
    assert response.database.details == "Database connection unavailable or rejected"


def test_health_endpoint_mocked_failure_returns_503(client: TestClient):
    """Unit test: verifies endpoint converts failure into HTTP 503 status."""
    mock_db = MagicMock()
    mock_db.execute.side_effect = OperationalError("failed connection", {}, None)

    def override_get_db():
        try:
            yield mock_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"]["status"] == "disconnected"
    finally:
        app.dependency_overrides.clear()
