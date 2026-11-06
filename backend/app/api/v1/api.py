from fastapi import APIRouter
from backend.app.api.v1.endpoints import health, auth, users, accounts

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health & Diagnostics"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["User Management (RBAC)"])
api_router.include_router(accounts.router, prefix="/accounts", tags=["Accounts & Lifecycle"])
