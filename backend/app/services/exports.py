"""Export service - builds Outreach-compatible lead rows and CSV output."""

import uuid
from datetime import datetime, timezone

from app.models import Prospect
from app.schemas.exports import LeadExportRow


def build_lead_rows(
    prospects: list[Prospect],
    workspace_id: str,
    batch_id: str,
) -> list[LeadExportRow]:
    """Map internal Prospect records to the Outreach Leads tab schema.

    lead_id must be unique and stable.
    status must be "new" for newly created prospects.
    draft_date must be empty for new records.
    """
    rows = []
    for prospect in prospects:
        first_name, last_name = _split_name(prospect.first_name, prospect.last_name, prospect.full_name)
        notes_parts: list[str] = []
        if prospect.business_problem:
            notes_parts.append(f"Problem: {prospect.business_problem}")
        if prospect.solution_match:
            notes_parts.append(f"Fit: {prospect.solution_match}")
        if prospect.research_summary:
            notes_parts.append(f"Research: {prospect.research_summary}")
        if prospect.missing_information:
            notes_parts.append(f"Missing: {prospect.missing_information}")
        notes = " | ".join(notes_parts) if notes_parts else None
        row = LeadExportRow(
            lead_id=_build_lead_id(prospect),
            first_name=first_name,
            last_name=last_name,
            email=prospect.email,
            company=prospect.company_name or (prospect.company.name if prospect.company else None),
            website=prospect.company_website or (prospect.company.website if prospect.company else None),
            role=prospect.role or (prospect.decision_maker.job_title if prospect.decision_maker else None),
            client_id=workspace_id,
            status="new",
            draft_date=None,
            notes=notes,
        )
        rows.append(row)
    return rows


def _build_lead_id(prospect: Prospect) -> str:
    """Produce a stable, unique lead_id from the prospect UUID."""
    return f"PROSPECT-{prospect.id}"


def _split_name(first_name: str | None, last_name: str | None, full_name: str | None):
    """Split a full name into first/last when first/last are missing."""
    if first_name and last_name:
        return first_name, last_name
    if full_name:
        parts = full_name.strip().split()
        if len(parts) >= 2:
            return parts[0], " ".join(parts[1:])
        return parts[0], None
    return first_name, last_name


def validate_lead_row(row: LeadExportRow) -> bool:
    """Return True if the row has the minimum fields required for Outreach."""
    if not row.lead_id:
        return False
    if not row.company:
        return False
    if not row.role:
        return False
    if not row.client_id:
        return False
    if row.status != "new":
        return False
    if row.draft_date:
        return False
    return True


def format_csv(rows: list[LeadExportRow]) -> str:
    """Format lead rows as CSV using the exact expected column order."""
    import csv
    import io

    fieldnames = [
        "lead_id",
        "first_name",
        "last_name",
        "email",
        "company",
        "website",
        "role",
        "client_id",
        "status",
        "draft_date",
        "notes",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row.model_dump())
    return output.getvalue()
