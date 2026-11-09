"""Export API endpoints: CSV and Google Sheets export for Outreach handoff.

The workspace comes from the authenticated membership; a batch from another
workspace returns 404 and the CSV contract stays exactly the 11-column Outreach
format.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import WorkspaceCtx, ensure_permission
from app.auth.permissions import Permission
from app.config import get_settings
from app.core.database import get_db
from app.models import Prospect, ProspectBatch, Workspace
from app.services.exports import build_lead_rows, format_csv, validate_lead_row

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


def _get_batch(db: Session, batch_id: uuid.UUID, workspace: Workspace) -> ProspectBatch:
    """Return a batch from this workspace, or raise 404."""
    batch = (
        db.query(ProspectBatch)
        .filter(
            ProspectBatch.id == batch_id,
            ProspectBatch.workspace_id == workspace.id,
        )
        .first()
    )
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found"
        )
    return batch


def _exportable_prospects(batch: ProspectBatch, include_all: bool) -> list[Prospect]:
    """Ready prospects by default; every prospect when explicitly requested.

    Prospects are never invented or padded: if only 12 of 100 qualify, only 12
    rows are exported. Demo/illustrative rows and synthetic records are excluded
    from the default (production) export path and require ``include_all=true``.
    """
    prospects = list(batch.prospects)
    if not include_all:
        prospects = [
            p
            for p in prospects
            if p.is_ready_for_outreach is True
            and p.qualification_status != "qualified_illustrative"
            and p.synthetic is not True
        ]
    return prospects


@router.get("/csv/{batch_id}")
def export_csv(
    batch_id: uuid.UUID,
    ctx: WorkspaceCtx,
    db: DbSession,
    include_all: bool = Query(False, alias="include_all"),
) -> Response:
    """Download prospects from a batch as a CSV in the Outreach Leads tab format."""
    ensure_permission(ctx, Permission.EXPORT_PROSPECTS)
    workspace = ctx.workspace
    batch = _get_batch(db, batch_id, workspace)
    prospects = _exportable_prospects(batch, include_all)
    if not prospects:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No prospects available for export. Qualify prospects or export with include_all=true.",
        )
    rows = build_lead_rows(prospects, str(workspace.id), str(batch.id))
    for row in rows:
        if not validate_lead_row(row):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lead row invalid for export: {row.company}",
            )
    csv_content = format_csv(rows)
    return Response(
        content=csv_content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="batch-{batch.id}-leads.csv"'},
    )


@router.get("/preview/{batch_id}")
def export_preview(
    batch_id: uuid.UUID,
    ctx: WorkspaceCtx,
    db: DbSession,
    include_all: bool = Query(False, alias="include_all"),
) -> dict:
    """Return lead rows as JSON for preview/debugging."""
    ensure_permission(ctx, Permission.EXPORT_PROSPECTS)
    workspace = ctx.workspace
    batch = _get_batch(db, batch_id, workspace)
    prospects = _exportable_prospects(batch, include_all)
    rows = build_lead_rows(prospects, str(workspace.id), str(batch.id))
    return {"batch_id": str(batch.id), "count": len(rows), "rows": rows}


@router.post("/google-sheets/{batch_id}")
def export_to_google_sheets(
    batch_id: uuid.UUID,
    ctx: WorkspaceCtx,
    db: DbSession,
    include_all: bool = Query(False, alias="include_all"),
) -> dict:
    """Push lead rows to the configured Google Sheets Leads tab.

    Requires GOOGLE_SHEETS_ENABLED=true and valid credentials configured.
    This path has not been exercised against a live sheet in this repo.

    Batch ownership and workspace visibility are validated before the
    configuration check so cross-tenant access always returns 404 rather than
    leaking that another tenant's batch exists or that Sheets is configured.
    """
    ensure_permission(ctx, Permission.EXPORT_PROSPECTS)
    workspace = ctx.workspace
    batch = _get_batch(db, batch_id, workspace)
    s = get_settings()
    if not s.is_google_sheets_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Sheets integration is not configured. Set GOOGLE_SHEETS_ENABLED=true and provide credentials.",
        )
    prospects = _exportable_prospects(batch, include_all)
    if not prospects:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No prospects available for export")
    rows = build_lead_rows(prospects, str(workspace.id), str(batch.id))
    for row in rows:
        if not validate_lead_row(row):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lead row invalid for export: {row.company}",
            )
    from app.services.google_sheets import push_leads_to_sheet

    result = push_leads_to_sheet(rows, s.google_sheet_id, s.google_sheet_tab_name)
    if result.get("status") != "ok":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("message") or "Google Sheets write failed",
        )
    return {
        "batch_id": str(batch.id),
        "count": len(rows),
        "status": result.get("status"),
        "message": result.get("message"),
    }
