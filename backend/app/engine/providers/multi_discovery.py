# ruff: noqa: D101, D102, D107, C901
"""Multi-source, API-independent company discovery.

This module provides a small set of generic, lawful source adapters and a
central aggregation layer.  Each adapter returns normalized ``CompanyCandidate``
records; the composite provider deduplicates across sources while preserving
source provenance in ``evidence`` and ``source_name``.

No adapter fabricates companies.  Adapters that cannot run (missing URLs,
blocked pages, SSRF-unsafe targets) report the failure through their normal
exception path or return an empty list; one failed adapter never fails the
whole batch.
"""

from __future__ import annotations

import logging
import urllib.parse
from collections.abc import Callable
from typing import Any, Literal

from bs4 import BeautifulSoup

from app.engine.contracts import (
    CompanyCandidate,
    CompanyDiscoveryProvider,
    DiscoveryRequest,
    ICPQuery,
    ProviderStatus,
    SourceRef,
)
from app.engine.normalization import normalize_company_name, normalize_domain
from app.engine.providers.public_discovery import (
    PublicSearchDiscoveryProvider,
    _is_aggregator,
    _is_directory_result,
)
from app.engine.safe_http import SafeHttpError, is_safe_url, safe_request

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT = 15.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _split_urls(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = str(value).replace("\n", ",").split(",")
    return [item.strip() for item in items if item.strip()]


def _fetch_html(url: str, timeout: float = DEFAULT_TIMEOUT) -> str | None:
    try:
        response = safe_request(
            url,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=timeout,
            max_response_bytes=MAX_RESPONSE_BYTES,
        )
        if response.status_code < 200 or response.status_code >= 300:
            return None
        if response.body_truncated:
            return None
        return response.body.decode("utf-8", errors="replace")
    except (SafeHttpError, TimeoutError, OSError, UnicodeDecodeError):
        return None


def _candidate_from_url(
    url: str,
    *,
    name: str | None = None,
    source_name: str,
    source_type: str,
    icp: ICPQuery,
    confidence: float,
    verified: bool = False,
) -> CompanyCandidate | None:
    domain = normalize_domain(url)
    if not domain or _is_aggregator(domain):
        return None
    if not name:
        label = domain.split(".")[0].replace("-", " ").replace("_", " ").strip()
        name = " ".join(part.capitalize() for part in label.split()) if label else domain
    if len(name) < 2:
        return None
    location = icp.countries[0] if icp.countries else (icp.regions[0] if icp.regions else None)
    country = icp.countries[0] if icp.countries else None
    industry = icp.industries[0] if icp.industries else None
    return CompanyCandidate(
        name=name[:255],
        website=f"https://{domain}",
        domain=domain,
        industry=industry,
        location=location,
        country=country,
        source_url=url,
        source_name=source_name,
        identity_confidence=confidence,
        synthetic=False,
        evidence=[
            SourceRef(
                url=url,
                title=name,
                source_type=source_type,
                snippet=None,
                verified=verified,
            )
        ],
    )


class CustomerUrlDiscoveryProvider(CompanyDiscoveryProvider):
    """Discover companies from user-supplied URLs."""

    name = "customer_urls"
    capability = "company_discovery"
    synthetic = False
    cost_per_call_usd = 0.0

    def __init__(self, urls: list[str] | None = None, *, fetch_titles: bool = False) -> None:
        self._urls = list(urls or [])
        self._fetch_titles = fetch_titles

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            capability=self.capability,
            state="ready",
            synthetic=False,
            detail="Validates and normalizes user-supplied company URLs.",
            cost_per_call_usd=0.0,
        )

    def discover(self, request: DiscoveryRequest) -> list[CompanyCandidate]:
        urls = list(self._urls) + list(request.seed_urls or [])
        results: list[CompanyCandidate] = []
        seen: set[str] = set()
        for raw_url in urls:
            url = raw_url.strip()
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            if not is_safe_url(url):
                continue
            # Title fetching is optional; discovery should stay fast and must
            # not make network calls that can time out the whole batch.
            title: str | None = None
            if self._fetch_titles:
                html = _fetch_html(url)
                if html:
                    try:
                        soup = BeautifulSoup(html, "html.parser")
                        if soup.title and soup.title.string:
                            title = " ".join(soup.title.string.split())[:120]
                    except Exception:  # noqa: BLE001
                        title = None
            domain = normalize_domain(url)
            if domain and domain in seen:
                continue
            candidate = _candidate_from_url(
                url,
                name=title,
                source_name=self.name,
                source_type="customer_supplied_url",
                icp=request.icp,
                confidence=0.5,
                verified=False,
            )
            if candidate is None:
                continue
            if candidate.domain:
                seen.add(candidate.domain)
            results.append(candidate)
            if len(results) >= request.limit:
                break
        return results


