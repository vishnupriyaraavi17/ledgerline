from typing import Tuple
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.schemas.health import (
    HealthResponse,
    DatabaseHealth,
    RedisHealth,
    LivenessResponse,
    ReadinessResponse,
    ReadinessDependencies,
)
from backend.app.repositories.health import HealthRepository


class HealthService:
    """
    Service coordinating application liveness, readiness, and subsystem diagnostics.
    """

    def __init__(self, repository: HealthRepository = HealthRepository()):
        self.repository = repository

    def check_liveness(self) -> LivenessResponse:
        """
        Confirms application process is running and event loop is processing requests.
        Requires zero database or external dependency access.
        """
        return LivenessResponse(
            status="alive",
            app_name=settings.PROJECT_NAME,
            version=settings.VERSION,
        )

    def check_readiness(self, db: Session) -> Tuple[bool, ReadinessResponse]:
        """
        Verifies all required external dependencies (PostgreSQL and Redis) are fully connected.
        Returns (is_ready: bool, response: ReadinessResponse).
        is_ready is False (yielding HTTP 503) if either dependency is unreachable.
        """
        db_alive, db_msg = self.repository.ping_database(db)
        redis_alive, redis_msg = self.repository.ping_redis()

        db_health = DatabaseHealth(
            status="connected" if db_alive else "disconnected",
            details=db_msg,
        )
        redis_health = RedisHealth(
            status="connected" if redis_alive else "disconnected",
            details=redis_msg,
        )

        is_ready = bool(db_alive and redis_alive)
        overall_status = "ready" if is_ready else "not_ready"

        response = ReadinessResponse(
            status=overall_status,
            app_name=settings.PROJECT_NAME,
            version=settings.VERSION,
            environment=settings.ENVIRONMENT,
            dependencies=ReadinessDependencies(
                database=db_health,
                redis=redis_health,
            ),
        )

        return is_ready, response

    def check_health(self, db: Session) -> Tuple[bool, HealthResponse]:
        """
        Legacy/General application health inspection.
        Returns a tuple: (is_healthy: bool, response: HealthResponse).
        """
        db_alive, db_msg = self.repository.ping_database(db)
        redis_alive, redis_msg = self.repository.ping_redis()

        db_health = DatabaseHealth(
            status="connected" if db_alive else "disconnected",
            details=db_msg,
        )
        redis_health = RedisHealth(
            status="connected" if redis_alive else "disconnected",
            details=redis_msg,
        )

        is_healthy = bool(db_alive and redis_alive)
        overall_status = "healthy" if is_healthy else "degraded"

        response = HealthResponse(
            status=overall_status,
            app_name=settings.PROJECT_NAME,
            version=settings.VERSION,
            environment=settings.ENVIRONMENT,
            database=db_health,
            redis=redis_health,
        )

        return is_healthy, response


health_service = HealthService()
