import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import (
    String,
    DateTime,
    BigInteger,
    Integer,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class AuditChainHead(Base):
    __tablename__ = "audit_chain_head"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("id = 1", name="chk_head_singleton_id"),
        CheckConstraint("sequence_number >= 0", name="chk_head_sequence_non_negative"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    sequence_number: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    actor_role: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    entity_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    prev_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    current_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    actor = relationship("User", lazy="joined")

    __table_args__ = (
        CheckConstraint("sequence_number > 0", name="chk_audit_sequence_positive"),
    )
