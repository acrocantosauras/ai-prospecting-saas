"""Engine pipeline orchestration.

Stages run in a fixed order and each stage is recorded in ``batch_stage_runs``
so progress and failures are observable. A failure on one company is isolated:
the company is recorded with a rejection/re-check reason and the batch continues.
Every external call is metered, and company rows are persisted as they complete
so a resumed run can skip work that is already checkpointed.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.core.database import SessionLocal
from app.engine.analysis import LLMAnalyzer, ProblemFitAnalyzer, RuleBasedAnalyzer
from app.engine.contracts import (
    CompanyCandidate,
    CompanyResearch,
    DecisionMakerCandidate,
    DiscoveryRequest,
    EmailStatus,
    EnrichmentResult,
    ICPQuery,
    ProblemFitAnalysis,
    QualificationStatus,
    VerificationResult,
    utcnow,
)
from app.engine.dedup import find_company_duplicate, find_decision_maker_duplicate
from app.engine.errors import (
    BudgetExceeded,
    EngineError,
    EvidenceValidationError,
    ICPValidationError,
    PipelineCancelled,
    ProviderNotConfigured,
    ProviderUnavailable,
)
from app.engine.evidence import sanitize_sources, summarise_sources
from app.engine.execution import (
    ProviderRunner,
    RateLimiter,
    RetryPolicy,
    UsageEvent,
    UsageMeter,
)
from app.engine.normalization import (
    normalize_company_name,
    normalize_domain,
    normalize_person_name,
)
from app.engine.qualification import (
    DecisionMakerAssessment,
    QualificationInput,
    QualificationOutcome,
    QualificationPolicy,
    evaluate,
    evaluate_precheck,
    excluded_company_reason,
)
from app.engine.registry import ProviderBundle, build_provider_bundle
from app.models import (
    BatchStageRun,
    Company,
    CompanyResearchRecord,
    DecisionMaker,
    EnrichmentRecord,
    Evidence,
    ICPProfile,
    Prospect,
    ProspectBatch,
    ProviderUsage,
    QualificationRecord,
    VerificationRecord,
    Workspace,
)

logger = logging.getLogger(__name__)

STAGES: tuple[str, ...] = (
    "icp_validation",
    "company_discovery",
    "company_dedup",
    "company_research",
    "company_precheck",
    "decision_maker_discovery",
    "contact_enrichment",
    "email_verification",
    "problem_fit_analysis",
    "final_qualification",
    "persistence",
)

MAX_DECISION_MAKERS_PER_COMPANY = 5

# A batch left in "running" by a crashed worker can be reclaimed once it has been
# silent for this long. Normal stages commit progress well within this window.
STALE_RUNNING_SECONDS = 900


@dataclass
class RunContext:
    """Mutable state for one pipeline execution."""

    db: Session
    batch: ProspectBatch
    workspace: Workspace
    icp: ICPProfile
    settings: Settings
    bundle: ProviderBundle
    policy: QualificationPolicy
    runner: ProviderRunner
    stage_runs: dict[str, BatchStageRun] = field(default_factory=dict)
    validation_notes: list[str] = field(default_factory=list)
    researched: int = 0
    prechecked: int = 0
    contacts: int = 0
    enriched: int = 0
    verified: int = 0
    analysed: int = 0
    skipped: int = 0

    @property
    def client_context(self) -> dict[str, Any]:
        """Return the client offering context used by the analyzer."""
        profile = self.batch.client_profile
        if profile is None:
            return {}
        return {
            "name": profile.name,
            "website": profile.website,
            "description": profile.description,
            "products_services": profile.products_services,
            "value_proposition": profile.value_proposition,
            "target_audience": profile.target_audience,
            "problems_solved": profile.problems_solved,
            "usp": profile.usp,
        }


@dataclass
class AssessmentBundle:
    """A decision-maker with the contact data actually retrieved for it."""

    candidate: DecisionMakerCandidate
    enrichment: EnrichmentResult
    verification: VerificationResult

    def as_assessment(self) -> DecisionMakerAssessment:
        """Convert to the qualification-layer view."""
        return DecisionMakerAssessment(
            candidate=self.candidate, verification=self.verification
        )


@dataclass
class CompanyResult:
    """Outcome of processing one company."""

    candidate: CompanyCandidate
    outcome: QualificationOutcome | None = None
    prospects_created: int = 0
    error: str | None = None


def run_engine_pipeline(
    batch_id: str,
    workspace_ref: str | None = None,
    bundle: ProviderBundle | None = None,
) -> None:
    """Run the engine pipeline for an already-authorized batch.

    ``workspace_ref`` (slug or id) is a consistency assertion, not an
    authorization input; the batch's persisted ``workspace_id`` scopes the run.
    Never raises into the request.
    """
    db = SessionLocal()
    batch: ProspectBatch | None = None
    try:
        batch = _load_batch(db, batch_id, workspace_ref)
        if batch is not None and batch.status not in ("completed", "cancelled"):
            if _claim_batch(db, batch):
                _execute(_build_context(db, batch, bundle))
    except Exception as exc:  # noqa: BLE001 - background task boundary
        _handle_pipeline_failure(db, batch, exc, batch_id)
    finally:
        db.close()


def _claim_batch(db: Session, batch: ProspectBatch) -> bool:
    """Atomically claim a batch for this worker.

    Only one runner can move a batch from pending/failed to running, so two
    background workers (or a retried task) cannot process the same batch
    concurrently and duplicate prospects or provider spend.
    """
    filters = [ProspectBatch.id == batch.id]
    if batch.status == "running":
        last_seen = _naive_utc(batch.updated_at or batch.created_at)
        cutoff = _naive_utc(utcnow()) - timedelta(seconds=STALE_RUNNING_SECONDS)
        if last_seen is None or last_seen > cutoff:
            return False
        # Optimistic claim: only matches if no other worker touched the row.
        filters.append(ProspectBatch.status == "running")
        filters.append(ProspectBatch.updated_at == batch.updated_at)
    else:
        filters.append(
            ProspectBatch.status.notin_(("completed", "cancelled", "running"))
        )
    claimed = (
        db.query(ProspectBatch)
        .filter(*filters)
        .update(
            {"status": "running", "error_message": None},
            synchronize_session=False,
        )
    )
    db.commit()
    db.refresh(batch)
    return claimed == 1


def _naive_utc(value: Any) -> Any:
    """Normalize a datetime to naive UTC so SQLite comparisons are consistent."""
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _build_context(
    db: Session, batch: ProspectBatch, bundle: ProviderBundle | None
) -> RunContext:
    """Build the run context, provider bundle and metered runner."""
    settings = get_settings()
    policy = QualificationPolicy.from_settings(settings, batch.source_mode)
    resolved_bundle = bundle or build_provider_bundle(
        settings, mode=batch.source_mode
    )
    meter = UsageMeter(
        max_cost_usd=settings.batch_cost_budget_usd,
        listener=_usage_listener(db, batch.workspace_id, batch.id),
    )
    runner = ProviderRunner(
        retry=RetryPolicy(
            max_attempts=settings.provider_max_attempts,
            base_delay_seconds=settings.provider_backoff_seconds,
            max_delay_seconds=settings.provider_max_backoff_seconds,
            timeout_seconds=settings.provider_timeout_seconds,
        ),
        meter=meter,
        limiter=RateLimiter(settings.provider_min_interval_seconds),
    )
    return RunContext(
        db=db,
        batch=batch,
        workspace=batch.workspace,
        icp=batch.icp_profile,
        settings=settings,
        bundle=resolved_bundle,
        policy=policy,
        runner=runner,
    )


def _handle_pipeline_failure(
    db: Session,
    batch: ProspectBatch | None,
    exc: Exception,
    batch_id: str,
) -> None:
    """Persist a clear terminal status instead of leaving a stuck batch."""
    if batch is None:
        return
    if isinstance(exc, PipelineCancelled):
        _mark_terminal(db, batch, status="cancelled", detail="Cancelled by operator")
    elif isinstance(exc, BudgetExceeded):
        _mark_terminal(db, batch, status="failed", detail=str(exc))
    elif isinstance(exc, EngineError):
        logger.warning("Engine batch %s failed: %s", batch.id, exc)
        _mark_terminal(db, batch, status="failed", detail=str(exc))
    else:
        logger.exception("Unexpected engine failure for batch %s", batch_id)
        _mark_terminal(
            db, batch, status="failed", detail=f"Unexpected pipeline error: {exc}"
        )


def _load_batch(
    db: Session, batch_id: str, workspace_ref: str | None = None
) -> ProspectBatch | None:
    """Load a batch by id and scope every later query to its persisted tenant.

    The optional ``workspace_ref`` is a defensive consistency check only (it can
    deny a mismatched run, never grant one): tenant scoping always comes from
    ``batch.workspace_id``, which was written when the batch was created by an
    authorized member. Background workers therefore never depend on a live user
    session or on a slug supplied by a caller.
    """
    try:
        parsed = uuid.UUID(batch_id)
    except ValueError:
        return None
    batch = db.query(ProspectBatch).filter(ProspectBatch.id == parsed).first()
    if batch is None:
        return None
    if workspace_ref:
        reference = workspace_ref.strip()
        workspace = batch.workspace
        matches = False
        if workspace is not None:
            matches = workspace.slug == reference or str(workspace.id) == reference
        if not matches:
            logger.warning(
                "Refusing to run batch %s: workspace reference does not match its persisted workspace",
                batch.id,
            )
            return None
    return batch


def _execute(ctx: RunContext) -> None:
    """Validate the ICP, then run every pipeline stage in order."""
    _seed_stages(ctx)
    query = ICPQuery.from_icp_record(ctx.icp)
    _stage(ctx, "icp_validation")
    problems = query.validation_problems()
    if problems:
        raise ICPValidationError("ICP validation failed: " + "; ".join(problems))
    ctx.batch.status = "running"
    ctx.batch.error_message = None
    ctx.db.commit()
    _complete_stage(ctx, "icp_validation", "ICP validated")

    candidates = _discover(ctx, query)
    accepted = _deduplicate(ctx, candidates)
    _process_candidates(ctx, accepted, query)

    _stage(ctx, "persistence")
    _complete_stage(ctx, "persistence", f"{ctx.batch.total_qualified} prospect row(s) stored")
    _finish_remaining_stages(ctx)
    # An operator may have cancelled during the final stage; never overwrite it.
    _check_cancelled(ctx)
    ctx.batch.status = "completed"
    ctx.batch.current_stage = "completed"
    ctx.batch.completed_at = utcnow()
    ctx.db.commit()


def _seed_stages(ctx: RunContext) -> None:
    for stage in STAGES:
        run = BatchStageRun(
            workspace_id=ctx.workspace.id,
            batch_id=ctx.batch.id,
            stage=stage,
            status="pending",
            attempt=1,
        )
        ctx.db.add(run)
        ctx.db.flush()
        ctx.stage_runs[stage] = run
    ctx.db.commit()


def _stage(ctx: RunContext, stage: str) -> BatchStageRun:
    """Mark a stage as running and make it the batch's current stage."""
    run = ctx.stage_runs[stage]
    if run.status != "completed":
        run.status = "running"
        run.finished_at = None
    ctx.batch.current_stage = stage
    ctx.db.commit()
    return run


