import pytest

from app.services.payment_state import PaymentStatus, transition


def test_payment_state_machine_allows_successful_flow():
    assert transition("created", PaymentStatus.PENDING) == "pending"
    assert transition("pending", PaymentStatus.SUCCEEDED) == "succeeded"
    assert transition("succeeded", PaymentStatus.REFUND_PENDING) == "refund_pending"
    assert transition("refund_pending", PaymentStatus.REFUNDED) == "refunded"


def test_payment_state_machine_rejects_invalid_transition():
    with pytest.raises(ValueError):
        transition("created", PaymentStatus.SUCCEEDED)