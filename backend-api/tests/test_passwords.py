import pytest

from app.core import otp, passwords, tokens


def test_hash_roundtrip():
    hashed = passwords.hash_password("motdepasse1")
    assert hashed != "motdepasse1"
    assert passwords.verify_password("motdepasse1", hashed) is True
    assert passwords.verify_password("autremotdepasse", hashed) is False


def test_verify_rejects_garbage_hash():
    assert passwords.verify_password("motdepasse1", "not-a-hash") is False


def test_rules_reject_short_and_all_digits():
    for bad in ("1234567", "12345678"):
        with pytest.raises(ValueError):
            passwords.check_rules(bad)
    with pytest.raises(ValueError):
        passwords.check_rules("a" * 129)
    assert passwords.check_rules("motdepasse1") is None


def test_secret_hmac_is_bound_to_user_and_kind():
    stored = tokens.hmac_secret(1, "verify_number", "123456")
    assert tokens.secret_matches(1, "verify_number", "123456", stored)
    assert not tokens.secret_matches(2, "verify_number", "123456", stored)
    assert not tokens.secret_matches(1, "reset_password", "123456", stored)
    assert not tokens.secret_matches(1, "verify_number", "654321", stored)


def test_otp_still_reexports_token_helpers():
    assert otp.new_refresh_token is tokens.new_refresh_token
    assert otp.hash_refresh_token is tokens.hash_refresh_token
    assert otp.new_family is tokens.new_family