def _complete_stage(ctx: RunContext, stage: str, detail: str | None = None) -> None:
    run = ctx.stage_runs[stage]
    run.status = "completed"
    run.finished_at = utcnow()
    run.detail = detail
    ctx.db.commit()


def _finish_remaining_stages(ctx: RunContext) -> None:
    details = {
        "company_research": f"{ctx.researched} company record(s) researched",
        "company_precheck": f"{ctx.prechecked} company record(s) passed pre-checks",
        "decision_maker_discovery": f"{ctx.contacts} decision-maker(s) discovered",
        "contact_enrichment": f"{ctx.enriched} contact record(s) enriched",
        "email_verification": f"{ctx.verified} email(s) independently verified",
        "problem_fit_analysis": f"{ctx.analysed} problem/fit analysis result(s)",
        "final_qualification": (
            f"{ctx.batch.total_qualified} prospect row(s) qualified; "
            f"{ctx.batch.total_rejected} company rejection(s)"
        ),
    }
    for stage in STAGES:
        run = ctx.stage_runs[stage]
        if run.status == "completed":
            continue
        if stage in details:
            run.status = "completed" if run.status == "running" else "skipped"
            run.detail = details[stage]
        else:
            run.status = "skipped"
        run.finished_at = utcnow()
    ctx.db.commit()