class PublicListingDiscoveryProvider(CompanyDiscoveryProvider):
    """Generic extractor for public directory/association/event pages."""

    def __init__(self, *, source_name: str, source_type: str, urls: list[str] | None = None) -> None:
        self.name = source_name
        self._source_type = source_type
        self._urls = list(urls or [])
        self.capability = "company_discovery"
        self.synthetic = False
        self.cost_per_call_usd = 0.0

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            capability=self.capability,
            state="ready" if self._urls else "not_configured",
            synthetic=False,
            detail=(
                "Extracts company links from configured public listing pages."
                if self._urls
                else "No listing URLs configured."
            ),
            cost_per_call_usd=0.0,
        )

    def discover(self, request: DiscoveryRequest) -> list[CompanyCandidate]:
        urls = self._urls
        results: list[CompanyCandidate] = []
        seen_domains: set[str] = set()
        seen_names: set[str] = set()
        for page_url in urls:
            html = _fetch_html(page_url)
            if not html:
                continue
            try:
                soup = BeautifulSoup(html, "html.parser")
            except Exception:  # noqa: BLE001
                continue
            for anchor in soup.find_all("a", href=True):
                href = str(anchor.get("href") or "").strip()
                if not href:
                    continue
                if href.startswith("/"):
                    href = urllib.parse.urljoin(page_url, href)
                if not href.startswith(("http://", "https://")):
                    continue
                if not is_safe_url(href):
                    continue
                domain = normalize_domain(href)
                if not domain or _is_aggregator(domain):
                    continue
                # Skip links back to the listing site itself.
                if domain == normalize_domain(page_url):
                    continue
                if _is_directory_result(anchor.get_text(" ", strip=True), href):
                    # The link text itself can be a directory phrase; still try
                    # only if the href points at a non-aggregator domain.
                    pass
                name = " ".join(anchor.get_text(" ", strip=True).split())
                generic_labels = {"website", "more", "visit", "read more", "view", "details", "profile"}
                if name.lower() in generic_labels or len(name) < 3:
                    attr_text = " ".join(str(anchor.get(attr) or "") for attr in ("title", "aria-label"))
                    lowered_attr = attr_text.lower()
                    if any(word in lowered_attr for word in ("partner", "sponsor", "affiliate", "foundation")):
                        # Skip non-member entries; only member agencies count.
                        continue
                    # Common pattern: "Website of <tier> member <Company>".
                    if "member" in lowered_attr:
                        idx = lowered_attr.rfind("member")
                        extracted = attr_text[idx + len("member") :].strip(" :-–—")
                        if 2 <= len(extracted) <= 120:
                            name = extracted
                    elif " of " in lowered_attr:
                        extracted = attr_text.rsplit(" of ", 1)[-1].strip(" :-–—")
                        if 2 <= len(extracted) <= 120:
                            name = extracted
                    if name.lower() in generic_labels or len(name) < 3:
                        heading = anchor.find_previous(["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"])
                        if heading is not None:
                            candidate_name = " ".join(heading.get_text(" ", strip=True).split())
                            if 2 <= len(candidate_name) <= 120:
                                name = candidate_name
                if len(name) < 2 or len(name) > 120:
                    # Fall back to domain label.
                    label = domain.split(".")[0].replace("-", " ").replace("_", " ").strip()
                    name = " ".join(part.capitalize() for part in label.split())
                if len(name) < 2:
                    continue
                key_domain = domain
                name_key = normalize_company_name(name)
                if key_domain in seen_domains or (name_key and name_key in seen_names):
                    continue
                candidate = _candidate_from_url(
                    href,
                    name=name,
                    source_name=self.name,
                    source_type=self._source_type,
                    icp=request.icp,
                    confidence=0.25,
                    verified=False,
                )
                if candidate is None:
                    continue
                if candidate.domain:
                    seen_domains.add(candidate.domain)
                if name_key:
                    seen_names.add(name_key)
                results.append(candidate)
                if len(results) >= request.limit:
                    return results
        return results


