"""Prospecting pipeline - orchestrates discovery, research, enrichment, and qualification."""

import logging
import uuid
from typing import Any

from app.config.settings import settings as _settings_fn
from app.core.database import SessionLocal
from app.models import (
    ProspectBatch,
    Company,
    DecisionMaker,
    Prospect,
    Evidence,
    EnrichmentRecord,
    VerificationRecord,
)
# Also import all models to ensure Base.metadata has them registered
# (avoid 'no such table' errors when pipeline runs in background task)
import app.models  # noqa: F401
from app.providers.base import ProviderRegistry
from app.schemas.icp_profile import ICPProfileResponse
from app.schemas.client_profile import ClientProfileResponse

# top-level aliases to avoid UnboundLocalError when helper functions import from app.models
_ClientProfile = ClientProfileResponse
_ICPProfile = ICPProfileResponse
__models_client = None
__models_icp = None

def _get_settings():
    return _settings_fn()

app_settings = _get_settings()

logger = logging.getLogger(__name__)

STAGES = [
    "configured",
    "discovering_companies",
    "researching_companies",
    "discovering_decision_makers",
    "enriching_contacts",
    "identifying_problems",
    "matching_solutions",
    "qualifying",
    "completed",
]


def get_registry() -> ProviderRegistry:
    """Build the provider registry based on configuration."""
    registry = ProviderRegistry()
    if app_settings.ai_provider == "openai":
        registry.use_openai()
    else:
        registry.use_demo()
    return registry


def _ensure_stage(db, batch: ProspectBatch, stage: str) -> None:
    """Persist a stage transition so the UI can poll meaningful progress."""
    batch.current_stage = stage
    batch.status = "running"
    db.commit()


def _get_client_profile(db, profile_id: uuid.UUID | None) -> ClientProfileResponse | None:
    if not profile_id:
        return None
    from app.models import ClientProfile as _ClientProfile2
    profile = db.query(_ClientProfile2).filter(_ClientProfile2.id == profile_id).first()
    if not profile:
        return None
    return ClientProfileResponse.model_validate(profile)


def _get_icp_profile(db, icp_id: uuid.UUID) -> ICPProfileResponse:
    from app.models import ICPProfile as _ICPProfile2
    icp = db.query(_ICPProfile2).filter(_ICPProfile2.id == icp_id).first()
    if not icp:
        raise ValueError("ICP profile not found")
    return ICPProfileResponse.model_validate(icp)


