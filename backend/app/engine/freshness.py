"""Deterministic freshness, evidence-history and change-detection helpers.

Freshness is always derived from the timestamp of the underlying evidence or
verification, never from the moment a database row was last touched. A failed
refresh therefore cannot make old data look current.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class FreshnessState(StrEnum):
    """Freshness states for retrieved evidence."""

    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


class ChangeStatus(StrEnum):
    """Content-change classifications."""

    UNCHANGED = "unchanged"
    CHANGED = "changed"
    SOURCE_UNAVAILABLE = "source_unavailable"
    PARSE_FAILED = "parse_failed"
    IDENTITY_CONFLICT = "identity_conflict"


class DecisionMakerStatus(StrEnum):
    """Decision-maker observation statuses."""

    SOURCE_SUPPORTED = "SOURCE_SUPPORTED"
    CURRENTLY_OBSERVED = "CURRENTLY_OBSERVED"
    STALE = "STALE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    UNCONFIRMED = "UNCONFIRMED"


class QualificationFreshnessStatus(StrEnum):
    """Qualification freshness statuses."""

    QUALIFIED = "QUALIFIED"
    RECHECK_REQUIRED = "RECHECK_REQUIRED"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    REJECTED = "REJECTED"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class FreshnessThresholds:
    """Configurable freshness thresholds."""

    company_identity_days: int = 7
    company_services_days: int = 14
    decision_maker_days: int = 14
    email_verification_days: int = 7
    social_marketing_days: int = 7

    def as_dict(self) -> dict[str, int]:
        """Return thresholds as a dictionary."""
        return asdict(self)


@dataclass
class FreshnessAssessment:
    """Freshness result for one category."""

    state: FreshnessState
    category: str
    retrieved_at: datetime | None
    max_age_days: int
    age_seconds: float | None = None
    reason: str = ""

    def is_usable(self) -> bool:
        """Return whether the data can be used without refresh."""
        return self.state in (FreshnessState.FRESH, FreshnessState.AGING)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the assessment."""
        return {
            "state": self.state.value,
            "category": self.category,
            "retrieved_at": _iso(self.retrieved_at),
            "max_age_days": self.max_age_days,
            "age_seconds": self.age_seconds,
            "reason": self.reason,
        }


def utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


def parse_timestamp(value: Any) -> datetime | None:
    """Parse a timestamp defensively and always return timezone-aware UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def content_fingerprint(value: Any) -> str:
    """Return a stable SHA-256 fingerprint for text or structured data."""
    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, sort_keys=True, default=str)
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def evaluate_freshness(
    retrieved_at: Any,
    *,
    max_age_days: int,
    now: datetime | None = None,
    unavailable: bool = False,
    parse_failed: bool = False,
    category: str = "research",
) -> FreshnessAssessment:
    """Evaluate one category's freshness from its evidence timestamp."""
    current = now or utcnow()
    parsed = parse_timestamp(retrieved_at)
    if unavailable:
        return FreshnessAssessment(
            state=FreshnessState.UNAVAILABLE,
            category=category,
            retrieved_at=parsed,
            max_age_days=max_age_days,
            reason="source unavailable",
        )
    if parse_failed:
        return FreshnessAssessment(
            state=FreshnessState.UNKNOWN,
            category=category,
            retrieved_at=parsed,
            max_age_days=max_age_days,
            reason="timestamp missing or malformed",
        )
    if parsed is None:
        return FreshnessAssessment(
            state=FreshnessState.UNKNOWN,
            category=category,
            retrieved_at=None,
            max_age_days=max_age_days,
            reason="no retrieval timestamp",
        )
    age = (current - parsed).total_seconds()
    if age < 0:
        age = 0.0
    max_age_seconds = max_age_days * 86400
    if age <= max_age_seconds:
        state = FreshnessState.FRESH
        reason = "within freshness threshold"
    elif age <= max_age_seconds * 2:
        state = FreshnessState.AGING
        reason = "approaching freshness threshold"
    elif age <= max_age_seconds * 4:
        state = FreshnessState.STALE
        reason = "exceeds freshness threshold"
    else:
        state = FreshnessState.EXPIRED
        reason = "far beyond freshness threshold"
    return FreshnessAssessment(
        state=state,
        category=category,
        retrieved_at=parsed,
        max_age_days=max_age_days,
        age_seconds=age,
        reason=reason,
    )


