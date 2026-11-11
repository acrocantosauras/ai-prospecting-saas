"""Safe, bounded website crawling using Crawlee.

The crawler is HTTP-first and treats every URL and byte of response as
untrusted. It enforces:

* SSRF protection (private/loopback/reserved IP rejection via DNS resolution).
* Redirect safety (final URL is re-validated).
* Response size limits and content-type validation.
* Crawl depth and page limits.
* Domain scoping (same-domain by default).
* robots.txt respect via Crawlee's built-in support.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup
from crawlee import Request
from crawlee._types import HttpHeaders, HttpMethod, HttpPayload
from crawlee.configuration import Configuration
from crawlee.crawlers import (
    BasicCrawlingContext,
    BeautifulSoupCrawler,
    BeautifulSoupCrawlingContext,
)
from crawlee.http_clients import HttpClient, HttpCrawlingResult, HttpResponse

from app.engine.safe_http import (
    DEFAULT_MAX_REDIRECTS,
    SafeHttpResponse,
    is_safe_url,
    safe_request,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator

    from crawlee.proxy_configuration import ProxyInfo
    from crawlee.sessions import Session
    from crawlee.statistics import Statistics

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "AlwaysBeenClosingBot/1.0 (+https://always-been-closing)"


@dataclass
class CrawledPage:
    """One retrieved page and its extracted text."""

    url: str
    final_url: str
    status_code: int
    title: str | None = None
    text: str = ""
    html: str | None = None
    content_type: str | None = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    depth: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Return True when the page was retrieved successfully."""
        return self.error is None and 200 <= self.status_code < 300


@dataclass
class CrawlConfig:
    """Bounded crawl configuration."""

    max_pages: int = 25
    max_depth: int = 2
    timeout_seconds: float = 15.0
    response_size_limit: int = 2_000_000
    allowed_content_types: tuple[str, ...] = (
        "text/html",
        "application/xhtml+xml",
        "text/plain",
    )
    same_domain_only: bool = True
    respect_robots: bool = True
    max_redirects: int = DEFAULT_MAX_REDIRECTS


class _CrawleeResponse:
    """Adapt a bounded response from the pinned transport for Crawlee."""

    def __init__(self, response: SafeHttpResponse) -> None:
        self._response = response
        self.http_version = "1.1"
        self.status_code = response.status_code
        self.headers = HttpHeaders.model_validate(response.headers)

    async def read(self) -> bytes:
        return self._response.body

    async def _read_stream(self) -> AsyncIterator[bytes]:
        if self._response.body:
            yield self._response.body

    def read_stream(self) -> AsyncIterator[bytes]:
        return self._read_stream()


class _PinnedCrawleeHttpClient(HttpClient):
    """Use the shared pinned-address HTTP implementation for every Crawlee request."""

    def __init__(self, response_size_limit: int, max_redirects: int) -> None:
        super().__init__()
        self._response_size_limit = response_size_limit
        self._max_redirects = max_redirects

    async def crawl(
        self,
        request: Request,
        *,
        session: Session | None = None,
        proxy_info: ProxyInfo | None = None,
        statistics: Statistics | None = None,
        timeout: timedelta | None = None,
    ) -> HttpCrawlingResult:
        del session
        if proxy_info is not None:
            raise RuntimeError("Crawlee proxies are unavailable with the pinned HTTP transport.")
        response = await self._request(
            request.url,
            method=request.method,
            headers=dict(request.headers or {}),
            body=request.payload,
            timeout=timeout.total_seconds() if timeout is not None else 15.0,
        )
        request.loaded_url = response.final_url
        if statistics is not None:
            statistics.register_status_code(response.status_code)
        return HttpCrawlingResult(http_response=_CrawleeResponse(response))

    async def send_request(
        self,
        url: str,
        *,
        method: HttpMethod = "GET",
        headers: HttpHeaders | dict[str, str] | None = None,
        payload: HttpPayload | None = None,
        session: Session | None = None,
        proxy_info: ProxyInfo | None = None,
        timeout: timedelta | None = None,
    ) -> HttpResponse:
        del session
        if proxy_info is not None:
            raise RuntimeError("Crawlee proxies are unavailable with the pinned HTTP transport.")
        response = await self._request(
            url,
            method=method,
            headers=(headers.root if isinstance(headers, HttpHeaders) else headers or {}),
            body=payload,
            timeout=timeout.total_seconds() if timeout is not None else 15.0,
        )
        return _CrawleeResponse(response)

    @asynccontextmanager
    async def stream(
        self,
        url: str,
        *,
        method: HttpMethod = "GET",
        headers: HttpHeaders | dict[str, str] | None = None,
        payload: HttpPayload | None = None,
        session: Session | None = None,
        proxy_info: ProxyInfo | None = None,
        timeout: timedelta | None = None,
    ) -> AsyncGenerator[HttpResponse, None]:
        response = await self.send_request(
            url,
            method=method,
            headers=headers,
            payload=payload,
            session=session,
            proxy_info=proxy_info,
            timeout=timeout,
        )
        yield response

    async def cleanup(self) -> None:
        return None

    async def _request(
        self,
        url: str,
        *,
        method: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
    ) -> SafeHttpResponse:
        return await asyncio.to_thread(
            safe_request,
            url,
            method=method,
            headers=headers,
            body=body,
            timeout=timeout,
            max_redirects=self._max_redirects,
            max_response_bytes=self._response_size_limit,
        )


