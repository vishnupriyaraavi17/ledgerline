from fastapi import APIRouter, Depends, status, Request, Response, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.session import get_db
from backend.app.schemas.user import LoginRequest, TokenResponse, UserRegister, UserResponse
from backend.app.services.auth import auth_service
from backend.app.security.dependencies import get_current_user
from backend.app.security.rate_limiter import registration_limiter
from backend.app.models.user import User

router = APIRouter()


def set_refresh_cookie(response: Response, refresh_token: str):
    """
    Sets the rotated refresh token in an HttpOnly, Secure cookie.
    Scoped strictly to /api/v1/auth.
    """
    is_prod = settings.ENVIRONMENT == "production"
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=is_prod,
        samesite="none" if is_prod else "lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=f"{settings.API_V1_STR}/auth",
    )


def clear_refresh_cookie(response: Response):
    """
    Clears the HttpOnly refresh cookie upon logout.
    """
    is_prod = settings.ENVIRONMENT == "production"
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=f"{settings.API_V1_STR}/auth",
        secure=is_prod,
        samesite="none" if is_prod else "lax",
    )


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
        "Returns a signed HS256 JWT access token and sets an HttpOnly, Secure refresh session cookie."
    ),
    responses={
        200: {"description": "Authentication successful.", "model": TokenResponse},
        401: {"description": "Invalid credentials or inactive account."},
    },
)
def login_json(
    request: LoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    token_response, refresh_token = auth_service.login_with_refresh(db, request)
    set_refresh_cookie(response, refresh_token)
    return token_response


@router.post(
    "/token",
    response_model=TokenResponse,
    include_in_schema=True,
    summary="OAuth2 Form Login (Swagger UI compatibility)",
    description="Standard OAuth2 form login for Swagger UI interactive authorization.",
)
def login_oauth2(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    req = LoginRequest(
        username_or_email=form_data.username,
        password=form_data.password
    )
    token_response, refresh_token = auth_service.login_with_refresh(db, req)
    set_refresh_cookie(response, refresh_token)
    return token_response


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate Refresh Session and Issue New Access Token",
    description=(
        "Validates the caller's HttpOnly refresh cookie, verifies active session in Redis, "
        "rotates the refresh token (issuing a new HttpOnly cookie), and returns a fresh access token."
    ),
    responses={
        200: {"description": "Session refreshed successfully.", "model": TokenResponse},
        401: {"description": "Invalid, expired, or revoked refresh session."},
    },
)
def refresh_session_endpoint(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    cookie_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not cookie_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Active refresh session not found. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_response, new_refresh_token = auth_service.refresh_session(db, cookie_token)
    set_refresh_cookie(response, new_refresh_token)
    return token_response


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Revoke Active Session and Clear Authentication Cookie",
    description="Revokes the active refresh session in Redis and clears the HttpOnly refresh cookie.",
)
def logout_endpoint(
    request: Request,
    response: Response
):
    cookie_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if cookie_token:
        auth_service.revoke_refresh_session(cookie_token)
    clear_refresh_cookie(response)
    return {"detail": "Successfully logged out"}


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
