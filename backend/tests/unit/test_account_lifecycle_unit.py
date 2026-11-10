import uuid
from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

from backend.app.models.user import User, UserRole
from backend.app.models.account import Account, AccountType, AccountStatus
from backend.app.services.account import account_service


def make_test_user(role: UserRole) -> User:
    return User(
        id=uuid.uuid4(),
        username=f"user_{role.value}",
        email=f"{role.value}@example.com",
        hashed_password="hash",
        role=role,
        is_active=True,
    )


def make_test_account(status: AccountStatus, balance: Decimal = Decimal("0.00")) -> Account:
    return Account(
        id=uuid.uuid4(),
        account_number="ACC-12345678",
        owner_id=uuid.uuid4(),
        name="Test Account",
        account_type=AccountType.CUSTOMER_CHECKING,
        currency="INR",
        balance=balance,
        status=status,
    )


def test_update_status_requires_admin(monkeypatch):
    db = MagicMock()
    account_id = uuid.uuid4()

    # Account holder
    account_holder = make_test_user(UserRole.ACCOUNT_HOLDER)
    with pytest.raises(HTTPException) as exc_info:
        account_service.update_account_status(db, account_holder, account_id, AccountStatus.FROZEN)
    assert exc_info.value.status_code == 403

    # Auditor
    auditor = make_test_user(UserRole.AUDITOR)
    with pytest.raises(HTTPException) as exc_info:
        account_service.update_account_status(db, auditor, account_id, AccountStatus.FROZEN)
    assert exc_info.value.status_code == 403


def test_active_to_frozen_succeeds(monkeypatch):
    db = MagicMock()
    admin = make_test_user(UserRole.ADMIN)
    account = make_test_account(AccountStatus.ACTIVE)

    monkeypatch.setattr(
        "backend.app.services.account.account_repository.get_by_id",
        lambda _db, _id: account,
    )
    monkeypatch.setattr(
        "backend.app.services.account.account_repository.update_status",
        lambda _db, acc, new_status: setattr(acc, "status", new_status) or acc,
    )

    res = account_service.update_account_status(db, admin, account.id, AccountStatus.FROZEN)
    assert res.status == AccountStatus.FROZEN


def test_frozen_to_active_succeeds(monkeypatch):
    db = MagicMock()
    admin = make_test_user(UserRole.ADMIN)
    account = make_test_account(AccountStatus.FROZEN)

    monkeypatch.setattr(
        "backend.app.services.account.account_repository.get_by_id",
        lambda _db, _id: account,
    )
    monkeypatch.setattr(
        "backend.app.services.account.account_repository.update_status",
        lambda _db, acc, new_status: setattr(acc, "status", new_status) or acc,
    )

    res = account_service.update_account_status(db, admin, account.id, AccountStatus.ACTIVE)
    assert res.status == AccountStatus.ACTIVE


def test_active_to_closed_zero_balance_succeeds(monkeypatch):
    db = MagicMock()
    admin = make_test_user(UserRole.ADMIN)
    account = make_test_account(AccountStatus.ACTIVE, balance=Decimal("0.00"))

    monkeypatch.setattr(
        "backend.app.services.account.account_repository.get_by_id",
        lambda _db, _id: account,
    )
    monkeypatch.setattr(
        "backend.app.services.account.account_repository.update_status",
        lambda _db, acc, new_status: setattr(acc, "status", new_status) or acc,
    )

    res = account_service.update_account_status(db, admin, account.id, AccountStatus.CLOSED)
    assert res.status == AccountStatus.CLOSED


def test_frozen_to_closed_zero_balance_succeeds(monkeypatch):
    db = MagicMock()
    admin = make_test_user(UserRole.ADMIN)
    account = make_test_account(AccountStatus.FROZEN, balance=Decimal("0.00"))

    monkeypatch.setattr(
        "backend.app.services.account.account_repository.get_by_id",
        lambda _db, _id: account,
    )
    monkeypatch.setattr(
        "backend.app.services.account.account_repository.update_status",
        lambda _db, acc, new_status: setattr(acc, "status", new_status) or acc,
    )

    res = account_service.update_account_status(db, admin, account.id, AccountStatus.CLOSED)
    assert res.status == AccountStatus.CLOSED


def test_close_account_with_non_zero_balance_fails(monkeypatch):
    db = MagicMock()
    admin = make_test_user(UserRole.ADMIN)
    account = make_test_account(AccountStatus.ACTIVE, balance=Decimal("500.00"))

    monkeypatch.setattr(
        "backend.app.services.account.account_repository.get_by_id",
        lambda _db, _id: account,
    )

    with pytest.raises(HTTPException) as exc_info:
        account_service.update_account_status(db, admin, account.id, AccountStatus.CLOSED)
    assert exc_info.value.status_code == 400
    assert "Cannot close account with non-zero balance" in exc_info.value.detail


def test_closed_account_reopening_rejected(monkeypatch):
    db = MagicMock()
    admin = make_test_user(UserRole.ADMIN)
    account = make_test_account(AccountStatus.CLOSED, balance=Decimal("0.00"))

    monkeypatch.setattr(
        "backend.app.services.account.account_repository.get_by_id",
        lambda _db, _id: account,
    )

    with pytest.raises(HTTPException) as exc_info:
        account_service.update_account_status(db, admin, account.id, AccountStatus.ACTIVE)
    assert exc_info.value.status_code == 400
    assert "Closed accounts cannot be reopened" in exc_info.value.detail


def test_system_account_freeze_or_close_rejected(monkeypatch):
    db = MagicMock()
    admin = make_test_user(UserRole.ADMIN)

    # Test with system account number ACC-SYSTEM01
    sys_acc_1 = Account(
        id=uuid.uuid4(),
        account_number="ACC-SYSTEM01",
        owner_id=None,
        name="System Reserve",
        account_type=AccountType.SYSTEM_RESERVE,
        currency="INR",
        balance=Decimal("0.00"),
        status=AccountStatus.ACTIVE,
    )
    monkeypatch.setattr(
        "backend.app.services.account.account_repository.get_by_id",
        lambda _db, _id: sys_acc_1,
    )

    with pytest.raises(HTTPException) as exc_info:
        account_service.update_account_status(db, admin, sys_acc_1.id, AccountStatus.FROZEN)
    assert exc_info.value.status_code == 400
    assert "System accounts cannot be frozen or closed" in exc_info.value.detail

    with pytest.raises(HTTPException) as exc_info:
        account_service.update_account_status(db, admin, sys_acc_1.id, AccountStatus.CLOSED)
    assert exc_info.value.status_code == 400
    assert "System accounts cannot be frozen or closed" in exc_info.value.detail

    # Test with system account number ACC-SYSTEM02
    sys_acc_2 = Account(
        id=uuid.uuid4(),
        account_number="ACC-SYSTEM02",
        owner_id=None,
        name="Internal Clearing",
        account_type=AccountType.INTERNAL_CLEARING,
        currency="INR",
        balance=Decimal("0.00"),
        status=AccountStatus.ACTIVE,
    )
    monkeypatch.setattr(
        "backend.app.services.account.account_repository.get_by_id",
        lambda _db, _id: sys_acc_2,
    )

    with pytest.raises(HTTPException) as exc_info:
        account_service.update_account_status(db, admin, sys_acc_2.id, AccountStatus.FROZEN)
    assert exc_info.value.status_code == 400
    assert "System accounts cannot be frozen or closed" in exc_info.value.detail