"""Deterministic normalization helpers used for identity matching.

Normalization is intentionally pure and dependency-free so deduplication
behaviour is identical across SQLite and PostgreSQL.
"""

from __future__ import annotations

from urllib.parse import urlparse

LEGAL_SUFFIXES = frozenset(
    {
        "inc",
        "inc.",
        "incorporated",
        "llc",
        "l.l.c.",
        "ltd",
        "ltd.",
        "limited",
        "co",
        "co.",
        "corp",
        "corp.",
        "corporation",
        "gmbh",
        "ag",
        "sa",
        "s.a.",
        "bv",
        "b.v.",
        "plc",
        "pty",
        "pte",
        "s.r.l.",
        "srl",
    }
)

_NON_ALNUM = str.maketrans({".": "", ",": "", "'": "", '"': ""})


def _clean(value: str) -> str:
    return " ".join(value.strip().lower().translate(_NON_ALNUM).split())


def normalize_domain(value: str | None) -> str | None:
    """Return a bare lowercase hostname (``www.`` stripped) or ``None``."""
    if not value:
        return None
    candidate = value.strip().lower()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    host = (urlparse(candidate).hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host or " " in host:
        return None
    return host


def normalize_company_name(value: str | None) -> str | None:
    """Return a comparable company key with legal suffixes removed."""
    if not value:
        return None
    cleaned = _clean(value)
    if not cleaned:
        return None
    tokens = [token for token in cleaned.split(" ") if token not in LEGAL_SUFFIXES]
    if not tokens:
        tokens = cleaned.split(" ")
    return " ".join(tokens)


def normalize_person_name(value: str | None) -> str | None:
    """Return a comparable person key."""
    if not value:
        return None
    cleaned = _clean(value)
    return cleaned or None


def normalize_email(value: str | None) -> str | None:
    """Return a lowercase, trimmed email address or ``None``."""
    if not value:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def normalize_url(value: str | None) -> str | None:
    """Return a comparable URL (lowercase host, no trailing slash or query)."""
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    path = parsed.path.rstrip("/")
    return f"https://{host}{path}"


def split_csv(value: str | None) -> list[str]:
    """Split a comma/semicolon separated settings value into clean items."""
    if not value:
        return []
    normalized = value.replace(";", ",").replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]
