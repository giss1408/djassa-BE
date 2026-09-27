from enum import StrEnum


class PaymentStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUND_PENDING = "refund_pending"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


_ALLOWED_TRANSITIONS = {
    PaymentStatus.CREATED: {PaymentStatus.PENDING, PaymentStatus.CANCELLED},
    PaymentStatus.PENDING: {PaymentStatus.SUCCEEDED, PaymentStatus.FAILED, PaymentStatus.CANCELLED, PaymentStatus.DISPUTED},
    PaymentStatus.SUCCEEDED: {PaymentStatus.REFUND_PENDING, PaymentStatus.DISPUTED},
    PaymentStatus.REFUND_PENDING: {PaymentStatus.REFUNDED, PaymentStatus.FAILED},
    PaymentStatus.DISPUTED: {PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED, PaymentStatus.FAILED},
    PaymentStatus.FAILED: set(),
    PaymentStatus.CANCELLED: set(),
    PaymentStatus.REFUNDED: set(),
}


def transition(current: str, target: PaymentStatus) -> str:
    current_status = PaymentStatus(current)
    if target not in _ALLOWED_TRANSITIONS[current_status]:
        raise ValueError(f"Invalid payment transition: {current_status} -> {target}")
    return target.value