def evaluate_company_freshness(
    *,
    research_retrieved_at: Any,
    decision_maker_retrieved_at: Any = None,
    email_verified_at: Any = None,
    thresholds: FreshnessThresholds | None = None,
    now: datetime | None = None,
    source_unavailable: bool = False,
) -> dict[str, Any]:
    """Evaluate the standard freshness categories for a company/prospect."""
    t = thresholds or FreshnessThresholds()
    current = now or utcnow()
    result = {
        "research": evaluate_freshness(
            research_retrieved_at,
            max_age_days=t.company_services_days,
            now=current,
            unavailable=source_unavailable,
            category="company_services",
        ).to_dict(),
        "identity": evaluate_freshness(
            research_retrieved_at,
            max_age_days=t.company_identity_days,
            now=current,
            unavailable=source_unavailable,
            category="company_identity",
        ).to_dict(),
        "decision_makers": evaluate_freshness(
            decision_maker_retrieved_at or research_retrieved_at,
            max_age_days=t.decision_maker_days,
            now=current,
            unavailable=source_unavailable,
            category="decision_makers",
        ).to_dict(),
        "email_verification": evaluate_freshness(
            email_verified_at,
            max_age_days=t.email_verification_days,
            now=current,
            unavailable=False,
            category="email_verification",
        ).to_dict(),
    }
    states = [item["state"] for item in result.values()]
    if FreshnessState.EXPIRED.value in states or FreshnessState.UNAVAILABLE.value in states:
        overall = FreshnessState.EXPIRED if FreshnessState.EXPIRED.value in states else FreshnessState.UNAVAILABLE
    elif FreshnessState.STALE.value in states:
        overall = FreshnessState.STALE
    elif FreshnessState.AGING.value in states:
        overall = FreshnessState.AGING
    elif FreshnessState.UNKNOWN.value in states:
        overall = FreshnessState.UNKNOWN
    else:
        overall = FreshnessState.FRESH
    result["overall"] = overall.value
    return result


def compare_content(
    previous_fingerprint: str | None,
    current_fingerprint: str | None,
    *,
    source_available: bool = True,
    parse_ok: bool = True,
    identity_conflict: bool = False,
) -> ChangeStatus:
    """Classify a content change without over-interpreting missing data."""
    if not source_available:
        return ChangeStatus.SOURCE_UNAVAILABLE
    if not parse_ok:
        return ChangeStatus.PARSE_FAILED
    if identity_conflict:
        return ChangeStatus.IDENTITY_CONFLICT
    if not previous_fingerprint or not current_fingerprint:
        return ChangeStatus.CHANGED
    if previous_fingerprint == current_fingerprint:
        return ChangeStatus.UNCHANGED
    return ChangeStatus.CHANGED


def decision_maker_status(
    *,
    last_observed_at: Any,
    now: datetime | None = None,
    max_age_days: int = 14,
    still_present: bool = True,
    conflicting: bool = False,
    source_supported: bool = True,
) -> DecisionMakerStatus:
    """Derive a conservative decision-maker status."""
    if conflicting:
        return DecisionMakerStatus.CONFLICTING_EVIDENCE
    if not source_supported:
        return DecisionMakerStatus.UNCONFIRMED
    parsed = parse_timestamp(last_observed_at)
    if parsed is None:
        return DecisionMakerStatus.SOURCE_SUPPORTED
    current = now or utcnow()
    age_days = (current - parsed).total_seconds() / 86400
    if age_days > max_age_days:
        return DecisionMakerStatus.STALE
    if still_present:
        return DecisionMakerStatus.CURRENTLY_OBSERVED
    return DecisionMakerStatus.SOURCE_SUPPORTED


