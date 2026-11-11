"""Crawlee-backed decision-maker discovery from public company pages.

Only names and titles that are explicitly published on the company's own pages
(or pages retrieved during crawling) are returned. LinkedIn and other platforms
are never scraped or bypassed; profile URLs are only recorded when the company
page links to them.
"""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from app.engine.contracts import (
    CompanyCandidate,
    DecisionMakerCandidate,
    DecisionMakerProvider,
    ICPQuery,
    ProviderStatus,
)
from app.engine.crawler import CrawlConfig, crawl_website_sync, is_safe_url
from app.engine.normalization import normalize_domain

# Title keywords we consider relevant decision-makers, in priority order.
ROLE_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\b(?:co[- ]?founder|founder)\b", re.I), 1),
    (re.compile(r"\bchief executive officer\b|\bceo\b", re.I), 2),
    (re.compile(r"\bchief marketing officer\b|\bcmo\b", re.I), 3),
    (re.compile(r"\bhead of marketing\b", re.I), 4),
    (re.compile(r"\bmarketing director\b", re.I), 5),
    (re.compile(r"\bvp (?:of )?marketing\b|\bvice president (?:of )?marketing\b", re.I), 6),
    (re.compile(r"\bcoo\b|chief operating officer\b", re.I), 7),
    (re.compile(r"\bcto\b|chief technology officer\b", re.I), 8),
]

NAME_RE = re.compile(
    r"\b([A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,}){1,2})\b"
)

# Lines like "Jane Doe, CEO" or "CEO: Jane Doe" or "Jane Doe - Chief Executive Officer"
LINE_PATTERNS = [
    re.compile(r"([A-Za-z][A-Za-z'’\-]+(?:\s+[A-Za-z][A-Za-z'’\-]+){1,2})\s*[,–—-]\s*(.+?)\s*$"),
    re.compile(r"^(.+?)\s*[:–—-]\s*([A-Za-z][A-Za-z'’\-]+(?:\s+[A-Za-z][A-Za-z'’\-]+){1,2})\s*$"),
]


def _role_priority(title: str) -> int:
    for pattern, priority in ROLE_PATTERNS:
        if pattern.search(title):
            return priority
    return 100


def _is_relevant_title(title: str) -> bool:
    lowered = title.lower()
    return any(
        keyword in lowered
        for keyword in (
            "founder",
            "ceo",
            "cmo",
            "marketing",
            "chief",
            "coo",
            "head of",
            "director",
            "president",
            "owner",
            "managing",
        )
    )


def _normalize_title(title: str) -> str:
    return " ".join(title.split())[:256]


def _jsonld_people(html: str, source_url: str) -> list[DecisionMakerCandidate]:  # noqa: C901
    """Extract Person objects from JSON-LD blocks."""
    results: list[DecisionMakerCandidate] = []
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:  # noqa: BLE001
        return results
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = payload if isinstance(payload, list) else [payload]
        stack = list(items)
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                node_type = node.get("@type")
                types = node_type if isinstance(node_type, list) else [node_type]
                if any(str(t).lower() in ("person", "employee", "organizationrole") for t in types if t):
                    name = node.get("name") or node.get("givenName")
                    title = node.get("jobTitle") or node.get("title")
                    if isinstance(name, str) and isinstance(title, str):
                        name = " ".join(name.split())
                        title = _normalize_title(title)
                        if len(name.split()) >= 2 and _is_relevant_title(title):
                            results.append(
                                DecisionMakerCandidate(
                                    full_name=name,
                                    job_title=title,
                                    profile_source=source_url,
                                    source_url=source_url,
                                    evidence_excerpt=f"{name}, {title}",
                                    role_priority=_role_priority(title),
                                    synthetic=False,
                                )
                            )
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(node, list):
                stack.extend(node)
    return results


def _html_card_people(html: str, source_url: str) -> list[DecisionMakerCandidate]:  # noqa: C901
    """Extract name/title pairs from semantic team cards."""
    results: list[DecisionMakerCandidate] = []
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:  # noqa: BLE001
        return results
    card_selectors = [
        "article",
        "li",
        "div",
        "section",
    ]
    for selector in card_selectors:
        for node in soup.find_all(selector):
            classes = " ".join(node.get("class") or []).lower()
            if not any(
                token in classes
                for token in ("team", "leader", "person", "member", "bio", "executive", "staff")
            ) and selector != "article":
                if not node.find(["h1", "h2", "h3", "h4", "h5", "h6", "strong"]):
                    continue
            text = " ".join(node.get_text(" ", strip=True).split())
            if not text or len(text) > 300:
                continue
            for pattern in LINE_PATTERNS:
                match = pattern.match(text)
                if not match:
                    continue
                left, right = match.group(1).strip(), match.group(2).strip()
                if _is_relevant_title(right) and NAME_RE.fullmatch(left):
                    name, title = left, right
                elif _is_relevant_title(left) and NAME_RE.fullmatch(right):
                    name, title = right, left
                else:
                    continue
                if not _is_relevant_title(title):
                    continue
                results.append(
                    DecisionMakerCandidate(
                        full_name=name,
                        job_title=_normalize_title(title),
                        profile_source=source_url,
                        source_url=source_url,
                        evidence_excerpt=text,
                        role_priority=_role_priority(title),
                        synthetic=False,
                    )
                )
    return results


