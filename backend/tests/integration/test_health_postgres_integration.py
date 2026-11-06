import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.db.session import get_db, engine
from backend.app.core.config import settings


def test_real_postgres_connection_healthy(client: TestClient):
    """
    Integration test: verifies the live application against the real PostgreSQL 17 instance.
    Does not use mocks. Directly tests real TCP connection and SQL execution.
    """
    response = client.get("/api/v1/health")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app_name"] == "LedgerLine"
    assert data["database"]["status"] == "connected"
    assert "Database connection responsive" in data["database"]["details"]


def test_real_postgres_invalid_configuration_handled_safely(client: TestClient):
    """
    Integration test: points to an invalid database endpoint to verify that real connection
    failure is safely handled by the driver without leaking passwords or exposing stack traces.
    """
    # Create an engine pointing to an unreachable port
    invalid_url = f"postgresql+psycopg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:54399/{settings.POSTGRES_DB}"
    unreachable_engine = create_engine(
        invalid_url,
        connect_args={"connect_timeout": 1}
    )
    InvalidSessionLocal = sessionmaker(bind=unreachable_engine)

    def override_get_unreachable_db():
        db = InvalidSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_unreachable_db
    try:
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"]["status"] == "disconnected"
        
        # Verify credentials are NOT exposed in any field of the response
        response_text = response.text
        assert settings.POSTGRES_PASSWORD not in response_text
        assert "54399" not in response_text
        assert "Traceback" not in response_text
    finally:
        app.dependency_overrides.clear()
        unreachable_engine.dispose()
