from typing import Tuple
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.schemas.health import HealthResponse, DatabaseHealth
from backend.app.repositories.health import HealthRepository


class HealthService:
    """
    Service coordinating application health inspection across subsystems.
    """

    def __init__(self, repository: HealthRepository = HealthRepository()):
        self.repository = repository

    def check_health(self, db: Session) -> Tuple[bool, HealthResponse]:
        """
        Inspects application and database health.
        Returns a tuple: (is_healthy: bool, response: HealthResponse).
        is_healthy is False if any critical dependency (e.g. database) is failing.
        """
        db_alive, db_msg = self.repository.ping_database(db)

        db_health = DatabaseHealth(
            status="connected" if db_alive else "disconnected",
            details=db_msg
        )

        overall_status = "healthy" if db_alive else "degraded"

        response = HealthResponse(
            status=overall_status,
            app_name=settings.PROJECT_NAME,
            version=settings.VERSION,
            environment=settings.ENVIRONMENT,
            database=db_health
        )

        return db_alive, response


health_service = HealthService()
