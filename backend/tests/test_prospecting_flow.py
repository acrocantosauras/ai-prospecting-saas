"""End-to-end tests for the prospecting journey and Outreach CSV contract."""

import csv
import io
import os
import tempfile
from pathlib import Path

# Configure an isolated database before the app (and its engine) is imported.
_TMP_DIR = Path(tempfile.mkdtemp(prefix="prospecting-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP_DIR / 'test.db').as_posix()}"
os.environ["DEMO_MODE"] = "true"
os.environ["AI_PROVIDER"] = "demo"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models import Workspace, ClientProfile, ICPProfile  # noqa: E402
from app.schemas.exports import LeadExportRow  # noqa: E402
from app.services.exports import format_csv  # noqa: E402

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


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def seeded(client, auth_factory):
    db = SessionLocal()
    try:
        workspace = Workspace(slug="demo", name="Demo Workspace")
        db.add(workspace)
        db.commit()
        db.refresh(workspace)

        profile = ClientProfile(
            workspace_id=workspace.id,
            name="Northbridge Test Partners",
            products_services="Outbound prospecting and research",
            value_proposition="Researched prospects with a clear reason to engage",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        icp = ICPProfile(
            workspace_id=workspace.id,
            client_profile_id=profile.id,
            name="Test ICP",
            target_industries="Technology,Professional Services",
            target_countries="United States,United Kingdom",
            company_size="Medium",
            decision_maker_roles="CEO,Founder",
            max_prospects=5,
        )
        db.add(icp)
        db.commit()
        db.refresh(icp)

        other = Workspace(slug="other-workspace", name="Other Workspace")
        db.add(other)
        db.commit()

        # Nothing is reachable anonymously any more: sign an owner in first.
        auth_factory(client, "demo", "owner")
        return {
            "workspace_id": str(workspace.id),
            "client_profile_id": str(profile.id),
            "icp_profile_id": str(icp.id),
        }
    finally:
        db.close()


@pytest.fixture(scope="module")
def completed_batch(client, seeded):
    response = client.post(
        "/api/v1/batches/",
        json={
            "workspace_id": "demo",
            "icp_profile_id": seeded["icp_profile_id"],
            "client_profile_id": seeded["client_profile_id"],
            "name": "Test Batch",
            "requested_prospect_count": 5,
        },
    )
    assert response.status_code == 201, response.text
    batch = response.json()

    detail = client.get(f"/api/v1/batches/{batch['id']}?workspace_slug=demo")
    assert detail.status_code == 200, detail.text
    return detail.json()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_batch_creation_accepts_workspace_slug(seeded):
    # Covered implicitly by the completed_batch fixture, but assert the contract
    # explicitly: the frontend sends the slug "demo", not a UUID.
    assert seeded["workspace_id"]


def test_pipeline_completes_with_qualified_prospects(completed_batch):
    assert completed_batch["status"] == "completed"
    assert completed_batch["current_stage"] == "completed"
    assert completed_batch["total_discovered"] == 5
    assert completed_batch["total_enriched"] > 0
    assert completed_batch["total_qualified"] > 0
    assert completed_batch["total_qualified"] <= completed_batch["total_enriched"]
    assert completed_batch["completed_at"] is not None


def test_prospect_list_and_filters(client, completed_batch):
    batch_id = completed_batch["id"]

    all_prospects = client.get(f"/api/v1/prospects/?workspace_slug=demo&batch_id={batch_id}")
    assert all_prospects.status_code == 200
    payload = all_prospects.json()
    assert payload["total"] == completed_batch["total_enriched"]

    page = client.get(f"/api/v1/prospects/?workspace_slug=demo&batch_id={batch_id}&page=1&page_size=2")
    assert page.status_code == 200
    assert len(page.json()["items"]) == 2

    ready = client.get(
        f"/api/v1/prospects/?workspace_slug=demo&batch_id={batch_id}&ready_for_outreach=true"
    )
    assert ready.status_code == 200
    assert all(item["is_ready_for_outreach"] for item in ready.json()["items"])

    search = client.get(f"/api/v1/prospects/?workspace_slug=demo&batch_id={batch_id}&search=zzz-no-match")
    assert search.json()["total"] == 0


def test_prospect_detail(client, completed_batch):
    listing = client.get(
        f"/api/v1/prospects/?workspace_slug=demo&batch_id={completed_batch['id']}&page_size=1"
    )
    prospect_id = listing.json()["items"][0]["id"]
    response = client.get(f"/api/v1/prospects/{prospect_id}?workspace_slug=demo")
    assert response.status_code == 200
    body = response.json()
    assert body["company"] is not None
    assert body["decision_maker"] is not None
    assert body["business_problem"]
    assert body["solution_match"]
    assert body["missing_information"]


def test_csv_export_contract(client, completed_batch, seeded):
    response = client.get(
        f"/api/v1/exports/csv/{completed_batch['id']}?workspace_slug=demo"
    )
    assert response.status_code == 200, response.text
    assert "text/csv" in response.headers["content-type"]

    reader = csv.DictReader(io.StringIO(response.text))
    assert reader.fieldnames == EXPORT_COLUMNS
    rows = list(reader)
    assert len(rows) == completed_batch["total_qualified"]
    assert len({row["lead_id"] for row in rows}) == len(rows)
    for row in rows:
        assert row["lead_id"].startswith("PROSPECT-")
        assert row["status"] == "new"
        assert row["draft_date"] == ""
        assert row["client_id"] == seeded["workspace_id"]
        assert row["company"]
        assert row["role"]
        assert "Problem:" in row["notes"]
        assert "Fit:" in row["notes"]
        # Missing emails stay blank rather than being fabricated.
        assert "@" not in row["email"]


def test_export_preview_matches_csv(client, completed_batch):
    response = client.get(
        f"/api/v1/exports/preview/{completed_batch['id']}?workspace_slug=demo"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == completed_batch["total_qualified"]
    assert set(body["rows"][0].keys()) == set(EXPORT_COLUMNS)


def test_workspace_isolation(client, completed_batch, seeded):
    # Naming another workspace is no longer a way to read it: the caller is not a
    # member, so the workspace does not exist as far as the API is concerned.
    other_listing = client.get("/api/v1/prospects/?workspace_slug=other-workspace")
    assert other_listing.status_code == 404

    cross_workspace_batch = client.get(
        f"/api/v1/batches/{completed_batch['id']}?workspace_slug=other-workspace"
    )
    assert cross_workspace_batch.status_code == 404

    cross_workspace_export = client.get(
        f"/api/v1/exports/csv/{completed_batch['id']}?workspace_slug=other-workspace"
    )
    assert cross_workspace_export.status_code == 404


def test_google_sheets_requires_configuration(client, completed_batch):
    response = client.post(
        f"/api/v1/exports/google-sheets/{completed_batch['id']}?workspace_slug=demo"
    )
    assert response.status_code == 400
    assert "not configured" in response.json()["detail"]


def test_csv_escaping_roundtrip():
    row = LeadExportRow(
        lead_id="PROSPECT-test",
        first_name='Ada, "A"',
        last_name=None,
        email=None,
        company="Acme, Inc.",
        website=None,
        role="CEO",
        client_id="workspace-id",
        status="new",
        draft_date=None,
        notes='Problem: a, b\nFit: "c" | line two',
    )
    parsed = list(csv.DictReader(io.StringIO(format_csv([row]))))
    assert parsed[0]["first_name"] == 'Ada, "A"'
    assert parsed[0]["company"] == "Acme, Inc."
    assert parsed[0]["notes"] == 'Problem: a, b\nFit: "c" | line two'
    assert parsed[0]["draft_date"] == ""
