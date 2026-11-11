"""API-independent company discovery via permitted public search sources.

The provider does not use Tavily, Serper, Apollo, PDL or any paid scraping
subscription. It queries publicly accessible search interfaces, normalizes and
validates the returned URLs, and turns them into candidate companies. Search
results are retrieval evidence only: they are never treated as verified company
facts and a candidate is only a candidate until later research/qualification.
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.engine.contracts import (
    CompanyCandidate,
    CompanyDiscoveryProvider,
    DiscoveryRequest,
    ICPQuery,
    ProviderStatus,
    SourceRef,
)
from app.engine.errors import ProviderUnavailable
from app.engine.normalization import normalize_domain
from app.engine.safe_http import SafeHttpError, safe_request

logger = logging.getLogger(__name__)

DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

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
        "duckduckgo.com",
        "clutch.co",
        "designrush.com",
        "goodfirms.co",
        "ahrefs.com",
        "itprofiles.com",
        "influencermarketinghub.com",
        "venturemedia.io",
        "simplythebestdigital.com",
    }
)


@dataclass(frozen=True)
class SearchHit:
    """A normalized public search result."""

    title: str
    url: str
    snippet: str


class PublicSearchDiscoveryProvider(CompanyDiscoveryProvider):
    """Discover companies through permitted public search interfaces."""

    name = "public_search"
    capability = "company_discovery"
    synthetic = False
    cost_per_call_usd = 0.0

    def __init__(
        self,
        *,
        max_queries: int = 6,
        max_results_per_query: int = 10,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        min_interval_seconds: float = 0.0,
        max_retries: int = 2,
        cooldown_seconds: float = 30.0,
        fetcher: Callable[[str, int, float], list[SearchHit]] | None = None,
    ) -> None:
        """Configure query/result limits and an optional fetcher for tests."""
        self._max_queries = max(1, max_queries)
        self._max_results_per_query = max(1, max_results_per_query)
        self._timeout = timeout_seconds
        self._min_interval = max(0.0, min_interval_seconds)
        self._max_retries = max(0, max_retries)
        self._cooldown = max(0.0, cooldown_seconds)
        self._fetcher = fetcher or self._fetch_search_results
        self._last_request_at = 0.0
        self._blocked_until = 0.0

    def status(self) -> ProviderStatus:
        """Report the provider as ready (no credentials required)."""
        return ProviderStatus(
            name=self.name,
            capability=self.capability,
            state="ready",
            synthetic=False,
            detail=(
                "API-independent discovery via permitted public search interfaces. "
                "Results are retrieval evidence, not verified company facts."
            ),
            cost_per_call_usd=0.0,
        )

    def discover(self, request: DiscoveryRequest) -> list[CompanyCandidate]:
        """Return deduplicated candidate companies for the ICP."""
        queries = plan_discovery_queries(request.icp, self._max_queries)
        hits: list[SearchHit] = []
        limitations: list[str] = []
        for query in queries:
            try:
                hits.extend(self._fetcher(query, self._max_results_per_query, self._timeout))
            except Exception as exc:  # noqa: BLE001 - one source must not fail the batch
                limitations.append(f"{query}: {exc}")
                logger.info("Public search query failed: %s (%s)", query, exc)
        if limitations and not hits:
            logger.warning("All public search queries failed: %s", limitations)
        candidates: list[CompanyCandidate] = []
        seen_domains: set[str] = set()
        seen_names: set[str] = set()
        for hit in hits:
            candidate = _candidate_from_hit(hit, request.icp)
            if candidate is None:
                continue
            domain = candidate.domain
            name_key = _normalize_name_key(candidate.name)
            if (domain and domain in seen_domains) or (name_key and name_key in seen_names):
                continue
            if domain:
                seen_domains.add(domain)
            if name_key:
                seen_names.add(name_key)
            candidates.append(candidate)
            if len(candidates) >= request.limit:
                break
        return candidates

    def _fetch_search_results(  # noqa: C901
        self, query: str, max_results: int, timeout: float
    ) -> list[SearchHit]:
        """Fetch and parse one DuckDuckGo HTML search page."""
        now = time.monotonic()
        if now < self._blocked_until:
            raise ProviderUnavailable("public search is cooling down after a block")
        if self._min_interval > 0:
            elapsed = now - self._last_request_at
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
        self._last_request_at = time.monotonic()
        data = urllib.parse.urlencode({"q": query, "kl": "us-en"}).encode("utf-8")
        request_headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = safe_request(
                    DUCKDUCKGO_HTML_URL,
                    method="POST",
                    body=data,
                    headers=request_headers,
                    timeout=timeout,
                    max_response_bytes=MAX_RESPONSE_BYTES,
                )
                if response.status_code in (429, 503, 403):
                    self._blocked_until = time.monotonic() + self._cooldown
                    raise ProviderUnavailable(f"public search blocked automation (HTTP {response.status_code})")
                if response.status_code < 200 or response.status_code >= 300:
                    raise ProviderUnavailable(f"public search returned HTTP {response.status_code}")
                if response.body_truncated:
                    raise ProviderUnavailable("public search response exceeded size limit")
                raw = response.body
                break
            except ProviderUnavailable:
                raise
            except (SafeHttpError, OSError, TimeoutError) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    time.sleep(min(2.0, 0.5 * (2**attempt)))
                    continue
                if isinstance(exc, TimeoutError):
                    raise ProviderUnavailable("public search timed out") from exc
                raise ProviderUnavailable(f"public search request failed: {exc}") from exc
        else:
            if last_exc is not None:
                raise ProviderUnavailable(f"public search request failed: {last_exc}") from last_exc
            raise ProviderUnavailable("public search request failed")
        try:
            text = raw.decode("utf-8", errors="replace")
        except UnicodeDecodeError as exc:
            raise ProviderUnavailable("public search returned non-UTF-8 content") from exc
        if _looks_blocked(text):
            self._blocked_until = time.monotonic() + self._cooldown
            raise ProviderUnavailable("public search blocked automation")
        return parse_duckduckgo_results(text, max_results)


def plan_discovery_queries(icp: ICPQuery, max_queries: int = 6) -> list[str]:
    """Generate deterministic, ICP-derived search queries."""
    queries: list[str] = []
    industries = [item.strip() for item in icp.industries if item.strip()][:3]
    geographies = (icp.countries + icp.regions)[:3]
    audience = (icp.target_audience or "").strip()
    criteria = (icp.additional_criteria or "").strip()[:160]
    size = (icp.company_size or "").strip()

    def add(query: str) -> None:
        cleaned = " ".join(query.split())
        if cleaned and cleaned not in queries:
            queries.append(cleaned)

    if industries:
        industry_part = " OR ".join(f'"{industry}"' for industry in industries)
        geo_part = " ".join(f'"{place}"' for place in geographies)
        add(f"{industry_part} companies {geo_part}".strip())
        add(f"{industry_part} {size} companies {geo_part}".strip())
        add(f"{industry_part} business directory {geo_part}".strip())
    elif audience:
        add(f"{audience} companies {' '.join(geographies)}")
    if audience and industries:
        add(f"{audience} {' '.join(industries)} {' '.join(geographies)}")
    if criteria:
        add(f"{criteria} {' '.join(geographies)}".strip())
    if not queries:
        add(f"companies {' '.join(geographies)}".strip())
    # A final, broader query helps when the ICP is sparse, but keep the total bounded.
    if industries:
        add(f"{' '.join(industries)} {' '.join(geographies)} official website")
    return queries[: max(1, max_queries)]


def parse_duckduckgo_results(html_text: str, max_results: int = 10) -> list[SearchHit]:  # noqa: C901
    """Parse DuckDuckGo HTML results into normalized hits."""
    soup = BeautifulSoup(html_text, "html.parser")
    hits: list[SearchHit] = []
    seen_urls: set[str] = set()
    for result in soup.select("div.result, div.web-result"):
        link = result.select_one("a.result__a")
        if link is None:
            link = result.select_one("a[href]")
        if link is None:
            continue
        title = " ".join(link.get_text(" ", strip=True).split())
        raw_href = str(link.get("href") or "").strip()
        url = _resolve_duckduckgo_url(raw_href)
        if not url:
            continue
        snippet_node = result.select_one(".result__snippet")
        snippet = ""
        if snippet_node is not None:
            snippet = " ".join(snippet_node.get_text(" ", strip=True).split())
        if url in seen_urls:
            continue
        seen_urls.add(url)
        hits.append(SearchHit(title=title, url=url, snippet=snippet[:1000]))
        if len(hits) >= max_results:
            break
    if not hits:
        # Fallback for simpler markup or test fixtures.
        for anchor in soup.find_all("a", href=True):
            href = _resolve_duckduckgo_url(str(anchor.get("href") or ""))
            if not href:
                continue
            title = " ".join(anchor.get_text(" ", strip=True).split())
            if not title or href in seen_urls:
                continue
            seen_urls.add(href)
            hits.append(SearchHit(title=title, url=href, snippet=""))
            if len(hits) >= max_results:
                break
    return hits[:max_results]


def _resolve_duckduckgo_url(raw_href: str) -> str | None:
    """Resolve DuckDuckGo redirect links to their target URL."""
    if not raw_href:
        return None
    if raw_href.startswith("//"):
        raw_href = "https:" + raw_href
    parsed = urlparse(raw_href)
    if "duckduckgo.com" in (parsed.hostname or ""):
        query = urllib.parse.parse_qs(parsed.query)
        for key in ("uddg", "u"):
            values = query.get(key)
            if values:
                decoded = urllib.parse.unquote(values[0])
                if decoded.startswith(("http://", "https://")):
                    return decoded
        return None
    if parsed.scheme in ("http", "https") and parsed.hostname:
        return raw_href
    return None


def _looks_blocked(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "captcha",
        "unusual traffic",
        "automated requests",
        "access denied",
        "please enable javascript",
        "too many requests",
        "rate limit",
        "bots use duckduckgo",
    )
    return any(marker in lowered for marker in markers)


def _is_aggregator(domain: str) -> bool:
    return any(domain == host or domain.endswith(f".{host}") for host in AGGREGATOR_HOSTS)


def _is_directory_result(title: str, url: str) -> bool:
    """Return True when the result is a directory/listing/blog page."""
    lowered_title = (title or "").lower()
    parsed = urllib.parse.urlparse(url)
    path = (parsed.path or "").lower()
    directory_markers = (
        "top ",
        "best ",
        "agencies",
        "directory",
        "ranked",
        "reviewed",
        "list of",
    )
    if any(marker in lowered_title for marker in directory_markers):
        return True
    if any(marker in path for marker in ("/agencies", "/directory", "/top-", "/best-", "/blog", "/post/")):
        return True
    return False


def _normalize_name_key(value: str | None) -> str | None:
    from app.engine.normalization import normalize_company_name

    return normalize_company_name(value)


def _candidate_from_hit(hit: SearchHit, icp: ICPQuery) -> CompanyCandidate | None:
    """Convert a search hit into a validated candidate, or None."""
    from app.engine.evidence import is_plausible_source_url

    url = hit.url.strip()
    if not is_plausible_source_url(url):
        return None
    domain = normalize_domain(url)
    if not domain or _is_aggregator(domain) or _is_directory_result(hit.title, url):
        return None
    name = _company_name_from_title(hit.title)
    if not name:
        label = domain.split(".")[0].replace("-", " ").replace("_", " ").strip()
        if len(label) < 2:
            return None
        name = " ".join(part.capitalize() for part in label.split())
    industry = icp.industries[0] if icp.industries else None
    location = icp.countries[0] if icp.countries else (icp.regions[0] if icp.regions else None)
    country = icp.countries[0] if icp.countries else None
    return CompanyCandidate(
        name=name[:255],
        website=f"https://{domain}",
        domain=domain,
        industry=industry,
        location=location,
        country=country,
        description=hit.snippet or None,
        source_url=url,
        source_name="public_search",
        identity_confidence=0.3,
        synthetic=False,
        evidence=[
            SourceRef(
                url=url,
                title=hit.title or None,
                source_type="search_result",
                snippet=hit.snippet or None,
                verified=False,
            )
        ],
    )


def _company_name_from_title(title: str) -> str | None:
    cleaned = (title or "").strip()
    for separator in (" | ", " - ", " – ", " — ", " :: "):
        if separator in cleaned:
            cleaned = cleaned.split(separator)[0].strip()
            break
    for suffix in (" Home", " Homepage", " Official Site", " | Official"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
    if len(cleaned) < 2:
        return None
    return cleaned[:255]
