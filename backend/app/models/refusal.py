import uuid
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    String,
    DateTime,
    Numeric,
    ForeignKey,
    CheckConstraint,
    CHAR,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class RefusedOperation(Base):
    __tablename__ = "refused_operations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    counterparty_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    operation_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 2),
        nullable=True,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default="INR",
    )

    refusal_reason: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    error_message: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    idempotency_key_hash: Mapped[Optional[str]] = mapped_column(
        CHAR(64),
        nullable=True,
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    account = relationship("Account", foreign_keys=[account_id])
    counterparty_account = relationship("Account", foreign_keys=[counterparty_account_id])

    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('deposit', 'withdraw', 'transfer')",
            name="chk_refused_operation_type",
        ),
        CheckConstraint(
            "amount IS NULL OR amount > 0",
            name="chk_refused_amount_positive",
        ),
        CheckConstraint(
            "currency = 'INR'",
            name="chk_refused_currency",
        ),
    )