def extract_decision_makers_from_html(html: str, source_url: str) -> list[DecisionMakerCandidate]:
    """Extract decision-makers from an HTML document using multiple methods."""
    results: list[DecisionMakerCandidate] = []
    results.extend(_jsonld_people(html, source_url))
    results.extend(_html_card_people(html, source_url))
    try:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
    except Exception:  # noqa: BLE001
        text = html
    results.extend(extract_decision_makers_from_text(text, source_url))
    # Deduplicate by name across extraction methods, keeping highest priority.
    by_name: dict[str, DecisionMakerCandidate] = {}
    for candidate in results:
        key = (candidate.full_name or "").lower()
        if key not in by_name or candidate.role_priority < by_name[key].role_priority:
            by_name[key] = candidate
    return list(by_name.values())


def extract_decision_makers_from_text(text: str, source_url: str) -> list[DecisionMakerCandidate]:  # noqa: C901
    """Extract (name, title) pairs from a block of text."""
    from app.engine.contracts import DecisionMakerCandidate

    results: list[DecisionMakerCandidate] = []
    seen: set[str] = set()
    # Try line-oriented patterns.
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line or len(line) > 120:
            continue
        for pattern in LINE_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            left, right = match.group(1).strip(), match.group(2).strip()
            if _is_relevant_title(right) and NAME_RE.fullmatch(left):
                name, title = left, right
            elif _is_relevant_title(left) and NAME_RE.fullmatch(right):
                name, title = right, left
            else:
                continue
            if not _is_relevant_title(title):
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            results.append(
                DecisionMakerCandidate(
                    full_name=name,
                    job_title=title[:256],
                    profile_source=source_url,
                    source_url=source_url,
                    evidence_excerpt=line,
                    role_priority=_role_priority(title),
                    synthetic=False,
                )
            )

    # Parenthetical form: "Sean Standberry (CEO)" or "Name (Title, Credential)".
    for match in re.finditer(
        r"([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){1,2})\s*\(([^)]{1,80})\)",
        text,
    ):
        name = " ".join(match.group(1).split())
        title = _normalize_title(match.group(2))
        if not NAME_RE.fullmatch(name):
            continue
        if not _is_relevant_title(title):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(
            DecisionMakerCandidate(
                full_name=name,
                job_title=title[:256],
                profile_source=source_url,
                source_url=source_url,
                evidence_excerpt=match.group(0),
                role_priority=_role_priority(title),
                synthetic=False,
            )
        )

    # Fallback: scan for "Name Title" adjacent capitalized words.
    if not results:
        for match in re.finditer(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s+(CEO|CTO|CMO|Founder|Co-Founder|Head of Marketing|Marketing Director)\b",
            text,
        ):
            name = match.group(1)
            title = match.group(2)
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            results.append(
                DecisionMakerCandidate(
                    full_name=name,
                    job_title=title,
                    profile_source=source_url,
                    source_url=source_url,
                    evidence_excerpt=match.group(0),
                    role_priority=_role_priority(title),
                    synthetic=False,
                )
            )
    return results


class CrawleeDecisionMakerProvider(DecisionMakerProvider):
    """Discover decision-makers from public company pages."""

    name = "crawlee_public_pages"
    synthetic = False
    cost_per_call_usd = 0.0

    def __init__(self, *, max_pages: int = 12) -> None:
        """Configure the crawl bound."""
        self._max_pages = max_pages

    def status(self) -> ProviderStatus:
        """Report readiness."""
        return ProviderStatus(
            name=self.name,
            capability="decision_makers",
            state="ready",
            synthetic=False,
            detail="Public company pages only; no platform scraping or access bypass.",
            cost_per_call_usd=self.cost_per_call_usd,
        )

    def discover_decision_makers(
        self, company: CompanyCandidate, icp: ICPQuery
    ) -> list[DecisionMakerCandidate]:
        """Return decision-makers found on public pages."""
        seed = self._seed_url(company)
        if not seed or not is_safe_url(seed):
            return []
        config = CrawlConfig(max_pages=self._max_pages, max_depth=2)
        pages = crawl_website_sync(
            seed,
            config,
            ["team", "leadership", "about", "people", "management", "executive", "contact"],
        )
        collected: list[DecisionMakerCandidate] = []
        by_name: dict[str, DecisionMakerCandidate] = {}
        for page in pages:
            if not page.ok:
                continue
            candidates: list[DecisionMakerCandidate] = []
            page_html = getattr(page, "html", None)
            if page_html:
                candidates.extend(
                    extract_decision_makers_from_html(page_html, page.final_url)
                )
            elif page.text:
                candidates.extend(
                    extract_decision_makers_from_text(page.text, page.final_url)
                )
            for candidate in candidates:
                key = (candidate.full_name or "").lower()
                if key not in by_name:
                    by_name[key] = candidate
                else:
                    existing = by_name[key]
                    if candidate.role_priority < existing.role_priority:
                        by_name[key] = candidate
            if len(by_name) >= 8:
                break
        collected = list(by_name.values())
        collected.sort(key=lambda item: (item.role_priority, item.full_name))
        return collected[:8]

    def _seed_url(self, company: CompanyCandidate) -> str | None:
        """Derive a seed URL from the company record."""
        domain = normalize_domain(company.domain or company.website)
        if not domain:
            return None
        if company.website and company.website.startswith(("http://", "https://")):
            return company.website
        return f"https://{domain}"
