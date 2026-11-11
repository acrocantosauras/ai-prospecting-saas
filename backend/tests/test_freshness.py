import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ.setdefault("DATABASE_URL", f"sqlite:///{(Path(tempfile.mkdtemp()) / 'f.db').as_posix()}")
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("AI_PROVIDER", "demo")
os.environ["PROSPECTING_MODE"] = "demo"

from app.engine.freshness import (
    ChangeStatus,
    DecisionMakerStatus,
    FreshnessState,
    QualificationFreshnessStatus,
    compare_content,
    content_fingerprint,
    decision_maker_status,
    evaluate_demo_readiness,
    evaluate_freshness,
    parse_timestamp,
    qualification_freshness_status,
)


def test_parse_timestamp_handles_none_naive_and_z():
    assert parse_timestamp(None) is None
    naive = datetime(2026, 1, 1, 12, 0, 0)
    parsed = parse_timestamp(naive)
    assert parsed is not None and parsed.tzinfo is not None
    z = parse_timestamp("2026-01-01T12:00:00Z")
    assert z == datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert parse_timestamp("not-a-date") is None


def test_freshness_states():
    now = datetime(2026, 1, 10, tzinfo=UTC)
    assert evaluate_freshness(now - timedelta(days=1), max_age_days=7, now=now).state == FreshnessState.FRESH
    assert evaluate_freshness(now - timedelta(days=10), max_age_days=7, now=now).state == FreshnessState.AGING
    assert evaluate_freshness(now - timedelta(days=20), max_age_days=7, now=now).state == FreshnessState.STALE
    assert evaluate_freshness(now - timedelta(days=40), max_age_days=7, now=now).state == FreshnessState.EXPIRED
    assert evaluate_freshness(None, max_age_days=7, now=now).state == FreshnessState.UNKNOWN
    assert evaluate_freshness(now, max_age_days=7, now=now, unavailable=True).state == FreshnessState.UNAVAILABLE


def test_failed_refresh_does_not_upgrade_age():
    old = datetime(2026, 1, 1, tzinfo=UTC)
    now = datetime(2026, 1, 20, tzinfo=UTC)
    result = evaluate_freshness(old, max_age_days=7, now=now)
    assert result.state in (FreshnessState.STALE, FreshnessState.EXPIRED)
    # Attempt timestamp is not a retrieval timestamp.
    assert evaluate_freshness(old, max_age_days=7, now=now).retrieved_at == old


def test_content_fingerprint_stable():
    assert content_fingerprint("Hello World") == content_fingerprint("hello   world")
    assert content_fingerprint({"a": 1, "b": 2}) == content_fingerprint({"b": 2, "a": 1})


def test_compare_content():
    fp = content_fingerprint("abc")
    assert compare_content(fp, fp) == ChangeStatus.UNCHANGED
    assert compare_content(fp, content_fingerprint("def")) == ChangeStatus.CHANGED
    assert compare_content(fp, fp, source_available=False) == ChangeStatus.SOURCE_UNAVAILABLE
    assert compare_content(fp, fp, parse_ok=False) == ChangeStatus.PARSE_FAILED
    assert compare_content(fp, fp, identity_conflict=True) == ChangeStatus.IDENTITY_CONFLICT


def test_decision_maker_status_conservative():
    now = datetime(2026, 1, 10, tzinfo=UTC)
    assert decision_maker_status(last_observed_at=now - timedelta(days=1), now=now, still_present=True).value == DecisionMakerStatus.CURRENTLY_OBSERVED.value
    assert decision_maker_status(last_observed_at=now - timedelta(days=30), now=now, still_present=True).value == DecisionMakerStatus.STALE.value
    assert decision_maker_status(last_observed_at=now, now=now, still_present=False).value == DecisionMakerStatus.SOURCE_SUPPORTED.value
    assert decision_maker_status(last_observed_at=now, now=now, conflicting=True).value == DecisionMakerStatus.CONFLICTING_EVIDENCE.value


def test_qualification_freshness_status():
    assert qualification_freshness_status(
        base_status="qualified",
        evidence_state=FreshnessState.STALE,
        has_verified_email=True,
        has_required_decision_makers=True,
        has_sourced_problem=True,
        has_solution_fit=True,
    ) == QualificationFreshnessStatus.STALE_EVIDENCE
    assert qualification_freshness_status(
        base_status="qualified",
        evidence_state=FreshnessState.FRESH,
        has_verified_email=True,
        has_required_decision_makers=True,
        has_sourced_problem=True,
        has_solution_fit=True,
    ) == QualificationFreshnessStatus.QUALIFIED


def test_demo_readiness():
    report = evaluate_demo_readiness(
        prospects=[{"id": "1"}],
        freshness_states=["FRESH"],
        decision_maker_fresh_count=2,
        broken_source_urls=0,
        qualification_blockers=[],
        last_successful_refresh=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert report.demo_ready is True
    assert report.to_dict()["fresh_prospects"] == 1
