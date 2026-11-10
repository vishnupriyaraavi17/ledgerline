from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.health import (
    HealthResponse,
    LivenessResponse,
    ReadinessResponse,
)
from backend.app.services.health import health_service

router = APIRouter()


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="Application Process Liveness Probe",
    description=(
        "Confirms that the FastAPI application process is up and handling HTTP requests. "
        "Operates independently of database and external dependencies. Always returns HTTP 200."
    ),
    responses={
        200: {
            "description": "Process is operational and event loop is responsive.",
            "model": LivenessResponse,
        }
    },
)
@router.get("/health/liveness", include_in_schema=False)
@router.get("/live", include_in_schema=False)
def get_liveness():
    return health_service.check_liveness()


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Subsystem Readiness Probe (PostgreSQL & Redis)",
    description=(
        "Verifies that all required external infrastructure dependencies (PostgreSQL database "
        "and Redis distributed cache/rate-limiter) are responsive. Returns HTTP 200 when ready, "
        "or HTTP 503 Service Unavailable when any dependency is offline or degraded."
    ),
    responses={
        200: {
            "description": "All required dependencies (PostgreSQL and Redis) are connected.",
            "model": ReadinessResponse,
        },
        503: {
            "description": "One or more dependencies are unavailable or timed out.",
            "model": ReadinessResponse,
        },
    },
)
@router.get("/health/readiness", include_in_schema=False)
@router.get("/ready", include_in_schema=False)
def get_readiness(db: Session = Depends(get_db)):
    is_ready, response_data = health_service.check_readiness(db)
    if not is_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_data.model_dump(mode="json"),
        )
    return response_data


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application Subsystems Diagnostic Health Probe",
    description=(
        "Returns the overall operational status of the LedgerLine backend application, "
        "its PostgreSQL database connection, and Redis cache. Returns HTTP 200 when fully healthy, "
        "or HTTP 503 Service Unavailable if any dependency is degraded."
    ),
    responses={
        200: {
            "description": "Application and all dependencies are fully operational.",
            "model": HealthResponse,
        },
        503: {
            "description": "One or more dependencies are unavailable or degraded.",
            "model": HealthResponse,
        },
    },
)
def get_health(db: Session = Depends(get_db)):
    is_healthy, response_data = health_service.check_health(db)
    if not is_healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_data.model_dump(mode="json"),
        )
    return response_data
