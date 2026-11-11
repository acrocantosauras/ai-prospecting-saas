"""Hardening tests: tenant isolation, SSRF-style URL rejection, search parsing.

Self-contained (own workspace) so it can run alone or alongside the main engine
suite without depending on another module's fixtures.
"""

import os
import tempfile
import time
import uuid
from pathlib import Path

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{(Path(tempfile.mkdtemp(prefix='hardening-tests-')) / 'h.db').as_posix()}",
)
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("AI_PROVIDER", "demo")
os.environ["PROSPECTING_MODE"] = "demo"
os.environ["TAVILY_API_KEY"] = ""
os.environ["SERPER_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.engine.contracts import (  # noqa: E402
    CompanyCandidate,
    CompanyResearch,
    DecisionMakerCandidate,
    ICPQuery,
    ProblemFitAnalysis,
    SourceRef,
    VerificationResult,
)
from app.engine.errors import ProviderResponseError, ProviderTimeout  # noqa: E402
from app.engine.evidence import is_plausible_source_url  # noqa: E402
from app.engine.execution import ProviderRunner, RetryPolicy, UsageMeter  # noqa: E402
from app.engine.orchestrator import run_engine_pipeline  # noqa: E402
from app.engine.providers.dns_verifier import (  # noqa: E402
    DnsEmailVerificationProvider,
    DomainLookup,
)
from app.engine.providers.search_api import (  # noqa: E402
    _parse_hits,
    _source_ref,
)
from app.engine.qualification import (  # noqa: E402
    DecisionMakerAssessment,
    QualificationInput,
    QualificationPolicy,
    evaluate,
)
from app.engine.safe_http import UnsafeUrlError, safe_request  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    ClientProfile,
    ICPProfile,
    Prospect,
    ProspectBatch,
    Workspace,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def seeded(client, auth_factory):
    db = SessionLocal()
    try:
        workspace = Workspace(slug="hardening-ws", name="Hardening Workspace")
        other = Workspace(slug="hardening-other", name="Hardening Other")
        db.add_all([workspace, other])
        db.commit()
        db.refresh(workspace)
        db.refresh(other)

        profile = ClientProfile(
            workspace_id=workspace.id,
            name="Hardening Client",
            products_services="Workflow automation platform",
        )
        other_profile = ClientProfile(
            workspace_id=other.id,
            name="Other Tenant Client",
            products_services="Other tenant secret offering",
        )
        db.add_all([profile, other_profile])
        db.commit()
        db.refresh(profile)
        db.refresh(other_profile)

        icp = ICPProfile(
            workspace_id=workspace.id,
            client_profile_id=profile.id,
            name="Hardening ICP",
            target_industries="Technology",
            target_countries="United States",
            decision_maker_roles="CEO,Founder",
            max_prospects=2,
        )
        db.add(icp)
        db.commit()
        db.refresh(icp)

        auth_factory(client, "hardening-ws", "owner")
        return {
            "workspace_id": str(workspace.id),
            "icp_profile_id": str(icp.id),
            "other_client_profile_id": str(other_profile.id),
        }
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Tenant isolation
# --------------------------------------------------------------------------- #


def test_batch_cannot_reference_another_tenants_client_profile(client, seeded):
    response = client.post(
        "/api/v1/engine/batches/",
        json={
            "workspace_id": "hardening-ws",
            "icp_profile_id": seeded["icp_profile_id"],
            "client_profile_id": seeded["other_client_profile_id"],
            "name": "Cross tenant profile attempt",
            "requested_prospect_count": 1,
        },
    )
    assert response.status_code == 404
    assert "Client profile" in response.json()["detail"]