def _mark_terminal(
    db: Session, batch: ProspectBatch, *, status: str, detail: str
) -> None:
    try:
        db.rollback()
        stage_name = batch.current_stage
        batch.status = status
        batch.current_stage = status
        batch.error_message = detail[:2000]
        if status == "completed":
            batch.completed_at = utcnow()
        run = (
            db.query(BatchStageRun)
            .filter(
                BatchStageRun.batch_id == batch.id,
                BatchStageRun.stage == stage_name,
            )
            .order_by(BatchStageRun.started_at.desc())
            .first()
        )
        if run is not None:
            run.status = "failed" if status == "failed" else status
            run.detail = detail[:2000]
            run.finished_at = utcnow()
        db.commit()
    except Exception:  # noqa: BLE001 - terminal state must not crash the task
        db.rollback()
        logger.exception("Could not persist terminal state for batch %s", batch.id)


def _check_cancelled(ctx: RunContext) -> None:
    ctx.db.refresh(ctx.batch)
    if ctx.batch.status == "cancelled":
        raise PipelineCancelled("Batch was cancelled by an operator")


def _usage_listener(
    db: Session, workspace_id: uuid.UUID, batch_id: uuid.UUID
) -> Any:
    """Return a listener that persists each usage event on the batch session.

    The pipeline is synchronous, so the same session is safe and avoids SQLite
    write-lock contention between an accounting session and the batch session.
    """

    def persist(event: UsageEvent) -> None:
        try:
            db.add(
                ProviderUsage(
                    workspace_id=workspace_id,
                    batch_id=batch_id,
                    provider=event.provider,
                    capability=event.capability,
                    operation=event.operation,
                    units=event.units,
                    cost_usd=event.cost_usd,
                    success=event.success,
                    attempts=event.attempts,
                    error_message=event.error,
                )
            )
            db.commit()
        except Exception:  # noqa: BLE001 - accounting must not kill the batch
            db.rollback()
            logger.exception("Failed to persist provider usage for batch %s", batch_id)

    return persist