def run_prospecting_pipeline(batch_id: str, workspace_slug: str) -> None:
    """Background task that executes the full prospecting journey."""
    db = SessionLocal()
    batch = None
    try:
        batch = (
            db.query(ProspectBatch)
            .filter(ProspectBatch.id == uuid.UUID(batch_id))
            .first()
        )
        if not batch:
            logger.error("Batch not found: %s", batch_id)
            return

        registry = get_registry()
        client_profile = _get_client_profile(db, batch.client_profile_id)
        icp_profile = _get_icp_profile(db, batch.icp_profile_id)
        icp_dict = icp_profile.model_dump()
        client_dict = client_profile.model_dump() if client_profile else {}

        _ensure_stage(db, batch, STAGE_NAMES[0])
        logger.info("Starting prospecting batch %s", batch.id)

        # Stage 1: Company discovery
        db.commit()
        _ensure_stage(db, batch, STAGE_NAMES[1])
        companies = registry.company_discovery.discover(icp_dict, batch.requested_prospect_count)
        batch.total_discovered = len(companies)
        db.commit()
        logger.info("Discovered %d companies", len(companies))

        if not companies:
            batch.status = "failed"
            batch.error_message = "No companies discovered"
            db.commit()
            return

        # Stage 2: Research each company
        _ensure_stage(db, batch, STAGE_NAMES[2])
        researched = 0
        for company_data in companies:
            research = registry.company_research.research(company_data)
            company = Company(
                batch_id=batch.id,
                name=company_data.get("name"),
                website=company_data.get("website"),
                industry=company_data.get("industry"),
                location=company_data.get("location"),
                country=company_data.get("country"),
                city=company_data.get("city"),
                description=company_data.get("description"),
                products_services=company_data.get("products_services"),
                company_size=company_data.get("company_size"),
                employee_count=company_data.get("employee_count"),
                revenue=company_data.get("revenue"),
                linkedin_url=company_data.get("linkedin_url"),
                instagram_url=company_data.get("instagram_url"),
                source_url=company_data.get("source_url"),
                source_name=company_data.get("source_name") or "Synthetic Demo Provider",
            )
            db.add(company)
            db.flush()
            if research.get("source_urls"):
                for url in research["source_urls"]:
                    if url:
                        ev = Evidence(
                            company_id=company.id,
                            url=url,
                            evidence_type="source",
                            label="Company source",
                        )
                        db.add(ev)
            researched += 1
        batch.total_researched = researched
        db.commit()
        logger.info("Researched %d companies", researched)

        # Stage 3: Decision-maker discovery
        _ensure_stage(db, batch, STAGE_NAMES[3])
        researched = 0
        decision_makers: list[DecisionMaker] = []
        # Never over-deliver: the provider returns several roles per company,
        # so stop once the batch's requested prospect count is reached.
        remaining = max(0, batch.requested_prospect_count)
        for company in batch.companies:
            if remaining <= 0:
                break
            dms = registry.decision_maker_discovery.discover_decision_makers(
                {
                    "name": company.name,
                    "website": company.website,
                    "industry": company.industry,
                    "linkedin_url": company.linkedin_url,
                    "synthetic": True,
                },
                icp_dict,
            )
            for idx, dm_data in enumerate(dms[:remaining]):
                remaining -= 1
                dm = DecisionMaker(
                    company_id=company.id,
                    first_name=dm_data.get("first_name"),
                    last_name=dm_data.get("last_name"),
                    full_name=dm_data.get("full_name"),
                    job_title=dm_data.get("job_title"),
                    professional_profile_url=dm_data.get("professional_profile_url"),
                    profile_source=dm_data.get("profile_source"),
                    is_primary=(idx == 0),
                )
                db.add(dm)
                decision_makers.append(dm)
            researched += 1
        db.commit()
        logger.info("Discovered decision makers for %d companies", researched)

        # Stage 4: Contact enrichment
        _ensure_stage(db, batch, STAGE_NAMES[4])
        enriched = 0
        for company in batch.companies:
            for dm in company.decision_makers:
                prospect = Prospect(
                    batch_id=batch.id,
                    company_id=company.id,
                    decision_maker_id=dm.id,
                    first_name=dm.first_name,
                    last_name=dm.last_name,
                    full_name=dm.full_name,
                    role=dm.job_title,
                    company_name=company.name,
                    company_website=company.website,
                    industry=company.industry,
                    country=company.country,
                    linkedin_url=dm.professional_profile_url,
                    research_confidence="unverified",
                    source_links=company.linkedin_url or company.website,
                )
                db.add(prospect)
                db.flush()
                enrichment = registry.contact_enrichment.enrich({
                    "email": prospect.email,
                    "linkedin_url": prospect.linkedin_url,
                    "instagram_url": prospect.instagram_url,
                    "synthetic": True,
                })
                if enrichment.get("email"):
                    prospect.email = enrichment["email"]
                if enrichment.get("linkedin_url"):
                    prospect.linkedin_url = enrichment["linkedin_url"]
                if enrichment.get("instagram_url"):
                    prospect.instagram_url = enrichment["instagram_url"]
                er = EnrichmentRecord(
                    prospect_id=prospect.id,
                    provider="demo",
                    provider_record_id=None,
                    email=enrichment.get("email"),
                    email_status=enrichment.get("email_status"),
                    email_confidence=enrichment.get("email_confidence"),
                    linkedin_url=enrichment.get("linkedin_url"),
                    instagram_url=enrichment.get("instagram_url"),
                    other_profiles=enrichment.get("other_profiles"),
                    raw_response=enrichment.get("raw_response"),
                )
                db.add(er)
                if enrichment.get("email_status") == "verified_deliverable":
                    prospect.research_confidence = "verified (synthetic demo)"
                elif enrichment.get("email_status") in ("invalid", "unavailable"):
                    prospect.research_confidence = "invalid/unavailable (synthetic demo)"
                enriched += 1
        batch.total_enriched = enriched
        db.commit()
        logger.info("Enriched %d prospects", enriched)

        # Stage 5: Problem identification
        _ensure_stage(db, batch, STAGE_NAMES[5])
        researched = 0
        for prospect in batch.prospects:
            company = prospect.company
            research = registry.company_research.research({
                "name": company.name if company else "Unknown",
                "industry": company.industry if company else None,
                "description": company.description if company else None,
                "products_services": company.products_services if company else None,
                "synthetic": True,
            })
            problem = _identify_problem(prospect, research, client_dict)
            prospect.business_problem = problem.get("problem")
            prospect.problem_evidence = problem.get("evidence")
            prospect.research_summary = research.get("what_it_does", "")
            missing: list[str] = []
            if not prospect.email:
                missing.append("email address not available")
            if not prospect.linkedin_url:
                missing.append("LinkedIn profile not available")
            missing.append("company facts are synthetic demo data, not verified")
            prospect.missing_information = "; ".join(missing)
            er = Evidence(
                prospect_id=prospect.id,
                company_id=company.id if company else None,
                url=research.get("source_urls", [])[0] if research.get("source_urls") else None,
                evidence_type="research",
                label="Research summary",
                content=research.get("what_it_does", ""),
            )
            db.add(er)
            researched += 1
        db.commit()
        logger.info("Identified problems for %d prospects", researched)

        # Stage 6: Client-solution matching
        _ensure_stage(db, batch, STAGE_NAMES[6])
        researched = 0
        for prospect in batch.prospects:
            match = _match_solution(prospect, client_dict)
            prospect.solution_match = match.get("solution_match")
            researched += 1
        db.commit()
        logger.info("Matched solutions for %d prospects", researched)

        # Stage 7: Qualification
        _ensure_stage(db, batch, STAGE_NAMES[7])
        qualified = 0
        for prospect in batch.prospects:
            score_result = _qualify(prospect, icp_dict, client_dict)
            prospect.qualification_score = score_result.get("score", 0.0)
            prospect.qualification_reasons = score_result.get("reasons", "")
            prospect.is_ready_for_outreach = score_result.get("ready", False)
            if prospect.is_ready_for_outreach:
                qualified += 1
        batch.total_qualified = qualified
        db.commit()
        logger.info("Qualified %d prospects", qualified)

        # Completed
        batch.status = "completed"
        batch.current_stage = STAGE_NAMES[8]
        from datetime import datetime, timezone
        batch.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Batch %s completed", batch.id)

    except Exception as exc:
        logger.exception("Prospecting pipeline failed for batch %s", batch_id)
        try:
            if batch is not None:
                batch.status = "failed"
                batch.error_message = f"Pipeline error: {type(exc).__name__}"
                db.commit()
        except Exception:
            logger.exception("Could not mark batch %s as failed", batch_id)
    finally:
        db.close()


