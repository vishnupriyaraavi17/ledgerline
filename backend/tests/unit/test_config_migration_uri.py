import pytest
from backend.app.core.config import Settings


def test_migration_database_uri_fails_closed_when_password_missing(monkeypatch):
    """
    Asserts zero fallback to runtime URI if migration credentials are missing.
    """
    s = Settings(
        POSTGRES_USER="ledgerline_app",
        POSTGRES_PASSWORD="app_password",
        MIGRATION_POSTGRES_USER="ledgerline_owner",
        MIGRATION_POSTGRES_PASSWORD=None,
    )
    with pytest.raises(ValueError) as exc_info:
        _ = s.MIGRATION_DATABASE_URI
    assert "MIGRATION_DATABASE_URI is not configured" in str(exc_info.value)


def test_migration_database_uri_rejects_non_owner_user():
    s = Settings(
        POSTGRES_USER="ledgerline_app",
        POSTGRES_PASSWORD="app_password",
        MIGRATION_POSTGRES_USER="other_user",
        MIGRATION_POSTGRES_PASSWORD="secret_password",
    )
    with pytest.raises(ValueError) as exc_info:
        _ = s.MIGRATION_DATABASE_URI
    assert "MIGRATION_POSTGRES_USER must be 'ledgerline_owner'" in str(exc_info.value)


def test_runtime_postgres_user_validates_canonical_name():
    s = Settings(
        POSTGRES_USER="ledgerline_app",
        POSTGRES_PASSWORD="app_password",
        MIGRATION_POSTGRES_USER="ledgerline_owner",
        MIGRATION_POSTGRES_PASSWORD="owner_password",
    )
    assert s.RUNTIME_POSTGRES_USER == "ledgerline_app"


def test_runtime_postgres_user_rejects_non_app_user():
    s = Settings(
        POSTGRES_USER="tampered_user",
        POSTGRES_PASSWORD="app_password",
        MIGRATION_POSTGRES_USER="ledgerline_owner",
        MIGRATION_POSTGRES_PASSWORD="owner_password",
    )
    with pytest.raises(ValueError) as exc_info:
        _ = s.RUNTIME_POSTGRES_USER
    assert "must be 'ledgerline_app'" in str(exc_info.value)
