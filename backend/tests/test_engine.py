"""Tests for the provider-independent prospecting engine.

Everything here is deterministic: no network calls, no real credentials and no
sleep-based retries (the runner accepts an injected sleeper).
"""

import csv
import io
import os
import tempfile
import time
import uuid
from pathlib import Path

# Configure an isolated database and force safe provider defaults before the app
# (and database module) is imported. Empty search keys guarantee that a
# real-mode request cannot accidentally call a live API.
_TMP_DIR = Path(tempfile.mkdtemp(prefix="engine-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP_DIR / 'engine.db').as_posix()}"
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("AI_PROVIDER", "demo")
os.environ["PROSPECTING_MODE"] = "demo"
os.environ["TAVILY_API_KEY"] = ""
os.environ["SERPER_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.config.settings import Settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.migrations import apply_additive_migrations  # noqa: E402
from app.engine.analysis import LLMAnalyzer  # noqa: E402
from app.engine.contracts import (  # noqa: E402
    CompanyCandidate,
    CompanyResearch,
    DecisionMakerCandidate,
    DiscoveryRequest,
    ICPQuery,
    ProblemFitAnalysis,
    ProviderDescriptor,
    SourceRef,
    VerificationResult,
)
from app.engine.dedup import find_company_duplicate  # noqa: E402
from app.engine.errors import (  # noqa: E402
    BudgetExceeded,
    EvidenceValidationError,
    ProviderNotConfigured,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.engine.evidence import is_plausible_source_url, sanitize_sources  # noqa: E402
from app.engine.execution import ProviderRunner, RetryPolicy, UsageMeter  # noqa: E402
from app.engine.orchestrator import run_engine_pipeline  # noqa: E402
from app.engine.providers.dns_verifier import (  # noqa: E402
    DnsEmailVerificationProvider,
    DomainLookup,
)
from app.engine.providers.search_api import SearchApiProvider  # noqa: E402
from app.engine.qualification import (  # noqa: E402
    DecisionMakerAssessment,
    QualificationInput,
    QualificationPolicy,
    evaluate,
)
from app.engine.registry import build_provider_bundle  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    ClientProfile,
    Company,
    ICPProfile,
    Prospect,
    ProspectBatch,
    VerificationRecord,
    Workspace,
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


def test_additive_migration_preserves_existing_rows(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE prospects (id VARCHAR(36) PRIMARY KEY, email VARCHAR(512))")
        )
        connection.execute(
            text("INSERT INTO prospects (id, email) VALUES ('p1', 'legacy@example.com')")
        )

    applied = apply_additive_migrations(engine)
    assert "prospects.qualification_status" in applied
    columns = {
        column["name"] for column in inspect(engine).get_columns("prospects")
    }
    assert {
        "qualification_status",
        "qualification_confidence",
        "evidence_urls",
        "synthetic",
    } <= columns
    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT email FROM prospects WHERE id = 'p1'")
        ).one()
    assert row[0] == "legacy@example.com"

    # Idempotent: a second startup applies nothing.
    assert apply_additive_migrations(engine) == []


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def seeded(client, auth_factory):
    db = SessionLocal()
    try:
        workspace = Workspace(slug="engine-ws", name="Engine Workspace")
        other = Workspace(slug="engine-other", name="Engine Other Workspace")
        db.add_all([workspace, other])
        db.commit()
        db.refresh(workspace)
        db.refresh(other)

        profile = ClientProfile(
            workspace_id=workspace.id,
            name="Engine Test Client",
            products_services="Workflow automation platform",
            value_proposition="Automate manual operational tracking",
            problems_solved="Manual tracking and reporting",
            target_audience="Operations leaders",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        other_profile = ClientProfile(
            workspace_id=other.id,
            name="Other Tenant Client",
            products_services="Other tenant secret offering",
        )
        db.add(other_profile)
        db.commit()
        db.refresh(other_profile)

        icp = ICPProfile(
            workspace_id=workspace.id,
            client_profile_id=profile.id,
            name="Engine Test ICP",
            target_industries="Technology",
            target_countries="United States",
            company_size="Medium",
            decision_maker_roles="CEO,Founder",
            max_prospects=4,
        )
        db.add(icp)
        db.commit()
        db.refresh(icp)

        # Every engine endpoint requires an authenticated workspace member;
        # the factory signs a real owner in through /api/v1/auth/login.
        auth_factory(client, "engine-ws", "owner")
        return {
            "workspace_id": str(workspace.id),
            "other_workspace_id": str(other.id),
            "workspace_slug": workspace.slug,
            "other_slug": other.slug,
            "client_profile_id": str(profile.id),
            "other_client_profile_id": str(other_profile.id),
            "icp_profile_id": str(icp.id),
        }
    finally:
        db.close()


@pytest.fixture(scope="module")
def demo_batch(client, seeded):
    response = client.post(
        "/api/v1/engine/batches/",
        json={
            "workspace_id": "engine-ws",
            "icp_profile_id": seeded["icp_profile_id"],
            "client_profile_id": seeded["client_profile_id"],
            "name": "Engine demo batch",
            "requested_prospect_count": 4,
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()
    # The POST response is serialized before background tasks execute, so read
    # the authoritative state back from the progress endpoint.
    progress = client.get(
        f"/api/v1/engine/batches/{created['id']}/progress?workspace_slug=engine-ws"
    )
    assert progress.status_code == 200, progress.text
    payload = progress.json()
    return {**payload["batch"], "_progress": payload}


# --------------------------------------------------------------------------- #
# End-to-end engine batch (demo provider)
# --------------------------------------------------------------------------- #


def test_engine_batch_completes_with_stage_progress(client, demo_batch):
    assert demo_batch["status"] == "completed"
    assert demo_batch["current_stage"] == "completed"
    assert demo_batch["source_mode"] == "demo"
    assert demo_batch["total_qualified"] > 0

    body = demo_batch["_progress"]
    assert body["progress_percent"] == 100.0
    stages = {stage["stage"]: stage["status"] for stage in body["stages"]}
    assert stages["icp_validation"] == "completed"
    assert stages["company_discovery"] == "completed"
    assert stages["company_dedup"] == "completed"
    assert stages["final_qualification"] == "completed"
    assert body["qualified_companies"] > 0
    assert body["usage"]["total_cost_usd"] == 0.0
    assert body["usage"]["budget_usd"] is not None


def test_engine_batch_labels_demo_results_as_illustrative(client, demo_batch):
    response = client.get(
        f"/api/v1/prospects/?workspace_slug=engine-ws&batch_id={demo_batch['id']}"
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == demo_batch["total_qualified"]
    for item in items:
        assert item["qualification_status"] == "qualified_illustrative"
        assert item["synthetic"] is True
        assert "synthetic demo" in (item["research_confidence"] or "")
        assert item["business_problem"]
        assert item["solution_match"]
        assert item["missing_information"]
        assert item["email"] is None
        assert item["is_ready_for_outreach"] is False


def test_engine_verification_never_claims_unproven_verification(client, demo_batch):
    listing = client.get(
        f"/api/v1/prospects/?workspace_slug=engine-ws&batch_id={demo_batch['id']}&page_size=1"
    )
    prospect_id = listing.json()["items"][0]["id"]
    response = client.get(
        f"/api/v1/engine/prospects/{prospect_id}/verification?workspace_slug=engine-ws"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email_verified"] is False
    assert body["verification"]
    assert all(row["status"] != "verified" for row in body["verification"])
    assert any("email not verified" in item for item in body["missing_information"])

    db = SessionLocal()
    try:
        rows = (
            db.query(VerificationRecord)
            .join(Prospect, VerificationRecord.prospect_id == Prospect.id)
            .filter(Prospect.batch_id == uuid.UUID(demo_batch["id"]))
            .all()
        )
        assert rows
        assert all(row.status != "verified" for row in rows)
        assert all(row.email is None for row in rows)
    finally:
        db.close()


def test_engine_qualifications_expose_gates_and_policy(client, demo_batch):
    response = client.get(
        f"/api/v1/engine/batches/{demo_batch['id']}/qualifications"
        "?workspace_slug=engine-ws&scope=company"
    )
    assert response.status_code == 200, response.text
    items = response.json()
    assert items
    for item in items:
        assert item["status"] in ("qualified_illustrative", "rejected", "recheck_later")
        assert item["policy"]["mode"] == "demo"
        assert item["policy"]["allow_unverified_emails"] is True
        gates = {gate["name"]: gate for gate in item["gates"]}
        assert gates["verified_emails"]["relaxed"] is True
        assert "verified business email" in " ".join(item["missing"]).lower()


def test_engine_illustrative_rows_are_excluded_from_default_export(
    client, demo_batch, seeded
):
    # Default export is the production path: illustrative/demo rows must not
    # enter it silently.
    excluded = client.get(
        f"/api/v1/exports/csv/{demo_batch['id']}?workspace_slug=engine-ws"
    )
    assert excluded.status_code == 404

    response = client.get(
        f"/api/v1/exports/csv/{demo_batch['id']}?workspace_slug=engine-ws&include_all=true"
    )
    assert response.status_code == 200, response.text
    reader = csv.DictReader(io.StringIO(response.text))
    assert reader.fieldnames == EXPORT_COLUMNS
    rows = list(reader)
    assert len(rows) == demo_batch["total_qualified"]
    for row in rows:
        assert row["lead_id"].startswith("PROSPECT-")
        assert row["client_id"] == seeded["workspace_id"]
        assert row["status"] == "new"
        assert "Problem:" in row["notes"]
        assert "Fit:" in row["notes"]
        assert row["email"] == ""


def test_engine_tenant_isolation(client, demo_batch):
    other = client.get(
        f"/api/v1/engine/batches/{demo_batch['id']}/progress?workspace_slug=engine-other"
    )
    assert other.status_code == 404

    other_qualifications = client.get(
        f"/api/v1/engine/batches/{demo_batch['id']}/qualifications"
        "?workspace_slug=engine-other"
    )
    assert other_qualifications.status_code == 404

    listing = client.get(
        f"/api/v1/prospects/?workspace_slug=engine-ws&batch_id={demo_batch['id']}&page_size=1"
    )
    prospect_id = listing.json()["items"][0]["id"]
    cross = client.get(
        f"/api/v1/engine/prospects/{prospect_id}/verification?workspace_slug=engine-other"
    )
    assert cross.status_code == 404


def test_second_batch_deduplicates_against_workspace_history(client, seeded, demo_batch):
    response = client.post(
        "/api/v1/engine/batches/",
        json={
            "workspace_id": "engine-ws",
            "icp_profile_id": seeded["icp_profile_id"],
            "name": "Engine duplicate batch",
            "requested_prospect_count": 2,
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()
    progress = client.get(
        f"/api/v1/engine/batches/{created['id']}/progress?workspace_slug=engine-ws"
    )
    assert progress.status_code == 200, progress.text
    payload = progress.json()
    batch = payload["batch"]
    assert batch["status"] == "completed"
    # Repeated companies are rejected rather than re-qualified.
    assert batch["total_rejected"] >= 1
    assert batch["total_discovered_companies"] < batch["total_discovered"]

    first_batch_companies = {
        item["company_name"]
        for item in client.get(
            f"/api/v1/prospects/?workspace_slug=engine-ws&batch_id={demo_batch['id']}"
        ).json()["items"]
    }
    second_batch = client.get(
        f"/api/v1/prospects/?workspace_slug=engine-ws&batch_id={batch['id']}"
    ).json()
    for item in second_batch["items"]:
        assert item["company_name"] not in first_batch_companies

    # No company/person pair is ever stored twice for this workspace.
    db = SessionLocal()
    try:
        rows = (
            db.query(Prospect.company_name, Prospect.full_name)
            .join(ProspectBatch, Prospect.batch_id == ProspectBatch.id)
            .filter(ProspectBatch.workspace_id == uuid.UUID(seeded["workspace_id"]))
            .all()
        )
        assert len(rows) == len({(company, person) for company, person in rows})
    finally:
        db.close()


def test_engine_rerun_is_idempotent(client, demo_batch):
    db = SessionLocal()
    try:
        before = (
            db.query(Prospect)
            .filter(Prospect.batch_id == uuid.UUID(demo_batch["id"]))
            .count()
        )
    finally:
        db.close()
    run_engine_pipeline(demo_batch["id"], "engine-ws")
    db = SessionLocal()
    try:
        after = (
            db.query(Prospect)
            .filter(Prospect.batch_id == uuid.UUID(demo_batch["id"]))
            .count()
        )
    finally:
        db.close()
    assert after == before


def test_completed_batch_cannot_be_cancelled(client, demo_batch):
    response = client.post(
        f"/api/v1/engine/batches/{demo_batch['id']}/cancel?workspace_slug=engine-ws"
    )
    assert response.status_code == 400


def test_real_mode_requires_configured_search_api(client, seeded):
    response = client.post(
        "/api/v1/engine/batches/",
        json={
            "workspace_id": "engine-ws",
            "icp_profile_id": seeded["icp_profile_id"],
            "name": "Real batch without credentials",
            "requested_prospect_count": 5,
            "mode": "real",
        },
    )
    assert response.status_code == 400
    assert "not configured" in response.json()["detail"].lower()


def test_provider_overview_reports_capabilities(client, seeded):
    response = client.get("/api/v1/engine/providers?workspace_slug=engine-ws")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "demo"
    assert body["policy"]["mode"] == "demo"
    assert body["policy"]["allow_unverified_emails"] is True
    by_capability = {item["capability"]: item for item in body["providers"]}
    assert by_capability["company_discovery"]["state"] == "ready"
    assert by_capability["company_discovery"]["synthetic"] is True
    assert by_capability["email_verification"]["available"] is True


# --------------------------------------------------------------------------- #
# Provider configuration, contracts and resilience
# --------------------------------------------------------------------------- #


def test_real_bundle_reports_missing_credentials_without_network():
    settings = Settings(
        _env_file=None,
        prospecting_mode="real",
        tavily_api_key="",
        serper_api_key="",
    )
    bundle = build_provider_bundle(settings, mode="real")
    discovery = bundle.discovery.status()
    assert discovery.state == "not_configured"
    assert not discovery.available
    assert "TAVILY_API_KEY" in (discovery.detail or "")
    assert bundle.decision_makers.status().state == "not_configured"
    assert bundle.enrichment.status().state == "not_configured"
    assert bundle.verification.status().state == "ready"
    with pytest.raises(ProviderNotConfigured):
        bundle.discovery.discover(
            DiscoveryRequest(icp=ICPQuery(industries=["Technology"]), limit=5)
        )


def test_search_provider_requires_api_key():
    with pytest.raises(ProviderNotConfigured):
        SearchApiProvider(provider="tavily", api_key="")
    with pytest.raises(ProviderNotConfigured):
        SearchApiProvider(provider="unknown", api_key="key")


def test_verification_contract_refuses_unproven_verified_status():
    with pytest.raises(ValidationError):
        VerificationResult(
            provider="dns",
            email="a@acme.com",
            status="verified",
            method="dns_mx",
            confidence=0.99,
        )
    with pytest.raises(ValidationError):
        VerificationResult(
            provider="demo",
            email="a@acme.com",
            status="verified",
            method="verification_api",
            confidence=0.99,
            synthetic=True,
        )
    result = VerificationResult(
        provider="api",
        email="a@acme.com",
        status="verified",
        method="verification_api",
        confidence=0.95,
    )
    assert result.status == "verified"


def test_dns_verifier_never_returns_verified():
    provider = DnsEmailVerificationProvider(
        resolver=lambda domain: DomainLookup(True, True, "MX present")
    )
    result = provider.verify("person@acme.com")
    assert result.status == "unknown"
    assert result.method == "dns_mx"

    missing = DnsEmailVerificationProvider(
        resolver=lambda domain: DomainLookup(False, None, "NXDOMAIN")
    )
    assert missing.verify("person@nowhere-xyz.com").status == "not_found"

    assert provider.verify("not-an-email").status == "invalid"


def test_evidence_rejects_unusable_sources():
    assert is_plausible_source_url("https://acme.com/about") is True
    assert is_plausible_source_url("javascript:alert(1)") is False
    assert is_plausible_source_url("https://example.com/about") is False
    assert is_plausible_source_url("https://localhost/admin") is False

    source = SourceRef(url="https://acme.com/about", title="About", verified=True)
    duplicate = SourceRef(url="https://acme.com/about/", title="About again", verified=True)
    assert len(sanitize_sources([source, duplicate])) == 1


class _CountingProvider(ProviderDescriptor):
    name = "flaky"
    capability = "company_discovery"

    def __init__(self):
        self.calls = 0


def test_provider_runner_retries_without_sleeping_for_real():
    provider = _CountingProvider()

    def call():
        provider.calls += 1
        if provider.calls < 3:
            raise ProviderUnavailable("temporary outage")
        return "ok"

    meter = UsageMeter()
    runner = ProviderRunner(
        retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.0, timeout_seconds=1.0),
        meter=meter,
        sleeper=lambda _: None,
    )
    assert runner.run(provider, "discover", call) == "ok"
    assert provider.calls == 3
    assert len(meter.events) == 3
    assert meter.events[-1].success is True


def test_provider_runner_stops_after_max_attempts():
    provider = _CountingProvider()

    def call():
        provider.calls += 1
        raise ProviderUnavailable("still down")

    runner = ProviderRunner(
        retry=RetryPolicy(max_attempts=2, base_delay_seconds=0.0, timeout_seconds=1.0),
        meter=UsageMeter(),
        sleeper=lambda _: None,
    )
    with pytest.raises(ProviderUnavailable):
        runner.run(provider, "discover", call)
    assert provider.calls == 2


def test_provider_runner_enforces_timeout():
    provider = _CountingProvider()
    runner = ProviderRunner(
        retry=RetryPolicy(max_attempts=1, timeout_seconds=0.05),
        meter=UsageMeter(),
        sleeper=lambda _: None,
    )
    with pytest.raises(ProviderTimeout):
        runner.run(provider, "research", lambda: time.sleep(0.3))


def test_budget_guard_blocks_further_spend():
    meter = UsageMeter(max_cost_usd=0.0)
    with pytest.raises(BudgetExceeded):
        meter.check_budget()


# --------------------------------------------------------------------------- #
# Qualification gates
# --------------------------------------------------------------------------- #


def _candidate() -> CompanyCandidate:
    return CompanyCandidate(
        name="Acme Widgets Inc",
        website="https://acme.com",
        industry="Technology",
        location="Austin, United States",
        country="United States",
    )


def _research() -> CompanyResearch:
    source = SourceRef(
        url="https://acme.com/about",
        title="About Acme",
        snippet="Acme builds widget tracking tools",
        verified=True,
    )
    return CompanyResearch(
        provider="test_search",
        what_it_does="Acme builds widget tracking tools",
        what_it_sells="Widget tracking software",
        who_it_serves="Manufacturers",
        observable_signals=["first-party page: About Acme"],
        evidence=[source],
        confidence=0.6,
    )


def _analysis(
    url: str = "https://acme.com/about", fit_confidence: float = 0.6
) -> ProblemFitAnalysis:
    return ProblemFitAnalysis(
        problem="Manual widget tracking slows fulfilment",
        problem_inference="Inferred from the About page describing manual processes.",
        problem_confidence=0.5,
        fit_explanation=(
            "The client's workflow automation platform addresses the manual tracking "
            "problem described on the company site."
        ),
        offering_reference="Workflow automation platform",
        fit_confidence=fit_confidence,
        evidence_urls=[url],
        analyzer="test",
    )


def _icp() -> ICPQuery:
    return ICPQuery(
        industries=["Technology"],
        countries=["United States"],
        decision_maker_roles=["CEO"],
    )


def _dm(index: int = 0) -> DecisionMakerCandidate:
    name = "Ada Lovelace" if index == 0 else "Grace Hopper"
    return DecisionMakerCandidate(
        full_name=name,
        job_title="CEO" if index == 0 else "CTO",
        linkedin_url=f"https://www.linkedin.com/in/{name.lower().replace(' ', '-')}",
        profile_source="search",
        source_url="https://acme.com/team",
    )


def _verified(email: str = "ada@acme.com") -> VerificationResult:
    return VerificationResult(
        provider="test_api",
        email=email,
        status="verified",
        method="verification_api",
        confidence=0.95,
    )


def _unverified(email: str = "grace@acme.com") -> VerificationResult:
    return VerificationResult(
        provider="dns",
        email=email,
        status="unknown",
        method="dns_mx",
        confidence=0.2,
    )


def test_qualification_accepts_fully_supported_company():
    data = QualificationInput(
        candidate=_candidate(),
        research=_research(),
        decision_makers=[
            DecisionMakerAssessment(_dm(0), _verified("ada@acme.com")),
            DecisionMakerAssessment(_dm(1), _verified("grace@acme.com")),
        ],
        analysis=_analysis(),
        icp=_icp(),
    )
    outcome = evaluate(data, QualificationPolicy(mode="real"))
    assert outcome.status == "qualified"
    assert outcome.score == 100.0
    assert outcome.gate("verified_emails") is not None
    assert outcome.gate("verified_emails").passed is True


def test_qualification_requires_two_verified_decision_makers():
    only_one = QualificationInput(
        candidate=_candidate(),
        research=_research(),
        decision_makers=[DecisionMakerAssessment(_dm(0), _verified())],
        analysis=_analysis(),
        icp=_icp(),
    )
    outcome = evaluate(only_one, QualificationPolicy(mode="real"))
    assert outcome.status == "rejected"
    count_gate = outcome.gate("decision_maker_count")
    assert count_gate is not None and count_gate.passed is False

    unverified_second = QualificationInput(
        candidate=_candidate(),
        research=_research(),
        decision_makers=[
            DecisionMakerAssessment(_dm(0), _verified("ada@acme.com")),
            DecisionMakerAssessment(_dm(1), _unverified("grace@acme.com")),
        ],
        analysis=_analysis(),
        icp=_icp(),
    )
    rejected = evaluate(unverified_second, QualificationPolicy(mode="real"))
    assert rejected.status == "rejected"
    email_gate = rejected.gate("verified_emails")
    assert email_gate is not None and email_gate.passed is False
    assert "verified business email" in (email_gate.missing or "")


def test_qualification_rejects_citations_that_were_not_retrieved():
    data = QualificationInput(
        candidate=_candidate(),
        research=_research(),
        decision_makers=[
            DecisionMakerAssessment(_dm(0), _verified("ada@acme.com")),
            DecisionMakerAssessment(_dm(1), _verified("grace@acme.com")),
        ],
        analysis=_analysis("https://invented-source.example.org/post"),
        icp=_icp(),
    )
    outcome = evaluate(data, QualificationPolicy(mode="real"))
    assert outcome.status == "rejected"
    gate = outcome.gate("problem_evidence")
    assert gate is not None and gate.passed is False
    assert "not retrieved" in gate.reason


def test_llm_analyzer_rejects_invented_sources():
    class InventedSourceLLM:
        def analyze(self, prompt, schema, system=None):
            return _analysis("https://invented-source.example.org/post")

    with pytest.raises(EvidenceValidationError):
        LLMAnalyzer(InventedSourceLLM()).analyze(
            company=_candidate(),
            research=_research(),
            icp=_icp(),
            client_context={"products_services": "Workflow automation platform"},
        )


def test_real_mode_policy_cannot_be_relaxed():
    settings = Settings(_env_file=None, prospecting_mode="real")
    policy = QualificationPolicy.from_settings(settings, "real")
    assert policy.allow_unverified_emails is False
    assert policy.allow_missing_sources is False
    demo = QualificationPolicy.from_settings(
        Settings(_env_file=None, prospecting_mode="demo"), "demo"
    )
    assert demo.allow_unverified_emails is True


# --------------------------------------------------------------------------- #
# Deduplication and normalization
# --------------------------------------------------------------------------- #


def test_company_dedup_is_tenant_scoped(seeded):
    db = SessionLocal()
    try:
        workspace = db.query(Workspace).filter(Workspace.slug == "engine-ws").one()
        other = db.query(Workspace).filter(Workspace.slug == "engine-other").one()
        icp = (
            db.query(ICPProfile)
            .filter(ICPProfile.workspace_id == workspace.id)
            .first()
        )
        batch = ProspectBatch(
            workspace_id=workspace.id,
            icp_profile_id=icp.id,
            name="Dedup fixture batch",
            source_mode="demo",
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)
        db.add(
            Company(
                batch_id=batch.id,
                name="Acme Widgets Inc",
                website="https://acme-widgets.com",
                domain="acme-widgets.com",
                normalized_name="acme widgets",
            )
        )
        db.commit()

        candidate = CompanyCandidate(
            name="Acme Widgets, LLC",
            website="https://www.acme-widgets.com/about",
        )
        within_workspace = find_company_duplicate(db, workspace.id, candidate)
        assert within_workspace.is_duplicate is True
        assert within_workspace.matched_on == "domain"

        other_workspace = find_company_duplicate(db, other.id, candidate)
        assert other_workspace.is_duplicate is False
    finally:
        db.close()
