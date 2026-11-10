from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.redis import init_redis, close_redis
from backend.app.db.session import get_db
from backend.app.services.health import health_service
from backend.app.api.v1.api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Redis connection pool
    init_redis()
    yield
    # Shutdown: Cleanly disconnect and close Redis connection pool
    close_redis()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "LedgerLine Core Financial Ledger API. "
        "Engineered for immutable auditability, concurrency safety, and guaranteed money conservation."
    ),
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS with environment-based allowed origins
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include API v1 Router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", include_in_schema=False)
def root():
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs",
        "health_url": f"{settings.API_V1_STR}/health",
        "liveness_url": f"{settings.API_V1_STR}/health/live",
        "readiness_url": f"{settings.API_V1_STR}/health/ready",
    }


# Root-level health probe aliases for orchestrator compatibility
@app.get("/health/live", include_in_schema=False)
@app.get("/live", include_in_schema=False)
def root_liveness():
    return health_service.check_liveness()


@app.get("/health/ready", include_in_schema=False)
@app.get("/ready", include_in_schema=False)
def root_readiness(db: Session = Depends(get_db)):
    is_ready, resp = health_service.check_readiness(db)
    if not is_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=resp.model_dump(mode="json"),
        )
    return resp
