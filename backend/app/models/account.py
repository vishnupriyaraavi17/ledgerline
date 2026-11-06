import enum
import uuid
from decimal import Decimal
from sqlalchemy import (
    String,
    DateTime,
    Numeric,
    func,
    text,
    ForeignKey,
    CheckConstraint,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class AccountType(str, enum.Enum):
    CUSTOMER_CHECKING = "customer_checking"
    CUSTOMER_SAVINGS = "customer_savings"
    SYSTEM_RESERVE = "system_reserve"
    INTERNAL_CLEARING = "internal_clearing"


class AccountStatus(str, enum.Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    account_number: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        index=True,
        nullable=False,
    )

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    account_type: Mapped[AccountType] = mapped_column(
        SQLEnum(
            AccountType,
            name="account_type_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default="INR",
    )

    # Note: server_default is strictly database-side DEFAULT 0.00.
    # No client-side default is provided so SQLAlchemy ORM never serializes 'balance'
    # in INSERT statements executed by the application runtime role.
    balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 2),
        nullable=False,
        server_default=text("0.00"),
    )

    status: Mapped[AccountStatus] = mapped_column(
        SQLEnum(
            AccountStatus,
            name="account_status_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=AccountStatus.ACTIVE,
        server_default="active",
        index=True,
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    owner = relationship("User", backref="accounts", lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "account_type NOT IN ('customer_checking', 'customer_savings') OR balance >= 0",
            name="chk_customer_balance_non_negative",
        ),
        CheckConstraint(
            "account_number ~ '^ACC-[A-Z0-9]{8}$'",
            name="chk_account_number_format",
        ),
        CheckConstraint(
            "currency = 'INR'",
            name="chk_account_currency",
        ),
    )
