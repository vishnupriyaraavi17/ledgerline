import argon2
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError, VerificationError

# Argon2id password hasher configuration (Memory-hard & GPU-resistant)
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MiB memory
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=argon2.Type.ID  # Strict Argon2id
)


def hash_password(plain_password: str) -> str:
    """
    Hashes a plain text password using strict Argon2id.
    """
    if not plain_password:
        raise ValueError("Password cannot be empty")
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a candidate password against an Argon2id hash in constant time.
    Returns False if hash format is invalid or password does not match.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False
    except Exception:
        return False


def is_argon2_hash(hash_str: str) -> bool:
    """
    Checks if the hash string has an Argon2id format.
    """
    return bool(hash_str and hash_str.startswith("$argon2id$"))
