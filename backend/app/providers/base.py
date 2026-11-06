"""Provider abstractions - interfaces for each external capability."""

from abc import ABC, abstractmethod
from typing import Any


class CompanyDiscoveryProvider(ABC):
    """Discovers companies matching an ICP."""

    @abstractmethod
    def discover(
        self,
        icp: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return a list of company candidate dicts."""
        raise NotImplementedError


class CompanyResearchProvider(ABC):
    """Researches a discovered company for relevant business context."""

    @abstractmethod
    def research(
        self,
        company: dict[str, Any],
    ) -> dict[str, Any]:
        """Return enriched research information for the company."""
        raise NotImplementedError


class DecisionMakerDiscoveryProvider(ABC):
    """Identifies decision-makers at a company."""

    @abstractmethod
    def discover_decision_makers(
        self,
        company: dict[str, Any],
        icp: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return a list of decision-maker candidate dicts."""
        raise NotImplementedError


class ContactEnrichmentProvider(ABC):
    """Enriches a prospect with contact details."""

    @abstractmethod
    def enrich(
        self,
        prospect: dict[str, Any],
    ) -> dict[str, Any]:
        """Return enrichment results, including email status."""
        raise NotImplementedError


class EmailVerificationProvider(ABC):
    """Verifies email deliverability status."""

    VERIFICATION_STATUSES = (
        "verified_deliverable",
        "risky",
        "invalid",
        "unverified",
        "unavailable",
    )

    @abstractmethod
    def verify(
        self,
        email: str,
    ) -> dict[str, Any]:
        """Return verification result."""
        raise NotImplementedError


class AIAnalysisProvider(ABC):
    """Runs AI analysis tasks with structured output."""

    @abstractmethod
    def analyze(
        self,
        prompt: str,
        schema: type,
        system: str | None = None,
    ) -> Any:
        """Return validated AI output matching the schema."""
        raise NotImplementedError


class ProviderRegistry:
    """Central registry for provider implementations."""

    def __init__(self) -> None:
        self.company_discovery: CompanyDiscoveryProvider | None = None
        self.company_research: CompanyResearchProvider | None = None
        self.decision_maker_discovery: DecisionMakerDiscoveryProvider | None = None
        self.contact_enrichment: ContactEnrichmentProvider | None = None
        self.email_verification: EmailVerificationProvider | None = None
        self.ai_analysis: AIAnalysisProvider | None = None

    def use_demo(self) -> None:
        """Use the built-in deterministic demo provider."""
        from app.providers.demo import DemoProvider

        provider = DemoProvider()
        self.company_discovery = provider
        self.company_research = provider
        self.decision_maker_discovery = provider
        self.contact_enrichment = provider
        self.email_verification = provider
        self.ai_analysis = provider

    def use_openai(self) -> None:
        """Use OpenAI as the AI analysis provider."""
        from app.providers.openai_provider import OpenAIProvider

        self.ai_analysis = OpenAIProvider()