STAGE_NAMES = [
    "configured",
    "discovering_companies",
    "researching_companies",
    "discovering_decision_makers",
    "enriching_contacts",
    "identifying_problems",
    "matching_solutions",
    "qualifying",
    "completed",
]


def _identify_problem(prospect: Prospect, research: dict[str, Any], client: dict[str, Any]) -> dict[str, Any]:
    """Identify a credible business problem grounded in available data."""
    challenges = research.get("observable_challenges", "")
    what_it_does = research.get("what_it_does", "")
    problem = (
        f"The prospect operates in the {prospect.industry or 'relevant'} sector. "
        f"{what_it_does} "
        f"{challenges} "
        f"As a synthetic demo record, this problem is illustrative rather than verified."
    )
    evidence = (
        f"Based on synthetic demo research for {prospect.company_name}. "
        f"Research confidence: {prospect.research_confidence}. "
        f"Observed challenges: {challenges}"
    )
    return {"problem": problem, "evidence": evidence}


def _match_solution(prospect: Prospect, client: dict[str, Any]) -> dict[str, Any]:
    """Explain why the client's offering fits this prospect."""
    client_name = client.get("name")
    client_offer = client.get("products_services") or "product/service offering"
    client_value = client.get("value_proposition") or "value proposition"
    problem = prospect.business_problem or ""
    fit = (
        f"{client_name} may be relevant to {prospect.company_name} because its {client_offer} "
        f"aligns with the prospect's needs. {client_value}. "
        f"This is a synthetic demo match and should be reviewed before outreach."
    )
    return {"solution_match": fit}


