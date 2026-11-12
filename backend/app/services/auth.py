import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.redis import get_redis_client
from backend.app.models.user import User, UserRole
from backend.app.schemas.user import UserCreate, UserRegister, UserResponse, LoginRequest, TokenResponse, UserListResponse
from backend.app.repositories.user import user_repository, UserRepository
from backend.app.repositories.audit import audit_repository
from backend.app.security.passwords import hash_password, verify_password
from backend.app.security.tokens import create_access_token, create_refresh_token, decode_refresh_token
from backend.app.db.session import SessionLocal

logger = logging.getLogger(__name__)


class AuthService:
    """
    Service coordinating identity verification, authentication, and user provisioning.
    """

    def __init__(self, repository: UserRepository = user_repository):
        self.repository = repository

    def authenticate_user(self, db: Session, identifier: str, password: str) -> Optional[User]:
        """
        Authenticates a user against credentials using Argon2id.
        Enforces that inactive accounts cannot authenticate.
        Returns the User if valid, None otherwise.
        """
        user = self.repository.get_by_identifier(db, identifier)
        if not user:
            # Run dummy verification to mitigate timing attacks on nonexistent users
            verify_password("dummy_password", "$argon2id$v=19$m=65536,t=2,p=1$c29tZXNhbHQAAAAAAAAAAA$e0D7k/yR3y0r7v8sNq3fWqR1A/3Q9i5sD6p0q+R7sWw")
            return None

        if not verify_password(password, user.hashed_password):
            return None

        # Server-side check: inactive users cannot authenticate
        if not user.is_active:
            return None

        return user

    def login(self, db: Session, request: LoginRequest) -> TokenResponse:
        """
        Executes user login, returning a signed JWT access token.
        Always returns generic 401 for any authentication failure (missing user, bad password, inactive).
        """
        user = self.authenticate_user(db, request.username_or_email, request.password)
        if not user:
            # Best-effort isolated audit transaction for failed login
            try:
                with SessionLocal() as audit_db:
                    audit_repository.append_event(
                        db=audit_db,
                        event_type="security.login_failure",
                        actor_id=None,
                        actor_role=None,
                        entity_type="auth",
                        entity_id="login_attempt",
                        payload={
                            "attempted_identifier": request.username_or_email[:64],
                            "reason": "invalid_credentials",
                        },
                    )
                    audit_db.commit()
            except Exception as e:
                logger.error(f"Failed to record login failure audit event: {e}")

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Successful login audit event
        audit_repository.append_event(
            db=db,
            event_type="security.login_success",
            actor_id=user.id,
            actor_role=user.role.value,
            entity_type="user",
            entity_id=str(user.id),
            payload={
                "user_id": str(user.id),
                "username": user.username,
                "role": user.role.value,
                "status": "success",
            },
        )
        db.commit()

        token_claims = {
            "sub": str(user.id),
            "role": user.role.value,
            "username": user.username,
            "email": user.email,
        }

        token = create_access_token(data=token_claims)

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )

    def create_refresh_session(self, user: User) -> str:
        """
        Creates a new cryptographically signed refresh token and registers the active
        session in Redis with server-side TTL for immediate revocation support.
        """
        jti = str(uuid.uuid4())
        token_claims = {
            "sub": str(user.id),
            "role": user.role.value,
            "jti": jti,
        }
        refresh_token = create_refresh_token(token_claims)

        try:
            redis_client = get_redis_client()
            session_key = f"session:refresh:{user.id}:{jti}"
            ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
            session_payload = json.dumps({
                "user_id": str(user.id),
                "role": user.role.value,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            redis_client.setex(session_key, ttl_seconds, session_payload)
        except Exception as exc:
            logger.error(f"Could not persist refresh session in Redis: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable. Please try again later.",
            )

        return refresh_token

    def login_with_refresh(self, db: Session, request: LoginRequest) -> Tuple[TokenResponse, str]:
        """
        Executes user login, returning both the access TokenResponse and an HttpOnly refresh token.
        """
        token_response = self.login(db, request)
        user = self.repository.get_by_identifier(db, request.username_or_email)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        refresh_token = self.create_refresh_session(user)
        return token_response, refresh_token

    def refresh_session(self, db: Session, refresh_token: str) -> Tuple[TokenResponse, str]:
        """
        Rotates the refresh token and issues a fresh access token.
        Strictly validates cryptographic signature, server-side revocation in Redis,
        and database user active status.
        """
        try:
            payload = decode_refresh_token(refresh_token)
            user_id_str = payload.get("sub")
            jti = payload.get("jti")
            if not user_id_str or not jti:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token payload")
            user_id = uuid.UUID(user_id_str)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid, tampered, or expired refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Atomically consume the single-use session key in Redis (enforces rotation and prevents race conditions)
        try:
            redis_client = get_redis_client()
            session_key = f"session:refresh:{user_id}:{jti}"
            deleted_count = redis_client.delete(session_key)
            if deleted_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session has been revoked, expired, or already consumed. Please sign in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Redis session verification failed due to Redis outage: {type(exc).__name__}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable. Please try again later.",
            )

        # Verify active user in database
        user = self.repository.get_by_id(db, user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive or not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Issue brand new refresh token (rotated)
        new_refresh_token = self.create_refresh_session(user)

        # Issue brand new access token
        token_claims = {
            "sub": str(user.id),
            "role": user.role.value,
            "username": user.username,
            "email": user.email,
        }
        new_access_token = create_access_token(data=token_claims)

        token_response = TokenResponse(
            access_token=new_access_token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )
        return token_response, new_refresh_token

    def revoke_refresh_session(self, refresh_token: str) -> None:
        """
        Revokes a refresh session in Redis upon user logout.
        """
        try:
            payload = decode_refresh_token(refresh_token)
            user_id_str = payload.get("sub")
            jti = payload.get("jti")
            if user_id_str and jti:
                redis_client = get_redis_client()
                redis_client.delete(f"session:refresh:{user_id_str}:{jti}")
        except Exception as exc:
            logger.warning(f"Failed to revoke refresh session in Redis: {exc}")

    def create_user(
        self, db: Session, user_in: UserCreate, admin_user: Optional[User] = None
    ) -> UserResponse:
        """
        Safely creates a new user, enforcing uniqueness and Argon2id password hashing.
        """
        if self.repository.get_by_username(db, user_in.username):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this username or email already exists",
            )

        if self.repository.get_by_email(db, user_in.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this username or email already exists",
            )

        hashed_pw = hash_password(user_in.password)
        user = self.repository.create_user(db, user_in, hashed_pw)

        audit_repository.append_event(
            db=db,
            event_type="security.user_registered",
            actor_id=admin_user.id if admin_user else None,
            actor_role=admin_user.role.value if admin_user else None,
            entity_type="user",
            entity_id=str(user.id),
            payload={
                "user_id": str(user.id),
                "username": user.username,
                "email": user.email,
                "role": user.role.value,
            },
        )
        db.commit()
        return UserResponse.model_validate(user)

    def register_account_holder(
        self, db: Session, register_in: UserRegister
    ) -> UserResponse:
        """
        Public self-registration service for Account Holders.
        Strictly forces role to UserRole.ACCOUNT_HOLDER server-side.
        Logs security.user_registered to the cryptographic audit chain.
        """
        user_create = UserCreate(
            username=register_in.username,
            email=register_in.email,
            password=register_in.password,
            role=UserRole.ACCOUNT_HOLDER,
        )
        return self.create_user(db, user_create, admin_user=None)

    def list_users(self, db: Session, skip: int = 0, limit: int = 50) -> UserListResponse:
        """
        Lists registered users with pagination.
        """
        limit = min(max(limit, 1), 100)  # Bound limit between 1 and 100
        skip = max(skip, 0)
        users, total = self.repository.list_users(db, skip=skip, limit=limit)
        return UserListResponse(
            items=[UserResponse.model_validate(u) for u in users],
            total=total,
            skip=skip,
            limit=limit,
        )


auth_service = AuthService()
