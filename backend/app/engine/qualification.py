"""Deterministic qualification gates and configurable exclusion rules.

Qualification is rule-based and reproducible: the same inputs and policy always
produce the same decision. The analysis layer supplies an interpretation, but it
cannot pass a gate on its own; gates check that required evidence exists and is
consistent.

Demo/illustrative policy is explicit and recorded with every decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.config.settings import Settings
from app.engine.contracts import (
    CompanyCandidate,
    CompanyResearch,
    DecisionMakerCandidate,
    ICPQuery,
    ProblemFitAnalysis,
    QualificationStatus,
    SourceRef,
    VerificationResult,
)
from app.engine.evidence import sanitize_sources, source_urls, validate_references
from app.engine.normalization import normalize_company_name, normalize_domain, split_csv


@dataclass(frozen=True)
class GateResult:
    """The outcome of one qualification gate."""

    name: str
    label: str
    passed: bool
    required: bool
    weight: float
    reason: str
    missing: str | None = None
    relaxed: bool = False
    blocked_by_capability: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "name": self.name,
            "label": self.label,
            "passed": self.passed,
            "required": self.required,
            "weight": self.weight,
            "reason": self.reason,
            "missing": self.missing,
            "relaxed": self.relaxed,
            "blocked_by_capability": self.blocked_by_capability,
        }


@dataclass(frozen=True)
class DecisionMakerAssessment:
    """A decision-maker plus whatever contact data was actually retrieved."""

    candidate: DecisionMakerCandidate
    verification: VerificationResult | None = None

    @property
    def email_status(self) -> str:
        """Return the independent verification status, if any."""
        return self.verification.status if self.verification else "unknown"

    @property
    def is_verified(self) -> bool:
        """Return True only for independently verified mailboxes."""
        return self.verification is not None and self.verification.status == "verified"

    @property
    def has_profile_evidence(self) -> bool:
        """Return True when a profile URL came with a retrievable source."""
        return bool(self.candidate.linkedin_url and self.candidate.source_url)


class QualificationPolicy(BaseModel):
    """Configurable rules that decide whether a company is qualified.

    ``mode="real"`` forbids the two demo relaxations outright, so an
    unverified email or an unsourced analysis can never pass in production.
    """

    mode: Literal["real", "demo"] = "real"
    min_decision_makers: int = Field(default=2, ge=1, le=10)
    min_sources: int = Field(default=1, ge=0, le=20)
    min_fit_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    min_research_confidence: float = Field(default=0.2, ge=0.0, le=1.0)
    allowed_countries: list[str] = Field(default_factory=list)
    excluded_industries: list[str] = Field(default_factory=list)
    excluded_domains: list[str] = Field(default_factory=list)
    excluded_name_keywords: list[str] = Field(default_factory=list)
    require_verified_emails: bool = True
    allow_unverified_emails: bool = False
    allow_missing_sources: bool = False

    @model_validator(mode="after")
    def _no_relaxation_in_real_mode(self) -> QualificationPolicy:
        if self.mode == "real":
            self.allow_unverified_emails = False
            self.allow_missing_sources = False
        return self

    @classmethod
    def from_settings(cls, settings: Settings, mode: str | None = None) -> QualificationPolicy:
        """Build the policy from settings for the requested mode."""
        resolved_mode: Literal["real", "demo"] = (
            "demo" if (mode or settings.prospecting_mode).lower() != "real" else "real"
        )
        demo = resolved_mode == "demo"
        return cls(
            mode=resolved_mode,
            min_decision_makers=settings.qualification_min_decision_makers,
            min_sources=settings.qualification_min_sources,
            min_fit_confidence=(
                0.0 if demo else settings.qualification_min_fit_confidence
            ),
            min_research_confidence=(
                0.0 if demo else settings.qualification_min_research_confidence
            ),
            allowed_countries=split_csv(settings.qualification_allowed_countries),
            excluded_industries=split_csv(settings.qualification_excluded_industries),
            excluded_domains=split_csv(settings.qualification_excluded_domains),
            excluded_name_keywords=split_csv(settings.qualification_excluded_name_keywords),
            require_verified_emails=settings.qualification_require_verified_emails,
            allow_unverified_emails=demo,
            allow_missing_sources=demo,
        )


@dataclass
class QualificationInput:
    """Everything the gates are allowed to look at."""

    candidate: CompanyCandidate
    research: CompanyResearch | None
    decision_makers: list[DecisionMakerAssessment]
    analysis: ProblemFitAnalysis | None
    icp: ICPQuery

    @property
    def evidence(self) -> list[SourceRef]:
        """Return the retrieved company evidence."""
        return sanitize_sources(self.research.evidence) if self.research else []

    @property
    def evidence_urls(self) -> list[str]:
        """Return validated evidence URLs."""
        return source_urls(self.evidence)


@dataclass(frozen=True)
class QualificationOutcome:
    """A complete, auditable qualification decision."""

    status: QualificationStatus
    score: float
    confidence: float
    gates: tuple[GateResult, ...]
    reasons: str
    missing: list[str]
    evidence_urls: list[str]
    policy: dict[str, Any]

    def gate(self, name: str) -> GateResult | None:
        """Return a single gate result by name."""
        return next((gate for gate in self.gates if gate.name == name), None)

    @property
    def is_qualified(self) -> bool:
        """Return True for qualified and illustrative-qualified outcomes."""
        return self.status in ("qualified", "qualified_illustrative")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "status": self.status,
            "score": self.score,
            "confidence": self.confidence,
            "gates": [gate.as_dict() for gate in self.gates],
            "reasons": self.reasons,
            "missing": self.missing,
            "evidence_urls": self.evidence_urls,
            "policy": self.policy,
        }


def _industry_matches(industry: str | None, targets: list[str]) -> bool:
    if not targets:
        return True
    if not industry:
        return False
    candidate = industry.strip().lower()
    return any(
        target.strip().lower() in candidate or candidate in target.strip().lower()
        for target in targets
        if target.strip()
    )


def _gate_icp_match(data: QualificationInput, policy: QualificationPolicy) -> GateResult:
    candidate = data.candidate
    icp = data.icp
    problems: list[str] = []
    if not _industry_matches(candidate.industry, icp.industries):
        problems.append(
            f"industry '{candidate.industry}' is outside the ICP industries "
            f"({', '.join(icp.industries)})"
        )
    target_countries = [item.lower() for item in icp.countries + icp.regions]
    if target_countries:
        country = (candidate.country or "").strip().lower()
        if not country:
            problems.append("country could not be confirmed")
        elif not any(
            country in target or target in country for target in target_countries
        ):
            problems.append(f"country '{candidate.country}' is outside the ICP geography")
    if policy.allowed_countries:
        allowed = [item.lower() for item in policy.allowed_countries]
        country = (candidate.country or "").strip().lower()
        if not any(item in country or country in item for item in allowed):
            problems.append(f"country '{candidate.country}' is not in the allowed country list")
    employee_problem = _employee_gate(candidate.employee_count, icp)
    if employee_problem:
        problems.append(employee_problem)
    if problems:
        return GateResult(
            name="icp_match",
            label="ICP match",
            passed=False,
            required=True,
            weight=15,
            reason="; ".join(problems),
            missing="; ".join(problems),
        )
    return GateResult(
        name="icp_match",
        label="ICP match",
        passed=True,
        required=True,
        weight=15,
        reason="industry and geography match the ICP",
    )


def _employee_gate(employee_count: str | None, icp: ICPQuery) -> str | None:
    if icp.employee_count_min is None and icp.employee_count_max is None:
        return None
    if not employee_count:
        return "employee count could not be confirmed against the ICP size range"
    digits = "".join(char for char in employee_count if char.isdigit())
    if not digits:
        return None
    count = int(digits)
    if icp.employee_count_min is not None and count < icp.employee_count_min:
        return f"employee count {count} is below the ICP minimum {icp.employee_count_min}"
    if icp.employee_count_max is not None and count > icp.employee_count_max:
        return f"employee count {count} is above the ICP maximum {icp.employee_count_max}"
    return None


def _gate_company_identity(data: QualificationInput, policy: QualificationPolicy) -> GateResult:
    candidate = data.candidate
    missing: list[str] = []
    if not (candidate.domain or candidate.website):
        missing.append("company website/domain")
    if not data.research or not data.research.has_usable_content:
        missing.append("researched company description")
    if missing:
        return GateResult(
            name="company_identity",
            label="Active, legitimate company",
            passed=False,
            required=True,
            weight=10,
            reason="company identity is incomplete: " + ", ".join(missing),
            missing=", ".join(missing),
        )
    return GateResult(
        name="company_identity",
        label="Active, legitimate company",
        passed=True,
        required=True,
        weight=10,
        reason="company has a resolvable domain and researched description",
    )


def _gate_business_relevance(
    data: QualificationInput, policy: QualificationPolicy
) -> GateResult:
    research = data.research
    if research is None or not research.has_usable_content:
        return GateResult(
            name="business_relevance",
            label="Business relevance",
            passed=False,
            required=True,
            weight=15,
            reason="no research findings are available for this company",
            missing="company-specific research findings",
        )
    if not research.observable_signals:
        return GateResult(
            name="business_relevance",
            label="Business relevance",
            passed=False,
            required=True,
            weight=15,
            reason="research found no observable signals that could be relevant to the offering",
            missing="at least one observable business signal",
        )
    return GateResult(
        name="business_relevance",
        label="Business relevance",
        passed=True,
        required=True,
        weight=15,
        reason=f"{len(research.observable_signals)} observable signal(s) retrieved",
    )


def _gate_exclusions(data: QualificationInput, policy: QualificationPolicy) -> GateResult:
    candidate = data.candidate
    name = (candidate.name or "").lower()
    industry = (candidate.industry or "").lower()
    domain = normalize_domain(candidate.domain or candidate.website) or ""
    reasons: list[str] = []
    for keyword in policy.excluded_name_keywords:
        if keyword.strip() and keyword.strip().lower() in name:
            reasons.append(f"company name contains excluded keyword '{keyword}'")
    for excluded_industry in policy.excluded_industries:
        if excluded_industry.strip() and excluded_industry.strip().lower() in industry:
            reasons.append(f"industry '{excluded_industry}' is excluded")
    for excluded_domain in policy.excluded_domains:
        target = normalize_domain(excluded_domain)
        if target and (domain == target or domain.endswith(f".{target}")):
            reasons.append(f"domain '{target}' is excluded")
    if reasons:
        return GateResult(
            name="no_exclusion",
            label="No exclusion rule triggered",
            passed=False,
            required=True,
            weight=5,
            reason="; ".join(reasons),
            missing=None,
        )
    return GateResult(
        name="no_exclusion",
        label="No exclusion rule triggered",
        passed=True,
        required=True,
        weight=5,
        reason="no exclusion rule matched",
    )


def _gate_decision_maker_count(
    data: QualificationInput, policy: QualificationPolicy
) -> GateResult:
    named = [
        assessment
        for assessment in data.decision_makers
        if assessment.candidate.full_name.strip() and assessment.candidate.job_title.strip()
    ]
    if len(named) < policy.min_decision_makers:
        return GateResult(
            name="decision_maker_count",
            label="Minimum decision-makers",
            passed=False,
            required=True,
            weight=15,
            reason=(
                f"{len(named)} decision-maker(s) with a name and title; "
                f"at least {policy.min_decision_makers} are required"
            ),
            missing=f"{policy.min_decision_makers} decision-makers with name and job title",
        )
    return GateResult(
        name="decision_maker_count",
        label="Minimum decision-makers",
        passed=True,
        required=True,
        weight=15,
        reason=f"{len(named)} decision-makers identified",
    )


def _gate_decision_maker_identity(
    data: QualificationInput, policy: QualificationPolicy
) -> GateResult:
    if policy.mode == "demo":
        return GateResult(
            name="decision_maker_identity",
            label="Verified decision-maker profiles",
            passed=True,
            required=True,
            weight=5,
            reason="synthetic demo profiles have no citable public profile URL",
            missing="verified LinkedIn/social profile URLs",
            relaxed=True,
        )
    missing_profiles = [
        assessment.candidate.full_name
        for assessment in data.decision_makers
        if not assessment.has_profile_evidence
    ]
    if missing_profiles:
        return GateResult(
            name="decision_maker_identity",
            label="Verified decision-maker profiles",
            passed=False,
            required=True,
            weight=5,
            reason="no citable profile source for: " + ", ".join(missing_profiles[:3]),
            missing="verified LinkedIn/social profile URLs",
        )
    return GateResult(
        name="decision_maker_identity",
        label="Verified decision-maker profiles",
        passed=True,
        required=True,
        weight=5,
        reason="every decision-maker has a profile URL with a retrievable source",
    )


def _gate_verified_emails(
    data: QualificationInput, policy: QualificationPolicy
) -> GateResult:
    assessments = data.decision_makers
    verified = [assessment for assessment in assessments if assessment.is_verified]
    statuses = ", ".join(
        f"{assessment.candidate.full_name}: {assessment.email_status}"
        for assessment in assessments
    )
    if len(verified) >= policy.min_decision_makers:
        return GateResult(
            name="verified_emails",
            label="Verified business emails",
            passed=True,
            required=True,
            weight=20,
            reason=f"{len(verified)} independently verified email(s)",
        )
    capability_gap = any(
        assessment.email_status == "provider_unavailable" for assessment in assessments
    )
    if policy.allow_unverified_emails:
        return GateResult(
            name="verified_emails",
            label="Verified business emails",
            passed=True,
            required=True,
            weight=20,
            reason=(
                f"policy allows unverified contacts in {policy.mode} mode; "
                f"no mailbox was verified ({statuses or 'no contacts'})"
            ),
            missing="verified business email addresses",
            relaxed=True,
            blocked_by_capability=capability_gap,
        )
    return GateResult(
        name="verified_emails",
        label="Verified business emails",
        passed=False,
        required=True,
        weight=20,
        reason=(
            f"{len(verified)} verified of {len(assessments)} decision-maker(s); "
            f"at least {policy.min_decision_makers} verified emails are required "
            f"({statuses or 'no contacts'})"
        ),
        missing="verified business email addresses",
        blocked_by_capability=capability_gap,
    )


def _gate_problem_evidence(
    data: QualificationInput, policy: QualificationPolicy
) -> GateResult:
    analysis = data.analysis
    if analysis is None or not analysis.problem.strip():
        return GateResult(
            name="problem_evidence",
            label="Evidence-backed business problem",
            passed=False,
            required=True,
            weight=5,
            reason="no specific business problem was identified",
            missing="a specific, sourced business problem",
        )
    cited, unsupported = validate_references(analysis.evidence_urls, data.evidence)
    if unsupported:
        return GateResult(
            name="problem_evidence",
            label="Evidence-backed business problem",
            passed=False,
            required=True,
            weight=5,
            reason=(
                f"analysis cited {len(unsupported)} source(s) that were not retrieved "
                "for this company"
            ),
            missing="analysis grounded in retrieved sources",
        )
    if not cited:
        if policy.allow_missing_sources:
            return GateResult(
                name="problem_evidence",
                label="Evidence-backed business problem",
                passed=True,
                required=True,
                weight=5,
                reason=(
                    f"policy allows unsourced analysis in {policy.mode} mode; "
                    "the problem is an unverified interpretation"
                ),
                missing="citable sources for the stated problem",
                relaxed=True,
            )
        return GateResult(
            name="problem_evidence",
            label="Evidence-backed business problem",
            passed=False,
            required=True,
            weight=5,
            reason="the stated problem is not linked to any retrieved source",
            missing="citable sources for the stated problem",
        )
    return GateResult(
        name="problem_evidence",
        label="Evidence-backed business problem",
        passed=True,
        required=True,
        weight=5,
        reason=f"problem cites {len(cited)} retrieved source(s)",
    )


def _gate_fit_credible(data: QualificationInput, policy: QualificationPolicy) -> GateResult:
    analysis = data.analysis
    if analysis is None or not analysis.fit_explanation.strip():
        return GateResult(
            name="fit_credible",
            label="Credible offering fit",
            passed=False,
            required=True,
            weight=5,
            reason="no fit explanation was produced",
            missing="a fit explanation tied to the client offering",
        )
    if analysis.fit_confidence < policy.min_fit_confidence:
        return GateResult(
            name="fit_credible",
            label="Credible offering fit",
            passed=False,
            required=True,
            weight=5,
            reason=(
                f"fit confidence {analysis.fit_confidence:.2f} is below the "
                f"threshold {policy.min_fit_confidence:.2f}"
            ),
            missing="stronger evidence for the fit",
        )
    if not analysis.offering_reference:
        return GateResult(
            name="fit_credible",
            label="Credible offering fit",
            passed=False,
            required=True,
            weight=5,
            reason="fit explanation does not reference a specific client offering",
            missing="reference to the client product/service",
        )
    return GateResult(
        name="fit_credible",
        label="Credible offering fit",
        passed=True,
        required=True,
        weight=5,
        reason="fit explanation references the client offering and clears the confidence threshold",
    )


def _gate_sources(data: QualificationInput, policy: QualificationPolicy) -> GateResult:
    urls = data.evidence_urls
    if len(urls) >= policy.min_sources and policy.min_sources > 0:
        return GateResult(
            name="sources_present",
            label="Required sources",
            passed=True,
            required=True,
            weight=5,
            reason=f"{len(urls)} retrievable source(s) recorded",
        )
    if policy.allow_missing_sources:
        return GateResult(
            name="sources_present",
            label="Required sources",
            passed=True,
            required=True,
            weight=5,
            reason=(
                f"policy allows missing sources in {policy.mode} mode; "
                "no source URLs are recorded for this record"
            ),
            missing="retrievable source URLs",
            relaxed=True,
        )
    return GateResult(
        name="sources_present",
        label="Required sources",
        passed=False,
        required=True,
        weight=5,
        reason=(
            f"{len(urls)} source(s) recorded; at least {policy.min_sources} are required"
        ),
        missing="retrievable source URLs",
    )


def _score_and_status(
    gates: tuple[GateResult, ...], policy: QualificationPolicy
) -> tuple[QualificationStatus, float, str, list[str]]:
    blocking = [gate for gate in gates if gate.required and not gate.passed]
    total_weight = sum(gate.weight for gate in gates) or 1.0
    earned = sum(gate.weight for gate in gates if gate.passed)
    score = round(earned / total_weight * 100, 1)
    failed = [gate for gate in gates if not gate.passed]
    relaxed = [gate for gate in gates if gate.relaxed and gate.required]
    if blocking:
        if any(gate.blocked_by_capability for gate in blocking):
            status: QualificationStatus = "recheck_later"
        else:
            status = "rejected"
    elif relaxed:
        status = "qualified_illustrative"
    else:
        status = "qualified"
    reasons: list[str] = []
    if failed:
        reasons.append("Failed: " + "; ".join(f"{gate.label}: {gate.reason}" for gate in failed))
    passed_labels = [gate.label for gate in gates if gate.passed and not gate.relaxed]
    if passed_labels:
        reasons.append("Passed: " + ", ".join(passed_labels))
    if relaxed:
        reasons.append(
            "Illustrative only: "
            + "; ".join(f"{gate.label} relaxed for {policy.mode} mode" for gate in relaxed)
        )
    if status == "recheck_later":
        reasons.append("A required provider capability was unavailable; re-check later.")
    return status, score, " | ".join(reasons), _missing_requirements(gates)


def _missing_requirements(gates: tuple[GateResult, ...]) -> list[str]:
    missing: list[str] = []
    for gate in gates:
        if gate.missing and gate.missing not in missing:
            missing.append(gate.missing)
    return missing


def _confidence(data: QualificationInput, policy: QualificationPolicy) -> float:
    research_confidence = data.research.confidence if data.research else 0.0
    analysis_confidence = 0.0
    if data.analysis:
        analysis_confidence = (
            data.analysis.problem_confidence + data.analysis.fit_confidence
        ) / 2
    total = len(data.decision_makers)
    verified_ratio = (
        sum(1 for item in data.decision_makers if item.is_verified) / total
        if total
        else 0.0
    )
    confidence = (
        0.45 * research_confidence + 0.35 * analysis_confidence + 0.20 * verified_ratio
    )
    if policy.mode == "demo":
        confidence = min(confidence, 0.25)
    return round(min(max(confidence, 0.0), 1.0), 3)


def _outcome(
    gates: list[GateResult], data: QualificationInput, policy: QualificationPolicy
) -> QualificationOutcome:
    status, score, reasons, missing = _score_and_status(tuple(gates), policy)
    return QualificationOutcome(
        status=status,
        score=score,
        confidence=_confidence(data, policy),
        gates=tuple(gates),
        reasons=reasons,
        missing=missing,
        evidence_urls=data.evidence_urls,
        policy=policy.model_dump(),
    )


def evaluate_precheck(
    data: QualificationInput, policy: QualificationPolicy
) -> QualificationOutcome:
    """Run the cheap gates before spending money on people/email providers."""
    gates = [
        _gate_icp_match(data, policy),
        _gate_company_identity(data, policy),
        _gate_business_relevance(data, policy),
        _gate_exclusions(data, policy),
    ]
    outcome = _outcome(gates, data, policy)
    if data.research and data.research.confidence < policy.min_research_confidence:
        failed = GateResult(
            name="research_confidence",
            label="Research confidence",
            passed=False,
            required=True,
            weight=0,
            reason=(
                f"research confidence {data.research.confidence:.2f} is below the "
                f"threshold {policy.min_research_confidence:.2f}"
            ),
            missing="enough retrieved evidence to research this company",
        )
        return _outcome([*gates, failed], data, policy)
    return outcome


def evaluate(
    data: QualificationInput, policy: QualificationPolicy
) -> QualificationOutcome:
    """Run every gate and return the final qualification decision."""
    gates = [
        _gate_icp_match(data, policy),
        _gate_company_identity(data, policy),
        _gate_business_relevance(data, policy),
        _gate_exclusions(data, policy),
        _gate_decision_maker_count(data, policy),
        _gate_decision_maker_identity(data, policy),
        _gate_verified_emails(data, policy),
        _gate_problem_evidence(data, policy),
        _gate_fit_credible(data, policy),
        _gate_sources(data, policy),
    ]
    return _outcome(gates, data, policy)


def excluded_company_reason(
    candidate: CompanyCandidate, policy: QualificationPolicy
) -> str | None:
    """Return an exclusion reason before any provider spend, if one matches."""
    name = candidate.name.lower()
    industry = (candidate.industry or "").lower()
    domain = normalize_domain(candidate.domain or candidate.website) or ""
    for keyword in policy.excluded_name_keywords:
        if keyword.strip() and keyword.strip().lower() in name:
            return f"company name contains excluded keyword '{keyword}'"
    for excluded_industry in policy.excluded_industries:
        if excluded_industry.strip() and excluded_industry.strip().lower() in industry:
            return f"industry '{excluded_industry}' is excluded"
    for excluded_domain in policy.excluded_domains:
        target = normalize_domain(excluded_domain)
        if target and (domain == target or domain.endswith(f".{target}")):
            return f"domain '{target}' is excluded"
    return None


def normalize_company_key(name: str | None) -> str | None:
    """Expose company-name normalization for callers that need a key."""
    return normalize_company_name(name)