def _root_domain(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _same_domain(url: str, root: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == root or host.endswith("." + root)


def _normalize_text(html: str) -> tuple[str | None, str]:
    """Extract a title and readable text from HTML."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:  # noqa: BLE001
        soup = BeautifulSoup(html, "html.parser")
    title = None
    if soup.title and soup.title.string:
        title = " ".join(soup.title.string.split())[:300] or None
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    return title, text


def _content_type_allowed(content_type: str | None, config: CrawlConfig) -> bool:
    if not content_type:
        return True
    lowered = content_type.lower()
    return any(allowed in lowered for allowed in config.allowed_content_types)


async def crawl_website(  # noqa: C901
    seed_url: str,
    config: CrawlConfig | None = None,
    path_hints: list[str] | None = None,
) -> list[CrawledPage]:
    """Crawl a website starting at ``seed_url`` and return extracted pages.

    The crawl is bounded by ``config``. Pages that cannot be safely retrieved
    are recorded with an ``error`` rather than raising.
    """
    config = config or CrawlConfig()
    seed_url = (seed_url or "").strip()
    if not is_safe_url(seed_url):
        return [
            CrawledPage(
                url=seed_url,
                final_url=seed_url,
                status_code=0,
                error="seed URL failed safety validation",
            )
        ]

    root = _root_domain(seed_url)
    results: list[CrawledPage] = []
    visited: set[str] = set()
    storage_dir = tempfile.mkdtemp(prefix="abc-crawl-")

    crawler = BeautifulSoupCrawler(
        max_requests_per_crawl=config.max_pages,
        request_handler_timeout=timedelta_seconds(config.timeout_seconds),
        respect_robots_txt_file=config.respect_robots,
        http_client=_PinnedCrawleeHttpClient(config.response_size_limit, config.max_redirects),
        configuration=Configuration(storage_dir=storage_dir),
    )

    @crawler.router.default_handler
    async def handler(context: BeautifulSoupCrawlingContext) -> None:  # noqa: C901
        url = context.request.url
        if url in visited:
            return
        visited.add(url)
        depth = 0
        try:
            user_data = context.request.user_data or {}
            raw_depth = user_data.get("depth", 0) if isinstance(user_data, dict) else 0
            try:
                depth = int(raw_depth)
            except (TypeError, ValueError):
                depth = 0
        except (TypeError, ValueError):
            depth = 0

        retrieved_at = datetime.now(UTC)
        status_code = 0
        final_url = url
        title: str | None = None
        text = ""
        html: str | None = None
        content_type: str | None = None
        error: str | None = None
        try:
            loaded = getattr(context.request, "loaded_url", None)
            if loaded:
                final_url = loaded
            if not is_safe_url(final_url):
                error = "redirect target failed safety validation"
                results.append(
                    CrawledPage(
                        url=url,
                        final_url=final_url,
                        status_code=status_code,
                        title=title,
                        text=text,
                        html=html,
                        content_type=content_type,
                        retrieved_at=retrieved_at,
                        depth=depth,
                        error=error,
                    )
                )
                return

            response = context.http_response
            status_code = int(getattr(response, "status_code", 0) or 0)
            headers = getattr(response, "headers", {}) or {}
            content_type = headers.get("content-type") or headers.get("Content-Type")
            content_length = headers.get("content-length") or headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > config.response_size_limit:
                        error = "response exceeded size limit"
                        results.append(
                            CrawledPage(
                                url=url,
                                final_url=final_url,
                                status_code=status_code,
                                title=title,
                                text=text,
                                html=html,
                                content_type=content_type,
                                retrieved_at=retrieved_at,
                                depth=depth,
                                error=error,
                            )
                        )
                        return
                except (TypeError, ValueError):
                    pass
            body = await response.read()
            if len(body) > config.response_size_limit:
                body = body[: config.response_size_limit]
            if not _content_type_allowed(content_type, config):
                error = f"unsupported content type: {content_type}"
            else:
                html = body.decode("utf-8", "replace")
                title, text = _normalize_text(html)
                html = html[:200000]
        except Exception as exc:  # noqa: BLE001
            error = f"fetch failed: {exc}"

        results.append(
            CrawledPage(
                url=url,
                final_url=final_url,
                status_code=status_code,
                title=title,
                text=text,
                html=html,
                content_type=content_type,
                retrieved_at=retrieved_at,
                depth=depth,
                error=error,
            )
        )

        if error is not None:
            return
        if depth >= config.max_depth:
            return
        if len(results) >= config.max_pages:
            return

        def transform(request: Any) -> Any:
            if isinstance(request, dict):
                url_value = request.get("url")
            else:
                url_value = getattr(request, "url", None)
            link_url = urldefrag(url_value)[0] if url_value else None
            if not link_url or not is_safe_url(link_url):
                return "skip"
            if config.same_domain_only and not _same_domain(link_url, root):
                return "skip"
            if path_hints:
                lowered = link_url.lower()
                if not any(hint in lowered for hint in path_hints):
                    if link_url.rstrip("/") not in (seed_url.rstrip("/"),):
                        return "skip"
            if isinstance(request, dict):
                request["user_data"] = {"depth": depth + 1}
            else:
                try:
                    request.user_data = {"depth": depth + 1}
                except Exception:  # noqa: BLE001
                    pass
            return request

        try:
            await context.enqueue_links(transform_request_function=transform)
        except Exception as exc:  # noqa: BLE001
            logger.warning("enqueue_links failed: %s", exc)

    @crawler.failed_request_handler
    async def failed_handler(
        context: BeautifulSoupCrawlingContext | BasicCrawlingContext,
        error: Exception,
    ) -> None:
        url = context.request.url
        if url in visited:
            return
        visited.add(url)
        user_data = context.request.user_data or {}
        raw_depth = user_data.get("depth", 0) if isinstance(user_data, dict) else 0
        try:
            depth = int(raw_depth)
        except (TypeError, ValueError):
            depth = 0
        results.append(
            CrawledPage(
                url=url,
                final_url=url,
                status_code=0,
                retrieved_at=datetime.now(UTC),
                depth=depth,
                error=f"fetch failed ({type(error).__name__})",
            )
        )

    try:
        seed_request = Request.from_url(seed_url, user_data={"depth": 0})
        await crawler.run([seed_request])
    except Exception as exc:  # noqa: BLE001
        logger.warning("crawl failed for %s: %s", seed_url, exc)
        if not results:
            results.append(
                CrawledPage(
                    url=seed_url,
                    final_url=seed_url,
                    status_code=0,
                    error=f"crawl failed: {exc}",
                )
            )
    finally:
        shutil.rmtree(storage_dir, ignore_errors=True)

    # Deduplicate by URL preserving order.
    seen_urls: set[str] = set()
    unique: list[CrawledPage] = []
    for page in results:
        if page.url in seen_urls:
            continue
        seen_urls.add(page.url)
        unique.append(page)
    return unique[: config.max_pages]


def timedelta_seconds(seconds: float) -> timedelta:  # noqa: D401
    """Return a timedelta for the given number of seconds."""
    from datetime import timedelta

    return timedelta(seconds=seconds)


_THREAD_LOCAL = threading.local()


def _thread_event_loop() -> asyncio.AbstractEventLoop:
    """Return a reusable event loop for the current thread."""
    loop = getattr(_THREAD_LOCAL, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _THREAD_LOCAL.loop = loop
    return loop


def crawl_website_sync(  # noqa: D401
    seed_url: str,
    config: CrawlConfig | None = None,
    path_hints: list[str] | None = None,
) -> list[CrawledPage]:
    """Run crawl_website synchronously."""
    loop = _thread_event_loop()
    return loop.run_until_complete(crawl_website(seed_url, config, path_hints))


def extract_links(html: str, base_url: str) -> list[str]:
    """Extract same-document links from HTML (utility for tests)."""
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        joined = urldefrag(urljoin(base_url, href))[0]
        if is_safe_url(joined):
            links.append(joined)
    return links
