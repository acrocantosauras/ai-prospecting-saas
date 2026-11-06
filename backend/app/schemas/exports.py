"""Outreach lead export schemas - mapping to Samprat's n8n expected fields."""

import uuid

from pydantic import BaseModel, Field


class LeadExportRow(BaseModel):
    lead_id: str
    first_name: str | None
    last_name: str | None
    email: str | None
    company: str | None
    website: str | None
    role: str | None
    client_id: str
    status: str = "new"
    draft_date: str | None = None
    notes: str | None = None


class LeadExportValidationError(Exception):
    pass
