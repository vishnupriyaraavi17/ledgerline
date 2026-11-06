from typing import Optional, Tuple, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.user import User
from backend.app.schemas.user import UserCreate, UserResponse, LoginRequest, TokenResponse, UserListResponse
from backend.app.repositories.user import user_repository, UserRepository
from backend.app.security.passwords import hash_password, verify_password
from backend.app.security.tokens import create_access_token


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
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

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

    def create_user(self, db: Session, user_in: UserCreate) -> UserResponse:
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
