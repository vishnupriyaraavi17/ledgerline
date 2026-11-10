import logging
from typing import Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from backend.app.core.redis import ping_redis

logger = logging.getLogger(__name__)


class HealthRepository:
    """
    Repository responsible for low-level infrastructure connectivity probing.
    Enforces strict masking to guarantee credentials, connection strings, or stack traces
    are never exposed to health probe consumers.
    """

    @staticmethod
    def ping_database(db: Session) -> Tuple[bool, str]:
        """
        Executes a minimal bounded test query ('SELECT 1') to verify live PostgreSQL connectivity.
        """
        try:
            result = db.execute(text("SELECT 1")).scalar()
            if result == 1:
                return True, "Database connection responsive"
            return False, "Database probe returned unexpected result"
        except SQLAlchemyError as exc:
            logger.error(f"Database connectivity check failed: {type(exc).__name__}")
            return False, "Database connection unavailable or rejected"
        except Exception as exc:
            logger.error(f"Unexpected error during database check: {type(exc).__name__}")
            return False, "Internal database communication failure"

    @staticmethod
    def ping_redis(timeout: float = 2.0) -> Tuple[bool, str]:
        """
        Executes a bounded ping against Redis to verify distributed cache/rate-limiter connectivity.
        """
        return ping_redis(timeout=timeout)
