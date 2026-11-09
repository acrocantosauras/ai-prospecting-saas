"""Normalized provider contracts for the prospecting engine.

These contracts are independent of any vendor. Adapters translate vendor
payloads into these models, so the pipeline, qualification rules and storage
layer never depend on a specific provider's response shape.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.engine.normalization import normalize_domain, normalize_email, normalize_person_name

EmailStatus = Literal[
    "verified",
    "invalid",
    "risky",
    "unknown",
    "not_found",
    "provider_unavailable",
]
"""Email verification states.

Only ``verified`` satisfies the mandatory qualification gate. Syntax/MX/DNS
checks must never produce ``verified``; mailbox proof requires an SMTP handshake
or a dedicated verification API.
"""

QualificationStatus = Literal[
    "qualified",
    "qualified_illustrative",
    "rejected",
    "recheck_later",
]
ProviderState = Literal["ready", "not_configured", "unavailable", "degraded"]

VERIFIED_EMAIL_METHODS = frozenset({"smtp_mailbox_check", "verification_api"})

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_URL_RE = re.compile(r"^https?://[^\s/]+\.[^\s/]+", re.IGNORECASE)
_NAME_RE = re.compile(r"[A-Za-z]")

DEMO_SYNTHETIC_MARKER = "synthetic demo"


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class SourceRef(BaseModel):
    """A source actually retrieved from a provider.

    ``verified`` means the provider returned the URL at retrieval time, not that
    the page content has been fact-checked. Synthetic sources are never marked
    verified.
    """

    url: str
    title: str | None = None
    source_type: str = "search_result"
    snippet: str | None = None
    retrieved_at: datetime = Field(default_factory=utcnow)
    verified: bool = False

    @field_validator("url")
    @classmethod
    def _absolute_url(cls, value: str) -> str:
        if not _URL_RE.match(value.strip()):
            raise ValueError("source url must be an absolute http(s) URL")
        return value.strip()


class CompanyCandidate(BaseModel):
    """A discovered company before research and qualification."""

    name: str = Field(min_length=1, max_length=255)
    website: str | None = None
    domain: str | None = None
    industry: str | None = None
    location: str | None = None
    country: str | None = None
    city: str | None = None
    description: str | None = None
    products_services: str | None = None
    company_size: str | None = None
    employee_count: str | None = None
    revenue: str | None = None
    linkedin_url: str | None = None
    instagram_url: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    identity_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    synthetic: bool = False
    evidence: list[SourceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _derive_domain(self) -> Self:
        if not self.domain:
            self.domain = normalize_domain(self.website or self.source_url)
        return self

    @field_validator("name")
    @classmethod
    def _meaningful_name(cls, value: str) -> str:
        if not _NAME_RE.search(value):
            raise ValueError("company name must contain letters")
        return " ".join(value.split())


class DecisionMakerCandidate(BaseModel):
    """A discovered decision-maker. Contact details arrive via enrichment."""

    full_name: str = Field(min_length=2, max_length=256)
    first_name: str | None = None
    last_name: str | None = None
    job_title: str = Field(min_length=1, max_length=256)
    linkedin_url: str | None = None
    instagram_url: str | None = None
    profile_source: str | None = None
    source_url: str | None = None
    role_priority: int = 100
    synthetic: bool = False

    @model_validator(mode="after")
    def _split_name(self) -> Self:
        if not self.first_name or not self.last_name:
            parts = self.full_name.strip().split()
            if parts:
                self.first_name = self.first_name or parts[0]
                self.last_name = self.last_name or (" ".join(parts[1:]) or None)
        return self

    @field_validator("full_name")
    @classmethod
    def _letters_only(cls, value: str) -> str:
        if not _NAME_RE.search(value):
            raise ValueError("decision-maker name must contain letters")
        return value


class EnrichmentResult(BaseModel):
    """Contact details returned by an enrichment provider."""

    provider: str
    email: str | None = None
    email_status: EmailStatus = "not_found"
    email_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    linkedin_url: str | None = None
    instagram_url: str | None = None
    other_profiles: dict[str, str] = Field(default_factory=dict)
    method: str | None = None
    notes: str | None = None
    synthetic: bool = False

    @field_validator("email")
    @classmethod
    def _email_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = normalize_email(value)
        if not cleaned or not _EMAIL_RE.match(cleaned):
            raise ValueError("enrichment returned a malformed email")
        return cleaned


class VerificationResult(BaseModel):
    """Result of an independent email verification attempt."""

    provider: str
    email: str | None
    status: EmailStatus
    method: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    checked_at: datetime = Field(default_factory=utcnow)
    detail: str | None = None
    synthetic: bool = False

    @model_validator(mode="after")
    def _verified_requires_proof(self) -> Self:
        if self.status == "verified":
            if self.method not in VERIFIED_EMAIL_METHODS:
                raise ValueError(
                    "status 'verified' requires a mailbox-level method "
                    f"({', '.join(sorted(VERIFIED_EMAIL_METHODS))}), got {self.method!r}"
                )
            if self.confidence < 0.8:
                raise ValueError("status 'verified' requires confidence >= 0.8")
            if self.synthetic:
                raise ValueError("synthetic results must never be labelled 'verified'")
        return self


class CompanyResearch(BaseModel):
    """Research findings with their supporting sources."""

    provider: str
    what_it_does: str | None = None
    what_it_sells: str | None = None
    who_it_serves: str | None = None
    positioning: str | None = None
    public_developments: str | None = None
    observable_signals: list[str] = Field(default_factory=list)
    evidence: list[SourceRef] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    synthetic: bool = False
    researched_at: datetime = Field(default_factory=utcnow)

    @property
    def has_usable_content(self) -> bool:
        """Return True when research produced at least one factual field."""
        return any(
            value
            for value in (
                self.what_it_does,
                self.what_it_sells,
                self.who_it_serves,
                self.positioning,
                self.public_developments,
            )
        )


class ProblemFitAnalysis(BaseModel):
    """Interpretation layer: a specific problem and why the offering fits.

    ``problem_inference`` is mandatory so a reader can distinguish the observed
    facts from the interpretation built on them.
    """

    problem: str
    problem_inference: str
    problem_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    fit_explanation: str
    offering_reference: str | None = None
    fit_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_urls: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    analyzer: str = "rule_based"
    synthetic: bool = False
    validation_notes: list[str] = Field(default_factory=list)

    @field_validator("problem", "problem_inference", "fit_explanation")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("analysis fields must not be blank")
        return cleaned


class ICPQuery(BaseModel):
    """Normalized ICP input for discovery providers."""

    name: str | None = None
    industries: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    company_size: str | None = None
    employee_count_min: int | None = None
    employee_count_max: int | None = None
    decision_maker_roles: list[str] = Field(default_factory=list)
    target_audience: str | None = None
    additional_criteria: str | None = None

    def validation_problems(self) -> list[str]:
        """Return the reasons this ICP cannot drive a real discovery run."""
        problems: list[str] = []
        if not self.industries and not self.target_audience and not self.additional_criteria:
            problems.append(
                "ICP must define at least one target industry, a target audience or additional criteria"
            )
        if self.employee_count_min and self.employee_count_max:
            if self.employee_count_min > self.employee_count_max:
                problems.append("ICP employee_count_min is greater than employee_count_max")
        if not self.countries and not self.regions:
            problems.append("ICP has no target country or region; discovery results cannot be scoped")
        return problems

    @classmethod
    def from_icp_record(cls, icp: Any) -> ICPQuery:
        """Build a query from an ``ICPProfile`` row without importing models."""
        from app.engine.normalization import split_csv

        return cls(
            name=getattr(icp, "name", None),
            industries=split_csv(getattr(icp, "target_industries", None)),
            countries=split_csv(getattr(icp, "target_countries", None)),
            regions=split_csv(getattr(icp, "target_regions", None)),
            company_size=getattr(icp, "company_size", None),
            employee_count_min=getattr(icp, "employee_count_min", None),
            employee_count_max=getattr(icp, "employee_count_max", None),
            decision_maker_roles=split_csv(getattr(icp, "decision_maker_roles", None)),
            target_audience=getattr(icp, "target_audience", None),
            additional_criteria=getattr(icp, "additional_criteria", None),
        )


class DiscoveryRequest(BaseModel):
    """Input to a company discovery provider."""

    icp: ICPQuery
    limit: int = Field(ge=1, le=300)


class ProviderStatus(BaseModel):
    """Capability/health report for one provider."""

    name: str
    capability: str
    state: ProviderState
    synthetic: bool = False
    detail: str | None = None
    cost_per_call_usd: float = 0.0

    @property
    def available(self) -> bool:
        """Return True when the provider can execute calls."""
        return self.state in ("ready", "degraded")


class ProviderDescriptor:
    """Common metadata and status reporting for every engine provider."""

    name: str = "unknown"
    capability: str = "unknown"
    synthetic: bool = False
    cost_per_call_usd: float = 0.0

    def status(self) -> ProviderStatus:
        """Report availability without making an external call."""
        return ProviderStatus(
            name=self.name,
            capability=self.capability,
            state="ready",
            synthetic=self.synthetic,
            cost_per_call_usd=self.cost_per_call_usd,
        )


class CompanyDiscoveryProvider(ProviderDescriptor, ABC):
    """Discovers companies that may match the ICP."""

    capability = "company_discovery"

    @abstractmethod
    def discover(self, request: DiscoveryRequest) -> list[CompanyCandidate]:
        """Return company candidates for the request."""
        raise NotImplementedError


class CompanyResearchProvider(ProviderDescriptor, ABC):
    """Retrieves public research and sources for a company."""

    capability = "company_research"

    @abstractmethod
    def research(self, company: CompanyCandidate, icp: ICPQuery) -> CompanyResearch:
        """Return research findings and their sources."""
        raise NotImplementedError


class DecisionMakerProvider(ProviderDescriptor, ABC):
    """Identifies decision-makers at a company."""

    capability = "decision_makers"

    @abstractmethod
    def discover_decision_makers(
        self, company: CompanyCandidate, icp: ICPQuery
    ) -> list[DecisionMakerCandidate]:
        """Return decision-maker candidates."""
        raise NotImplementedError


class ContactEnrichmentProvider(ProviderDescriptor, ABC):
    """Resolves contact details for a decision-maker."""

    capability = "contact_enrichment"

    @abstractmethod
    def enrich(
        self, company: CompanyCandidate, decision_maker: DecisionMakerCandidate
    ) -> EnrichmentResult:
        """Return contact details, or an explicit missing/unavailable status."""
        raise NotImplementedError


class EmailVerificationProvider(ProviderDescriptor, ABC):
    """Independently verifies an email address."""

    capability = "email_verification"

    @abstractmethod
    def verify(self, email: str) -> VerificationResult:
        """Return a verification result for the address."""
        raise NotImplementedError


class EvidenceProvider(ProviderDescriptor, ABC):
    """Collects additional citable sources for a company."""

    capability = "evidence_collection"

    @abstractmethod
    def collect(self, company: CompanyCandidate) -> list[SourceRef]:
        """Return validated source references."""
        raise NotImplementedError


def normalize_person_key(full_name: str | None) -> str | None:
    """Expose person-name normalization for dedup callers."""
    return normalize_person_name(full_name)