class WorkspaceHistoryDiscoveryProvider(CompanyDiscoveryProvider):
    """Reuse companies already discovered in the same workspace (tenant-scoped)."""

    name = "workspace_history"
    capability = "company_discovery"
    synthetic = False
    cost_per_call_usd = 0.0

    def __init__(self, lookup: Callable[[str | None, ICPQuery, int], list[CompanyCandidate]] | None = None) -> None:
        self._lookup = lookup

    def set_lookup(self, lookup: Callable[[str | None, ICPQuery, int], list[CompanyCandidate]]) -> None:
        self._lookup = lookup

    def status(self) -> ProviderStatus:
        if self._lookup is None:
            return ProviderStatus(
                name=self.name,
                capability=self.capability,
                state="not_configured",
                synthetic=False,
                detail="Workspace history lookup is not bound.",
                cost_per_call_usd=0.0,
            )
        return ProviderStatus(
            name=self.name,
            capability=self.capability,
            state="ready",
            synthetic=False,
            detail="Reuses prior discoveries within the same workspace only.",
            cost_per_call_usd=0.0,
        )

    def discover(self, request: DiscoveryRequest) -> list[CompanyCandidate]:
        if self._lookup is None:
            return []
        try:
            return list(self._lookup(request.workspace_id, request.icp, request.limit))
        except Exception as exc:  # noqa: BLE001
            logger.info("workspace history lookup failed: %s", exc)
            return []


class CompositeDiscoveryProvider(CompanyDiscoveryProvider):
    """Aggregate multiple discovery adapters with failure isolation and dedup."""

    name = "multi_source_discovery"
    capability = "company_discovery"
    synthetic = False
    cost_per_call_usd = 0.0

    def __init__(self, adapters: list[CompanyDiscoveryProvider]) -> None:
        self._adapters = [adapter for adapter in adapters if adapter is not None]

    @property
    def adapters(self) -> list[CompanyDiscoveryProvider]:
        return list(self._adapters)

    def status(self) -> ProviderStatus:
        ready = [adapter for adapter in self._adapters if adapter.status().available]
        state: Literal["ready", "not_configured", "unavailable", "degraded"] = "ready" if ready else "unavailable"
        return ProviderStatus(
            name=self.name,
            capability=self.capability,
            state=state,
            synthetic=any(adapter.synthetic for adapter in self._adapters),
            detail="Adapters: " + ", ".join(adapter.name for adapter in self._adapters),
            cost_per_call_usd=0.0,
        )

    def discover(self, request: DiscoveryRequest) -> list[CompanyCandidate]:
        collected: list[CompanyCandidate] = []
        for adapter in self._adapters:
            try:
                collected.extend(adapter.discover(request))
            except Exception as exc:  # noqa: BLE001 - one source must not fail the batch
                logger.info("Discovery adapter %s failed: %s", adapter.name, exc)
        return _aggregate_candidates(collected, request.limit)

    def set_history_lookup(self, lookup: Any) -> None:
        for adapter in self._adapters:
            if isinstance(adapter, WorkspaceHistoryDiscoveryProvider):
                adapter.set_lookup(lookup)


def _aggregate_candidates(candidates: list[CompanyCandidate], limit: int) -> list[CompanyCandidate]:
    """Deduplicate candidates across sources while preserving provenance."""
    aggregated: list[CompanyCandidate] = []
    index_by_domain: dict[str, int] = {}
    index_by_name: dict[str, int] = {}
    for candidate in candidates:
        domain = normalize_domain(candidate.domain or candidate.website)
        name_key = normalize_company_name(candidate.name)
        existing_idx: int | None = None
        if domain and domain in index_by_domain:
            existing_idx = index_by_domain[domain]
        elif name_key and name_key in index_by_name:
            existing_idx = index_by_name[name_key]
        if existing_idx is not None:
            existing = aggregated[existing_idx]
            # Merge evidence provenance.
            merged_evidence = list(existing.evidence)
            for source in candidate.evidence:
                if not any(s.url == source.url for s in merged_evidence):
                    merged_evidence.append(source)
            # Prefer higher confidence and a non-empty website.
            confidence = max(existing.identity_confidence, candidate.identity_confidence)
            website = existing.website or candidate.website
            source_name = existing.source_name
            if existing.source_name not in (candidate.source_name, None) and candidate.source_name:
                source_name = f"{existing.source_name}+{candidate.source_name}"
            updated = existing.model_copy(
                update={
                    "evidence": merged_evidence,
                    "identity_confidence": confidence,
                    "website": website,
                    "source_name": source_name,
                }
            )
            aggregated[existing_idx] = updated
            continue
        if domain:
            index_by_domain[domain] = len(aggregated)
        if name_key:
            index_by_name[name_key] = len(aggregated)
        aggregated.append(candidate)
        if len(aggregated) >= limit:
            break
    return aggregated[:limit]


