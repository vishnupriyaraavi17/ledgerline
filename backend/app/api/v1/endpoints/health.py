from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.health import HealthResponse
from backend.app.services.health import health_service

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application & Database Health Probe",
    description=(
        "Returns the operational status of the LedgerLine backend application "
        "and its PostgreSQL database connection. Returns HTTP 200 when fully healthy, "
        "or HTTP 503 Service Unavailable if the database is disconnected."
    ),
    responses={
        200: {
            "description": "Application and database are fully operational.",
            "model": HealthResponse,
        },
        503: {
            "description": "Database connection is unavailable or degraded.",
            "model": HealthResponse,
        },
    },
)
def get_health(db: Session = Depends(get_db)):
    is_healthy, response_data = health_service.check_health(db)
    
    if not is_healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_data.model_dump(mode="json")
        )
    
    return response_data
