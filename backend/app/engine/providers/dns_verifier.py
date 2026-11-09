"""DNS-level email checks.

These checks can show that an address is malformed or that a domain does not
accept mail. They can never prove a mailbox exists, so this provider never
returns ``verified``. A dedicated mailbox-verification API is required for that.
"""

from __future__ import annotations

import importlib
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass

from app.engine.contracts import (
    EmailVerificationProvider,
    ProviderStatus,
    VerificationResult,
)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# A provider-supplied address must not make the server resolve internal names.
_INTERNAL_SUFFIXES = (
    ".internal",
    ".local",
    ".localdomain",
    ".localhost",
    ".lan",
    ".corp",
    ".home",
    ".intranet",
)


def _is_internal_domain(domain: str) -> bool:
    candidate = domain.strip().lower().rstrip(".")
    if candidate in ("localhost", "metadata", "instance-data"):
        return True
    if "." not in candidate:
        return True
    return any(candidate.endswith(suffix) for suffix in _INTERNAL_SUFFIXES)


@dataclass(frozen=True)
class DomainLookup:
    """Outcome of a DNS lookup for an email domain."""

    resolves: bool
    has_mx: bool | None
    detail: str


DomainResolver = Callable[[str], DomainLookup]


def default_resolver(domain: str) -> DomainLookup:
    """Resolve a domain using a system A record and optional MX lookup."""
    try:
        socket.getaddrinfo(domain, None)
    except socket.gaierror:
        return DomainLookup(False, None, "domain did not resolve")
    except OSError as exc:  # pragma: no cover - platform dependent
        return DomainLookup(False, None, f"DNS lookup failed: {exc}")
    has_mx = _lookup_mx(domain)
    if has_mx is True:
        return DomainLookup(True, True, "domain resolves and publishes MX records")
    if has_mx is False:
        return DomainLookup(True, False, "domain resolves but publishes no MX record")
    return DomainLookup(
        True, None, "domain resolves via system DNS; MX records were not checked"
    )


def _lookup_mx(domain: str) -> bool | None:
    """Return MX presence when dnspython is installed, else ``None``."""
    try:
        resolver_module = importlib.import_module("dns.resolver")
    except ImportError:
        return None
    try:
        answers = resolver_module.resolve(domain, "MX", lifetime=5.0)
    except Exception:  # noqa: BLE001 - optional dependency, any resolver error
        return None
    return bool(list(answers))


class DnsEmailVerificationProvider(EmailVerificationProvider):
    """Syntax + DNS verification. Deliberately never returns ``verified``."""

    name = "dns_syntax"
    capability = "email_verification"

    def __init__(
        self,
        *,
        resolver: DomainResolver | None = None,
        cost_per_call_usd: float = 0.0,
    ) -> None:
        """Allow injecting a resolver so tests never touch the network."""
        self._resolver = resolver or default_resolver
        self.cost_per_call_usd = cost_per_call_usd

    def status(self) -> ProviderStatus:
        """Report readiness and the method's fundamental limitation."""
        return ProviderStatus(
            name=self.name,
            capability=self.capability,
            state="ready",
            synthetic=False,
            detail=(
                "Syntax and DNS checks only. Mailbox existence is never proven, so this "
                "provider never returns status 'verified'."
            ),
            cost_per_call_usd=self.cost_per_call_usd,
        )

    def verify(self, email: str) -> VerificationResult:
        """Return a conservative verification result for ``email``."""
        cleaned = (email or "").strip().lower()
        if not cleaned or not EMAIL_RE.match(cleaned):
            return VerificationResult(
                provider=self.name,
                email=cleaned or None,
                status="invalid",
                method="syntax",
                confidence=0.85,
                detail="address failed syntax validation",
            )
        domain = cleaned.rsplit("@", 1)[1]
        if _is_internal_domain(domain):
            return VerificationResult(
                provider=self.name,
                email=cleaned,
                status="invalid",
                method="dns_resolution",
                confidence=0.8,
                detail="email domain is not a public domain; DNS lookup skipped",
            )
        lookup = self._resolver(domain)
        if not lookup.resolves:
            return VerificationResult(
                provider=self.name,
                email=cleaned,
                status="not_found",
                method="dns_resolution",
                confidence=0.7,
                detail=f"{domain}: {lookup.detail}; mailbox not checked",
            )
        if lookup.has_mx is False:
            return VerificationResult(
                provider=self.name,
                email=cleaned,
                status="risky",
                method="dns_mx",
                confidence=0.35,
                detail=(
                    f"{domain}: {lookup.detail}; the address is likely undeliverable "
                    "but mailbox existence is not proven"
                ),
            )
        return VerificationResult(
            provider=self.name,
            email=cleaned,
            status="unknown",
            method="dns_mx",
            confidence=0.2,
            detail=f"{domain}: {lookup.detail}; mailbox existence not verified",
        )