def qualification_freshness_status(
    *,
    base_status: str,
    evidence_state: FreshnessState | str,
    has_verified_email: bool,
    has_required_decision_makers: bool,
    has_sourced_problem: bool,
    has_solution_fit: bool,
) -> QualificationFreshnessStatus:
    """Map qualification plus freshness into an explicit status."""
    state = evidence_state.value if isinstance(evidence_state, FreshnessState) else str(evidence_state)
    if base_status == "rejected":
        return QualificationFreshnessStatus.REJECTED
    if not has_required_decision_makers or not has_sourced_problem or not has_solution_fit:
        return QualificationFreshnessStatus.INCOMPLETE
    if not has_verified_email:
        return QualificationFreshnessStatus.INCOMPLETE
    if state in (FreshnessState.STALE.value, FreshnessState.EXPIRED.value, FreshnessState.UNAVAILABLE.value):
        return QualificationFreshnessStatus.STALE_EVIDENCE
    if state in (FreshnessState.AGING.value, FreshnessState.UNKNOWN.value):
        return QualificationFreshnessStatus.RECHECK_REQUIRED
    if base_status == "qualified":
        return QualificationFreshnessStatus.QUALIFIED
    return QualificationFreshnessStatus.RECHECK_REQUIRED


@dataclass
class DemoReadinessReport:
    """Demo readiness summary."""

    total_prospects: int = 0
    fresh_prospects: int = 0
    aging_prospects: int = 0
    stale_prospects: int = 0
    incomplete_prospects: int = 0
    decision_makers_with_fresh_evidence: int = 0
    broken_source_urls: int = 0
    qualification_blockers: list[str] = field(default_factory=list)
    last_successful_refresh: datetime | None = None
    demo_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report."""
        return {
            "total_prospects": self.total_prospects,
            "fresh_prospects": self.fresh_prospects,
            "aging_prospects": self.aging_prospects,
            "stale_prospects": self.stale_prospects,
            "incomplete_prospects": self.incomplete_prospects,
            "decision_makers_with_fresh_evidence": self.decision_makers_with_fresh_evidence,
            "broken_source_urls": self.broken_source_urls,
            "qualification_blockers": self.qualification_blockers,
            "last_successful_refresh": _iso(self.last_successful_refresh),
            "demo_ready": self.demo_ready,
        }


def evaluate_demo_readiness(
    *,
    prospects: list[dict[str, Any]],
    freshness_states: list[str],
    decision_maker_fresh_count: int,
    broken_source_urls: int,
    qualification_blockers: list[str],
    last_successful_refresh: Any = None,
) -> DemoReadinessReport:
    """Build a demo-readiness report."""
    report = DemoReadinessReport(
        total_prospects=len(prospects),
        fresh_prospects=sum(1 for s in freshness_states if s == FreshnessState.FRESH.value),
        aging_prospects=sum(1 for s in freshness_states if s == FreshnessState.AGING.value),
        stale_prospects=sum(1 for s in freshness_states if s in (FreshnessState.STALE.value, FreshnessState.EXPIRED.value)),
        incomplete_prospects=sum(1 for s in freshness_states if s in (FreshnessState.UNKNOWN.value, FreshnessState.UNAVAILABLE.value)),
        decision_makers_with_fresh_evidence=decision_maker_fresh_count,
        broken_source_urls=broken_source_urls,
        qualification_blockers=list(qualification_blockers),
        last_successful_refresh=parse_timestamp(last_successful_refresh),
    )
    report.demo_ready = (
        report.total_prospects > 0
        and report.stale_prospects == 0
        and report.incomplete_prospects == 0
        and report.broken_source_urls == 0
        and not report.qualification_blockers
        and report.decision_makers_with_fresh_evidence >= 2
    )
    return report


def _iso(value: Any) -> str | None:
    parsed = parse_timestamp(value)
    return parsed.isoformat() if parsed is not None else None
