import uuid
from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

from backend.app.models.user import User, UserRole
from backend.app.models.account import Account, AccountType, AccountStatus
from backend.app.schemas.transfer import DepositRequest, WithdrawRequest, TransferRequest
from backend.app.services.transfer import transfer_service


def make_test_user(role: UserRole) -> User:
    return User(
        id=uuid.uuid4(),
        username=f"user_{role.value}",
        email=f"{role.value}@example.com",
        hashed_password="hash",
        role=role,
        is_active=True,
    )


def make_test_account(
    owner_id: uuid.UUID | None,
    status: AccountStatus = AccountStatus.ACTIVE,
    balance: Decimal = Decimal("1000.00"),
    account_type: AccountType = AccountType.CUSTOMER_CHECKING,
    account_number: str = "ACC-12345678",
) -> Account:
    return Account(
        id=uuid.uuid4(),
        account_number=account_number,
        owner_id=owner_id,
        name="Test Account",
        account_type=account_type,
        currency="INR",
        balance=balance,
        status=status,
    )


def test_auditor_prohibited_from_financial_operations():
    db = MagicMock()
    auditor = make_test_user(UserRole.AUDITOR)

    # Deposit
    with pytest.raises(HTTPException) as exc_dep:
        transfer_service.deposit(
            db, auditor, DepositRequest(account_id=uuid.uuid4(), amount=Decimal("100.00"))
        )
    assert exc_dep.value.status_code == 403

    # Withdraw
    with pytest.raises(HTTPException) as exc_wd:
        transfer_service.withdraw(
            db, auditor, WithdrawRequest(account_id=uuid.uuid4(), amount=Decimal("100.00"))
        )
    assert exc_wd.value.status_code == 403

    # Transfer
    with pytest.raises(HTTPException) as exc_tr:
        transfer_service.transfer(
            db,
            auditor,
            TransferRequest(
                source_account_id=uuid.uuid4(),
                destination_account_id=uuid.uuid4(),
                amount=Decimal("100.00"),
            ),
        )
    assert exc_tr.value.status_code == 403


def test_admin_prohibited_from_financial_mutations():
    db = MagicMock()
    admin = make_test_user(UserRole.ADMIN)

    # Deposit
    with pytest.raises(HTTPException) as exc_dep:
        transfer_service.deposit(
            db, admin, DepositRequest(account_id=uuid.uuid4(), amount=Decimal("100.00"))
        )
    assert exc_dep.value.status_code == 403
    assert "Only Account Holders are permitted to perform deposits" in exc_dep.value.detail

    # Withdraw
    with pytest.raises(HTTPException) as exc_wd:
        transfer_service.withdraw(
            db, admin, WithdrawRequest(account_id=uuid.uuid4(), amount=Decimal("100.00"))
        )
    assert exc_wd.value.status_code == 403
    assert "Only Account Holders are permitted to perform withdrawals" in exc_wd.value.detail

    # Transfer
    with pytest.raises(HTTPException) as exc_tr:
        transfer_service.transfer(
            db,
            admin,
            TransferRequest(
                source_account_id=uuid.uuid4(),
                destination_account_id=uuid.uuid4(),
                amount=Decimal("100.00"),
            ),
        )
    assert exc_tr.value.status_code == 403
    assert "Only Account Holders are permitted to initiate transfers" in exc_tr.value.detail


def test_deposit_anti_enumeration_non_owned_account():
    db = MagicMock()
    account_holder = make_test_user(UserRole.ACCOUNT_HOLDER)
    other_owner_id = uuid.uuid4()
    target_account = make_test_account(owner_id=other_owner_id)

    # Mock scalar to return target account
    db.scalar.return_value = target_account

    with pytest.raises(HTTPException) as exc_info:
        transfer_service.deposit(
            db,
            account_holder,
            DepositRequest(account_id=target_account.id, amount=Decimal("500.00")),
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Account not found"


def test_withdraw_insufficient_funds_rejected():
    db = MagicMock()
    account_holder = make_test_user(UserRole.ACCOUNT_HOLDER)
    customer_acc = make_test_account(
        owner_id=account_holder.id,
        balance=Decimal("200.00"),
    )

    db.scalar.return_value = customer_acc

    with pytest.raises(HTTPException) as exc_info:
        transfer_service.withdraw(
            db,
            account_holder,
            WithdrawRequest(account_id=customer_acc.id, amount=Decimal("500.00")),
        )
    assert exc_info.value.status_code == 400
    assert "Insufficient funds" in exc_info.value.detail


def test_transfer_insufficient_funds_rejected():
    db = MagicMock()
    account_holder = make_test_user(UserRole.ACCOUNT_HOLDER)
    src_acc = make_test_account(
        owner_id=account_holder.id,
        balance=Decimal("150.00"),
        account_number="ACC-SRC11111",
    )
    dst_acc = make_test_account(
        owner_id=uuid.uuid4(),
        balance=Decimal("50.00"),
        account_number="ACC-DST22222",
    )

    # Mock scalar returning appropriate account
    def mock_scalar(query):
        # First call min, second call max
        return src_acc if src_acc.id < dst_acc.id else dst_acc

    db.scalar.side_effect = lambda query: src_acc if src_acc.id in str(query) or True else dst_acc

    # Directly set side effect on scalar for min/max
    first_id = min(src_acc.id, dst_acc.id)
    db.scalar.side_effect = lambda q: src_acc if first_id == src_acc.id else dst_acc

    # Test transfer logic using deterministic mock returns
    def select_account_mock(stmt):
        # Check Account.id equality in where clauses
        if str(src_acc.id) in str(stmt):
            return src_acc
        return dst_acc

    db.scalar.side_effect = [src_acc, dst_acc] if src_acc.id < dst_acc.id else [dst_acc, src_acc]

    with pytest.raises(HTTPException) as exc_info:
        transfer_service.transfer(
            db,
            account_holder,
            TransferRequest(
                source_account_id=src_acc.id,
                destination_account_id=dst_acc.id,
                amount=Decimal("300.00"),
            ),
        )
    assert exc_info.value.status_code == 400
    assert "Insufficient funds" in exc_info.value.detail


def test_frozen_account_operations_rejected():
    db = MagicMock()
    account_holder = make_test_user(UserRole.ACCOUNT_HOLDER)
    frozen_acc = make_test_account(
        owner_id=account_holder.id,
        status=AccountStatus.FROZEN,
        balance=Decimal("500.00"),
    )

    db.scalar.return_value = frozen_acc

    # Deposit rejected
    with pytest.raises(HTTPException) as exc_dep:
        transfer_service.deposit(
            db,
            account_holder,
            DepositRequest(account_id=frozen_acc.id, amount=Decimal("100.00")),
        )
    assert exc_dep.value.status_code == 400
    assert "frozen" in exc_dep.value.detail

    # Withdraw rejected
    with pytest.raises(HTTPException) as exc_wd:
        transfer_service.withdraw(
            db,
            account_holder,
            WithdrawRequest(account_id=frozen_acc.id, amount=Decimal("100.00")),
        )
    assert exc_wd.value.status_code == 400
    assert "frozen" in exc_wd.value.detail