def _discover(ctx: RunContext, query: ICPQuery) -> list[CompanyCandidate]:
    _stage(ctx, "company_discovery")
    requested = max(ctx.batch.requested_prospect_count, 1)
    limit = min(
        ctx.settings.discovery_max_candidates,
        max(requested * ctx.settings.discovery_oversample_factor, requested),
    )
    request = DiscoveryRequest(icp=query, limit=limit)
    discovery = ctx.bundle.discovery
    candidates = ctx.runner.run(
        discovery,
        "discover",
        lambda: discovery.discover(request),
        capability="company_discovery",
    )
    _complete_stage(
        ctx, "company_discovery", f"{len(candidates)} candidate(s) returned by {discovery.name}"
    )
    return candidates


def _deduplicate(
    ctx: RunContext, candidates: list[CompanyCandidate]
) -> list[CompanyCandidate]:
    _stage(ctx, "company_dedup")
    accepted: list[CompanyCandidate] = []
    seen_domains: set[str] = set()
    seen_names: set[str] = set()
    duplicates = 0
    for candidate in candidates:
        domain = normalize_domain(candidate.domain or candidate.website)
        name_key = normalize_company_name(candidate.name)
        if (domain and domain in seen_domains) or (name_key and name_key in seen_names):
            duplicates += 1
            continue
        match = find_company_duplicate(ctx.db, ctx.workspace.id, candidate)
        if match.is_duplicate:
            duplicates += 1
            _record_duplicate(
                ctx,
                candidate,
                match.reason or "duplicate company",
                existing_id=match.existing_id,
            )
            continue
        accepted.append(candidate)
        if domain:
            seen_domains.add(domain)
        if name_key:
            seen_names.add(name_key)
    ctx.batch.total_discovered = len(candidates)
    ctx.batch.total_discovered_companies = len(accepted)
    ctx.db.commit()
    _complete_stage(
        ctx,
        "company_dedup",
        f"{duplicates} duplicate(s) skipped; {len(accepted)} new company record(s)",
    )
    return accepted


def _record_duplicate(
    ctx: RunContext,
    candidate: CompanyCandidate,
    reason: str,
    existing_id: uuid.UUID | None = None,
) -> None:
    """Persist a duplicate company with a rejection record for auditing."""
    company = Company(
        batch_id=ctx.batch.id,
        duplicate_of_id=existing_id,
        name=candidate.name,
        website=candidate.website,
        domain=normalize_domain(candidate.domain or candidate.website),
        normalized_name=normalize_company_name(candidate.name),
        industry=candidate.industry,
        location=candidate.location,
        country=candidate.country,
        city=candidate.city,
        synthetic=candidate.synthetic,
    )
    ctx.db.add(company)
    ctx.db.flush()
    ctx.db.add(
        QualificationRecord(
            workspace_id=ctx.workspace.id,
            batch_id=ctx.batch.id,
            company_id=company.id,
            scope="company",
            status="rejected",
            score=0.0,
            confidence=0.0,
            gates_json=json.dumps(
                [
                    {
                        "name": "no_duplicate",
                        "label": "Not a duplicate",
                        "passed": False,
                        "required": True,
                        "reason": reason,
                    }
                ]
            ),
            reasons=f"Rejected as duplicate: {reason}",
            missing_requirements_json=json.dumps([]),
            evidence_urls_json=json.dumps([]),
            policy_json=json.dumps(ctx.policy.model_dump()),
        )
    )
    ctx.batch.total_rejected += 1
    ctx.db.commit()


def _process_candidates(
    ctx: RunContext, candidates: list[CompanyCandidate], query: ICPQuery
) -> None:
    for candidate in candidates:
        if ctx.batch.total_qualified >= ctx.batch.requested_prospect_count:
            break
        _check_cancelled(ctx)
        exclusion = excluded_company_reason(candidate, ctx.policy)
        if exclusion:
            _record_duplicate(ctx, candidate, exclusion)
            continue
        if _already_checkpointed(ctx, candidate):
            ctx.skipped += 1
            continue
        try:
            result = _process_company(ctx, candidate, query)
        except (BudgetExceeded, PipelineCancelled):
            raise
        except ProviderUnavailable as exc:
            _record_company_error(ctx, candidate, str(exc), capability=True)
            continue
        except EngineError as exc:
            _record_company_error(ctx, candidate, str(exc), capability=False)
            continue
        except Exception as exc:  # noqa: BLE001 - isolate per-company failures
            logger.exception("Company processing failed for %s", candidate.name)
            _record_company_error(
                ctx, candidate, f"unexpected error: {exc}", capability=False
            )
            continue
        ctx.batch.total_enriched += result.prospects_created
        ctx.batch.total_qualified += result.prospects_created
        if result.outcome is not None and not result.outcome.is_qualified:
            ctx.batch.total_rejected += 1
        ctx.db.commit()


