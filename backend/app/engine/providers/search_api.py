"""Real search-API adaptation for discovery, research and evidence.

Only documented public HTTP APIs are used (Tavily or Serper). No page scraping,
authenticated browsing or CAPTCHA bypass is attempted. The adapter reports
``ProviderNotConfigured`` when no API key is present rather than falling back to
fabricated data.

Retrieved URLs are treated as untrusted retrieval evidence: they are never
marked ``verified``, and they must pass the public-source validator so an
internal host, private IP or metadata endpoint can never be stored as a source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.config.settings import Settings
from app.engine.contracts import (
    CompanyCandidate,
    CompanyDiscoveryProvider,
    CompanyResearch,
    CompanyResearchProvider,
    DiscoveryRequest,
    EvidenceProvider,
    ICPQuery,
    ProviderStatus,
    SourceRef,
)
from app.engine.errors import (
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.engine.evidence import is_plausible_source_url
from app.engine.normalization import normalize_domain
from app.engine.safe_http import (
    SafeHttpError,
    SafeHttpResponse,
    UnsafeUrlError,
    safe_request,
)

ENDPOINTS = {
    "tavily": "https://api.tavily.com/search",
    "serper": "https://google.serper.dev/search",
}

# Directories, social networks and news aggregators are useful as sources but are
# not companies, so they are never turned into company candidates.
AGGREGATOR_HOSTS = frozenset(
    {
        "linkedin.com",
        "facebook.com",
        "twitter.com",
        "x.com",
        "instagram.com",
        "youtube.com",
        "wikipedia.org",
        "crunchbase.com",
        "glassdoor.com",
        "yelp.com",
        "indeed.com",
        "bloomberg.com",
        "reuters.com",
        "forbes.com",
        "medium.com",
        "reddit.com",
        "quora.com",
        "pinterest.com",
        "tiktok.com",
        "amazon.com",
        "g2.com",
        "capterra.com",
        "trustpilot.com",
        "owler.com",
        "zoominfo.com",
        "apollo.io",
        "github.com",
    }
)

TITLE_SEPARATORS = (" | ", " - ", " – ", " — ", " :: ")

# A hostile or compromised provider must not be able to stream an unbounded body
# into memory, or redirect the request at an internal service.
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3


@dataclass(frozen=True)
class SearchHit:
    """A normalized search result."""

    title: str
    url: str
    snippet: str


class SearchApiProvider(CompanyDiscoveryProvider, CompanyResearchProvider, EvidenceProvider):
    """Tavily/Serper adapter implementing discovery, research and evidence."""

    synthetic = False

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        cost_per_call_usd: float = 0.0,
        timeout_seconds: float = 15.0,
    ) -> None:
        """Store credentials; raise immediately when they are missing."""
        resolved = (provider or "").lower()
        if resolved not in ENDPOINTS:
            raise ProviderNotConfigured(f"Unsupported search provider '{provider}'. Supported: tavily, serper.")
        if not api_key:
            raise ProviderNotConfigured(
                f"{resolved} search API key is not configured "
                f"(set {'TAVILY_API_KEY' if resolved == 'tavily' else 'SERPER_API_KEY'})"
            )
        self.name = resolved
        self.capability = "company_discovery"
        self._provider = resolved
        self._api_key = api_key
        self._timeout = timeout_seconds
        self.cost_per_call_usd = cost_per_call_usd

    @classmethod
    def from_settings(cls, settings: Settings) -> SearchApiProvider:
        """Build the adapter from application settings."""
        provider = (settings.search_provider or "").lower()
        api_key = settings.tavily_api_key if provider == "tavily" else settings.serper_api_key
        return cls(
            provider=provider,
            api_key=api_key,
            cost_per_call_usd=settings.cost_search_call_usd,
            timeout_seconds=settings.provider_timeout_seconds,
        )

    def status(self) -> ProviderStatus:
        """Report the configured search API as available."""
        return ProviderStatus(
            name=self.name,
            capability=self.capability,
            state="ready",
            synthetic=False,
            detail=("Documented search API only; results are retrieval evidence, not fact-checked claims."),
            cost_per_call_usd=self.cost_per_call_usd,
        )

    def discover(self, request: DiscoveryRequest) -> list[CompanyCandidate]:
        """Search for company homepages and normalize them into candidates."""
        query = _discovery_query(request.icp)
        hits = self._search(query, max_results=min(max(request.limit, 5), 40))
        candidates: list[CompanyCandidate] = []
        seen_domains: set[str] = set()
        for hit in hits:
            domain = normalize_domain(hit.url)
            if not domain or _is_aggregator(domain):
                continue
            if domain in seen_domains:
                continue
            name = _company_name_from_title(hit.title)
            if not name:
                continue
            seen_domains.add(domain)
            candidates.append(
                CompanyCandidate(
                    name=name,
                    website=f"https://{domain}",
                    domain=domain,
                    industry=request.icp.industries[0] if request.icp.industries else None,
                    location=request.icp.countries[0] if request.icp.countries else None,
                    country=request.icp.countries[0] if request.icp.countries else None,
                    description=hit.snippet or None,
                    source_url=hit.url,
                    source_name=self.name,
                    identity_confidence=0.3,
                    synthetic=False,
                    evidence=[_source_ref(hit)],
                )
            )
            if len(candidates) >= request.limit:
                break
        return candidates

    def research(self, company: CompanyCandidate, icp: ICPQuery) -> CompanyResearch:
        """Retrieve first-party pages and turn them into research findings."""
        domain = normalize_domain(company.domain or company.website)
        if not domain:
            raise ProviderResponseError(f"cannot research '{company.name}' without a resolvable domain")
        hits = self._search(
            f"site:{domain} (about OR services OR products OR pricing OR customers)",
            max_results=8,
        )
        sources = [_source_ref(hit) for hit in hits if is_plausible_source_url(hit.url)]
        first_party = [hit for hit in hits if normalize_domain(hit.url) == domain]
        snippets = [hit.snippet for hit in first_party if hit.snippet]
        missing: list[str] = []
        if not first_party:
            missing.append(f"no first-party pages were retrieved for {domain}")
        if not company.industry:
            missing.append("industry was not confirmed by a source")
        missing.append("public developments were not retrieved in this run")
        what_it_does = snippets[0][:400] if snippets else None
        what_it_sells = next(
            (snippet[:400] for snippet in snippets if _looks_like_offering(snippet)),
            None,
        )
        signals = [f"first-party page: {hit.title}" for hit in first_party[:5]]
        confidence = 0.0
        if first_party:
            confidence = min(0.65, 0.2 + 0.1 * len(first_party))
        return CompanyResearch(
            provider=self.name,
            what_it_does=what_it_does,
            what_it_sells=what_it_sells,
            who_it_serves=None,
            positioning=None,
            public_developments=None,
            observable_signals=signals,
            evidence=sources,
            missing_information=missing,
            confidence=round(confidence, 3),
            synthetic=False,
        )

    def collect(self, company: CompanyCandidate) -> list[SourceRef]:
        """Retrieve sources for a company without producing research findings."""
        domain = normalize_domain(company.domain or company.website)
        if not domain:
            return []
        hits = self._search(f"site:{domain}", max_results=5)
        return [_source_ref(hit) for hit in hits if is_plausible_source_url(hit.url)]

    def _search(self, query: str, *, max_results: int) -> list[SearchHit]:
        """POST to the configured search API and normalize its results."""
        endpoint = ENDPOINTS[self._provider]
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._provider == "tavily":
            payload: dict[str, Any] = {
                "api_key": self._api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "include_answer": False,
                "include_raw_content": False,
            }
        else:
            payload = {"q": query, "num": max_results}
            headers["X-API-KEY"] = self._api_key
        data = _post_json(endpoint, payload, headers, self._timeout)
        return _parse_hits(self._provider, data)


def _request_search_api(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> SafeHttpResponse:
    """POST JSON using only pinned HTTPS and same-origin redirects."""
    try:
        return safe_request(
            url,
            method="POST",
            body=json.dumps(payload).encode("utf-8"),
            headers=headers,
            timeout=timeout,
            max_redirects=MAX_REDIRECTS,
            max_response_bytes=MAX_RESPONSE_BYTES,
            require_https=True,
            same_origin_only=True,
        )
    except UnsafeUrlError as exc:
        raise ProviderResponseError("search API request or redirect was blocked by the safe network policy") from exc
    except TimeoutError as exc:
        raise ProviderTimeout("search API request timed out") from exc
    except SafeHttpError as exc:
        raise ProviderUnavailable("search API request could not be completed safely") from exc
    except OSError as exc:
        raise ProviderUnavailable("search API is unreachable") from exc


def _raise_for_search_response(response: SafeHttpResponse) -> None:
    """Map API status and size failures to their established provider errors."""
    if response.status_code == 429:
        raise ProviderRateLimited(f"search API rate limit hit ({response.status_code})")
    if response.status_code in (401, 403):
        raise ProviderNotConfigured(f"search API rejected the configured credentials ({response.status_code})")
    if response.status_code < 200 or response.status_code >= 300:
        raise ProviderResponseError(f"search API returned HTTP {response.status_code}")
    if response.body_truncated:
        raise ProviderResponseError("search API response exceeded the size limit")


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    """POST JSON over HTTPS using the pinned-address redirect-safe transport."""
    response = _request_search_api(url, payload, headers, timeout)
    _raise_for_search_response(response)
    try:
        body = response.body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProviderResponseError("search API returned non-UTF-8 content") from exc
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError("search API returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise ProviderResponseError("search API returned an unexpected payload")
    return parsed


def _parse_hits(provider: str, data: dict[str, Any]) -> list[SearchHit]:
    """Strictly normalize Tavily and Serper result shapes.

    Provider payloads are untrusted: a missing results envelope is an error
    (not silently zero results), non-string fields are dropped, and every URL
    must pass the public-source validator.
    """
    if data.get("error"):
        raise ProviderResponseError("search API returned an error payload")
    key = "results" if provider == "tavily" else "organic"
    if key not in data:
        raise ProviderResponseError(f"search API response is missing the '{key}' field")
    raw_results = data.get(key)
    if not isinstance(raw_results, list):
        raise ProviderResponseError(f"search API field '{key}' is not a list")
    hits: list[SearchHit] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = item.get("url") if provider == "tavily" else item.get("link")
        title = item.get("title")
        snippet = item.get("content") if provider == "tavily" else item.get("snippet")
        if not isinstance(url, str) or not is_plausible_source_url(url):
            continue
        if title is not None and not isinstance(title, str):
            continue
        if snippet is not None and not isinstance(snippet, str):
            continue
        hits.append(
            SearchHit(
                title=(title or "").strip()[:300],
                url=url.strip(),
                snippet=(snippet or "").strip()[:1000],
            )
        )
    return hits


def _discovery_query(icp: ICPQuery) -> str:
    """Build a discovery query from the ICP without inventing constraints."""
    parts: list[str] = []
    if icp.industries:
        parts.append(" OR ".join(f'"{industry}"' for industry in icp.industries[:3]))
    elif icp.target_audience:
        parts.append(icp.target_audience)
    parts.append("companies")
    geography = icp.countries + icp.regions
    if geography:
        parts.append(" ".join(f'"{place}"' for place in geography[:3]))
    if icp.company_size:
        parts.append(icp.company_size)
    if icp.additional_criteria:
        parts.append(icp.additional_criteria[:200])
    return " ".join(part for part in parts if part)


def _is_aggregator(domain: str) -> bool:
    return any(domain == host or domain.endswith(f".{host}") for host in AGGREGATOR_HOSTS)


def _company_name_from_title(title: str) -> str | None:
    """Extract a company name from a search result title."""
    cleaned = title.strip()
    for separator in TITLE_SEPARATORS:
        if separator in cleaned:
            cleaned = cleaned.split(separator)[0].strip()
            break
    for suffix in (" Home", " Homepage", " Official Site", " | Official"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
    if len(cleaned) < 2:
        return None
    return cleaned[:255]


def _looks_like_offering(snippet: str) -> bool:
    markers = ("pricing", "plans", "product", "platform", "service", "solution", "software")
    return any(marker in snippet.lower() for marker in markers)


def _source_ref(hit: SearchHit) -> SourceRef:
    """Wrap a search hit as a citation.

    ``verified`` is deliberately False: a search engine returning a URL proves
    retrieval only, not that the page content (or any company fact) is true.
    """
    return SourceRef(
        url=hit.url,
        title=hit.title or None,
        source_type="search_result",
        snippet=hit.snippet or None,
        verified=False,
    )
