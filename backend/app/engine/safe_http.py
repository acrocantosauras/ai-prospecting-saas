"""HTTP requests with explicit redirects and pinned, validated IP addresses."""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin, urlsplit

DEFAULT_MAX_REDIRECTS = 5
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 15.0

# Methods that may be retried on another validated address when a connection
# attempt fails. Non-idempotent methods (POST) are never retried across
# addresses: even an ambiguous failure must not duplicate a paid provider call.
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE", "PUT", "DELETE"})
_PROHIBITED_HOST_SUFFIXES = (
    ".internal",
    ".local",
    ".localdomain",
    ".lan",
    ".corp",
    ".home",
    ".intranet",
)


class SafeHttpError(Exception):
    """Base exception for URL validation and pinned HTTP failures."""


class UnsafeUrlError(SafeHttpError):
    """The URL or one of its resolved addresses violates the network policy."""


class RedirectLoopError(SafeHttpError):
    """A request attempted to revisit a URL in its redirect chain."""


class TooManyRedirectsError(SafeHttpError):
    """A request exceeded its configured redirect limit."""


@dataclass(frozen=True)
class ResolvedAddress:
    """A single validated socket destination returned by DNS resolution."""

    family: int
    socket_type: int
    protocol: int
    sockaddr: tuple[object, ...]
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address


@dataclass(frozen=True)
class SafeHttpResponse:
    """A bounded HTTP response and the final URL reached safely."""

    status_code: int
    headers: dict[str, str]
    body: bytes
    final_url: str
    body_truncated: bool = False


