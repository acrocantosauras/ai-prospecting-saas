"""Provider selection, capability reporting and degradation.

The registry never invents a capability. When a required integration is not
configured (for example a people-data provider), it returns a provider that
reports ``not_configured`` and raises ``ProviderNotConfigured`` when called, so
batches fail or defer with an explicit reason instead of fabricating contacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn

from app.config.settings import Settings, get_settings
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
    EvidenceProvider,
    ICPQuery,
    ProviderStatus,
    SourceRef,
)
from app.engine.errors import ProviderNotConfigured
from app.engine.providers.crawlee_people import CrawleeDecisionMakerProvider
from app.engine.providers.crawlee_research import CrawleeResearchProvider
from app.engine.providers.demo_adapter import DemoEngineProvider
from app.engine.providers.dns_verifier import DnsEmailVerificationProvider
from app.engine.providers.multi_discovery import (
    build_multi_source_discovery,
)
from app.engine.providers.search_api import SearchApiProvider

SEARCH_CONFIG_HINT = (
    "Set PROSPECTING_MODE=real and configure SEARCH_PROVIDER plus "
    "TAVILY_API_KEY or SERPER_API_KEY."
)
PEOPLE_CONFIG_HINT = (
    "No decision-maker data provider is integrated. Configure a permitted "
    "people-data API before running real batches."
)
ENRICHMENT_CONFIG_HINT = (
    "No contact-enrichment provider is integrated. Configure a permitted "
    "enrichment API before running real batches."
)
LLM_CONFIG_HINT = "Set AI_PROVIDER=openai and OPENAI_API_KEY for LLM analysis."


class UnconfiguredProvider(
    CompanyDiscoveryProvider,
    CompanyResearchProvider,
    DecisionMakerProvider,
    ContactEnrichmentProvider,
    EvidenceProvider,
):
    """A placeholder that reports a missing integration and refuses to guess."""

    synthetic = False

    def __init__(self, *, name: str, capability: str, detail: str) -> None:
        """Record which capability is missing and why."""
        self.name = name
        self.capability = capability
        self._detail = detail

    def status(self) -> ProviderStatus:
        """Report this capability as not configured."""
        return ProviderStatus(
            name=self.name,
            capability=self.capability,
            state="not_configured",
            synthetic=False,
            detail=self._detail,
            cost_per_call_usd=0.0,
        )

    def _unavailable(self) -> NoReturn:
        raise ProviderNotConfigured(self._detail)

    def discover(self, request: DiscoveryRequest) -> list[CompanyCandidate]:
        """Refuse to invent companies."""
        self._unavailable()

    def research(self, company: CompanyCandidate, icp: ICPQuery) -> CompanyResearch:
        """Refuse to invent research."""
        self._unavailable()

    def discover_decision_makers(
        self, company: CompanyCandidate, icp: ICPQuery
    ) -> list[DecisionMakerCandidate]:
        """Refuse to invent people."""
        self._unavailable()

    def enrich(
        self, company: CompanyCandidate, decision_maker: DecisionMakerCandidate
    ) -> EnrichmentResult:
        """Refuse to invent contact details."""
        self._unavailable()

    def collect(self, company: CompanyCandidate) -> list[SourceRef]:
        """Refuse to invent sources."""
        self._unavailable()


@dataclass(frozen=True)
class ProviderBundle:
    """The concrete providers a pipeline run will use."""

    discovery: CompanyDiscoveryProvider
    research: CompanyResearchProvider
    decision_makers: DecisionMakerProvider
    enrichment: ContactEnrichmentProvider
    verification: EmailVerificationProvider
    evidence: EvidenceProvider | None
    analyzer_provider: Any | None
    mode: str

    @property
    def synthetic(self) -> bool:
        """Return True when discovery data is synthetic."""
        return bool(self.discovery.synthetic)

    def statuses(self) -> list[ProviderStatus]:
        """Return capability status for every provider in the bundle."""
        entries: list[tuple[Any, str]] = [
            (self.discovery, "company_discovery"),
            (self.research, "company_research"),
            (self.decision_makers, "decision_makers"),
            (self.enrichment, "contact_enrichment"),
            (self.verification, "email_verification"),
        ]
        if self.evidence is not None:
            entries.append((self.evidence, "evidence_collection"))
        statuses = [
            _status_for(provider, capability) for provider, capability in entries
        ]
        if self.analyzer_provider is None:
            statuses.append(
                UnconfiguredProvider(
                    name="rule_based_analysis",
                    capability="problem_fit_analysis",
                    detail=(
                        f"{LLM_CONFIG_HINT} Falling back to deterministic rule-based "
                        "analysis."
                    ),
                ).status()
            )
        else:
            statuses.append(
                _AnalyzerDescriptor(name=_analyzer_name(self.analyzer_provider)).status()
            )
        return statuses


class _AnalyzerDescriptor:
    """Minimal descriptor for the configured LLM analysis provider."""

    name = "llm_analysis"
    capability = "problem_fit_analysis"
    synthetic = False
    cost_per_call_usd = 0.0

    def __init__(self, *, name: str) -> None:
        """Label the analyzer with the underlying provider name."""
        self.name = name

    def status(self) -> ProviderStatus:
        """Report the analyzer as ready."""
        return ProviderStatus(
            name=self.name,
            capability=self.capability,
            state="ready",
            synthetic=False,
            detail="Structured LLM analysis with mandatory citation validation.",
        )


def _status_for(provider: Any, capability: str) -> ProviderStatus:
    """Return a provider's status labelled with the capability being reported."""
    status: ProviderStatus = provider.status()
    if status.capability == capability:
        return status
    return status.model_copy(update={"capability": capability})


