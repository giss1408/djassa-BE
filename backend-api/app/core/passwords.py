"""Password hashing (argon2id) and the rules a new password must meet."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_LENGTH = 8
MAX_LENGTH = 128

_hasher = PasswordHasher()


def check_rules(plain: str) -> None:
    """Raise ValueError (French message, shown to the person) if not acceptable."""
    if len(plain) < MIN_LENGTH:
        raise ValueError("Le mot de passe doit contenir au moins 8 caractères.")
    if len(plain) > MAX_LENGTH:
        raise ValueError("Le mot de passe doit contenir au plus 128 caractères.")
    if plain.isdigit():
        raise ValueError("Le mot de passe ne peut pas être composé uniquement de chiffres.")


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerificationError, InvalidHashError):
        return False