def _already_checkpointed(ctx: RunContext, candidate: CompanyCandidate) -> bool:
    existing = _find_company(ctx, candidate)
    if existing is None:
        return False
    return bool(existing.research_records) and bool(existing.qualification_records)


def _find_company(ctx: RunContext, candidate: CompanyCandidate) -> Company | None:
    domain = normalize_domain(candidate.domain or candidate.website)
    name_key = normalize_company_name(candidate.name)
    query = ctx.db.query(Company).filter(Company.batch_id == ctx.batch.id)
    if domain:
        found = query.filter(Company.domain == domain).first()
        if found is not None:
            return found
    if name_key:
        return query.filter(Company.normalized_name == name_key).first()
    return None


def _get_or_create_company(
    ctx: RunContext, candidate: CompanyCandidate
) -> Company:
    existing = _find_company(ctx, candidate)
    if existing is not None:
        return existing
    company = Company(
        batch_id=ctx.batch.id,
        name=candidate.name,
        website=candidate.website,
        domain=normalize_domain(candidate.domain or candidate.website),
        normalized_name=normalize_company_name(candidate.name),
        industry=candidate.industry,
        location=candidate.location,
        country=candidate.country,
        city=candidate.city,
        description=candidate.description,
        products_services=candidate.products_services,
        company_size=candidate.company_size,
        employee_count=candidate.employee_count,
        revenue=candidate.revenue,
        linkedin_url=candidate.linkedin_url,
        instagram_url=candidate.instagram_url,
        source_url=candidate.source_url,
        source_name=candidate.source_name,
        synthetic=candidate.synthetic,
    )
    ctx.db.add(company)
    ctx.db.commit()
    ctx.db.refresh(company)
    return company


def _process_company(
    ctx: RunContext, candidate: CompanyCandidate, query: ICPQuery
) -> CompanyResult:
    company = _get_or_create_company(ctx, candidate)
    _stage(ctx, "company_research")
    research = _research(ctx, candidate, query)
    ctx.researched += 1
    _persist_company(ctx, company, candidate, research)

    _stage(ctx, "company_precheck")
    precheck = evaluate_precheck(
        QualificationInput(
            candidate=candidate,
            research=research,
            decision_makers=[],
            analysis=None,
            icp=query,
        ),
        ctx.policy,
    )
    assessments: list[AssessmentBundle] = []
    analysis: ProblemFitAnalysis | None = None
    capability_note: str | None = None
    if precheck.is_qualified:
        ctx.prechecked += 1
        _stage(ctx, "decision_maker_discovery")
        try:
            assessments = _discover_contacts(ctx, company, candidate, query)
        except ProviderNotConfigured as exc:
            capability_note = str(exc)
        if assessments:
            _stage(ctx, "problem_fit_analysis")
            analysis = _analyze(ctx, candidate, research, query)
            ctx.analysed += 1

    _stage(ctx, "final_qualification")
    final = evaluate(
        QualificationInput(
            candidate=candidate,
            research=research,
            decision_makers=[item.as_assessment() for item in assessments],
            analysis=analysis,
            icp=query,
        ),
        ctx.policy,
    )
    if capability_note and final.status == "rejected":
        final = replace(
            final,
            status="recheck_later",
            reasons=(
                f"{final.reasons} | Required provider not configured: {capability_note}"
            ),
            missing=[*final.missing, "a configured provider for the missing capability"],
        )
    prospects = _persist_outcome(ctx, company, candidate, research, assessments, analysis, final)
    return CompanyResult(candidate=candidate, outcome=final, prospects_created=prospects)


def _research(
    ctx: RunContext, candidate: CompanyCandidate, query: ICPQuery
) -> CompanyResearch:
    provider = ctx.bundle.research
    research = ctx.runner.run(
        provider,
        "research",
        lambda: provider.research(candidate, query),
        capability="company_research",
    )
    return research.model_copy(update={"evidence": sanitize_sources(research.evidence)})


