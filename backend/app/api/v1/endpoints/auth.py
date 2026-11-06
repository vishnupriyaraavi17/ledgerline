from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.user import LoginRequest, TokenResponse, UserResponse
from backend.app.services.auth import auth_service
from backend.app.security.dependencies import get_current_user
from backend.app.models.user import User

router = APIRouter()


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User Authentication (JSON Body)",
    description=(
        "Authenticates a user via username/email and plaintext password using Argon2id verification. "
        "Returns a signed HS256 JWT access token. Returns generic HTTP 401 for invalid credentials."
    ),
    responses={
        200: {"description": "Authentication successful.", "model": TokenResponse},
        401: {"description": "Invalid credentials or inactive account."},
    },
)
def login_json(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    return auth_service.login(db, request)


@router.post(
    "/token",
    response_model=TokenResponse,
    include_in_schema=True,
    summary="OAuth2 Form Login (Swagger UI compatibility)",
    description="Standard OAuth2 form login for Swagger UI interactive authorization.",
)
def login_oauth2(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    req = LoginRequest(
        username_or_email=form_data.username,
        password=form_data.password
    )
    return auth_service.login(db, req)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Current Authenticated User Profile",
    description="Retrieves the profile and role of the currently authenticated active user.",
    responses={
        200: {"description": "Current user profile.", "model": UserResponse},
        401: {"description": "Missing, expired, or invalid token."},
    },
)
def read_current_user(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)
