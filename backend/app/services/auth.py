import logging
from typing import Optional, Tuple, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.user import User
from backend.app.schemas.user import UserCreate, UserResponse, LoginRequest, TokenResponse, UserListResponse
from backend.app.repositories.user import user_repository, UserRepository
from backend.app.repositories.audit import audit_repository
from backend.app.security.passwords import hash_password, verify_password
from backend.app.security.tokens import create_access_token
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