def _discover_contacts(
    ctx: RunContext,
    company: Company,
    candidate: CompanyCandidate,
    query: ICPQuery,
) -> list[AssessmentBundle]:
    provider = ctx.bundle.decision_makers
    discovered = ctx.runner.run(
        provider,
        "discover_decision_makers",
        lambda: provider.discover_decision_makers(candidate, query),
        capability="decision_makers",
    )
    ordered = sorted(discovered, key=lambda item: item.role_priority)[
        :MAX_DECISION_MAKERS_PER_COMPANY
    ]
    ctx.contacts += len(ordered)
    assessments: list[AssessmentBundle] = []
    seen: set[str] = set()
    enrichment_provider = ctx.bundle.enrichment
    for decision_maker in ordered:
        key = normalize_person_name(decision_maker.full_name) or ""
        if key in seen:
            continue
        seen.add(key)
        duplicate = find_decision_maker_duplicate(
            ctx.db,
            ctx.workspace.id,
            decision_maker,
            company_name=candidate.name,
            company_id=company.id,
        )
        if duplicate.is_duplicate:
            continue
        _stage(ctx, "contact_enrichment")

        def _enrich(dm: DecisionMakerCandidate = decision_maker) -> EnrichmentResult:
            return enrichment_provider.enrich(candidate, dm)

        enrichment = ctx.runner.run(
            enrichment_provider,
            "enrich",
            _enrich,
            capability="contact_enrichment",
        )
        ctx.enriched += 1
        _stage(ctx, "email_verification")
        verification = _verify(ctx, enrichment)
        if verification.status == "verified":
            ctx.verified += 1
        assessments.append(
            AssessmentBundle(
                candidate=decision_maker,
                enrichment=enrichment,
                verification=verification,
            )
        )
    return assessments


def _verify(ctx: RunContext, enrichment: EnrichmentResult) -> VerificationResult:
    provider = ctx.bundle.verification
    if not enrichment.email:
        return VerificationResult(
            provider=provider.name,
            email=None,
            status=_status_from_enrichment(enrichment.email_status),
            method="none",
            confidence=0.0,
            detail="No email address was returned by enrichment; nothing to verify.",
        )
    return ctx.runner.run(
        provider,
        "verify",
        lambda: provider.verify(enrichment.email or ""),
        capability="email_verification",
    )


def _status_from_enrichment(status: str) -> EmailStatus:
    """Map an enrichment claim to a verification status.

    An enrichment provider's own "verified" claim is never accepted as
    verification; absent an independent check the status is ``unknown``.
    """
    mapping: dict[str, EmailStatus] = {
        "invalid": "invalid",
        "risky": "risky",
        "not_found": "not_found",
        "provider_unavailable": "provider_unavailable",
        "unknown": "unknown",
    }
    return mapping.get(status, "unknown")


def _build_analyzer(ctx: RunContext) -> ProblemFitAnalyzer:
    if ctx.bundle.analyzer_provider is not None:
        return LLMAnalyzer(ctx.bundle.analyzer_provider)
    return RuleBasedAnalyzer()


def _analyze(
    ctx: RunContext,
    candidate: CompanyCandidate,
    research: CompanyResearch,
    query: ICPQuery,
) -> ProblemFitAnalysis:
    analyzer = _build_analyzer(ctx)
    try:
        return analyzer.analyze(
            company=candidate,
            research=research,
            icp=query,
            client_context=ctx.client_context,
        )
    except EvidenceValidationError as exc:
        note = f"LLM analysis rejected by evidence validation: {exc}"
        ctx.validation_notes.append(note)
        logger.info("Falling back to rule-based analysis: %s", note)
        fallback = RuleBasedAnalyzer().analyze(
            company=candidate,
            research=research,
            icp=query,
            client_context=ctx.client_context,
        )
        return fallback.model_copy(
            update={"validation_notes": [*fallback.validation_notes, note]}
        )


def _persist_company(
    ctx: RunContext,
    company: Company,
    candidate: CompanyCandidate,
    research: CompanyResearch,
) -> None:
    company.description = research.what_it_does or company.description or candidate.description
    company.products_services = company.products_services or candidate.products_services
    company.research_confidence = research.confidence
    company.research_timestamp = research.researched_at
    company.synthetic = candidate.synthetic
    ctx.db.add(
        CompanyResearchRecord(
            workspace_id=ctx.workspace.id,
            batch_id=ctx.batch.id,
            company_id=company.id,
            provider=research.provider,
            what_it_does=research.what_it_does,
            what_it_sells=research.what_it_sells,
            who_it_serves=research.who_it_serves,
            positioning=research.positioning,
            public_developments=research.public_developments,
            observable_signals_json=json.dumps(research.observable_signals),
            evidence_json=json.dumps(
                [source.model_dump(mode="json") for source in research.evidence]
            ),
            missing_information_json=json.dumps(research.missing_information),
            confidence=research.confidence,
            synthetic=research.synthetic,
            research_timestamp=research.researched_at,
        )
    )
    for source in research.evidence:
        ctx.db.add(
            Evidence(
                company_id=company.id,
                label=source.title or source.source_type,
                url=source.url,
                content=source.snippet,
                evidence_type="company_research",
            )
        )
    ctx.db.commit()


