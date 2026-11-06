import uuid
from typing import List, Union
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.session import get_db
from backend.app.models.user import User, UserRole
from backend.app.repositories.user import user_repository
from backend.app.security.tokens import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Decodes the JWT token and fetches the user from the database.
    Strictly verifies server-side that the account exists and is currently active.
    Prevents deactivated accounts from accessing endpoints with existing valid tokens.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        user_id_str: str = payload.get("sub")
        if not user_id_str:
            raise credentials_exception
        user_id = uuid.UUID(user_id_str)
    except (PyJWTError, ValueError):
        raise credentials_exception

    user = user_repository.get_by_id(db, user_id)
    if not user:
        raise credentials_exception

    # Server-side validation: reject previously issued tokens if account was deactivated
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_role(allowed_roles: Union[UserRole, List[UserRole]]):
    """
    Dependency factory enforcing role-based authorization at the endpoint level.
    Returns HTTP 403 Forbidden if the authenticated user's role is not allowed.
    """
    if isinstance(allowed_roles, UserRole):
        roles_list = [allowed_roles]
    else:
        roles_list = allowed_roles

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles_list:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required role: {[r.value for r in roles_list]}",
            )
        return current_user

    return role_checker