def test_stale_running_batch_is_reclaimed(client, seeded):
    from datetime import UTC, datetime, timedelta

    db = SessionLocal()
    try:
        batch = ProspectBatch(
            workspace_id=uuid.UUID(seeded["workspace_id"]),
            icp_profile_id=uuid.UUID(seeded["icp_profile_id"]),
            name="Crashed worker batch",
            source_mode="demo",
            status="running",
            requested_prospect_count=1,
        )
        db.add(batch)
        db.commit()
        batch.updated_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
        db.commit()
        batch_id = str(batch.id)
    finally:
        db.close()

    run_engine_pipeline(batch_id, "hardening-ws")

    db = SessionLocal()
    try:
        batch = db.query(ProspectBatch).filter(ProspectBatch.id == uuid.UUID(batch_id)).one()
        # The stale claim succeeded and the pipeline actually ran.
        assert batch.status == "completed"
        assert len(batch.stage_runs) > 0
    finally:
        db.close()


def test_redirects_to_internal_or_plain_http_are_blocked():
    for target in (
        "http://api.tavily.com/search",
        "https://169.254.169.254/latest/meta-data/",
        "https://metadata.google.internal/x",
        "https://localhost/admin",
    ):
        with pytest.raises(UnsafeUrlError):
            safe_request(target, require_https=True)


def test_dns_lookup_skipped_for_internal_domains():
    calls: list[str] = []

    def resolver(domain: str) -> DomainLookup:
        calls.append(domain)
        return DomainLookup(True, True, "resolved")

    provider = DnsEmailVerificationProvider(resolver=resolver)
    for email in (
        "ada@metadata.google.internal",
        "ada@localhost",
        "ada@service.local",
        "ada@intranet",
    ):
        result = provider.verify(email)
        assert result.status == "invalid"
        assert result.status != "verified"
    assert calls == []

    provider.verify("ada@acme.com")
    assert calls == ["acme.com"]


def test_concurrent_run_guard_does_not_double_process(client, seeded):
    db = SessionLocal()
    try:
        batch = ProspectBatch(
            workspace_id=uuid.UUID(seeded["workspace_id"]),
            icp_profile_id=uuid.UUID(seeded["icp_profile_id"]),
            name="Already running batch",
            source_mode="demo",
            status="running",
        )
        db.add(batch)
        db.commit()
        batch_id = str(batch.id)
    finally:
        db.close()

    run_engine_pipeline(batch_id, "hardening-ws")

    db = SessionLocal()
    try:
        batch = db.query(ProspectBatch).filter(ProspectBatch.id == uuid.UUID(batch_id)).one()
        assert batch.status == "running"
        assert db.query(Prospect).filter(Prospect.batch_id == batch.id).count() == 0
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# SSRF-style evidence rejection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://10.0.0.5/internal",
        "http://192.168.1.20/router",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://acme.local/portal",
        "http://service.internal/health",
        "https://user:pass@acme.com/about",
        "http://[::1]/admin",
        "http://localhost:8000/admin",
    ],
)
def test_evidence_rejects_internal_and_credentialed_urls(url):
    assert is_plausible_source_url(url) is False


def test_evidence_accepts_public_urls_with_ports():
    assert is_plausible_source_url("https://acme.com:8443/about") is True
    assert is_plausible_source_url("https://news.bbc.co.uk/story") is True


# --------------------------------------------------------------------------- #
# Search adapter: untrusted provider payloads
# --------------------------------------------------------------------------- #


def test_search_parse_rejects_missing_envelope():
    with pytest.raises(ProviderResponseError):
        _parse_hits("tavily", {"unexpected": []})
    with pytest.raises(ProviderResponseError):
        _parse_hits("serper", {"organic": "not-a-list"})
    with pytest.raises(ProviderResponseError):
        _parse_hits("tavily", {"error": "quota exceeded"})


def test_search_parse_drops_malformed_entries_and_unverified_sources():
    hits = _parse_hits(
        "tavily",
        {
            "results": [
                {
                    "url": "https://acme.com/about",
                    "title": "Acme",
                    "content": "widgets",
                },
                {"url": "http://169.254.169.254/latest/meta-data/", "title": "meta"},
                {"url": "https://acme.com/x", "title": {"bad": "type"}},
                {"title": "no url"},
                "junk",
            ]
        },
    )
    assert len(hits) == 1
    source = _source_ref(hits[0])
    # Search retrieval is not fact verification.
    assert source.verified is False
    assert source.url == "https://acme.com/about"


