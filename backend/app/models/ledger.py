import enum
import uuid
from decimal import Decimal
from sqlalchemy import (
    String,
    DateTime,
    Numeric,
    Integer,
    func,
    ForeignKey,
    CheckConstraint,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class EntryType(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class TransactionType(str, enum.Enum):
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"
    SETTLEMENT = "settlement"


class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    reference: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    transaction_type: Mapped[TransactionType] = mapped_column(
        SQLEnum(
            TransactionType,
            name="transaction_type_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )

    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    posted_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    entries = relationship(
        "LedgerEntry",
        back_populates="transaction",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    entry_type: Mapped[EntryType] = mapped_column(
        SQLEnum(
            EntryType,
            name="entry_type_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 2),
        nullable=False,
    )

    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    transaction = relationship("LedgerTransaction", back_populates="entries")
    account = relationship("Account", backref="ledger_entries")

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="chk_ledger_entry_amount_positive",
        ),
    )
