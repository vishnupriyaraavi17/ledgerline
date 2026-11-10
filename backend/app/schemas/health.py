from datetime import datetime, timezone
from typing import Optional, Literal
from pydantic import BaseModel, Field


class DatabaseHealth(BaseModel):
    status: Literal["connected", "disconnected"] = Field(
        ...,
        description="Database connectivity status: 'connected' if alive, 'disconnected' on failure."
    )
    details: Optional[str] = Field(
        None,
        description="Sanitized diagnostic information (never contains credentials or internal traces)."
    )


class RedisHealth(BaseModel):
    status: Literal["connected", "disconnected"] = Field(
        ...,
        description="Redis connectivity status: 'connected' if alive, 'disconnected' on failure."
    )
    details: Optional[str] = Field(
        None,
        description="Sanitized diagnostic information (never contains credentials or internal traces)."
    )


class LivenessResponse(BaseModel):
    status: Literal["alive"] = Field(
        "alive",
        description="Process liveness indicator ('alive')"
    )
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the liveness inspection"
    )


class ReadinessDependencies(BaseModel):
    database: DatabaseHealth = Field(..., description="PostgreSQL database connectivity")
    redis: RedisHealth = Field(..., description="Redis cache and distributed rate-limiter connectivity")


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"] = Field(
        ...,
        description="'ready' when all required dependencies are operational, 'not_ready' if any fail."
    )
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Active runtime environment")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the readiness inspection"
    )
    dependencies: ReadinessDependencies = Field(..., description="Component readiness details")


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"] = Field(
        ...,
        description="'healthy' when all subsystems are operational, 'degraded' if any component is failing."
    )
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Active runtime environment")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the health inspection"
    )
    database: DatabaseHealth = Field(..., description="Database subsystem health")
    redis: Optional[RedisHealth] = Field(
        None,
        description="Redis subsystem health"
    )