def _analyzer_name(provider: Any) -> str:
    return str(getattr(provider, "name", "llm") or "llm")


def build_provider_bundle(
    settings: Settings | None = None, *, mode: str | None = None
) -> ProviderBundle:
    """Select providers for the configured mode.

    ``PROSPECTING_MODE=demo`` uses the synthetic provider for everything.
    ``real`` uses a configured search API for discovery/research and the DNS
    verifier for email sanity checks, and reports people/enrichment as not
    configured until a real integration is added.
    """
    resolved = settings or get_settings()
    requested_mode = (mode or resolved.prospecting_mode or "").lower()
    resolved_mode = "real" if requested_mode == "real" else "demo"
    verification = DnsEmailVerificationProvider(
        cost_per_call_usd=resolved.cost_email_verification_usd
    )
    if resolved_mode == "demo":
        demo = DemoEngineProvider()
        return ProviderBundle(
            discovery=demo,
            research=demo,
            decision_makers=demo,
            enrichment=demo,
            verification=demo,
            evidence=None,
            analyzer_provider=None,
            mode="demo",
        )

    crawlee_research = CrawleeResearchProvider()
    crawlee_people = CrawleeDecisionMakerProvider()
    # Discovery is API-independent and multi-source: public search plus optional
    # customer URLs, public listings and tenant-scoped history.
    discovery: Any = build_multi_source_discovery(resolved)
    research: Any = crawlee_research
    evidence: EvidenceProvider | None = crawlee_research
    if resolved.is_search_api_configured:
        # Prefer the explicitly configured adapter when credentials are present,
        # but never require them for real mode. Keep it as an additional source
        # rather than replacing the API-independent composite.
        try:
            paid = SearchApiProvider.from_settings(resolved)
        except Exception:  # noqa: BLE001 - optional adapter must not break local discovery
            paid = None
        if paid is not None:
            from app.engine.providers.multi_discovery import CompositeDiscoveryProvider

            discovery = CompositeDiscoveryProvider([paid, discovery])

    decision_makers = crawlee_people
    enrichment = UnconfiguredProvider(
        name="contact_enrichment",
        capability="contact_enrichment",
        detail=ENRICHMENT_CONFIG_HINT,
    )
    analyzer: Any | None = None
    if resolved.is_llm_configured:
        from app.providers.openai_provider import OpenAIProvider

        analyzer = OpenAIProvider()
    elif resolved.is_local_llm_configured:
        from app.providers.local_llm_provider import LocalLLMProvider

        analyzer = LocalLLMProvider()
    return ProviderBundle(
        discovery=discovery,
        research=research,
        decision_makers=decision_makers,
        enrichment=enrichment,
        verification=verification,
        evidence=evidence,
        analyzer_provider=analyzer,
        mode="real",
    )
