from backend.app.core.config import Settings


def test_config_defaults_and_env():
    settings = Settings()
    assert settings.PROJECT_NAME == "LedgerLine"
    assert settings.API_V1_STR == "/api/v1"
    assert isinstance(settings.BACKEND_CORS_ORIGINS, list)
    assert len(settings.BACKEND_CORS_ORIGINS) >= 1


def test_cors_origins_parsing():
    settings = Settings(BACKEND_CORS_ORIGINS="http://localhost:3000,http://localhost:5173")
    assert settings.BACKEND_CORS_ORIGINS == ["http://localhost:3000", "http://localhost:5173"]


def test_safe_db_info_masks_password():
    settings = Settings(
        POSTGRES_USER="testuser",
        POSTGRES_PASSWORD="super_secret_password_123",
        POSTGRES_SERVER="db.internal",
        POSTGRES_PORT=5432,
        POSTGRES_DB="testdb"
    )
    # Verify password is present in the URI but masked in safe_db_info
    assert "super_secret_password_123" in settings.SQLALCHEMY_DATABASE_URI
    assert "super_secret_password_123" not in settings.safe_db_info
    assert settings.safe_db_info == "testuser@db.internal:5432/testdb"
