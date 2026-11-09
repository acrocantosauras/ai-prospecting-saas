"""Tenant-scoped deduplication for companies and decision-makers.

Every query is scoped through ``ProspectBatch.workspace_id`` so two tenants can
own the same company, person or email without interfering with each other.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.engine.contracts import CompanyCandidate, DecisionMakerCandidate
from app.engine.normalization import (
    normalize_company_name,
    normalize_domain,
    normalize_person_name,
    normalize_url,
)
from app.models import Company, DecisionMaker, ProspectBatch

MAX_SCAN_ROWS = 5000


@dataclass(frozen=True)
class DuplicateMatch:
    """Outcome of a duplicate lookup."""

    is_duplicate: bool
    matched_on: str | None = None
    existing_id: uuid.UUID | None = None
    reason: str | None = None


def _workspace_companies(db: Session, workspace_id: uuid.UUID) -> list[Company]:
    return (
        db.query(Company)
        .join(ProspectBatch, Company.batch_id == ProspectBatch.id)
        .filter(ProspectBatch.workspace_id == workspace_id)
        .limit(MAX_SCAN_ROWS)
        .all()
    )


def find_company_duplicate(
    db: Session, workspace_id: uuid.UUID, candidate: CompanyCandidate
) -> DuplicateMatch:
    """Return a match when the company already exists for this workspace.

    Matching uses a normalized domain first (authoritative) and a normalized
    name with legal suffixes removed second. Legacy rows whose new columns are
    null are normalized on the fly, so old data participates in deduplication.
    """
    domain = normalize_domain(candidate.domain or candidate.website)
    name_key = normalize_company_name(candidate.name)
    for existing in _workspace_companies(db, workspace_id):
        existing_domain = normalize_domain(existing.domain or existing.website)
        if domain and existing_domain and domain == existing_domain:
            return DuplicateMatch(
                True,
                "domain",
                existing.id,
                f"company domain {domain} already exists in this workspace",
            )
        existing_name = normalize_company_name(existing.normalized_name or existing.name)
        if name_key and existing_name and name_key == existing_name:
            return DuplicateMatch(
                True,
                "name",
                existing.id,
                f"company name '{candidate.name}' already exists in this workspace",
            )
    return DuplicateMatch(False)


def find_decision_maker_duplicate(
    db: Session,
    workspace_id: uuid.UUID,
    candidate: DecisionMakerCandidate,
    *,
    company_name: str | None,
    company_id: uuid.UUID | None = None,
) -> DuplicateMatch:
    """Return a match for an existing decision-maker in this workspace."""
    linkedin = normalize_url(candidate.linkedin_url)
    person_key = normalize_person_name(candidate.full_name)
    company_key = normalize_company_name(company_name)
    rows = (
        db.query(DecisionMaker)
        .join(Company, DecisionMaker.company_id == Company.id)
        .join(ProspectBatch, Company.batch_id == ProspectBatch.id)
        .filter(ProspectBatch.workspace_id == workspace_id)
        .limit(MAX_SCAN_ROWS)
        .all()
    )
    for existing in rows:
        existing_linkedin = normalize_url(existing.professional_profile_url)
        if linkedin and existing_linkedin and linkedin == existing_linkedin:
            return DuplicateMatch(
                True, "linkedin", existing.id, "LinkedIn profile already stored"
            )
        existing_company_key = normalize_company_name(
            existing.company.name if existing.company else None
        )
        if (
            person_key
            and company_key
            and existing_company_key
            and normalize_person_name(existing.full_name) == person_key
            and existing_company_key == company_key
        ):
            return DuplicateMatch(
                True,
                "person",
                existing.id,
                f"{candidate.full_name} at {company_name} already exists in this workspace",
            )
        if company_id is not None and existing.company_id == company_id:
            if normalize_person_name(existing.full_name) == person_key:
                return DuplicateMatch(
                    True, "person", existing.id, "decision-maker already stored for company"
                )
    return DuplicateMatch(False)
