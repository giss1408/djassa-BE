from enum import IntEnum


class VerificationTier(IntEnum):
    TIER_0 = 0
    TIER_1 = 1
    TIER_2 = 2


def require_tier(current_tier: int, required_tier: VerificationTier) -> None:
    if current_tier < int(required_tier):
        raise PermissionError(f"verification tier {required_tier} required")
