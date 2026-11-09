"""Password hashing and opaque token helpers.

Only the Python standard library is used. ``hashlib.scrypt`` is a memory-hard
key-derivation function provided by OpenSSL, so no third-party crypto package
(passlib, bcrypt, argon2-cffi) is required and no custom scheme is invented.
The work factors are encoded in the stored hash, so they can be raised later
without invalidating existing credentials.

Session and CSRF secrets are generated with ``secrets`` and stored only as
SHA-256 digests; they are compared in constant time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from functools import lru_cache

ALGORITHM = "scrypt"
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
DKLEN = 32
SALT_BYTES = 16
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024
TOKEN_BYTES = 32
_MAX_MEM = 64 * 1024 * 1024


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def validate_password_strength(password: str) -> None:
    """Reject passwords that do not meet the minimum policy.

    Raises:
        ValueError: when the password is too short, too long or blank.

    """
    if not password or not password.strip():
        raise ValueError("Password must not be blank")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("Password is too long")


def hash_password(password: str) -> str:
    """Return a salted scrypt hash for a new password."""
    validate_password_strength(password)
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=DKLEN,
        maxmem=_MAX_MEM,
    )
    return "$".join(
        [
            ALGORITHM,
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            _b64encode(salt),
            _b64encode(digest),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password against a stored hash. Never raises."""
    if not password or not encoded or len(password) > MAX_PASSWORD_LENGTH:
        return False
    try:
        algorithm, n, r, p, salt_b64, digest_b64 = encoded.split("$")
        if algorithm != ALGORITHM:
            return False
        salt = _b64decode(salt_b64)
        expected = _b64decode(digest_b64)
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
            maxmem=_MAX_MEM,
        )
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(candidate, expected)


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """Return a throwaway hash used to equalise login timing for unknown users."""
    return hash_password(secrets.token_urlsafe(32))


def new_session_token() -> str:
    """Return a new opaque session secret."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def new_csrf_token() -> str:
    """Return a new CSRF secret for a session."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_digest(token: str) -> str:
    """Return the SHA-256 hex digest stored for a token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def digests_match(candidate: str, stored: str | None) -> bool:
    """Constant-time comparison of a presented token against a stored digest."""
    if not candidate or not stored:
        return False
    return hmac.compare_digest(token_digest(candidate), stored)