def _qualify(prospect: Prospect, icp: dict[str, Any], client: dict[str, Any]) -> dict[str, Any]:
    """Compute a transparent qualification score."""
    reasons: list[str] = []
    score = 0.0

    # Industry match
    industry = (icp.get("target_industries") or "").lower()
    prospect_industry = (prospect.industry or "").lower()
    if industry and prospect_industry and industry in prospect_industry:
        score += 15
        reasons.append("Industry match")
    elif prospect_industry:
        score += 5
        reasons.append("Partial industry relevance")

    # Geographic match
    countries = (icp.get("target_countries") or "").lower()
    prospect_country = (prospect.country or "").lower()
    if countries and prospect_country and prospect_country in countries:
        score += 10
        reasons.append("Geographic match")
    elif prospect_country:
        score += 3
        reasons.append("Partial geographic relevance")

    # Company size match
    size = icp.get("company_size") or ""
    company_size = prospect.company.company_size if prospect.company else ""
    if size and company_size and size.lower() == company_size.lower():
        score += 10
        reasons.append("Company size match")
    elif company_size:
        score += 4
        reasons.append("Partial size relevance")

    # Decision-maker relevance
    role = (prospect.role or "").lower()
    target_roles = (icp.get("decision_maker_roles") or "").lower()
    if target_roles and role:
        role_keywords = [r.strip().lower() for r in target_roles.replace(";", ",").split(",")]
        if any(k in role for k in role_keywords):
            score += 10
            reasons.append("Decision-maker relevance")
        else:
            score += 2
            reasons.append("Decision-maker present but role not targeted")
    else:
        score += 2
        reasons.append("Decision-maker identified")

    # Business problem relevance
    if prospect.business_problem:
        score += 10
        reasons.append("Business problem identified")
    else:
        score += 1
        reasons.append("No business problem identified")

    # Solution fit
    if prospect.solution_match:
        score += 10
        reasons.append("Solution match available")
    else:
        score += 1
        reasons.append("No solution match")

    # Research confidence
    conf = (prospect.research_confidence or "").lower()
    if "verified" in conf or "deliverable" in conf:
        score += 5
        reasons.append("Verified enrichment")
    elif "unverified" in conf:
        score += 2
        reasons.append("Unverified enrichment")
    elif "invalid" in conf or "unavailable" in conf:
        score += 0
        reasons.append("Unreliable contact data")

    # Contact data quality
    if prospect.email:
        score += 5
        reasons.append("Email available")
    else:
        score += 0
        reasons.append("No email")

    if prospect.linkedin_url:
        score += 3
        reasons.append("LinkedIn available")

    reasons_text = "; ".join(reasons)
    # Missing contact details are recorded in missing_information instead of
    # blocking qualification or fabricating an address.
    ready = bool(prospect.business_problem and prospect.solution_match and score >= 30)
    return {"score": score, "reasons": reasons_text, "ready": ready}
