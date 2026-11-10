import os
import sys
from pathlib import Path
import pytest
from sqlalchemy.engine.url import make_url

# Strictly force POSTGRES_DB to ledgerline_test before any backend modules are imported
os.environ["POSTGRES_DB"] = os.getenv("TEST_POSTGRES_DB", "ledgerline_test")

# Ensure project root is in sys.path for test execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import settings

# Dual URL Fail-Closed Verification Guard
runtime_url = make_url(settings.SQLALCHEMY_DATABASE_URI)
migration_url = make_url(settings.MIGRATION_DATABASE_URI)

if runtime_url.database != "ledgerline_test" or migration_url.database != "ledgerline_test":
    raise RuntimeError(
        f"CRITICAL TEST GUARD VIOLATION: Automated tests attempted to connect to unauthorized database!\n"
        f"  Runtime DB Target:   '{runtime_url.database}'\n"
        f"  Migration DB Target: '{migration_url.database}'\n"
        f"Both must strictly equal 'ledgerline_test'. Execution aborted to protect development/demo data."
    )

if runtime_url.database == "ledgerline" or migration_url.database == "ledgerline":
    raise RuntimeError(
        "FATAL: Tests attempted to target the development database 'ledgerline'! Execution aborted."
    )

from fastapi.testclient import TestClient
from backend.app.main import app


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Guarantees that every pytest session runs against a fresh, clean, predictable ledgerline_test database.
    Restricts schema resets strictly to ledgerline_test.
    """
    r_url = make_url(settings.SQLALCHEMY_DATABASE_URI)
    m_url = make_url(settings.MIGRATION_DATABASE_URI)
    if r_url.database != "ledgerline_test" or m_url.database != "ledgerline_test":
        raise RuntimeError(
            f"CRITICAL GUARD: setup_test_database aborted! Unauthorized database targets: "
            f"runtime='{r_url.database}', migration='{m_url.database}'"
        )

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from alembic.config import Config
    from alembic import command
    from backend.app.db.seed import seed_development_accounts

    # 1. Reset schema public on ledgerline_test using migration owner
    owner_engine = create_engine(settings.MIGRATION_DATABASE_URI)
    with owner_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT").execute(
            text(
                "DROP SCHEMA IF EXISTS public CASCADE; "
                "CREATE SCHEMA public AUTHORIZATION ledgerline_owner; "
                "GRANT ALL ON SCHEMA public TO ledgerline_owner; "
                "GRANT USAGE ON SCHEMA public TO ledgerline_app;"
            )
        )
    owner_engine.dispose()

    # 2. Run all Alembic migrations up to head on ledgerline_test
    alembic_ini_path = str(PROJECT_ROOT / "backend" / "alembic.ini")
    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", settings.MIGRATION_DATABASE_URI)
    command.upgrade(alembic_cfg, "head")

    # 3. Grant application runtime role DML permissions on users table (consistent with scripts/setup_roles.sql)
    owner_engine = create_engine(settings.MIGRATION_DATABASE_URI)
    with owner_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT").execute(
            text("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.users TO ledgerline_app;")
        )
    owner_engine.dispose()

    # 4. Seed baseline development accounts on ledgerline_test using runtime role
    app_engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
    with Session(app_engine) as session:
        seed_development_accounts(session)
    app_engine.dispose()

    yield


@pytest.fixture(scope="session", autouse=True)
def setup_test_redis():
    """
    Provides an isolated in-memory Redis instance with full Lua script evaluation (via lupa)
    for automated test execution, ensuring tests are hermetic and do not require external services.
    """
    import fakeredis
    from backend.app.core.redis import set_redis_client, close_redis

    fake_client = fakeredis.FakeRedis(decode_responses=True)
    set_redis_client(fake_client)
    yield fake_client
    close_redis()


@pytest.fixture(autouse=True)
def flush_test_redis(setup_test_redis):
    """Guarantees each test starts with an isolated, clean Redis state."""
    setup_test_redis.flushall()
    yield


@pytest.fixture(scope="session")
def client() -> TestClient:
    """
    Reusable FastAPI TestClient.
    """
    with TestClient(app) as test_client:
        yield test_client
