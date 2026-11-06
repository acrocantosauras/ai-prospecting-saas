"""Export API endpoints: CSV and Google Sheets export for Outreach handoff."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import Response

from app.config import get_settings
from app.core.database import get_db
from app.models import Prospect, Workspace, ProspectBatch
from app.services.exports import build_lead_rows, validate_lead_row, format_csv

router = APIRouter()


def _get_workspace(db, workspace_slug: str) -> Workspace:
    ws = db.query(Workspace).filter(Workspace.slug == workspace_slug).first()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return ws


def _get_batch(db, batch_id: uuid.UUID, workspace: Workspace) -> ProspectBatch:
    batch = (
        db.query(ProspectBatch)
        .filter(ProspectBatch.id == batch_id, ProspectBatch.workspace_id == workspace.id)
        .first()
    )
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
    return batch


def _exportable_prospects(batch: ProspectBatch, include_all: bool) -> list[Prospect]:
    """Ready prospects by default; every prospect when explicitly requested.

    Prospects are never invented or padded: if only 12 of 100 qualify, only 12
    rows are exported.
    """
    prospects = list(batch.prospects)
    if not include_all:
        prospects = [p for p in prospects if p.is_ready_for_outreach is True]
    return prospects


@router.get("/csv/{batch_id}")
def export_csv(
    batch_id: uuid.UUID,
    workspace_slug: str,
    include_all: bool = Query(False, alias="include_all"),
    db=Depends(get_db),
):
    """Download prospects from a batch as a CSV in the Outreach Leads tab format."""
    workspace = _get_workspace(db, workspace_slug)
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
    workspace_slug: str,
    include_all: bool = Query(False, alias="include_all"),
    db=Depends(get_db),
):
    """Return lead rows as JSON for preview/debugging."""
    workspace = _get_workspace(db, workspace_slug)
    batch = _get_batch(db, batch_id, workspace)
    prospects = _exportable_prospects(batch, include_all)
    rows = build_lead_rows(prospects, str(workspace.id), str(batch.id))
    return {"batch_id": str(batch.id), "count": len(rows), "rows": rows}


@router.post("/google-sheets/{batch_id}")
def export_to_google_sheets(
    batch_id: uuid.UUID,
    workspace_slug: str,
    include_all: bool = Query(False, alias="include_all"),
    db=Depends(get_db),
):
    """Push lead rows to the configured Google Sheets Leads tab.

    Requires GOOGLE_SHEETS_ENABLED=true and valid credentials configured.
    This path has not been exercised against a live sheet in this repo.
    """
    s = get_settings()
    if not s.is_google_sheets_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Sheets integration is not configured. Set GOOGLE_SHEETS_ENABLED=true and provide credentials.",
        )
    workspace = _get_workspace(db, workspace_slug)
    batch = _get_batch(db, batch_id, workspace)
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
