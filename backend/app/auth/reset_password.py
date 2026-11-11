"""Local-development password reset for an existing account.

Run with ``python -m app.auth.reset_password --email user@example.com``.
This command is intentionally unavailable outside development or against a
non-SQLite database, and it never creates users or changes memberships. The new
password must satisfy the same policy as account creation.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import update
from sqlalchemy.engine import CursorResult, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.security import hash_password, validate_password_strength
from app.auth.service import get_user_by_email
from app.config import get_settings
from app.core.database import SessionLocal
from app.models import User


def _validate_local_target(environment: str, database_url: str) -> None:
    """Allow password resets only for development backed by local SQLite."""
    if (environment or "").strip().lower() != "development":
        raise RuntimeError("Password reset is available only in development.")

    try:
        url = make_url(database_url)
    except ArgumentError as exc:
        raise RuntimeError("Password reset requires valid local database settings.") from exc
    if not url.drivername.startswith("sqlite") or url.host:
        raise RuntimeError("Password reset requires a local SQLite database.")


def reset_existing_account_password(
    db: Session,
    email: str,
    password: str,
    *,
    environment: str,
    database_url: str,
) -> None:
    """Replace only the password hash for an existing account."""
    _validate_local_target(environment, database_url)
    # Apply the account-creation policy before touching any row: a weak password
    # must fail without a lookup, a write or a session change.
    validate_password_strength(password)
    user = get_user_by_email(db, email)
    if user is None:
        raise LookupError("No existing account matches that email.")

    encoded = hash_password(password)
    try:
        result = cast(
            CursorResult[Any],
            db.execute(
                update(User)
                .where(User.id == user.id)
                .values(password_hash=encoded, updated_at=User.updated_at)
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount != 1:
            raise LookupError("No existing account matches that email.")
        db.commit()
    except Exception:
        db.rollback()
        raise


def main(argv: Sequence[str] | None = None) -> int:
    """Prompt for a password and reset an existing local development account."""
    parser = argparse.ArgumentParser(
        prog="python -m app.auth.reset_password",
        description="Set a new password for an existing local development account.",
    )
    parser.add_argument("--email", required=True, help="Email of the existing account")
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        _validate_local_target(settings.environment, settings.database_url)
    except (RuntimeError, ValueError) as exc:
        print(f"Password reset refused: {exc}", file=sys.stderr)
        return 2

    try:
        password = getpass.getpass("New password: ")
        confirmation = getpass.getpass("Confirm new password: ")
    except (EOFError, KeyboardInterrupt):
        print("Password reset cancelled.", file=sys.stderr)
        return 1

    if password != confirmation:
        print("Password reset failed: passwords do not match.", file=sys.stderr)
        return 1

    db: Session | None = None
    try:
        db = SessionLocal()
        reset_existing_account_password(
            db,
            args.email,
            password,
            environment=settings.environment,
            database_url=settings.database_url,
        )
    except (LookupError, RuntimeError, ValueError) as exc:
        print(f"Password reset failed: {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Password reset failed: the local database operation was unsuccessful.", file=sys.stderr)
        return 1
    finally:
        if db is not None:
            db.close()

    print("Password updated for the existing account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
