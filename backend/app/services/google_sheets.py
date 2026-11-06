"""Google Sheets integration service.

Uses the official Google Sheets API. This integration is optional and only
active when GOOGLE_SHEETS_ENABLED=true and credentials are configured.

Credentials are loaded from a service account JSON path specified via
GOOGLE_CREDENTIALS_PATH, or from GOOGLE_APPLICATION_CREDENTIALS.
"""

from typing import Any

from app.config import settings as app_settings


def _get_credentials() -> Any:
    """Load Google service account credentials if configured."""
    from google.oauth2 import service_account

    creds_path = app_settings.google_credentials_path or ""
    if not creds_path:
        import os
        creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not creds_path:
        raise RuntimeError("Google credentials path not configured")
    credentials = service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
        ],
    )
    return credentials


def _get_sheets_service() -> Any:
    """Build a Google Sheets API service client."""
    from googleapiclient.discovery import build

    credentials = _get_credentials()
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    return service


def push_leads_to_sheet(
    rows: list[dict[str, Any]],
    sheet_id: str,
    tab_name: str,
) -> dict[str, Any]:
    """Append lead rows to the configured Google Sheets tab.

    Returns a status dict. Raises on API errors.
    """
    service = _get_sheets_service()
    sheet = service.spreadsheets()
    values = [_normalize_row(row) for row in rows]
    body = {"values": values}
    try:
        response = (
            sheet.values()
            .append(
                spreadsheetId=sheet_id,
                range=f"{tab_name}!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )
        updates = response.get("updates", {})
        return {
            "status": "ok",
            "message": f"Appended {len(values)} row(s)",
            "updated_rows": updates.get("updatedRows"),
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Google Sheets write failed: {exc!s}",
        }


def _normalize_row(row: dict[str, Any]) -> list[Any]:
    """Convert a lead row dict into an ordered list of cell values."""
    ordered_keys = [
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
    return [row.get(key) for key in ordered_keys]