def build_multi_source_discovery(settings: Any, *, history_lookup: Any = None) -> CompositeDiscoveryProvider:
    """Build the default multi-source discovery bundle from settings."""
    from app.config.settings import get_settings

    resolved = settings or get_settings()
    adapters: list[CompanyDiscoveryProvider] = [
        PublicSearchDiscoveryProvider(
            max_queries=6,
            max_results_per_query=10,
            timeout_seconds=getattr(resolved, "provider_timeout_seconds", DEFAULT_TIMEOUT),
            min_interval_seconds=getattr(resolved, "discovery_request_min_interval_seconds", 1.0),
            max_retries=getattr(resolved, "discovery_max_retries", 2),
        )
    ]
    customer_urls = _split_urls(getattr(resolved, "discovery_customer_urls", ""))
    if customer_urls:
        adapters.append(CustomerUrlDiscoveryProvider(customer_urls))
    for urls, name, source_type in (
        (_split_urls(getattr(resolved, "discovery_directory_urls", "")), "public_directory", "directory_listing"),
        (
            _split_urls(getattr(resolved, "discovery_association_urls", "")),
            "association_directory",
            "association_membership",
        ),
        (_split_urls(getattr(resolved, "discovery_event_urls", "")), "event_exhibitor_directory", "event_exhibitor"),
    ):
        if urls:
            adapters.append(PublicListingDiscoveryProvider(source_name=name, source_type=source_type, urls=urls))
    history = WorkspaceHistoryDiscoveryProvider(history_lookup)
    adapters.append(history)
    composite = CompositeDiscoveryProvider(adapters)
    if history_lookup is not None:
        composite.set_history_lookup(history_lookup)
    return composite


def workspace_history_lookup(db: Any, workspace_id: Any, icp: ICPQuery, limit: int) -> list[CompanyCandidate]:
    """Default DB-backed, tenant-scoped history lookup."""
    if db is None or not workspace_id:
        return []
    try:
        import uuid as _uuid

        from app.models import Company, ProspectBatch

        parsed = _uuid.UUID(str(workspace_id))
    except (ValueError, TypeError):
        return []
    try:
        rows = (
            db.query(Company)
            .join(ProspectBatch, Company.batch_id == ProspectBatch.id)
            .filter(ProspectBatch.workspace_id == parsed)
            .order_by(Company.created_at.desc())
            .limit(max(1, min(limit, 50)))
            .all()
        )
    except Exception:  # noqa: BLE001
        return []
    results: list[CompanyCandidate] = []
    seen: set[str] = set()
    for row in rows:
        domain = normalize_domain(row.domain or row.website)
        if domain and domain in seen:
            continue
        if domain:
            seen.add(domain)
        # Optional ICP scoping: keep companies whose industry/country overlap.
        if icp.industries and row.industry:
            if not any(ind.lower() in (row.industry or "").lower() for ind in icp.industries):
                # Still include: history reuse is valuable even on partial match.
                pass
        candidate = CompanyCandidate(
            name=row.name,
            website=row.website,
            domain=domain,
            industry=row.industry,
            location=row.location,
            country=row.country,
            city=row.city,
            description=row.description,
            products_services=row.products_services,
            source_url=row.source_url,
            source_name="workspace_history",
            identity_confidence=0.6,
            synthetic=bool(row.synthetic),
            evidence=[
                SourceRef(
                    url=row.source_url or row.website or f"https://{domain}",
                    title=row.name,
                    source_type="workspace_history",
                    snippet=None,
                    verified=False,
                )
            ],
        )
        results.append(candidate)
        if len(results) >= limit:
            break
    return results
