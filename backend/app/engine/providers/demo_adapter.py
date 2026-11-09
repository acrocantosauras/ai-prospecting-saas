"""Adapter exposing the synthetic demo provider through engine contracts.

Everything this adapter returns is synthetic and labelled as such. It never
returns an email address and never reports a mailbox as verified, so a demo run
can only produce explicitly illustrative results.
"""

from __future__ import annotations

from app.engine.contracts import (
    CompanyCandidate,
    CompanyDiscoveryProvider,
    CompanyResearch,
    CompanyResearchProvider,
    ContactEnrichmentProvider,
    DecisionMakerCandidate,
    DecisionMakerProvider,
    DiscoveryRequest,
    EmailVerificationProvider,
    EnrichmentResult,
    ICPQuery,
    ProviderStatus,
    VerificationResult,
)
from app.providers.demo import DemoProvider

SYNTHETIC_SOURCE = "Synthetic Demo Provider"


class DemoEngineProvider(
    CompanyDiscoveryProvider,
    CompanyResearchProvider,
    DecisionMakerProvider,
    ContactEnrichmentProvider,
    EmailVerificationProvider,
):
    """Deterministic synthetic provider. Never represents real-world data."""

    name = "synthetic_demo"
    synthetic = True

    def __init__(self, *, cost_per_call_usd: float = 0.0) -> None:
        """Wrap the existing demo provider with an explicit zero cost."""
        self.cost_per_call_usd = cost_per_call_usd
        self._demo = DemoProvider()

    def status(self) -> ProviderStatus:
        """Report the demo provider as available but synthetic."""
        return ProviderStatus(
            name=self.name,
            capability=self.capability,
            state="ready",
            synthetic=True,
            detail=(
                "Deterministic synthetic data. Companies, people and URLs are not real; "
                "emails are never verified."
            ),
            cost_per_call_usd=self.cost_per_call_usd,
        )

    def discover(self, request: DiscoveryRequest) -> list[CompanyCandidate]:
        """Return synthetic company candidates derived from the ICP."""
        raw = self._demo.discover(_icp_payload(request.icp), request.limit)
        candidates: list[CompanyCandidate] = []
        for item in raw:
            candidates.append(
                CompanyCandidate(
                    name=item.get("name") or "Unnamed synthetic company",
                    website=item.get("website"),
                    industry=item.get("industry"),
                    location=item.get("location"),
                    country=item.get("country"),
                    city=item.get("city"),
                    description=item.get("description"),
                    products_services=item.get("products_services"),
                    company_size=item.get("company_size"),
                    employee_count=item.get("employee_count"),
                    revenue=item.get("revenue"),
                    linkedin_url=None,
                    instagram_url=None,
                    source_url=None,
                    source_name=SYNTHETIC_SOURCE,
                    identity_confidence=0.05,
                    synthetic=True,
                    evidence=[],
                )
            )
        return candidates

    def research(self, company: CompanyCandidate, icp: ICPQuery) -> CompanyResearch:
        """Return synthetic research with no citable sources."""
        raw = self._demo.research(company.model_dump())
        signals: list[str] = []
        if raw.get("what_it_does"):
            signals.append(f"synthetic profile: {raw['what_it_does']}")
        if raw.get("what_it_sells"):
            signals.append(f"synthetic offering: {raw['what_it_sells']}")
        return CompanyResearch(
            provider=self.name,
            what_it_does=raw.get("what_it_does"),
            what_it_sells=raw.get("what_it_sells"),
            who_it_serves=raw.get("who_it_serves"),
            positioning=raw.get("positioning"),
            public_developments=None,
            observable_signals=signals,
            evidence=[],
            missing_information=[
                "No real sources: this is a synthetic demo record.",
                "Company facts and contacts are not verified.",
            ],
            confidence=0.1,
            synthetic=True,
        )

    def discover_decision_makers(
        self, company: CompanyCandidate, icp: ICPQuery
    ) -> list[DecisionMakerCandidate]:
        """Return synthetic decision-makers with no profile URLs."""
        raw = self._demo.discover_decision_makers(
            company.model_dump(), _icp_payload(icp)
        )
        candidates: list[DecisionMakerCandidate] = []
        for index, item in enumerate(raw):
            candidates.append(
                DecisionMakerCandidate(
                    full_name=item.get("full_name") or "Synthetic Contact",
                    first_name=item.get("first_name"),
                    last_name=item.get("last_name"),
                    job_title=item.get("job_title") or "Decision Maker",
                    linkedin_url=None,
                    profile_source=SYNTHETIC_SOURCE,
                    source_url=None,
                    role_priority=index * 10,
                    synthetic=True,
                )
            )
        return candidates

    def enrich(
        self, company: CompanyCandidate, decision_maker: DecisionMakerCandidate
    ) -> EnrichmentResult:
        """Return an explicit not-found result: the demo has no contact data."""
        return EnrichmentResult(
            provider=self.name,
            email=None,
            email_status="not_found",
            email_confidence=0.0,
            linkedin_url=None,
            instagram_url=None,
            method="none",
            notes="Synthetic demo provider has no contact data and never invents emails.",
            synthetic=True,
        )

    def verify(self, email: str) -> VerificationResult:
        """Never verify a mailbox: the demo cannot prove deliverability."""
        return VerificationResult(
            provider=self.name,
            email=email or None,
            status="unknown",
            method="synthetic_demo",
            confidence=0.0,
            detail=(
                "Synthetic demo provider: no mailbox check was performed, so the "
                "address is reported as unknown, never verified."
            ),
            synthetic=True,
        )


def _icp_payload(icp: ICPQuery) -> dict[str, object]:
    """Translate an ``ICPQuery`` into the legacy demo provider payload."""
    return {
        "target_industries": ", ".join(icp.industries),
        "target_countries": ", ".join(icp.countries),
        "company_size": icp.company_size,
        "decision_maker_roles": ", ".join(icp.decision_maker_roles),
        "target_audience": icp.target_audience,
        "additional_criteria": icp.additional_criteria,
    }
