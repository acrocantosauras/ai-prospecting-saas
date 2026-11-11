"""Crawlee-backed company research and evidence collection.

This provider replaces search-snippet-only research with actual first-party
website crawling. It never invents facts: every field is derived from text that
was retrieved, and missing fields are reported in ``missing_information``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.engine.contracts import (
    CompanyCandidate,
    CompanyResearch,
    CompanyResearchProvider,
    EvidenceProvider,
    ICPQuery,
    ProviderStatus,
    SourceRef,
)
from app.engine.crawler import CrawlConfig, CrawledPage, crawl_website_sync, is_safe_url
from app.engine.normalization import normalize_domain

RELEVANT_PATH_HINTS = (
    "about",
    "product",
    "service",
    "solution",
    "industry",
    "case",
    "customer",
    "blog",
    "news",
    "team",
    "leadership",
    "contact",
)


class CrawleeResearchProvider(CompanyResearchProvider, EvidenceProvider):
    """Crawl a company website and extract structured research."""

    name = "crawlee_http"
    synthetic = False
    cost_per_call_usd = 0.0

    def __init__(self, *, max_pages: int = 15, max_depth: int = 2) -> None:
        """Configure crawl bounds."""
        self._max_pages = max_pages
        self._max_depth = max_depth

    def status(self) -> ProviderStatus:
        """Report readiness."""
        return ProviderStatus(
            name=self.name,
            capability="company_research",
            state="ready",
            synthetic=False,
            detail="HTTP crawling of permitted public first-party pages via Crawlee.",
            cost_per_call_usd=self.cost_per_call_usd,
        )

    def _seed_url(self, company: CompanyCandidate) -> str | None:
        """Derive a seed URL from the company record."""
        domain = normalize_domain(company.domain or company.website)
        if not domain:
            return None
        if company.website and company.website.startswith(("http://", "https://")):
            return company.website
        return f"https://{domain}"

    def research(self, company: CompanyCandidate, icp: ICPQuery) -> CompanyResearch:
        """Crawl and extract research."""
        seed = self._seed_url(company)
        if not seed or not is_safe_url(seed):
            return CompanyResearch(
                provider=self.name,
                missing_information=["no safe, resolvable website URL was available"],
                confidence=0.0,
                synthetic=False,
            )
        config = CrawlConfig(max_pages=self._max_pages, max_depth=self._max_depth)
        pages = crawl_website_sync(seed, config, list(RELEVANT_PATH_HINTS))
        ok_pages = [page for page in pages if page.ok and page.text]
        evidence = self._evidence_from_pages(ok_pages)
        what_it_does = self._field_from_pages(ok_pages, ("about", "home", ""), "about")
        what_it_sells = self._field_from_pages(ok_pages, ("product", "service", "solution", "pricing"), "offering")
        who_it_serves = self._detect_customers(ok_pages)
        positioning = self._positioning(ok_pages)
        signals = [f"page: {page.title or page.url}" for page in ok_pages[:8]]
        missing: list[str] = []
        if not ok_pages:
            missing.append(f"no accessible first-party pages were retrieved for {normalize_domain(seed)}")
        if not what_it_does:
            missing.append("company description was not found on crawled pages")
        if not what_it_sells:
            missing.append("product/service details were not found on crawled pages")
        missing.append("public developments were not retrieved in this run")
        confidence = 0.0
        if ok_pages:
            confidence = min(0.75, 0.25 + 0.08 * len(ok_pages))
        return CompanyResearch(
            provider=self.name,
            what_it_does=what_it_does,
            what_it_sells=what_it_sells,
            who_it_serves=who_it_serves,
            positioning=positioning,
            public_developments=None,
            observable_signals=signals,
            evidence=evidence,
            missing_information=missing,
            confidence=round(confidence, 3),
            synthetic=False,
            researched_at=datetime.now(UTC),
        )

    def collect(self, company: CompanyCandidate) -> list[SourceRef]:
        """Collect evidence references."""
        seed = self._seed_url(company)
        if not seed or not is_safe_url(seed):
            return []
        config = CrawlConfig(max_pages=self._max_pages, max_depth=self._max_depth)
        pages = crawl_website_sync(seed, config, list(RELEVANT_PATH_HINTS))
        return self._evidence_from_pages([p for p in pages if p.ok and p.text])

    def _evidence_from_pages(self, pages: list[CrawledPage]) -> list[SourceRef]:
        refs: list[SourceRef] = []
        seen: set[str] = set()
        for page in pages:
            if page.final_url in seen:
                continue
            seen.add(page.final_url)
            refs.append(
                SourceRef(
                    url=page.final_url,
                    title=page.title,
                    source_type="crawled_page",
                    snippet=(page.text or "")[:400] or None,
                    retrieved_at=page.retrieved_at,
                    verified=True,
                )
            )
        return refs

    def _field_from_pages(
        self, pages: list[CrawledPage], keywords: tuple[str, ...], fallback_label: str
    ) -> str | None:
        # Prefer a page whose URL or title matches the requested topic.
        for page in pages:
            haystack = f"{page.url} {page.title or ''}".lower()
            if any(keyword in haystack for keyword in keywords):
                if page.text:
                    return page.text[:400]
        # Fall back to the first substantial page (usually the homepage).
        for page in pages:
            if page.text and len(page.text) > 80:
                return page.text[:400]
        return None

    def _detect_customers(self, pages: list[CrawledPage]) -> str | None:
        combined = " ".join(page.text for page in pages).lower()
        markers = ("customers", "clients", "trusted by", "used by", "case study")
        for marker in markers:
            idx = combined.find(marker)
            if idx != -1:
                start = max(0, idx - 40)
                return combined[start : start + 240].strip()[:400] or None
        return None

    def _positioning(self, pages: list[CrawledPage]) -> str | None:
        for page in pages:
            if "about" in page.url.lower() or "about" in (page.title or "").lower():
                if page.text:
                    return page.text[:400]
        return None