def _is_public_ip(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """Reject every non-global address, including IPv4-mapped IPv6."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return (
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def _is_allowed_port(scheme: str, port: int) -> bool:
    """Permit only the conventional HTTP and HTTPS service ports."""
    return (scheme == "http" and port == 80) or (scheme == "https" and port == 443)


def _literal_address(host: str, port: int) -> ResolvedAddress | None:
    """Validate and normalize an IP literal without performing DNS."""
    try:
        literal = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return None
    if "%" in host or not _is_public_ip(literal):
        raise UnsafeUrlError("URL host resolves to a prohibited address.")
    family = socket.AF_INET6 if literal.version == 6 else socket.AF_INET
    sockaddr: tuple[object, ...] = (str(literal), port, 0, 0) if family == socket.AF_INET6 else (str(literal), port)
    return ResolvedAddress(family, socket.SOCK_STREAM, 0, sockaddr, literal)


def _resolved_address(
    family: int,
    socket_type: int,
    protocol: int,
    sockaddr: tuple[object, ...],
    port: int,
) -> ResolvedAddress:
    """Validate and normalize one DNS answer for direct socket use."""
    if family not in (socket.AF_INET, socket.AF_INET6):
        raise UnsafeUrlError("URL host resolved to an unsupported address.")
    if socket_type != socket.SOCK_STREAM:
        raise UnsafeUrlError("URL host resolved to an unsupported socket type.")
    try:
        raw_host = sockaddr[0]
        if not isinstance(raw_host, str) or "%" in raw_host:
            raise UnsafeUrlError("URL host resolved to an invalid address.")
        address = ipaddress.ip_address(raw_host)
    except (ValueError, IndexError, TypeError) as exc:
        raise UnsafeUrlError("URL host resolved to an invalid address.") from exc
    if not _is_public_ip(address):
        raise UnsafeUrlError("URL host resolves to a prohibited address.")
    if family == socket.AF_INET6:
        scope_id = sockaddr[3] if len(sockaddr) > 3 else 0
        if scope_id:
            raise UnsafeUrlError("Scoped IPv6 destinations are not allowed.")
        pinned_sockaddr: tuple[object, ...] = (str(address), port, 0, 0)
    else:
        pinned_sockaddr = (str(address), port)
    return ResolvedAddress(family, socket_type, protocol, pinned_sockaddr, address)


def _resolve_host(host: str, port: int) -> tuple[ResolvedAddress, ...]:
    """Resolve once and reject the entire host if any answer is unsafe."""
    literal = _literal_address(host, port)
    if literal is not None:
        return (literal,)

    if "." not in host or host.lower().endswith(_PROHIBITED_HOST_SUFFIXES):
        raise UnsafeUrlError("URL host is not publicly routable.")

    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, OSError) as exc:
        raise SafeHttpError("URL host could not be resolved.") from exc

    addresses: list[ResolvedAddress] = []
    seen: set[tuple[int, str]] = set()
    for family, socket_type, protocol, _, sockaddr in records:
        address = _resolved_address(family, socket_type, protocol, sockaddr, port)
        key = (address.family, str(address.ip))
        if key not in seen:
            seen.add(key)
            addresses.append(address)
    if not addresses:
        raise SafeHttpError("URL host did not resolve to a usable address.")
    return tuple(addresses)


def _validate_and_resolve(
    url: str, *, require_https: bool = False
) -> tuple[str, str, int, tuple[ResolvedAddress, ...]]:
    """Validate the URL and bind the request to its already-vetted DNS answers."""
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        host = parsed.hostname
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeUrlError("URL is malformed.") from exc

    if scheme not in ("http", "https") or not host:
        raise UnsafeUrlError("Only absolute HTTP and HTTPS URLs are allowed.")
    if require_https and scheme != "https":
        raise UnsafeUrlError("This request requires HTTPS at every redirect hop.")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("URL credentials are not allowed.")
    if not _is_allowed_port(scheme, port):
        raise UnsafeUrlError("URL port is not allowed.")
    addresses = _resolve_host(host, port)
    return scheme, host, port, addresses


def is_safe_url(url: str) -> bool:
    """Return whether a URL is currently safe to request under this policy."""
    try:
        _validate_and_resolve(url)
    except (SafeHttpError, TypeError, ValueError):
        return False
    return True


def _connect_pinned(address: ResolvedAddress, timeout: float) -> socket.socket:
    """Connect directly to a validated sockaddr without resolving its hostname."""
    sock = socket.socket(address.family, address.socket_type, address.protocol)
    try:
        sock.settimeout(timeout)
        sock.connect(address.sockaddr)
    except Exception:
        sock.close()
        raise
    return sock


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: ResolvedAddress, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._validated_address = address

    def connect(self) -> None:
        self.sock = _connect_pinned(self._validated_address, self.timeout or 15.0)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        port: int,
        address: ResolvedAddress,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(host, port, timeout=timeout, context=context)
        self._validated_address = address
        self._ssl_context = context

    def connect(self) -> None:
        raw_socket = _connect_pinned(self._validated_address, self.timeout or DEFAULT_TIMEOUT_SECONDS)
        try:
            self.sock = self._ssl_context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def _normalized_url(url: str) -> str:
    """Normalize fragments away for redirect-loop detection."""
    return urldefrag(url)[0]


def _redirect_target(
    status_code: int,
    headers: dict[str, str],
    current_url: str,
    visited: set[str],
    *,
    redirects: int,
    max_redirects: int,
    same_origin_only: bool,
) -> str | None:
    """Validate redirect count, loop, syntax, origin policy and TLS downgrades."""
    location = headers.get("location")
    if status_code not in (301, 302, 303, 307, 308) or not location:
        return None
    if redirects >= max_redirects:
        raise TooManyRedirectsError("HTTP redirect limit exceeded.")

    next_url = _normalized_url(urljoin(current_url, location))
    if next_url in visited:
        raise RedirectLoopError("HTTP redirect loop detected.")
    try:
        old_parts = urlsplit(current_url)
        new_parts = urlsplit(next_url)
        old_origin = (old_parts.scheme.lower(), old_parts.hostname, old_parts.port)
        new_origin = (new_parts.scheme.lower(), new_parts.hostname, new_parts.port)
    except ValueError as exc:
        raise UnsafeUrlError("HTTP redirect target is malformed.") from exc
    # A secured hop must never be downgraded to cleartext, whatever the caller
    # asked for: the redirect itself is attacker-controllable.
    if old_parts.scheme.lower() == "https" and new_parts.scheme.lower() == "http":
        raise UnsafeUrlError("HTTPS-to-HTTP redirect downgrades are not allowed.")
    if same_origin_only and old_origin != new_origin:
        raise UnsafeUrlError("Cross-origin redirects are blocked for this request.")
    return next_url


def _send_once(
    scheme: str,
    host: str,
    port: int,
    addresses: tuple[ResolvedAddress, ...],
    method: str,
    target: str,
    headers: dict[str, str],
    body: bytes | None,
    deadline: float,
    max_response_bytes: int,
    retry_across_addresses: bool = True,
) -> tuple[int, dict[str, str], bytes, bool]:
    """Issue one request using only the already-validated address list."""
    last_error: OSError | None = None
    for address_index, address in enumerate(addresses):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("HTTP request timed out.")
        if scheme == "https":
            connection: http.client.HTTPConnection = _PinnedHTTPSConnection(
                host,
                port,
                address,
                remaining,
                ssl.create_default_context(),
            )
        else:
            connection = _PinnedHTTPConnection(host, port, address, remaining)
        try:
            connection.request(method, target, body=body, headers=headers)
            response = connection.getresponse()
            response_headers = {name.lower(): value for name, value in response.getheaders()}
            if response.status in (301, 302, 303, 307, 308) and response_headers.get("location"):
                return response.status, response_headers, b"", False
            data = response.read(max_response_bytes + 1)
            return (
                response.status,
                response_headers,
                data[:max_response_bytes],
                len(data) > max_response_bytes,
            )
        except OSError as exc:
            last_error = exc
            if (
                not retry_across_addresses
                or connection.sock is not None
                or address_index == len(addresses) - 1
            ):
                raise
        finally:
            connection.close()
    if last_error is not None:
        raise last_error
    raise SafeHttpError("No validated address could be connected.")


def _send_hop(
    url: str,
    method: str,
    headers: dict[str, str],
    body: bytes | None,
    deadline: float,
    max_response_bytes: int,
    require_https: bool,
) -> tuple[int, dict[str, str], bytes, bool]:
    """Validate and send one hop before any socket request is issued."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("HTTP request timed out.")
    scheme, host, port, addresses = _validate_and_resolve(url, require_https=require_https)
    parsed = urlsplit(url)
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    request_headers = {key: value for key, value in headers.items() if key.lower() not in ("host", "connection")}
    request_headers["Connection"] = "close"
    return _send_once(
        scheme,
        host,
        port,
        addresses,
        method,
        target,
        request_headers,
        body,
        deadline,
        max_response_bytes,
        retry_across_addresses=method.upper() in _IDEMPOTENT_METHODS,
    )


def _prepare_redirect_request(
    status_code: int,
    current_url: str,
    next_url: str,
    headers: dict[str, str],
    method: str,
    body: bytes | None,
) -> tuple[dict[str, str], str, bytes | None]:
    """Apply origin credential stripping and HTTP redirect method semantics."""
    old_parts = urlsplit(current_url)
    new_parts = urlsplit(next_url)
    if (old_parts.scheme, old_parts.hostname, old_parts.port) != (
        new_parts.scheme,
        new_parts.hostname,
        new_parts.port,
    ):
        headers = {
            key: value
            for key, value in headers.items()
            if key.lower() not in ("authorization", "cookie", "proxy-authorization")
        }
    if status_code == 303 and method not in ("GET", "HEAD"):
        return headers, "GET", None
    if status_code in (301, 302) and method == "POST":
        return headers, "GET", None
    return headers, method, body


def safe_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    require_https: bool = False,
    same_origin_only: bool = False,
) -> SafeHttpResponse:
    """Send an HTTP request with hop-by-hop validation and pinned connections.

    Each URL is resolved exactly once immediately before connecting. Every
    answer must be globally routable, and the socket connects directly to one
    of those validated addresses. Redirect destinations are independently
    resolved and validated before any request is sent to them.
    """
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if max_redirects < 0:
        raise ValueError("max_redirects must be non-negative")
    if max_response_bytes < 0:
        raise ValueError("max_response_bytes must be non-negative")
    deadline = time.monotonic() + timeout
    current_url = _normalized_url(url)
    current_method = method.upper()
    current_body = body
    current_headers = dict(headers or {})
    visited: set[str] = set()
    redirects = 0

    while True:
        normalized = _normalized_url(current_url)
        if normalized in visited:
            raise RedirectLoopError("HTTP redirect loop detected.")
        visited.add(normalized)
        status_code, response_headers, response_body, body_truncated = _send_hop(
            current_url,
            current_method,
            current_headers,
            current_body,
            deadline,
            max_response_bytes,
            require_https,
        )
        next_url = _redirect_target(
            status_code,
            response_headers,
            current_url,
            visited,
            redirects=redirects,
            max_redirects=max_redirects,
            same_origin_only=same_origin_only,
        )
        if next_url is None:
            return SafeHttpResponse(
                status_code=status_code,
                headers=response_headers,
                body=response_body,
                final_url=current_url,
                body_truncated=body_truncated,
            )
        current_headers, current_method, current_body = _prepare_redirect_request(
            status_code,
            current_url,
            next_url,
            current_headers,
            current_method,
            current_body,
        )
        current_url = next_url
        redirects += 1
