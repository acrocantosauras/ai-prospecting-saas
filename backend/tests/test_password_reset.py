"""Tests for the local-only existing-account password reset command."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import reset_password as reset_command
from app.auth.security import hash_password
from app.auth.service import authenticate
from app.core.database import Base
from app.models import User, Workspace, WorkspaceMembership


@pytest.fixture
def local_db(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'reset-test.db'}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(reset_command, "SessionLocal", test_sessions)
    monkeypatch.setattr(
        reset_command,
        "get_settings",
        lambda: SimpleNamespace(
            environment="development",
            database_url=database_url,
        ),
    )
    db = test_sessions()
    workspace = Workspace(slug="demo", name="Demo")
    db.add(workspace)
    db.flush()
    user = User(
        email="qa@example.com",
        password_hash=hash_password("OldSecurePassword123!"),
        display_name="QA",
        is_active=True,
    )
    db.add(user)
    db.flush()
    membership = WorkspaceMembership(
        user_id=user.id,
        workspace_id=workspace.id,
        role="owner",
        is_active=True,
    )
    db.add(membership)
    db.commit()
    db.refresh(user)
    user_id = user.id
    membership_id = membership.id
    original_updated_at = user.updated_at
    yield db, database_url, user_id, membership_id, original_updated_at
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_cli_prompts_and_resets_only_existing_password(local_db, monkeypatch, capsys):
    db, _, user_id, membership_id, original_updated_at = local_db
    new_password = "NewSecurePassword456!"
    prompts = iter([new_password, new_password])
    monkeypatch.setattr(reset_command.getpass, "getpass", lambda _prompt: next(prompts))

    assert reset_command.main(["--email", "qa@example.com"]) == 0
    output = capsys.readouterr()
    assert "Password updated" in output.out
    assert new_password not in output.out
    assert new_password not in output.err

    db.expire_all()
    user = db.query(User).filter(User.id == user_id).one()
    membership = db.query(WorkspaceMembership).filter(WorkspaceMembership.id == membership_id).one()
    assert authenticate(db, "qa@example.com", new_password) is user
    assert authenticate(db, "qa@example.com", "OldSecurePassword123!") is None
    assert user.password_hash.startswith("scrypt$")
    assert membership.role == "owner"
    assert membership.is_active is True
    assert user.updated_at == original_updated_at
    assert db.query(Workspace).filter_by(slug="demo").count() == 1
    assert db.query(User).count() == 1


@pytest.mark.parametrize(
    ("environment", "database_url"),
    [
        ("production", "sqlite:///local.db"),
        ("development", "postgresql://localhost/app"),
        ("development", "sqlite://remote-host/path.db"),
    ],
)
def test_reset_refuses_non_local_targets(local_db, environment, database_url):
    db, _, _, _, _ = local_db
    with pytest.raises(RuntimeError):
        reset_command.reset_existing_account_password(
            db,
            "qa@example.com",
            "NewSecurePassword456!",
            environment=environment,
            database_url=database_url,
        )
    assert authenticate(db, "qa@example.com", "OldSecurePassword123!") is not None


@pytest.mark.parametrize("password", ("short", "ElevenChars", "            "))
def test_reset_rejects_passwords_below_policy(local_db, password):
    db, database_url, user_id, _, _ = local_db
    with pytest.raises(ValueError):
        reset_command.reset_existing_account_password(
            db,
            "qa@example.com",
            password,
            environment="development",
            database_url=database_url,
        )
    db.expire_all()
    user = db.query(User).filter(User.id == user_id).one()
    assert authenticate(db, "qa@example.com", "OldSecurePassword123!") is user


def test_cli_rejects_short_password_without_changing_the_hash(local_db, monkeypatch, capsys):
    db, _, user_id, _, _ = local_db
    prompts = iter(["Short1!", "Short1!"])
    monkeypatch.setattr(reset_command.getpass, "getpass", lambda _prompt: next(prompts))

    assert reset_command.main(["--email", "qa@example.com"]) == 1
    output = capsys.readouterr()
    assert "Password reset failed" in output.err
    assert "at least 12 characters" in output.err
    assert "Short1!" not in output.out
    assert "Short1!" not in output.err

    db.expire_all()
    user = db.query(User).filter(User.id == user_id).one()
    assert authenticate(db, "qa@example.com", "OldSecurePassword123!") is user


def test_reset_does_not_create_unknown_account(local_db):
    db, database_url, _, _, _ = local_db
    with pytest.raises(LookupError):
        reset_command.reset_existing_account_password(
            db,
            "missing@example.com",
            "NewSecurePassword456!",
            environment="development",
            database_url=database_url,
        )
    assert db.query(User).count() == 1
