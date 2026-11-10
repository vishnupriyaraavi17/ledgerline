import json
import uuid
import hashlib
from decimal import Decimal
from typing import Any, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.user import User, UserRole
from backend.app.models.account import Account, AccountType, AccountStatus
from backend.app.models.ledger import LedgerTransaction, TransactionType
from backend.app.schemas.transfer import (
    DepositRequest,
    WithdrawRequest,
    TransferRequest,
    TransactionResponse,
)
from backend.app.repositories.ledger import ledger_repository
from backend.app.repositories.idempotency import idempotency_repository
from backend.app.repositories.audit import audit_repository
from backend.app.repositories.refusal import refusal_repository


class TransferService:
    """
    Business logic and orchestration for financial operations:
    - Deposits (external simulated -> customer checking/savings via ACC-SYSTEM02)
    - Withdrawals (customer checking/savings -> external simulated via ACC-SYSTEM02)
    - Transfers (customer -> customer)
    - Journal inspection with RBAC and anti-enumeration protections.
    - PostgreSQL ACID idempotency concurrency and replay deduplication.
    """

    @staticmethod
    def deposit(
        db: Session,
        current_user: User,
        req: DepositRequest,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[Any, bool]:
        record = None
        request_hash = None

        if idempotency_key is not None:
            canonical_data = {
                "account_id": req.account_id,
                "amount": req.amount,
                "description": req.description or "",
            }
            request_hash = idempotency_repository.compute_canonical_fingerprint(
                "deposit", canonical_data
            )

            # 1. Try atomic reservation
            record = idempotency_repository.try_create_processing_record(
                db=db,
                user_id=current_user.id,
                idempotency_key=idempotency_key,
                operation_type="deposit",
                request_hash=request_hash,
            )

            # 2. If conflict, wait on pessimistic lock of existing record
            if not record:
                record = idempotency_repository.get_locked_record(
                    db=db,
                    user_id=current_user.id,
                    idempotency_key=idempotency_key,
                )
                if not record:
                    # Previous concurrent attempt rolled back, retry claiming
                    record = idempotency_repository.try_create_processing_record(
                        db=db,
                        user_id=current_user.id,
                        idempotency_key=idempotency_key,
                        operation_type="deposit",
                        request_hash=request_hash,
                    )
                    if not record:
                        record = idempotency_repository.get_locked_record(
                            db=db,
                            user_id=current_user.id,
                            idempotency_key=idempotency_key,
                        )

            # 3. Check for replay or parameter conflict on completed record
            if record and record.status == "completed":
                if record.request_hash != request_hash:
                    refusal_repository.record_refusal(
                        user_id=current_user.id,
                        operation_type="deposit",
                        account_id=req.account_id,
                        counterparty_account_id=None,
                        amount=req.amount,
                        refusal_reason="IDEMPOTENCY_CONFLICT",
                        error_message="Idempotency key was previously used with a different request payload.",
                        idempotency_key_hash=hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest() if idempotency_key else None,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency key was previously used with a different request payload.",
                    )
                cached_data = json.loads(record.response_body)
                return cached_data, True

        try:
            # RBAC Check: Only Account Holders can perform deposits
            if current_user.role != UserRole.ACCOUNT_HOLDER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only Account Holders are permitted to perform deposits",
                )

            # Retrieve and lock customer account
            customer_acc = db.scalar(
                select(Account).where(Account.id == req.account_id).with_for_update(of=Account)
            )
            if not customer_acc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Account not found",
                )

            # Anti-Enumeration: Account Holder can only deposit to their own accounts
            if customer_acc.owner_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Account not found",
                )

            # Account type check: Customer accounts only
            if customer_acc.account_type not in (
                AccountType.CUSTOMER_CHECKING,
                AccountType.CUSTOMER_SAVINGS,
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Deposits can only be performed on customer accounts",
                )

            # Status check
            if customer_acc.status != AccountStatus.ACTIVE:
                user_id_val = current_user.id
                acc_id_val = customer_acc.id
                amount_val = req.amount
                reason_code = "ACCOUNT_FROZEN" if customer_acc.status == AccountStatus.FROZEN else "ACCOUNT_CLOSED"
                msg = f"Account is {customer_acc.status.value}; transactions are only permitted on active accounts"
                idem_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest() if idempotency_key else None
                db.rollback()
                refusal_repository.record_refusal(
                    user_id=user_id_val,
                    operation_type="deposit",
                    account_id=acc_id_val,
                    counterparty_account_id=None,
                    amount=amount_val,
                    refusal_reason=reason_code,
                    error_message=msg,
                    idempotency_key_hash=idem_hash,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=msg,
                )

            # Resolve system clearing transit account
            clearing_acc = db.scalar(
                select(Account).where(Account.account_number == "ACC-SYSTEM02").with_for_update(of=Account)
            )
            if not clearing_acc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="System clearing account ACC-SYSTEM02 is not configured",
                )

            ref = ledger_repository.generate_unique_reference(db)
            desc = req.description or f"Deposit of ₹{req.amount} to {customer_acc.account_number}"

            # Double-entry posting:
            # Leg 1: DEBIT ACC-SYSTEM02 (Asset/Transit increases with debit)
            # Leg 2: CREDIT customer account (Liability increases with credit)
            txn = ledger_repository.create_transaction_with_entries(
                db=db,
                reference=ref,
                transaction_type=TransactionType.SETTLEMENT,
                description=desc,
                debit_account_id=clearing_acc.id,
                credit_account_id=customer_acc.id,
                amount=req.amount,
            )

            # Re-query with eager-loaded entries
            full_txn = ledger_repository.get_transaction_by_id(db, txn.id)
            response_dto = TransactionResponse.model_validate(full_txn)
            response_dict = response_dto.model_dump(mode="json")
            response_json = json.dumps(response_dict)

            # Stage 3 Lock: Append immutable cryptographic audit event
            idem_hash = (
                hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
                if idempotency_key
                else None
            )
            audit_repository.append_event(
                db=db,
                event_type="financial.deposit",
                actor_id=current_user.id,
                actor_role=current_user.role.value,
                entity_type="transaction",
                entity_id=txn.reference,
                payload={
                    "transaction_id": str(txn.id),
                    "account_id": str(customer_acc.id),
                    "amount": str(req.amount.quantize(Decimal("0.01"))),
                    "currency": customer_acc.currency,
                    "description": req.description or "",
                    "idempotency_key_hash": idem_hash,
                },
            )

            # Mark idempotency record completed within same transaction
            if record:
                idempotency_repository.mark_completed(
                    db=db,
                    record=record,
                    transaction_id=txn.id,
                    status_code=status.HTTP_201_CREATED,
                    response_body=response_json,
                )

            db.commit()
            return response_dict, False

        except Exception:
            db.rollback()
            raise

    @staticmethod
    def withdraw(
        db: Session,
        current_user: User,
        req: WithdrawRequest,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[Any, bool]:
        record = None
        request_hash = None

        if idempotency_key is not None:
            canonical_data = {
                "account_id": req.account_id,
                "amount": req.amount,
                "description": req.description or "",
            }
            request_hash = idempotency_repository.compute_canonical_fingerprint(
                "withdraw", canonical_data
            )

            # 1. Try atomic reservation
            record = idempotency_repository.try_create_processing_record(
                db=db,
                user_id=current_user.id,
                idempotency_key=idempotency_key,
                operation_type="withdraw",
                request_hash=request_hash,
            )

            # 2. If conflict, wait on pessimistic lock of existing record
            if not record:
                record = idempotency_repository.get_locked_record(
                    db=db,
                    user_id=current_user.id,
                    idempotency_key=idempotency_key,
                )
                if not record:
                    record = idempotency_repository.try_create_processing_record(
                        db=db,
                        user_id=current_user.id,
                        idempotency_key=idempotency_key,
                        operation_type="withdraw",
                        request_hash=request_hash,
                    )
                    if not record:
                        record = idempotency_repository.get_locked_record(
                            db=db,
                            user_id=current_user.id,
                            idempotency_key=idempotency_key,
                        )

            # 3. Check for replay or parameter conflict on completed record
            if record and record.status == "completed":
                if record.request_hash != request_hash:
                    refusal_repository.record_refusal(
                        user_id=current_user.id,
                        operation_type="withdraw",
                        account_id=req.account_id,
                        counterparty_account_id=None,
                        amount=req.amount,
                        refusal_reason="IDEMPOTENCY_CONFLICT",
                        error_message="Idempotency key was previously used with a different request payload.",
                        idempotency_key_hash=hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest() if idempotency_key else None,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency key was previously used with a different request payload.",
                    )
                cached_data = json.loads(record.response_body)
                return cached_data, True

        try:
            # RBAC Check: Only Account Holders can perform withdrawals
            if current_user.role != UserRole.ACCOUNT_HOLDER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only Account Holders are permitted to perform withdrawals",
                )

            # Retrieve and lock customer account
            customer_acc = db.scalar(
                select(Account).where(Account.id == req.account_id).with_for_update(of=Account)
            )
            if not customer_acc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Account not found",
                )

            # Anti-Enumeration: Account Holder can only withdraw from their own accounts
            if customer_acc.owner_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Account not found",
                )

            # Account type check: Customer accounts only
            if customer_acc.account_type not in (
                AccountType.CUSTOMER_CHECKING,
                AccountType.CUSTOMER_SAVINGS,
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Withdrawals can only be performed on customer accounts",
                )

            # Status check
            if customer_acc.status != AccountStatus.ACTIVE:
                user_id_val = current_user.id
                acc_id_val = customer_acc.id
                amount_val = req.amount
                reason_code = "ACCOUNT_FROZEN" if customer_acc.status == AccountStatus.FROZEN else "ACCOUNT_CLOSED"
                msg = f"Account is {customer_acc.status.value}; transactions are only permitted on active accounts"
                idem_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest() if idempotency_key else None
                db.rollback()
                refusal_repository.record_refusal(
                    user_id=user_id_val,
                    operation_type="withdraw",
                    account_id=acc_id_val,
                    counterparty_account_id=None,
                    amount=amount_val,
                    refusal_reason=reason_code,
                    error_message=msg,
                    idempotency_key_hash=idem_hash,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=msg,
                )

            # Sufficiency check: Customer balance must cover withdrawal amount
            if customer_acc.balance < req.amount:
                user_id_val = current_user.id
                acc_id_val = customer_acc.id
                amount_val = req.amount
                idem_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest() if idempotency_key else None
                db.rollback()
                refusal_repository.record_refusal(
                    user_id=user_id_val,
                    operation_type="withdraw",
                    account_id=acc_id_val,
                    counterparty_account_id=None,
                    amount=amount_val,
                    refusal_reason="INSUFFICIENT_FUNDS",
                    error_message="Insufficient funds",
                    idempotency_key_hash=idem_hash,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Insufficient funds",
                )

            # Resolve system clearing transit account
            clearing_acc = db.scalar(
                select(Account).where(Account.account_number == "ACC-SYSTEM02").with_for_update(of=Account)
            )
            if not clearing_acc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="System clearing account ACC-SYSTEM02 is not configured",
                )

            ref = ledger_repository.generate_unique_reference(db)
            desc = req.description or f"Withdrawal of ₹{req.amount} from {customer_acc.account_number}"

            # Double-entry posting:
            # Leg 1: DEBIT customer account (Liability decreases with debit)
            # Leg 2: CREDIT ACC-SYSTEM02 (Asset/Transit decreases with credit)
            txn = ledger_repository.create_transaction_with_entries(
                db=db,
                reference=ref,
                transaction_type=TransactionType.SETTLEMENT,
                description=desc,
                debit_account_id=customer_acc.id,
                credit_account_id=clearing_acc.id,
                amount=req.amount,
            )

            full_txn = ledger_repository.get_transaction_by_id(db, txn.id)
            response_dto = TransactionResponse.model_validate(full_txn)
            response_dict = response_dto.model_dump(mode="json")
            response_json = json.dumps(response_dict)

            # Stage 3 Lock: Append immutable cryptographic audit event
            idem_hash = (
                hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
                if idempotency_key
                else None
            )
            audit_repository.append_event(
                db=db,
                event_type="financial.withdraw",
                actor_id=current_user.id,
                actor_role=current_user.role.value,
                entity_type="transaction",
                entity_id=txn.reference,
                payload={
                    "transaction_id": str(txn.id),
                    "account_id": str(customer_acc.id),
                    "amount": str(req.amount.quantize(Decimal("0.01"))),
                    "currency": customer_acc.currency,
                    "description": req.description or "",
                    "idempotency_key_hash": idem_hash,
                },
            )

            if record:
                idempotency_repository.mark_completed(
                    db=db,
                    record=record,
                    transaction_id=txn.id,
                    status_code=status.HTTP_201_CREATED,
                    response_body=response_json,
                )

            db.commit()
            return response_dict, False

        except Exception:
            db.rollback()
            raise

    @staticmethod
    def transfer(
        db: Session,
        current_user: User,
        req: TransferRequest,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[Any, bool]:
        record = None
        request_hash = None

        if idempotency_key is not None:
            canonical_data = {
                "source_account_id": req.source_account_id,
                "destination_account_id": req.destination_account_id,
                "amount": req.amount,
                "description": req.description or "",
            }
            request_hash = idempotency_repository.compute_canonical_fingerprint(
                "transfer", canonical_data
            )

            # 1. Try atomic reservation
            record = idempotency_repository.try_create_processing_record(
                db=db,
                user_id=current_user.id,
                idempotency_key=idempotency_key,
                operation_type="transfer",
                request_hash=request_hash,
            )

            # 2. If conflict, wait on pessimistic lock of existing record
            if not record:
                record = idempotency_repository.get_locked_record(
                    db=db,
                    user_id=current_user.id,
                    idempotency_key=idempotency_key,
                )
                if not record:
                    record = idempotency_repository.try_create_processing_record(
                        db=db,
                        user_id=current_user.id,
                        idempotency_key=idempotency_key,
                        operation_type="transfer",
                        request_hash=request_hash,
                    )
                    if not record:
                        record = idempotency_repository.get_locked_record(
                            db=db,
                            user_id=current_user.id,
                            idempotency_key=idempotency_key,
                        )

            # 3. Check for replay or parameter conflict on completed record
            if record and record.status == "completed":
                if record.request_hash != request_hash:
                    refusal_repository.record_refusal(
                        user_id=current_user.id,
                        operation_type="transfer",
                        account_id=req.source_account_id,
                        counterparty_account_id=req.destination_account_id,
                        amount=req.amount,
                        refusal_reason="IDEMPOTENCY_CONFLICT",
                        error_message="Idempotency key was previously used with a different request payload.",
                        idempotency_key_hash=hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest() if idempotency_key else None,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency key was previously used with a different request payload.",
                    )
                cached_data = json.loads(record.response_body)
                return cached_data, True

        try:
            # RBAC Check: Only Account Holders are permitted to initiate customer-fund transfers
            if current_user.role != UserRole.ACCOUNT_HOLDER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only Account Holders are permitted to initiate transfers",
                )

            # Deadlock-free deterministic row locking ordered by UUID
            first_id = min(req.source_account_id, req.destination_account_id)
            second_id = max(req.source_account_id, req.destination_account_id)

            first_acc = db.scalar(select(Account).where(Account.id == first_id).with_for_update(of=Account))
            second_acc = db.scalar(select(Account).where(Account.id == second_id).with_for_update(of=Account))

            source_acc = first_acc if first_id == req.source_account_id else second_acc
            dest_acc = second_acc if first_id == req.source_account_id else first_acc

            # Sourcing account existence check
            if not source_acc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Account not found",
                )

            # Anti-Enumeration: Account Holder can only source from accounts they own
            if current_user.role == UserRole.ACCOUNT_HOLDER:
                if source_acc.owner_id != current_user.id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Account not found",
                    )

            # Self-transfer check
            if req.source_account_id == req.destination_account_id:
                user_id_val = current_user.id
                src_id_val = req.source_account_id
                amount_val = req.amount
                idem_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest() if idempotency_key else None
                db.rollback()
                refusal_repository.record_refusal(
                    user_id=user_id_val,
                    operation_type="transfer",
                    account_id=src_id_val,
                    counterparty_account_id=src_id_val,
                    amount=amount_val,
                    refusal_reason="SELF_TRANSFER_PROHIBITED",
                    error_message="Source and destination accounts must be distinct",
                    idempotency_key_hash=idem_hash,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Source and destination accounts must be distinct",
                )

            # Destination account existence check
            if not dest_acc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Destination account not found",
                )

            # Both accounts must be customer checking or savings accounts
            for acc, label in [(source_acc, "Source"), (dest_acc, "Destination")]:
                if acc.account_type not in (
                    AccountType.CUSTOMER_CHECKING,
                    AccountType.CUSTOMER_SAVINGS,
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"{label} account must be a customer checking or savings account",
                    )

            # Status check: both accounts must be active
            if source_acc.status != AccountStatus.ACTIVE:
                user_id_val = current_user.id
                src_id_val = source_acc.id
                dst_id_val = dest_acc.id if dest_acc else None
                amount_val = req.amount
                reason_code = "ACCOUNT_FROZEN" if source_acc.status == AccountStatus.FROZEN else "ACCOUNT_CLOSED"
                msg = f"Source account is {source_acc.status.value}; transactions are only permitted on active accounts"
                idem_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest() if idempotency_key else None
                db.rollback()
                refusal_repository.record_refusal(
                    user_id=user_id_val,
                    operation_type="transfer",
                    account_id=src_id_val,
                    counterparty_account_id=dst_id_val,
                    amount=amount_val,
                    refusal_reason=reason_code,
                    error_message=msg,
                    idempotency_key_hash=idem_hash,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=msg,
                )
            if dest_acc.status != AccountStatus.ACTIVE:
                user_id_val = current_user.id
                src_id_val = source_acc.id
                dst_id_val = dest_acc.id
                amount_val = req.amount
                reason_code = "DESTINATION_FROZEN" if dest_acc.status == AccountStatus.FROZEN else "DESTINATION_CLOSED"
                msg = f"Destination account is {dest_acc.status.value}; transactions are only permitted on active accounts"
                idem_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest() if idempotency_key else None
                db.rollback()
                refusal_repository.record_refusal(
                    user_id=user_id_val,
                    operation_type="transfer",
                    account_id=src_id_val,
                    counterparty_account_id=dst_id_val,
                    amount=amount_val,
                    refusal_reason=reason_code,
                    error_message=msg,
                    idempotency_key_hash=idem_hash,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=msg,
                )

            # Sufficiency check: Source account balance must cover transfer amount
            if source_acc.balance < req.amount:
                user_id_val = current_user.id
                src_id_val = source_acc.id
                dst_id_val = dest_acc.id
                amount_val = req.amount
                idem_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest() if idempotency_key else None
                db.rollback()
                refusal_repository.record_refusal(
                    user_id=user_id_val,
                    operation_type="transfer",
                    account_id=src_id_val,
                    counterparty_account_id=dst_id_val,
                    amount=amount_val,
                    refusal_reason="INSUFFICIENT_FUNDS",
                    error_message="Insufficient funds",
                    idempotency_key_hash=idem_hash,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Insufficient funds",
                )

            ref = ledger_repository.generate_unique_reference(db)
            desc = (
                req.description
                or f"Transfer of ₹{req.amount} from {source_acc.account_number} to {dest_acc.account_number}"
            )

            # Double-entry posting:
            # Leg 1: DEBIT source account (Liability decreases with debit)
            # Leg 2: CREDIT destination account (Liability increases with credit)
            txn = ledger_repository.create_transaction_with_entries(
                db=db,
                reference=ref,
                transaction_type=TransactionType.TRANSFER,
                description=desc,
                debit_account_id=source_acc.id,
                credit_account_id=dest_acc.id,
                amount=req.amount,
            )

            full_txn = ledger_repository.get_transaction_by_id(db, txn.id)
            response_dto = TransactionResponse.model_validate(full_txn)
            response_dict = response_dto.model_dump(mode="json")
            response_json = json.dumps(response_dict)

            # Stage 3 Lock: Append immutable cryptographic audit event
            idem_hash = (
                hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
                if idempotency_key
                else None
            )
            audit_repository.append_event(
                db=db,
                event_type="financial.transfer",
                actor_id=current_user.id,
                actor_role=current_user.role.value,
                entity_type="transaction",
                entity_id=txn.reference,
                payload={
                    "transaction_id": str(txn.id),
                    "source_account_id": str(source_acc.id),
                    "destination_account_id": str(dest_acc.id),
                    "amount": str(req.amount.quantize(Decimal("0.01"))),
                    "currency": source_acc.currency,
                    "description": req.description or "",
                    "idempotency_key_hash": idem_hash,
                },
            )

            if record:
                idempotency_repository.mark_completed(
                    db=db,
                    record=record,
                    transaction_id=txn.id,
                    status_code=status.HTTP_201_CREATED,
                    response_body=response_json,
                )

            db.commit()
            return response_dict, False

        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_transaction(
        db: Session, current_user: User, reference: str
    ) -> LedgerTransaction:
        txn = ledger_repository.get_transaction_by_reference(db, reference)
        if not txn:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found",
            )

        # Anti-Enumeration for Account Holder:
        # Must own at least one account associated with this transaction's entries
        if current_user.role == UserRole.ACCOUNT_HOLDER:
            user_account_ids = set(
                db.scalars(
                    select(Account.id).where(Account.owner_id == current_user.id)
                ).all()
            )
            txn_account_ids = {entry.account_id for entry in txn.entries}
            if not (user_account_ids & txn_account_ids):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Transaction not found",
                )

        return txn

    @staticmethod
    def list_transactions(
        db: Session, current_user: User, skip: int = 0, limit: int = 50
    ) -> Tuple[List[LedgerTransaction], int]:
        if current_user.role == UserRole.ACCOUNT_HOLDER:
            user_account_ids = list(
                db.scalars(
                    select(Account.id).where(Account.owner_id == current_user.id)
                ).all()
            )
            if not user_account_ids:
                return [], 0
            return ledger_repository.list_transactions_for_accounts(
                db, user_account_ids, skip=skip, limit=limit
            )

        return ledger_repository.list_all_transactions(db, skip=skip, limit=limit)


transfer_service = TransferService()
