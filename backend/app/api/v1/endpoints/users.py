from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.user import User, UserRole
from backend.app.schemas.user import UserCreate, UserResponse, UserListResponse
from backend.app.services.auth import auth_service
from backend.app.security.dependencies import require_role

router = APIRouter()


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create New User (Admin Only)",
    description=(
        "Provisions a new user account with a specified role. "
        "Strictly restricted to users with the Administrator role."
    ),
    responses={
        201: {"description": "User successfully created.", "model": UserResponse},
        403: {"description": "Forbidden: Requires Administrator role."},
        409: {"description": "Conflict: Username or email already registered."},
    },
)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    return auth_service.create_user(db, user_in, admin_user=_admin)


@router.get(
    "",
    response_model=UserListResponse,
    summary="List Users (Admin and Auditor Only)",
    description=(
        "Retrieves a paginated list of registered users. "
        "Permitted for Administrator and Auditor roles. "
        "Account Holders are strictly rejected with HTTP 403 Forbidden."
    ),
    responses={
        200: {"description": "Paginated list of users.", "model": UserListResponse},
        403: {"description": "Forbidden: Insufficient privileges."},
    },
)
def list_users(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    db: Session = Depends(get_db),
    _authorized_user: User = Depends(require_role([UserRole.ADMIN, UserRole.AUDITOR])),
):
    return auth_service.list_users(db, skip=skip, limit=limit)
