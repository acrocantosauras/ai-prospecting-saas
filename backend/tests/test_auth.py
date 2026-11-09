"""Authentication and multi-tenant authorization tests.

These tests exercise the real login endpoint, the real session cookies and the
real authorization dependencies - nothing is stubbed. Each test gets its own
``TestClient`` (and therefore its own cookie jar) so "user A" and "user B" cannot
share a session by accident.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth.security import hash_password, verify_password
from app.core.database import SessionLocal
from app.main import app
from app.models import (
    AuthSession,
    ClientProfile,
    Company,
    ICPProfile,
    Prospect,
    ProspectBatch,
    User,
    Workspace,
    WorkspaceMembership,
)

EXPORT_COLUMNS = [
    "lead_id",
    "first_name",
    "last_name",
    "email",
    "company",
    "website",
    "role",
    "client_id",
    "status",
    "draft_date",
    "notes",
]


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    """Keep failed-login counters from leaking between tests."""
    from app.auth.service import login_throttle

    login_throttle.clear()
    yield
    login_throttle.clear()


@pytest.fixture()
def api():
    """A fresh client with an empty cookie jar."""
    with TestClient(app) as client:
        yield client


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _db():
    return SessionLocal()


def _workspace(slug: str | None = None, name: str | None = None) -> Workspace:
    db = _db()
    try:
        workspace = Workspace(slug=slug or _unique("ws"), name=name or "Test Workspace")
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        db.expire_on_commit = False
        return workspace
    finally:
        db.close()


def _membership(workspace_id: uuid.UUID, role: str, active: bool = True) -> User:
    """Create an account with a membership in ``workspace_id``.

    Returns a fully-loaded, detached user so callers can safely read its scalar
    attributes after the session used here is closed.
    """
    from app.auth.service import create_user

    db = _db()
    try:
        workspace = (
            db.query(Workspace).filter(Workspace.id == workspace_id).one()
        )
        user = create_user(db, _unique("user") + "@example.test", "CorrectHorseBattery1")
        db.add(
            WorkspaceMembership(
                user_id=user.id,
                workspace_id=workspace.id,
                role=role,
                is_active=active,
            )
        )
        db.commit()
        # Materialize scalars while the session is still live.
        _ = (user.id, user.email, user.display_name, user.is_active)
        return user
    finally:
        db.close()


def _tenant_with_batch(prefix: str) -> dict[str, str]:
    """Create a workspace with profile, ICP, batch and prospect directly in the DB."""
    db = _db()
    try:
        workspace = Workspace(slug=_unique(prefix), name=f"{prefix} tenant")
        db.add(workspace)
        db.commit()
        db.refresh(workspace)

        profile = ClientProfile(
            workspace_id=workspace.id,
            name="Tenant Client",
            products_services="Workflow automation",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        icp = ICPProfile(
            workspace_id=workspace.id,
            client_profile_id=profile.id,
            name="Tenant ICP",
            target_industries="Technology",
            target_countries="US",
            decision_maker_roles="CEO",
            max_prospects=2,
        )
        db.add(icp)
        db.commit()
        db.refresh(icp)

        batch = ProspectBatch(
            workspace_id=workspace.id,
            icp_profile_id=icp.id,
            client_profile_id=profile.id,
            name="Tenant batch",
            source_mode="demo",
            status="pending",
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)

        company = Company(batch_id=batch.id, name="Tenant Co", website="https://tenant.example")
        db.add(company)
        db.commit()
        db.refresh(company)

        prospect = Prospect(
            batch_id=batch.id,
            company_id=company.id,
            full_name="Tenant Person",
            role="CEO",
            company_name="Tenant Co",
            qualification_status="rejected",
            is_ready_for_outreach=False,
        )
        db.add(prospect)
        db.commit()
        db.refresh(prospect)

        return {
            "workspace_id": str(workspace.id),
            "workspace_slug": workspace.slug,
            "client_profile_id": str(profile.id),
            "icp_profile_id": str(icp.id),
            "batch_id": str(batch.id),
            "prospect_id": str(prospect.id),
            "company_id": str(company.id),
        }
    finally:
        db.close()


def _login(api: TestClient, email: str, password: str = "CorrectHorseBattery1") -> dict:
    response = api.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #

PROTECTED_REQUESTS = [
    ("get", "/api/v1/auth/me"),
    ("get", "/api/v1/workspaces/"),
    ("get", "/api/v1/business-profile/"),
    ("get", "/api/v1/icp/"),
    ("get", "/api/v1/batches/"),
    ("get", "/api/v1/prospects/"),
    ("get", "/api/v1/exports/preview/{batch}"),
    ("get", "/api/v1/exports/csv/{batch}"),
    ("get", "/api/v1/engine/batches/{batch}/progress"),
    ("get", "/api/v1/engine/batches/{batch}/qualifications"),
    ("get", "/api/v1/engine/prospects/{prospect}/verification"),
    ("get", "/api/v1/engine/companies/{company}/evidence"),
    ("get", "/api/v1/engine/providers"),
    ("get", "/api/v1/engine/usage"),
    ("post", "/api/v1/engine/batches/{batch}/cancel"),
    ("post", "/api/v1/exports/google-sheets/{batch}"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED_REQUESTS)
def test_anonymous_requests_are_rejected(api, method, path):
    ids = {
        "batch": uuid.uuid4(),
        "prospect": uuid.uuid4(),
        "company": uuid.uuid4(),
    }
    url = path.format(**ids)
    response = getattr(api, method)(url)
    assert response.status_code == 401, (url, response.status_code, response.text)


def test_anonymous_mutations_are_rejected(api):
    response = api.post(
        "/api/v1/business-profile/",
        json={"workspace_id": "demo", "name": "Anon"},
    )
    assert response.status_code == 401
    response = api.post(
        "/api/v1/batches/",
        json={"workspace_id": "demo", "icp_profile_id": str(uuid.uuid4()), "name": "x"},
    )
    assert response.status_code == 401


def test_health_and_auth_status_are_public(api):
    assert api.get("/health").json() == {"status": "ok"}
    status_response = api.get("/api/v1/auth/status")
    assert status_response.status_code == 200
    assert status_response.json()["authentication_available"] is True


def test_login_rejects_invalid_credentials(api, auth_factory):
    workspace = _workspace()
    account = auth_factory(api, workspace.slug, "owner")
    api.headers.pop("X-CSRF-Token", None)
    header_only = {k: v for k, v in api.headers.items() if k.lower() != "x-csrf-token"}
    del header_only

    wrong_password = api.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": "WrongPassword123"},
    )
    assert wrong_password.status_code == 401

    unknown_email = api.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.test", "password": "CorrectHorseBattery1"},
    )
    assert unknown_email.status_code == 401
    # Identical message: the API does not reveal whether the account exists.
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


def test_passwords_are_never_stored_in_plaintext(api, auth_factory):
    workspace = _workspace()
    account = auth_factory(api, workspace.slug, "owner")
    db = _db()
    try:
        user = db.query(User).filter(User.email == account["email"]).one()
        assert user.password_hash != account["password"]
        assert account["password"] not in user.password_hash
        assert user.password_hash.startswith("scrypt$")
        assert verify_password(account["password"], user.password_hash) is True
        assert verify_password("not-the-password", user.password_hash) is False
        assert verify_password(account["password"], hash_password("AnotherPass12345")) is False
    finally:
        db.close()


def test_session_cookie_is_httponly_and_csrf_cookie_is_readable(api, auth_factory):
    workspace = _workspace()
    account = auth_factory(api, workspace.slug, "owner")
    api.headers.pop("X-CSRF-Token", None)
    login = api.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": account["password"]},
    )
    assert login.status_code == 200
    raw_cookies = login.headers.get_list("set-cookie")
    session_cookie = next(c for c in raw_cookies if c.startswith("prospect_session="))
    csrf_cookie = next(c for c in raw_cookies if c.startswith("prospect_csrf="))
    assert "httponly" in session_cookie.lower()
    assert "httponly" not in csrf_cookie.lower()
    assert "samesite=lax" in session_cookie.lower()


def test_logout_revokes_the_session(api, auth_factory):
    workspace = _workspace()
    account = auth_factory(api, workspace.slug, "owner")
    stolen_cookie = api.cookies.get("prospect_session")
    assert stolen_cookie

    assert api.get("/api/v1/auth/me").status_code == 200
    assert api.post("/api/v1/auth/logout").status_code == 204
    assert api.get("/api/v1/auth/me").status_code == 401

    # Replaying the old cookie must fail: the session row is revoked.
    replay = api.get(
        "/api/v1/auth/me", headers={"Cookie": f"prospect_session={stolen_cookie}"}
    )
    assert replay.status_code == 401


def _session_row(email: str) -> AuthSession:
    db = _db()
    try:
        user = db.query(User).filter(User.email == email).one()
        return (
            db.query(AuthSession)
            .filter(AuthSession.user_id == user.id)
            .order_by(AuthSession.created_at.desc())
            .first()
        )
    finally:
        db.close()


def test_expired_session_is_rejected(api, auth_factory):
    from datetime import UTC, datetime, timedelta

    workspace = _workspace()
    account = auth_factory(api, workspace.slug, "owner")
    session = _session_row(account["email"])

    db = _db()
    try:
        row = db.query(AuthSession).filter(AuthSession.id == session.id).one()
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    assert api.get("/api/v1/auth/me").status_code == 401


def test_idle_session_is_rejected(api, auth_factory):
    from datetime import UTC, datetime, timedelta

    workspace = _workspace()
    account = auth_factory(api, workspace.slug, "owner")
    session = _session_row(account["email"])

    db = _db()
    try:
        row = db.query(AuthSession).filter(AuthSession.id == session.id).one()
        row.last_seen_at = datetime.now(UTC) - timedelta(days=3)
        db.commit()
    finally:
        db.close()

    assert api.get("/api/v1/auth/me").status_code == 401


def test_csrf_token_is_required_for_cookie_mutations(api, auth_factory):
    workspace = _workspace()
    payload = {
        "workspace_id": workspace.slug,
        "name": "CSRF ICP",
        "target_industries": "Technology",
    }
    account = auth_factory(api, workspace.slug, "owner")
    assert api.post("/api/v1/icp/", json=payload).status_code == 201

    valid = api.headers["X-CSRF-Token"]
    api.headers.pop("X-CSRF-Token")
    missing = api.post("/api/v1/icp/", json=payload)
    assert missing.status_code == 403
    assert "csrf" in missing.json()["detail"].lower()

    api.headers["X-CSRF-Token"] = "definitely-not-the-token"
    assert api.post("/api/v1/icp/", json=payload).status_code == 403

    api.headers["X-CSRF-Token"] = valid
    assert api.post("/api/v1/icp/", json=payload).status_code == 201
    assert account["csrf_token"] == valid


def test_bearer_token_is_accepted_without_csrf(auth_factory):
    workspace = _workspace()
    with TestClient(app) as browser:
        account = auth_factory(browser, workspace.slug, "owner")
        token = browser.cookies.get("prospect_session")
        assert token

    with TestClient(app) as script:
        script.headers["Authorization"] = f"Bearer {token}"
        response = script.post(
            "/api/v1/icp/",
            json={
                "workspace_id": workspace.slug,
                "name": "Bearer ICP",
                "target_industries": "Technology",
            },
        )
        assert response.status_code == 201, response.text
        assert script.get("/api/v1/auth/me").status_code == 200
        assert account["email"]


def test_login_is_rate_limited(api):
    email = _unique("throttle") + "@example.test"
    for _ in range(5):
        response = api.post(
            "/api/v1/auth/login", json={"email": email, "password": "WrongPassword123"}
        )
        assert response.status_code == 401
    blocked = api.post(
        "/api/v1/auth/login", json={"email": email, "password": "WrongPassword123"}
    )
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after")


# --------------------------------------------------------------------------- #
# Workspace authorization
# --------------------------------------------------------------------------- #


def test_workspace_slug_cannot_be_used_to_reach_another_tenant(api, auth_factory):
    mine = _tenant_with_batch("mine")
    theirs = _tenant_with_batch("theirs")
    auth_factory(api, mine["workspace_slug"], "owner")

    for path in (
        "/api/v1/prospects/",
        "/api/v1/batches/",
        "/api/v1/icp/",
        "/api/v1/business-profile/",
        "/api/v1/engine/providers",
        "/api/v1/engine/usage",
        "/api/v1/workspaces/",
    ):
        separator = "&" if "?" in path else "?"
        response = api.get(f"{path}{separator}workspace_slug={theirs['workspace_slug']}")
        assert response.status_code == 404, (path, response.status_code)

    # Naming their slug with their resource id also fails.
    response = api.get(
        f"/api/v1/batches/{theirs['batch_id']}?workspace_slug={theirs['workspace_slug']}"
    )
    assert response.status_code == 404


def test_workspace_id_in_request_body_does_not_grant_access(api, auth_factory):
    mine = _tenant_with_batch("mine-body")
    theirs = _tenant_with_batch("theirs-body")
    auth_factory(api, mine["workspace_slug"], "owner")

    batch = api.post(
        "/api/v1/batches/",
        json={
            "workspace_id": theirs["workspace_id"],
            "icp_profile_id": theirs["icp_profile_id"],
            "name": "Cross tenant batch",
        },
    )
    assert batch.status_code == 404

    profile = api.post(
        "/api/v1/business-profile/",
        json={"workspace_id": theirs["workspace_id"], "name": "Cross tenant profile"},
    )
    assert profile.status_code == 404

    icp = api.post(
        "/api/v1/icp/",
        json={"workspace_id": theirs["workspace_id"], "name": "Cross tenant ICP"},
    )
    assert icp.status_code == 404


def test_user_without_membership_cannot_access_a_workspace(api):
    from app.auth.service import create_user

    db = _db()
    try:
        user = create_user(db, _unique("lone") + "@example.test", "CorrectHorseBattery1")
        email = user.email
    finally:
        db.close()

    response = api.post(
        "/api/v1/auth/login", json={"email": email, "password": "CorrectHorseBattery1"}
    )
    assert response.status_code == 200
    assert response.json()["workspaces"] == []
    assert api.get("/api/v1/prospects/").status_code == 404

    tenant = _tenant_with_batch("unrelated")
    response = api.get(f"/api/v1/prospects/?workspace_slug={tenant['workspace_slug']}")
    assert response.status_code == 404


def test_revoked_membership_prevents_access(api, auth_factory):
    mine = _tenant_with_batch("revoked")
    account = auth_factory(api, mine["workspace_slug"], "owner")
    assert api.get(f"/api/v1/prospects/?workspace_slug={mine['workspace_slug']}").status_code == 200

    db = _db()
    try:
        membership = (
            db.query(WorkspaceMembership)
            .filter(
                WorkspaceMembership.user_id == uuid.UUID(account["user_id"]),
                WorkspaceMembership.workspace_id == uuid.UUID(mine["workspace_id"]),
            )
            .one()
        )
        membership.is_active = False
        db.commit()
    finally:
        db.close()

    assert (
        api.get(f"/api/v1/prospects/?workspace_slug={mine['workspace_slug']}").status_code
        == 404
    )
    # The session itself is still valid, it just no longer reaches the tenant.
    me = api.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["workspaces"] == []


def test_viewer_can_read_but_not_mutate(api, auth_factory):
    tenant = _tenant_with_batch("viewer")
    auth_factory(api, tenant["workspace_slug"], "viewer")
    slug = tenant["workspace_slug"]

    assert api.get(f"/api/v1/prospects/?workspace_slug={slug}").status_code == 200
    assert api.get(f"/api/v1/batches/?workspace_slug={slug}").status_code == 200

    create = api.post(
        "/api/v1/icp/", json={"workspace_id": slug, "name": "Viewer ICP"}
    )
    assert create.status_code == 403

    batch = api.post(
        "/api/v1/batches/",
        json={
            "workspace_id": slug,
            "icp_profile_id": tenant["icp_profile_id"],
            "name": "Viewer batch",
        },
    )
    assert batch.status_code == 403

    export = api.get(f"/api/v1/exports/csv/{tenant['batch_id']}?workspace_slug={slug}")
    assert export.status_code == 403

    cancel = api.post(
        f"/api/v1/engine/batches/{tenant['batch_id']}/cancel?workspace_slug={slug}"
    )
    assert cancel.status_code == 403


def test_member_can_run_batches_but_not_manage_members(api, auth_factory):
    tenant = _tenant_with_batch("member")
    auth_factory(api, tenant["workspace_slug"], "member")
    slug = tenant["workspace_slug"]

    # The batch is pending, so cancelling exercises the run permission.
    cancel = api.post(f"/api/v1/engine/batches/{tenant['batch_id']}/cancel?workspace_slug={slug}")
    assert cancel.status_code == 200

    members = api.get(f"/api/v1/workspaces/{slug}/members?workspace_slug={slug}")
    assert members.status_code == 200

    add = api.post(
        f"/api/v1/workspaces/{slug}/members?workspace_slug={slug}",
        json={"email": "someone@example.test", "role": "viewer"},
    )
    assert add.status_code == 403

    settings = api.patch(
        f"/api/v1/workspaces/{slug}?workspace_slug={slug}", json={"name": "Renamed"}
    )
    assert settings.status_code == 403


def test_admin_can_manage_members_but_cannot_grant_owner(api):
    tenant = _tenant_with_batch("admin")
    admin = _membership(uuid.UUID(tenant["workspace_id"]), "admin")
    target = _membership(uuid.UUID(tenant["workspace_id"]), "viewer")

    login = api.post(
        "/api/v1/auth/login", json={"email": admin.email, "password": "CorrectHorseBattery1"}
    )
    assert login.status_code == 200
    api.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    slug = tenant["workspace_slug"]

    add = api.post(
        f"/api/v1/workspaces/{slug}/members",
        json={"email": target.email, "role": "member"},
    )
    assert add.status_code == 409  # already a member

    promote = api.patch(
        f"/api/v1/workspaces/{slug}/members/{target.id}",
        json={"role": "owner"},
    )
    assert promote.status_code == 403

    demote = api.patch(
        f"/api/v1/workspaces/{slug}/members/{target.id}",
        json={"role": "member"},
    )
    assert demote.status_code == 200
    assert demote.json()["role"] == "member"

    rename = api.patch(f"/api/v1/workspaces/{slug}", json={"name": "Admin Renamed"})
    assert rename.status_code == 200


def test_workspace_must_keep_an_owner(api, auth_factory):
    tenant = _tenant_with_batch("lastowner")
    account = auth_factory(api, tenant["workspace_slug"], "owner")
    slug = tenant["workspace_slug"]

    response = api.delete(f"/api/v1/workspaces/{slug}/members/{account['user_id']}")
    assert response.status_code == 400
    assert "owner" in response.json()["detail"].lower()


def test_owner_can_manage_membership_lifecycle(api, auth_factory):
    tenant = _tenant_with_batch("ownerlife")
    auth_factory(api, tenant["workspace_slug"], "owner")
    slug = tenant["workspace_slug"]

    from app.auth.service import create_user

    db = _db()
    try:
        new_user = create_user(db, _unique("invitee") + "@example.test", "CorrectHorseBattery1")
        new_email, new_id = new_user.email, str(new_user.id)
    finally:
        db.close()

    added = api.post(
        f"/api/v1/workspaces/{slug}/members",
        json={"email": new_email, "role": "viewer"},
    )
    assert added.status_code == 201, added.text
    assert added.json()["role"] == "viewer"

    promoted = api.patch(
        f"/api/v1/workspaces/{slug}/members/{new_id}", json={"role": "member"}
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "member"

    removed = api.delete(f"/api/v1/workspaces/{slug}/members/{new_id}")
    assert removed.status_code == 204

    listing = api.get(f"/api/v1/workspaces/{slug}/members")
    revoked = next(item for item in listing.json() if item["user_id"] == new_id)
    assert revoked["is_active"] is False


# --------------------------------------------------------------------------- #
# Resource isolation
# --------------------------------------------------------------------------- #


def test_cross_tenant_resources_are_rejected(api, auth_factory):
    mine = _tenant_with_batch("iso-mine")
    theirs = _tenant_with_batch("iso-theirs")
    auth_factory(api, mine["workspace_slug"], "owner")

    attempts = [
        f"/api/v1/batches/{theirs['batch_id']}",
        f"/api/v1/engine/batches/{theirs['batch_id']}/progress",
        f"/api/v1/engine/batches/{theirs['batch_id']}/qualifications",
        f"/api/v1/prospects/{theirs['prospect_id']}",
        f"/api/v1/engine/prospects/{theirs['prospect_id']}/verification",
        f"/api/v1/engine/companies/{theirs['company_id']}/evidence",
        f"/api/v1/exports/csv/{theirs['batch_id']}",
        f"/api/v1/exports/preview/{theirs['batch_id']}",
        f"/api/v1/business-profile/{theirs['client_profile_id']}",
        f"/api/v1/icp/{theirs['icp_profile_id']}",
    ]
    for path in attempts:
        response = api.get(path)
        assert response.status_code == 404, (path, response.status_code, response.text)

    cancel = api.post(f"/api/v1/engine/batches/{theirs['batch_id']}/cancel")
    assert cancel.status_code == 404

    sheets = api.post(f"/api/v1/exports/google-sheets/{theirs['batch_id']}")
    assert sheets.status_code == 404

    # My own resources still work, so this is isolation rather than a blanket 404.
    assert api.get(f"/api/v1/batches/{mine['batch_id']}").status_code == 200
    assert api.get(f"/api/v1/prospects/{mine['prospect_id']}").status_code == 200


def test_changing_the_workspace_slug_does_not_switch_tenants(api, auth_factory):
    mine = _tenant_with_batch("switch-mine")
    theirs = _tenant_with_batch("switch-theirs")
    auth_factory(api, mine["workspace_slug"], "owner")

    own = api.get(f"/api/v1/prospects/?workspace_slug={mine['workspace_slug']}")
    assert own.status_code == 200
    assert own.json()["total"] == 1

    foreign = api.get(f"/api/v1/prospects/?workspace_slug={theirs['workspace_slug']}")
    assert foreign.status_code == 404

    # No slug at all with a single membership resolves to that membership.
    implicit = api.get("/api/v1/prospects/")
    assert implicit.status_code == 200
    assert implicit.json()["total"] == 1


# --------------------------------------------------------------------------- #
# Background execution
# --------------------------------------------------------------------------- #


def test_authorized_batch_runs_in_background_and_stays_tenant_scoped(api, auth_factory):
    tenant = _tenant_with_batch("bg")
    auth_factory(api, tenant["workspace_slug"], "member")
    slug = tenant["workspace_slug"]

    created = api.post(
        "/api/v1/engine/batches/",
        json={
            "workspace_id": slug,
            "icp_profile_id": tenant["icp_profile_id"],
            "client_profile_id": tenant["client_profile_id"],
            "name": "Background batch",
            "requested_prospect_count": 2,
        },
    )
    assert created.status_code == 201, created.text
    batch_id = created.json()["id"]

    progress = api.get(f"/api/v1/engine/batches/{batch_id}/progress?workspace_slug={slug}")
    assert progress.status_code == 200
    assert progress.json()["batch"]["status"] in ("completed", "failed", "running")

    db = _db()
    try:
        batch = db.query(ProspectBatch).filter(ProspectBatch.id == uuid.UUID(batch_id)).one()
        # The worker persisted the authorized workspace with the job.
        assert str(batch.workspace_id) == tenant["workspace_id"]
        assert batch.status == "completed"
    finally:
        db.close()

    with TestClient(app) as other:
        other_tenant = _tenant_with_batch("bg-other")
        auth_factory(other, other_tenant["workspace_slug"], "owner")
        assert other.get(f"/api/v1/engine/batches/{batch_id}/progress").status_code == 404
        assert other.post(f"/api/v1/engine/batches/{batch_id}/cancel").status_code == 404


def test_worker_refuses_a_mismatched_workspace_reference():
    from app.engine.orchestrator import run_engine_pipeline

    tenant = _tenant_with_batch("worker")
    db = _db()
    try:
        before = (
            db.query(ProspectBatch)
            .filter(ProspectBatch.id == uuid.UUID(tenant["batch_id"]))
            .one()
            .status
        )
    finally:
        db.close()

    run_engine_pipeline(tenant["batch_id"], "some-other-workspace")

    db = _db()
    try:
        after = (
            db.query(ProspectBatch)
            .filter(ProspectBatch.id == uuid.UUID(tenant["batch_id"]))
            .one()
            .status
        )
        prospects = (
            db.query(Prospect)
            .filter(Prospect.batch_id == uuid.UUID(tenant["batch_id"]))
            .count()
        )
    finally:
        db.close()
    assert after == before == "pending"
    assert prospects == 1


# --------------------------------------------------------------------------- #
# Regression guards
# --------------------------------------------------------------------------- #


def test_csv_contract_and_synthetic_exclusion_are_unchanged(api, auth_factory):
    import csv
    import io

    tenant = _tenant_with_batch("csv")
    auth_factory(api, tenant["workspace_slug"], "owner")
    slug = tenant["workspace_slug"]

    # The only prospect is synthetic-only and not outreach ready.
    default_export = api.get(f"/api/v1/exports/csv/{tenant['batch_id']}?workspace_slug={slug}")
    assert default_export.status_code == 404

    full_export = api.get(
        f"/api/v1/exports/csv/{tenant['batch_id']}?workspace_slug={slug}&include_all=true"
    )
    assert full_export.status_code == 200
    reader = csv.DictReader(io.StringIO(full_export.text))
    assert reader.fieldnames == EXPORT_COLUMNS
    rows = list(reader)
    assert rows and all(row["status"] == "new" for row in rows)
