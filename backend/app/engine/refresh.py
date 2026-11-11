"""Safe, single-company research refresh orchestration.

A refresh re-runs the existing Crawlee research and decision-maker providers for
one company, persists the new evidence alongside the old evidence, and records
the outcome without overwriting a previous successful research timestamp on
failure.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.core.database import SessionLocal
from app.engine.contracts import CompanyCandidate, ICPQuery
from app.engine.evidence import sanitize_sources
from app.engine.freshness import content_fingerprint, decision_maker_status
from app.engine.registry import build_provider_bundle
from app.models import Company, CompanyResearchRecord, DecisionMaker, Evidence

logger = logging.getLogger(__name__)

_REFRESH_IN_PROGRESS: set[str] = set()
_REFRESH_LOCK = threading.Lock()


def is_refresh_running(company_id: str) -> bool:
    """Return whether a refresh is currently queued or running."""
    with _REFRESH_LOCK:
        return company_id in _REFRESH_IN_PROGRESS


def mark_refresh_started(company_id: str) -> bool:
    """Atomically mark a refresh as started; return False if already running."""
    with _REFRESH_LOCK:
        if company_id in _REFRESH_IN_PROGRESS:
            return False
        _REFRESH_IN_PROGRESS.add(company_id)
        return True


def mark_refresh_finished(company_id: str) -> None:
    """Clear the in-process refresh marker."""
    with _REFRESH_LOCK:
        _REFRESH_IN_PROGRESS.discard(company_id)


def _candidate_from_company(company: Company) -> CompanyCandidate:
    return CompanyCandidate(
        name=company.name,
        website=company.website,
        domain=company.domain,
        industry=company.industry,
        location=company.location,
        country=company.country,
        city=company.city,
        description=company.description,
        products_services=company.products_services,
        company_size=company.company_size,
        employee_count=company.employee_count,
        revenue=company.revenue,
        linkedin_url=company.linkedin_url,
        instagram_url=company.instagram_url,
        source_url=company.source_url,
        source_name=company.source_name,
        synthetic=bool(company.synthetic),
    )


def _icp_from_company(company: Company) -> ICPQuery:
    batch = getattr(company, "batch", None)
    icp = getattr(batch, "icp_profile", None) if batch is not None else None
    if icp is not None:
        try:
            return ICPQuery.from_icp_record(icp)
        except Exception:  # noqa: BLE001
            pass
    industries = [company.industry] if company.industry else []
    countries = [company.country] if company.country else []
    return ICPQuery(industries=industries, countries=countries)


def run_company_refresh(company_id: str, workspace_id: str) -> None:  # noqa: C901
    """Refresh one company's research and decision-maker evidence.

    Never raises into the caller; outcomes are persisted on the research record.
    """
    db: Session = SessionLocal()
    record: CompanyResearchRecord | None = None
    try:
        try:
            parsed_company = __import__("uuid").UUID(company_id)
            parsed_workspace = __import__("uuid").UUID(workspace_id)
        except ValueError:
            return
        company = (
            db.query(Company)
            .filter(Company.id == parsed_company)
            .first()
        )
        if company is None:
            return
        # Tenant guard: never refresh a company outside the claimed workspace.
        batch = getattr(company, "batch", None)
        if batch is None or str(batch.workspace_id) != workspace_id:
            # Fall back to a direct workspace check via the batch relation.
            from app.models import ProspectBatch

            batch = (
                db.query(ProspectBatch)
                .filter(
                    ProspectBatch.id == company.batch_id,
                    ProspectBatch.workspace_id == parsed_workspace,
                )
                .first()
            )
            if batch is None:
                logger.warning("Refresh refused: company %s not in workspace %s", company_id, workspace_id)
                return
            company.batch = batch

        settings = get_settings()
        mode = getattr(batch, "source_mode", None) or "demo"
        bundle = build_provider_bundle(settings, mode=mode)
        candidate = _candidate_from_company(company)
        icp = _icp_from_company(company)

        previous_success = (
            db.query(CompanyResearchRecord)
            .filter(CompanyResearchRecord.company_id == company.id)
            .order_by(CompanyResearchRecord.last_successful_at.desc().nullslast())
            .first()
        )
        now = datetime.now(UTC)
        record = CompanyResearchRecord(
            workspace_id=parsed_workspace,
            batch_id=company.batch_id,
            company_id=company.id,
            provider=getattr(bundle.research, "name", "refresh"),
            what_it_does=None,
            what_it_sells=None,
            who_it_serves=None,
            positioning=None,
            public_developments=None,
            observable_signals_json="[]",
            evidence_json="[]",
            missing_information_json="[]",
            confidence=0.0,
            synthetic=bool(company.synthetic),
            research_timestamp=previous_success.last_successful_at if previous_success and previous_success.last_successful_at else (previous_success.research_timestamp if previous_success else now),
            last_attempted_at=now,
            last_successful_at=previous_success.last_successful_at if previous_success else None,
            research_status="running",
            research_version=(previous_success.research_version + 1) if previous_success else 1,
            content_fingerprint=None,
            error_message=None,
            decision_maker_extracted_at=None,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        research = bundle.research.research(candidate, icp)
        research = research.model_copy(update={"evidence": sanitize_sources(research.evidence)})

        decision_makers = bundle.decision_makers.discover_decision_makers(candidate, icp)

        # Persist the successful research record by updating the running row.
        record.provider = research.provider
        record.what_it_does = research.what_it_does
        record.what_it_sells = research.what_it_sells
        record.who_it_serves = research.who_it_serves
        record.positioning = research.positioning
        record.public_developments = research.public_developments
        record.observable_signals_json = __import__("json").dumps(research.observable_signals)
        record.evidence_json = __import__("json").dumps(
            [source.model_dump(mode="json") for source in research.evidence]
        )
        record.missing_information_json = __import__("json").dumps(research.missing_information)
        record.confidence = research.confidence
        record.synthetic = research.synthetic
        record.research_timestamp = research.researched_at
        record.last_successful_at = research.researched_at
        record.research_status = "success"
        record.content_fingerprint = content_fingerprint(
            {
                "what_it_does": research.what_it_does,
                "what_it_sells": research.what_it_sells,
                "who_it_serves": research.who_it_serves,
                "positioning": research.positioning,
                "evidence": [s.url for s in research.evidence],
            }
        )
        record.decision_maker_extracted_at = datetime.now(UTC)
        record.error_message = None

        for source in research.evidence:
            db.add(
                Evidence(
                    company_id=company.id,
                    label=source.title or source.source_type,
                    url=source.url,
                    content=source.snippet,
                    evidence_type="company_research",
                    retrieved_at=source.retrieved_at,
                    verification_status="retrieved",
                    content_fingerprint=content_fingerprint(source.snippet or source.url),
                    is_accessible=True,
                )
            )

        # Update or insert decision-makers without deleting historical rows.
        existing = {
            (dm.full_name or "").lower(): dm
            for dm in db.query(DecisionMaker).filter(DecisionMaker.company_id == company.id).all()
        }
        now_observed = datetime.now(UTC)
        for index, dm_candidate in enumerate(sorted(decision_makers, key=lambda item: item.role_priority)):
            key = (dm_candidate.full_name or "").lower()
            if key in existing:
                dm = existing[key]
                dm.job_title = dm_candidate.job_title
                dm.professional_profile_url = dm_candidate.linkedin_url or dm.professional_profile_url
                dm.profile_source = dm_candidate.profile_source or dm.profile_source
                dm.role_source_url = dm_candidate.source_url or dm.role_source_url
                dm.evidence_excerpt = dm_candidate.evidence_excerpt or dm.evidence_excerpt
                dm.last_observed_at = now_observed
                dm.status = decision_maker_status(
                    last_observed_at=now_observed,
                    still_present=True,
                    source_supported=True,
                ).value
                dm.observation_confidence = 0.8
            else:
                db.add(
                    DecisionMaker(
                        company_id=company.id,
                        first_name=dm_candidate.first_name,
                        last_name=dm_candidate.last_name,
                        full_name=dm_candidate.full_name,
                        job_title=dm_candidate.job_title,
                        professional_profile_url=dm_candidate.linkedin_url,
                        profile_source=dm_candidate.profile_source,
                        role_source_url=dm_candidate.source_url,
                        evidence_excerpt=dm_candidate.evidence_excerpt,
                        is_primary=index == 0,
                        synthetic=dm_candidate.synthetic,
                        status=decision_maker_status(
                            last_observed_at=now_observed,
                            still_present=True,
                            source_supported=True,
                        ).value,
                        last_observed_at=now_observed,
                        observation_confidence=0.8,
                    )
                )

        company.description = research.what_it_does or company.description
        company.research_confidence = research.confidence
        company.research_timestamp = research.researched_at
        company.updated_at = datetime.now(UTC)

        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Company refresh failed for %s", company_id)
        db.rollback()
        try:
            if record is not None:
                record.research_status = "failed"
                record.last_attempted_at = datetime.now(UTC)
                record.error_message = str(exc)[:2000]
                # Preserve the previous successful timestamp; do not upgrade it.
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    finally:
        db.close()
        mark_refresh_finished(company_id)


def latest_refresh_status(db: Session, company_id: str) -> CompanyResearchRecord | None:
    """Return the most recent refresh/research record for a company."""
    try:
        parsed = __import__("uuid").UUID(company_id)
    except ValueError:
        return None
    return (
        db.query(CompanyResearchRecord)
        .filter(CompanyResearchRecord.company_id == parsed)
        .order_by(CompanyResearchRecord.last_attempted_at.desc().nullslast(), CompanyResearchRecord.research_timestamp.desc())
        .first()
    )
