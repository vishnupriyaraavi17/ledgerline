import uuid
from typing import Optional, List, Tuple
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from backend.app.models.user import User, UserRole
from backend.app.schemas.user import UserCreate


class UserRepository:
    """
    Data access layer for User entities.
    """

    @staticmethod
    def get_by_id(db: Session, user_id: uuid.UUID) -> Optional[User]:
        return db.scalar(select(User).where(User.id == user_id))

    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[User]:
        normalized = username.strip().lower()
        return db.scalar(select(User).where(User.username == normalized))

    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        normalized = email.strip().lower()
        return db.scalar(select(User).where(User.email == normalized))

    @staticmethod
    def get_by_identifier(db: Session, identifier: str) -> Optional[User]:
        normalized = identifier.strip().lower()
        stmt = select(User).where(
            or_(
                User.username == normalized,
                User.email == normalized
            )
        )
        return db.scalar(stmt)

    @staticmethod
    def create_user(db: Session, user_in: UserCreate, hashed_password: str) -> User:
        user = User(
            id=uuid.uuid4(),
            username=user_in.username,
            email=user_in.email,
            hashed_password=hashed_password,
            role=user_in.role,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def list_users(db: Session, skip: int = 0, limit: int = 50) -> Tuple[List[User], int]:
        total = db.scalar(select(func.count()).select_from(User)) or 0
        stmt = select(User).order_by(User.created_at.asc()).offset(skip).limit(limit)
        items = list(db.scalars(stmt).all())
        return items, total


user_repository = UserRepository()
