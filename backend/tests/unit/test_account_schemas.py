import pytest
from pydantic import ValidationError
from backend.app.schemas.account import AccountCreate, AccountStatusUpdate
from backend.app.models.account import AccountType, AccountStatus


def test_account_create_valid_defaults():
    payload = AccountCreate(
        name="Daily Checking",
        account_type=AccountType.CUSTOMER_CHECKING,
    )
    assert payload.currency == "INR"
    assert payload.name == "Daily Checking"
    assert payload.account_type == AccountType.CUSTOMER_CHECKING
    assert payload.owner_id is None


def test_account_create_rejects_non_inr_currency():
    for invalid_currency in ["USD", "EUR", "GBP", "JPY"]:
        with pytest.raises(ValidationError) as exc_info:
            AccountCreate(
                name="Global Savings",
                account_type=AccountType.CUSTOMER_SAVINGS,
                currency=invalid_currency,
            )
        assert "Only INR currency is supported" in str(exc_info.value)


def test_account_create_rejects_system_account_types():
    for sys_type in [AccountType.SYSTEM_RESERVE, AccountType.INTERNAL_CLEARING]:
        with pytest.raises(ValidationError) as exc_info:
            AccountCreate(
                name="Core Reserve",
                account_type=sys_type,
            )
        assert "Only customer accounts" in str(exc_info.value)


def test_account_create_rejects_opening_balance_extra_field():
    with pytest.raises(ValidationError) as exc_info:
        AccountCreate.model_validate({
            "name": "Checking Account",
            "account_type": "customer_checking",
            "balance": "100.00",
        })
    assert "Extra inputs are not permitted" in str(exc_info.value)


def test_account_create_name_validation():
    # Too short
    with pytest.raises(ValidationError):
        AccountCreate(name="ab", account_type=AccountType.CUSTOMER_CHECKING)

    # Empty
    with pytest.raises(ValidationError):
        AccountCreate(name="   ", account_type=AccountType.CUSTOMER_CHECKING)


def test_account_status_update_rejects_extra_fields():
    with pytest.raises(ValidationError) as exc_info:
        AccountStatusUpdate.model_validate({
            "status": "frozen",
            "balance": "500.00",
        })
    assert "Extra inputs are not permitted" in str(exc_info.value)
