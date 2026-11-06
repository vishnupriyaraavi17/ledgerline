import logging
from typing import Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class HealthRepository:
    """
    Repository responsible for low-level database connectivity probing.
    """

    @staticmethod
    def ping_database(db: Session) -> Tuple[bool, str]:
        """
        Executes a minimal test query ('SELECT 1') to verify live database connectivity.
        Guarantees that sensitive error details, passwords, or stack traces are never exposed.
        """
        try:
            result = db.execute(text("SELECT 1")).scalar()
            if result == 1:
                return True, "Database connection responsive"
            return False, "Database probe returned unexpected result"
        except SQLAlchemyError as exc:
            # Log error details internally for operators while masking sensitive info
            logger.error(f"Database connectivity check failed: {type(exc).__name__}")
            return False, "Database connection unavailable or rejected"
        except Exception as exc:
            logger.error(f"Unexpected error during database check: {type(exc).__name__}")
            return False, "Internal database communication failure"