def _persist_outcome(
    ctx: RunContext,
    company: Company,
    candidate: CompanyCandidate,
    research: CompanyResearch,
    assessments: list[AssessmentBundle],
    analysis: ProblemFitAnalysis | None,
    outcome: QualificationOutcome,
) -> int:
    dm_rows = [
        (item, _persist_decision_maker(ctx, company, item, index))
        for index, item in enumerate(assessments)
    ]
    ctx.db.add(
        QualificationRecord(
            workspace_id=ctx.workspace.id,
            batch_id=ctx.batch.id,
            company_id=company.id,
            scope="company",
            status=outcome.status,
            score=outcome.score,
            confidence=outcome.confidence,
            gates_json=json.dumps([gate.as_dict() for gate in outcome.gates]),
            reasons=outcome.reasons,
            missing_requirements_json=json.dumps(outcome.missing),
            evidence_urls_json=json.dumps(outcome.evidence_urls),
            policy_json=json.dumps(outcome.policy),
        )
    )
    created = 0
    if outcome.is_qualified:
        for item, dm_row in dm_rows:
            if ctx.batch.total_qualified + created >= ctx.batch.requested_prospect_count:
                break
            if not _prospect_eligible(item, outcome):
                continue
            _create_prospect(
                ctx, company, candidate, research, analysis, outcome, item, dm_row
            )
            created += 1
    ctx.db.commit()
    return created


def _prospect_eligible(item: AssessmentBundle, outcome: QualificationOutcome) -> bool:
    if outcome.status == "qualified":
        return item.verification.status == "verified"
    if outcome.status == "qualified_illustrative":
        return bool(item.candidate.full_name.strip())
    return False


def _persist_decision_maker(
    ctx: RunContext,
    company: Company,
    item: AssessmentBundle,
    index: int,
) -> DecisionMaker:
    verified_at = (
        item.verification.checked_at if item.verification.status == "verified" else None
    )
    row = DecisionMaker(
        company_id=company.id,
        first_name=item.candidate.first_name,
        last_name=item.candidate.last_name,
        full_name=item.candidate.full_name,
        job_title=item.candidate.job_title,
        professional_profile_url=item.candidate.linkedin_url,
        profile_source=item.candidate.profile_source,
        email=item.enrichment.email,
        email_status=item.verification.status,
        email_verified_at=verified_at,
        profile_verified_at=(
            utcnow()
            if item.candidate.linkedin_url and item.candidate.source_url
            else None
        ),
        role_source_url=item.candidate.source_url,
        is_primary=index == 0,
        synthetic=item.candidate.synthetic,
    )
    ctx.db.add(row)
    ctx.db.flush()
    return row


def _create_prospect(
    ctx: RunContext,
    company: Company,
    candidate: CompanyCandidate,
    research: CompanyResearch,
    analysis: ProblemFitAnalysis | None,
    outcome: QualificationOutcome,
    item: AssessmentBundle,
    dm_row: DecisionMaker,
) -> Prospect:
    verified = item.verification.status == "verified"
    missing = _missing_information(research, analysis, item, outcome)
    prospect = Prospect(
        batch_id=ctx.batch.id,
        company_id=company.id,
        decision_maker_id=dm_row.id,
        first_name=item.candidate.first_name,
        last_name=item.candidate.last_name,
        full_name=item.candidate.full_name,
        email=item.enrichment.email if verified else None,
        role=item.candidate.job_title,
        linkedin_url=item.candidate.linkedin_url,
        instagram_url=item.candidate.instagram_url,
        company_name=candidate.name,
        company_website=candidate.website,
        industry=candidate.industry,
        country=candidate.country,
        research_summary=_research_summary(research),
        business_problem=analysis.problem if analysis else None,
        problem_evidence=(
            f"{analysis.problem_inference} Sources: {summarise_sources(research.evidence)}"
            if analysis
            else None
        ),
        solution_match=analysis.fit_explanation if analysis else None,
        qualification_score=outcome.score,
        qualification_reasons=outcome.reasons,
        research_confidence=_research_confidence(research, verified),
        missing_information="; ".join(missing) if missing else None,
        source_links=", ".join(outcome.evidence_urls) or None,
        qualification_status=outcome.status,
        qualification_confidence=outcome.confidence,
        evidence_urls=json.dumps(outcome.evidence_urls),
        synthetic=candidate.synthetic,
        # Illustrative/demo rows are never outreach-ready; only a genuinely
        # qualified company (verified emails, sourced evidence) sets this.
        is_ready_for_outreach=outcome.status == "qualified",
    )
    ctx.db.add(prospect)
    ctx.db.flush()
    for source in research.evidence:
        ctx.db.add(
            Evidence(
                prospect_id=prospect.id,
                company_id=company.id,
                label=source.title or source.source_type,
                url=source.url,
                content=source.snippet,
                evidence_type="company_research",
            )
        )
    ctx.db.add(
        EnrichmentRecord(
            prospect_id=prospect.id,
            provider=item.enrichment.provider,
            email=item.enrichment.email,
            email_status=item.enrichment.email_status,
            email_confidence=item.enrichment.email_confidence,
            linkedin_url=item.enrichment.linkedin_url,
            instagram_url=item.enrichment.instagram_url,
            other_profiles=json.dumps(item.enrichment.other_profiles)
            if item.enrichment.other_profiles
            else None,
            raw_response=item.enrichment.notes,
            fetched_at=utcnow(),
        )
    )
    ctx.db.add(
        VerificationRecord(
            prospect_id=prospect.id,
            email=item.verification.email,
            status=item.verification.status,
            provider=item.verification.provider,
            details=item.verification.detail,
            verified_at=item.verification.checked_at,
        )
    )
    ctx.db.add(
        QualificationRecord(
            workspace_id=ctx.workspace.id,
            batch_id=ctx.batch.id,
            company_id=company.id,
            prospect_id=prospect.id,
            scope="prospect",
            status=outcome.status,
            score=outcome.score,
            confidence=outcome.confidence,
            gates_json=json.dumps([gate.as_dict() for gate in outcome.gates]),
            reasons=outcome.reasons,
            missing_requirements_json=json.dumps(missing),
            evidence_urls_json=json.dumps(outcome.evidence_urls),
            policy_json=json.dumps(outcome.policy),
        )
    )
    return prospect


