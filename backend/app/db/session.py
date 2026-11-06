from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.app.core.config import settings

# Synchronous SQLAlchemy 2.x engine using psycopg (Psycopg 3)
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,       # Detect disconnects proactively
    pool_size=10,             # Keep baseline connection pool
    max_overflow=20,          # Allow surge capacity for concurrent operations
    connect_args={
        "connect_timeout": 5  # Fail fast on unreachable database
    }
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """
    Reusable FastAPI database session dependency.
    Ensures that each HTTP request operates within its own session lifecycle
    and explicitly closes the session upon request completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
