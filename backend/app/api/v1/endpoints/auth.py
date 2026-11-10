from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.user import LoginRequest, TokenResponse, UserRegister, UserResponse
from backend.app.services.auth import auth_service
from backend.app.security.dependencies import get_current_user
from backend.app.security.rate_limiter import registration_limiter
from backend.app.models.user import User

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(registration_limiter)],
    summary="Public Account Holder Registration",
    description=(
        "Registers a new self-service customer profile. "
        "Strictly server-assigns ACCOUNT_HOLDER role without permitting role selection. "
        "Does not issue an active session token upon registration; the user must subsequently sign in. "
        "Protected by client IP rate limiting."
    ),
    responses={
        201: {"description": "Customer registered successfully.", "model": UserResponse},
        409: {"description": "Conflict: Username or email already registered."},
        422: {"description": "Validation Error: Password complexity or format violation."},
        429: {"description": "Too Many Requests: Rate limit exceeded."},
    },
)
def register_customer(
    request: UserRegister,
    db: Session = Depends(get_db)
):
    return auth_service.register_account_holder(db, request)



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
