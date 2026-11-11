"""Additive schema migrations for installations created before the engine.

The project has no migration framework; tables are created with
``Base.metadata.create_all``. ``create_all`` never alters existing tables, so
columns added by the prospecting engine are applied here with ``ALTER TABLE
... ADD COLUMN``. Only nullable, additive changes are applied: existing rows,
data and indexes are never dropped, rewritten or reset.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# table -> list of (column, SQL type) that must exist. Types are intentionally
# portable across SQLite (dev) and PostgreSQL (deployed).
ADDITIVE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "company_research_records": [
        ("last_attempted_at", "TIMESTAMP"),
        ("last_successful_at", "TIMESTAMP"),
        ("research_status", "VARCHAR(32)"),
        ("research_version", "INTEGER"),
        ("content_fingerprint", "VARCHAR(128)"),
        ("error_message", "TEXT"),
        ("decision_maker_extracted_at", "TIMESTAMP"),
    ],
    "companies": [
        ("domain", "VARCHAR(255)"),
        ("normalized_name", "VARCHAR(255)"),
        ("research_confidence", "FLOAT"),
        ("research_timestamp", "TIMESTAMP"),
        ("synthetic", "BOOLEAN"),
    ],
    "decision_makers": [
        ("status", "VARCHAR(32)"),
        ("last_observed_at", "TIMESTAMP"),
        ("observation_confidence", "FLOAT"),
        ("email", "VARCHAR(512)"),
        ("email_status", "VARCHAR(32)"),
        ("email_verified_at", "TIMESTAMP"),
        ("profile_verified_at", "TIMESTAMP"),
        ("role_source_url", "VARCHAR(512)"),
        ("evidence_excerpt", "TEXT"),
        ("synthetic", "BOOLEAN"),
    ],
    "prospects": [
        ("qualification_status", "VARCHAR(32)"),
        ("qualification_confidence", "FLOAT"),
        ("evidence_urls", "TEXT"),
        ("synthetic", "BOOLEAN"),
    ],
    "evidence": [
        ("retrieved_at", "TIMESTAMP"),
        ("publication_date", "TIMESTAMP"),
        ("verification_status", "VARCHAR(32)"),
        ("content_fingerprint", "VARCHAR(128)"),
        ("is_accessible", "BOOLEAN"),
    ],
    "prospect_batches": [
        ("total_rejected", "INTEGER"),
        ("total_discovered_companies", "INTEGER"),
    ],
}


def apply_additive_migrations(engine: Engine) -> list[str]:
    """Add missing engine columns without touching existing schema or data.

    Returns the list of applied ``table.column`` names so startup logs can show
    exactly what changed. Safe to run on every startup.
    """
    inspector = inspect(engine)
    applied: list[str] = []
    with engine.begin() as connection:
        for table, columns in ADDITIVE_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, sql_type in columns:
                if name in existing:
                    continue
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
                )
                applied.append(f"{table}.{name}")
    return applied
