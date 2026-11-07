import uuid
from decimal import Decimal
import pytest
from pydantic import ValidationError

from backend.app.schemas.transfer import (
    DepositRequest,
    WithdrawRequest,
    TransferRequest,
    validate_monetary_amount,
)


def test_monetary_amount_validation():
    # Valid positive amounts with at most 2 decimal places
    assert validate_monetary_amount(Decimal("100.00")) == Decimal("100.00")
    assert validate_monetary_amount(Decimal("0.01")) == Decimal("0.01")
    assert validate_monetary_amount(Decimal("50")) == Decimal("50")
    assert validate_monetary_amount(Decimal("9999999.99")) == Decimal("9999999.99")

    # Zero rejected
    with pytest.raises(ValueError, match="strictly greater than 0.00"):
        validate_monetary_amount(Decimal("0.00"))

    # Negative rejected
    with pytest.raises(ValueError, match="strictly greater than 0.00"):
        validate_monetary_amount(Decimal("-10.50"))

    # Sub-paise fractions rejected (more than 2 decimal places)
    with pytest.raises(ValueError, match="more than 2 decimal places"):
        validate_monetary_amount(Decimal("10.001"))

    with pytest.raises(ValueError, match="more than 2 decimal places"):
        validate_monetary_amount(Decimal("0.005"))


def test_deposit_request_valid():
    acc_id = uuid.uuid4()
    req = DepositRequest(
        account_id=acc_id,
        amount=Decimal("500.00"),
        description="Salary deposit",
    )
    assert req.account_id == acc_id
    assert req.amount == Decimal("500.00")
    assert req.description == "Salary deposit"


def test_deposit_request_rejects_extra_fields():
    acc_id = str(uuid.uuid4())
    with pytest.raises(ValidationError) as exc_info:
        DepositRequest.model_validate({
            "account_id": acc_id,
            "amount": "100.00",
            "fake_field": "injected",
        })
    assert "Extra inputs are not permitted" in str(exc_info.value)


def test_withdraw_request_valid():
    acc_id = uuid.uuid4()
    req = WithdrawRequest(
        account_id=acc_id,
        amount=Decimal("250.50"),
    )
    assert req.account_id == acc_id
    assert req.amount == Decimal("250.50")
    assert req.description is None


def test_withdraw_request_rejects_invalid_amount():
    acc_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        WithdrawRequest(account_id=acc_id, amount=Decimal("-50.00"))

    with pytest.raises(ValidationError):
        WithdrawRequest(account_id=acc_id, amount=Decimal("0.00"))

    with pytest.raises(ValidationError):
        WithdrawRequest(account_id=acc_id, amount=Decimal("10.123"))


def test_transfer_request_valid():
    src_id = uuid.uuid4()
    dst_id = uuid.uuid4()
    req = TransferRequest(
        source_account_id=src_id,
        destination_account_id=dst_id,
        amount=Decimal("150.00"),
        description="Dinner split",
    )
    assert req.source_account_id == src_id
    assert req.destination_account_id == dst_id
    assert req.amount == Decimal("150.00")
    assert req.description == "Dinner split"


def test_transfer_request_allows_self_transfer_payload_for_service_refusal():
    acc_id = uuid.uuid4()
    req = TransferRequest(
        source_account_id=acc_id,
        destination_account_id=acc_id,
        amount=Decimal("100.00"),
    )
    assert req.source_account_id == acc_id
    assert req.destination_account_id == acc_id


def test_transfer_request_rejects_extra_fields():
    src_id = str(uuid.uuid4())
    dst_id = str(uuid.uuid4())
    with pytest.raises(ValidationError) as exc_info:
        TransferRequest.model_validate({
            "source_account_id": src_id,
            "destination_account_id": dst_id,
            "amount": "100.00",
            "override_fee": "0.00",
        })
    assert "Extra inputs are not permitted" in str(exc_info.value)