def _missing_information(
    research: CompanyResearch,
    analysis: ProblemFitAnalysis | None,
    item: AssessmentBundle,
    outcome: QualificationOutcome,
) -> list[str]:
    missing: list[str] = []
    for value in [
        *outcome.missing,
        *research.missing_information,
        *(analysis.missing_information if analysis else []),
    ]:
        if value and value not in missing:
            missing.append(value)
    if item.verification.status != "verified":
        missing.append(
            f"email not verified (status: {item.verification.status})"
        )
    if not item.candidate.linkedin_url:
        missing.append("no verified LinkedIn/social profile URL")
    return missing


def _research_summary(research: CompanyResearch) -> str | None:
    parts = [
        value
        for value in (
            research.what_it_does,
            research.what_it_sells,
            research.who_it_serves,
            research.positioning,
        )
        if value
    ]
    if not parts:
        return None
    return " | ".join(parts)[:2000]


def _research_confidence(research: CompanyResearch, verified_email: bool) -> str:
    if research.synthetic:
        return f"unverified (synthetic demo) | sources={len(research.evidence)}"
    prefix = "verified email" if verified_email else "unverified email"
    return (
        f"{prefix}; research confidence {research.confidence:.2f} "
        f"| sources={len(research.evidence)}"
    )


def _record_company_error(
    ctx: RunContext, candidate: CompanyCandidate, reason: str, *, capability: bool
) -> None:
    """Persist a company that could not be processed, without inventing data."""
    try:
        ctx.db.rollback()
        company = _get_or_create_company(ctx, candidate)
        status: QualificationStatus = "recheck_later" if capability else "rejected"
        ctx.db.add(
            QualificationRecord(
                workspace_id=ctx.workspace.id,
                batch_id=ctx.batch.id,
                company_id=company.id,
                scope="company",
                status=status,
                score=0.0,
                confidence=0.0,
                gates_json=json.dumps(
                    [
                        {
                            "name": "provider_execution",
                            "label": "Provider execution",
                            "passed": False,
                            "required": True,
                            "reason": reason,
                            "blocked_by_capability": capability,
                        }
                    ]
                ),
                reasons=(
                    f"{'Deferred for re-check' if capability else 'Rejected'}: {reason}"
                ),
                missing_requirements_json=json.dumps(
                    ["provider capability"] if capability else []
                ),
                evidence_urls_json=json.dumps([]),
                policy_json=json.dumps(ctx.policy.model_dump()),
            )
        )
        ctx.batch.total_rejected += 1
        ctx.db.commit()
    except Exception:  # noqa: BLE001 - never let recording abort the batch
        ctx.db.rollback()
        logger.exception("Could not record company failure for %s", candidate.name)


def batch_progress(batch: ProspectBatch) -> dict[str, Any]:
    """Return a progress snapshot for the API layer."""
    runs = sorted(
        batch.stage_runs,
        key=lambda run: run.started_at.isoformat() if run.started_at else "",
    )
    latest: dict[str, BatchStageRun] = {}
    for run in runs:
        latest[run.stage] = run
    ordered = [latest[stage] for stage in STAGES if stage in latest]
    completed = sum(
        1 for run in ordered if run.status in ("completed", "skipped")
    )
    percent = round(completed / len(STAGES) * 100, 1) if STAGES else 0.0
    return {
        "percent": percent,
        "stages": [
            {
                "stage": run.stage,
                "status": run.status,
                "detail": run.detail,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            }
            for run in ordered
        ],
    }
