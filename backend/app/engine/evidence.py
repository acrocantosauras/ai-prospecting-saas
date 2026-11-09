"""Evidence validation: only genuinely retrieved sources count as proof.

The engine refuses to store or cite a URL that does not look like a real,
retrievable web location. This prevents fabricated citations from satisfying
the evidence gate.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from urllib.parse import urlparse

from app.engine.contracts import SourceRef
from app.engine.normalization import normalize_url

BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "example.com",
        "example.org",
        "example.net",
        "test.com",
        "invalid",
        # Cloud metadata endpoints must never be stored as citable sources.
        "metadata",
        "metadata.google.internal",
        "instance-data",
        "169.254.169.254",
        "100.100.100.200",
    }
)

# Single-label and internal-only suffixes are not public web sources.
BLOCKED_HOST_SUFFIXES = (
    ".local",
    ".localdomain",
    ".internal",
    ".intranet",
    ".corp",
    ".home",
    ".lan",
    ".test",
    ".invalid",
    ".example",
)


def is_public_hostname(host: str) -> bool:
    """Return True only for a public DNS name or public IP address.

    Blocks loopback, link-local, private and reserved IP ranges, single-label
    hosts, internal-only suffixes and known cloud metadata hostnames. This is
    used for evidence URLs so no stored or displayed source can point at an
    internal service or metadata endpoint.
    """
    candidate = host.strip().lower().rstrip(".")
    if not candidate or candidate in BLOCKED_HOSTS:
        return False
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        if "." not in candidate:
            return False
        return not any(
            candidate.endswith(suffix) for suffix in BLOCKED_HOST_SUFFIXES
        )
    return address.is_global


def is_plausible_source_url(value: str | None) -> bool:
    """Return True when ``value`` is a plausible absolute http(s) source URL."""
    if not value:
        return False
    candidate = value.strip()
    if " " in candidate or not candidate.lower().startswith(("http://", "https://")):
        return False
    parsed = urlparse(candidate)
    # Credentials in a URL are never acceptable in evidence.
    if parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").lower()
    if not is_public_hostname(host):
        return False
    tld = host.rsplit(".", 1)[-1]
    return tld.isalpha() and len(tld) >= 2


def sanitize_sources(sources: Iterable[SourceRef]) -> list[SourceRef]:
    """Drop implausible URLs and de-duplicate by normalized URL."""
    seen: set[str] = set()
    kept: list[SourceRef] = []
    for source in sources:
        if not is_plausible_source_url(source.url):
            continue
        key = normalize_url(source.url) or source.url
        if key in seen:
            continue
        seen.add(key)
        kept.append(source)
    return kept


def source_urls(sources: Iterable[SourceRef]) -> list[str]:
    """Return the de-duplicated URLs for a set of sources, in order."""
    return [source.url for source in sanitize_sources(sources)]


def validate_references(
    references: Iterable[str], sources: Iterable[SourceRef]
) -> tuple[list[str], list[str]]:
    """Split analysis references into (cited, unsupported).

    A reference is valid only when it matches a source that was actually
    retrieved for the company. Matching is normalized (case, ``www.``, trailing
    slash) but never fuzzy: an invented URL cannot pass.
    """
    allowed = {normalize_url(url) for url in source_urls(sources)}
    cited: list[str] = []
    unsupported: list[str] = []
    for reference in references:
        normalized = normalize_url(reference)
        if normalized and normalized in allowed:
            cited.append(reference)
        else:
            unsupported.append(reference)
    return cited, unsupported


def summarise_sources(sources: Iterable[SourceRef], limit: int = 5) -> str:
    """Return a short human-readable citation list."""
    parts: list[str] = []
    for source in sanitize_sources(sources)[:limit]:
        label = source.title.strip() if source.title else source.source_type
        parts.append(f"{label} ({source.url})")
    return "; ".join(parts)
