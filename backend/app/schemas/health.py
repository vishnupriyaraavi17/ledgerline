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
