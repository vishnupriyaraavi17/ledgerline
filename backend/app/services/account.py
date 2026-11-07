import uuid
from decimal import Decimal
from typing import List, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.user import User, UserRole
from backend.app.models.account import Account, AccountType, AccountStatus
from backend.app.models.ledger import LedgerEntry
from backend.app.schemas.account import AccountCreate
from backend.app.repositories.account import account_repository
from backend.app.repositories.ledger import ledger_repository
from backend.app.repositories.user import user_repository
from backend.app.repositories.audit import audit_repository


class AccountService:
    """
    Business logic and lifecycle FSM for Accounts.
    Enforces RBAC and HTTP 404 anti-enumeration protections.
    """

    @staticmethod
    def create_account(
        db: Session, current_user: User, account_in: AccountCreate
    ) -> Account:
        # RBAC Check: Auditors cannot create accounts
        if current_user.role == UserRole.AUDITOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Auditors are not permitted to create accounts",
            )

        # Enforce Account Holder self-ownership
        if current_user.role == UserRole.ACCOUNT_HOLDER:
            owner_id = current_user.id
        elif current_user.role == UserRole.ADMIN:
            owner_id = account_in.owner_id or current_user.id
            # Verify owner exists if explicitly provided
            if account_in.owner_id:
                owner = user_repository.get_by_id(db, account_in.owner_id)
                if not owner:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Specified account owner was not found",
                    )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized role for account creation",
            )

        # Ensure account type is a customer account type
        if account_in.account_type not in (
            AccountType.CUSTOMER_CHECKING,
            AccountType.CUSTOMER_SAVINGS,
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only customer accounts (customer_checking, customer_savings) can be created via API",
            )

        account = account_repository.create_account(
            db=db,
            name=account_in.name,
            account_type=account_in.account_type,
            owner_id=owner_id,
            currency=account_in.currency,
        )

        audit_repository.append_event(
            db=db,
            event_type="account.created",
            actor_id=current_user.id,
            actor_role=current_user.role.value,
            entity_type="account",
            entity_id=account.account_number,
            payload={
                "account_id": str(account.id),
                "name": account.name,
                "account_type": account.account_type.value,
                "currency": account.currency,
                "owner_id": str(account.owner_id),
            },
        )
        db.commit()
        db.refresh(account)
        return account

    @staticmethod
    def get_account_for_user(
        db: Session, current_user: User, account_id: uuid.UUID
    ) -> Account:
        account = account_repository.get_by_id(db, account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found",
            )

        # HTTP 404 Anti-Enumeration: Account Holder can only access their own accounts
        if current_user.role == UserRole.ACCOUNT_HOLDER:
            if account.owner_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Account not found",
                )

        return account

    @staticmethod
    def list_accounts_for_user(
        db: Session, current_user: User, skip: int = 0, limit: int = 50
    ) -> Tuple[List[Account], int]:
        if current_user.role == UserRole.ACCOUNT_HOLDER:
            return account_repository.list_accounts_by_owner(
                db, current_user.id, skip=skip, limit=limit
            )
        return account_repository.list_all_accounts(db, skip=skip, limit=limit)

    @staticmethod
    def update_account_status(
        db: Session,
        current_user: User,
        account_id: uuid.UUID,
        new_status: AccountStatus,
    ) -> Account:
        # RBAC Check: Only Admins can modify account status
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators are permitted to update account status",
            )

        account = account_repository.get_by_id(db, account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found",
            )

        # Closed accounts are terminal - cannot be reopened or transitioned
        if account.status == AccountStatus.CLOSED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Closed accounts cannot be reopened or have their status changed",
            )

        if account.status == new_status:
            return account

        # Closing an account requires exactly ₹0.00 balance
        if new_status == AccountStatus.CLOSED:
            if account.balance != Decimal("0.00"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot close account with non-zero balance: ₹{account.balance}",
                )

        prev_status = account.status.value
        updated_account = account_repository.update_status(db, account, new_status)

        audit_repository.append_event(
            db=db,
            event_type="account.status_updated",
            actor_id=current_user.id,
            actor_role=current_user.role.value,
            entity_type="account",
            entity_id=updated_account.account_number,
            payload={
                "account_id": str(updated_account.id),
                "previous_status": prev_status,
                "new_status": new_status.value,
            },
        )
        db.commit()
        db.refresh(updated_account)
        return updated_account

    @staticmethod
    def get_account_ledger(
        db: Session, current_user: User, account_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> Tuple[List[LedgerEntry], int]:
        # Enforce ownership / anti-enumeration via get_account_for_user
        AccountService.get_account_for_user(db, current_user, account_id)
        return ledger_repository.list_entries_by_account(db, account_id, skip=skip, limit=limit)


account_service = AccountService()