# --------------------------------------------------------------------------- #
# Execution and qualification guards
# --------------------------------------------------------------------------- #


class _SlowProvider:
    name = "slow"
    capability = "company_research"
    synthetic = False
    cost_per_call_usd = 0.0

    def __init__(self):
        self.calls = 0

    def status(self):
        from app.engine.contracts import ProviderStatus

        return ProviderStatus(name=self.name, capability=self.capability, state="ready")


def test_timeouts_are_not_retried_to_avoid_duplicate_charges():
    provider = _SlowProvider()

    def call():
        provider.calls += 1
        time.sleep(0.3)

    runner = ProviderRunner(
        retry=RetryPolicy(max_attempts=3, timeout_seconds=0.05),
        meter=UsageMeter(),
        sleeper=lambda _: None,
    )
    with pytest.raises(ProviderTimeout):
        runner.run(provider, "research", call)
    assert provider.calls == 1


def _candidate() -> CompanyCandidate:
    return CompanyCandidate(
        name="Acme Widgets Inc",
        website="https://acme.com",
        industry="Technology",
        country="United States",
    )


def _research() -> CompanyResearch:
    return CompanyResearch(
        provider="test_search",
        what_it_does="Acme builds widget tracking tools",
        observable_signals=["first-party page: About Acme"],
        evidence=[
            SourceRef(
                url="https://acme.com/about",
                title="About Acme",
                snippet="Acme builds widget tracking tools",
            )
        ],
        confidence=0.6,
    )


def _analysis(fit_confidence: float = 0.6) -> ProblemFitAnalysis:
    return ProblemFitAnalysis(
        problem="Manual widget tracking slows fulfilment",
        problem_inference="Inferred from the About page.",
        problem_confidence=0.5,
        fit_explanation="The client platform addresses manual widget tracking.",
        offering_reference="Workflow automation platform",
        fit_confidence=fit_confidence,
        evidence_urls=["https://acme.com/about"],
        analyzer="test",
    )


def _icp() -> ICPQuery:
    return ICPQuery(industries=["Technology"], countries=["United States"])


def _dm(index: int = 0) -> DecisionMakerCandidate:
    name = "Ada Lovelace" if index == 0 else "Grace Hopper"
    return DecisionMakerCandidate(
        full_name=name,
        job_title="CEO" if index == 0 else "CTO",
        linkedin_url=f"https://www.linkedin.com/in/{name.lower().replace(' ', '-')}",
        profile_source="search",
        source_url="https://acme.com/team",
    )


def _verified(email: str) -> VerificationResult:
    return VerificationResult(
        provider="test_api",
        email=email,
        status="verified",
        method="verification_api",
        confidence=0.95,
    )


def _dns_only(email: str) -> VerificationResult:
    return VerificationResult(
        provider="dns",
        email=email,
        status="unknown",
        method="dns_mx",
        confidence=0.2,
    )


def test_high_ai_confidence_cannot_override_failed_email_gate():
    data = QualificationInput(
        candidate=_candidate(),
        research=_research(),
        decision_makers=[
            DecisionMakerAssessment(_dm(0), _verified("ada@acme.com")),
            DecisionMakerAssessment(_dm(1), _dns_only("grace@acme.com")),
        ],
        analysis=_analysis(fit_confidence=1.0),
        icp=_icp(),
    )
    outcome = evaluate(data, QualificationPolicy(mode="real"))
    assert outcome.status == "rejected"
    email_gate = outcome.gate("verified_emails")
    assert email_gate is not None and email_gate.passed is False


def test_dns_only_status_never_satisfies_the_email_gate():
    data = QualificationInput(
        candidate=_candidate(),
        research=_research(),
        decision_makers=[
            DecisionMakerAssessment(_dm(0), _dns_only("ada@acme.com")),
            DecisionMakerAssessment(_dm(1), _dns_only("grace@acme.com")),
        ],
        analysis=_analysis(),
        icp=_icp(),
    )
    outcome = evaluate(data, QualificationPolicy(mode="real"))
    assert outcome.status == "rejected"
