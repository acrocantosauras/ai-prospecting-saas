"""Adversarial tests for redirect validation and pinned outbound connections."""

from __future__ import annotations

import datetime
import http.server
import ipaddress
import socket
import ssl
import threading
from collections import Counter
from pathlib import Path

import pytest

import app.engine.safe_http as safe_http
from app.engine.crawler import CrawlConfig, crawl_website_sync
from app.engine.providers.multi_discovery import _fetch_html
from app.engine.safe_http import (
    RedirectLoopError,
    ResolvedAddress,
    TooManyRedirectsError,
    UnsafeUrlError,
    safe_request,
)


class _Server:
    def __init__(self) -> None:
        self.requests: Counter[str] = Counter()
        self.redirects: dict[str, str] = {}
        self._handler = self._make_handler()
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self._handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def _make_handler(self):
        state = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):  # noqa: N802
                state.requests[self.path] += 1
                if self.path == "/large":
                    body = b"x" * 65_536
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                location = state.redirects.get(self.path)
                if location is not None:
                    self.send_response(302)
                    self.send_header("Location", location)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body = b"<html><title>Safe test page</title></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):  # noqa: N802
                self.do_GET()

            def log_message(self, *_args):
                return

        return Handler

    def close(self) -> None:
        self.httpd.shutdown()
        self.thread.join(timeout=5)
        self.httpd.server_close()


@pytest.fixture
def servers():
    source = _Server()
    sink = _Server()
    try:
        yield source, sink
    finally:
        source.close()
        sink.close()


def _mock_public_transport(monkeypatch, source: _Server, sink: _Server) -> None:
    public_ip = ipaddress.ip_address("8.8.8.8")

    def resolve(host: str, port: int, **_kwargs):
        if host not in ("public.test", "middle.test"):
            raise AssertionError(f"Unexpected DNS lookup for {host}")
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (str(public_ip), port),
            )
        ]

    def connect(address: ResolvedAddress, timeout: float):
        destination = source if address.ip == public_ip else sink
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(("127.0.0.1", destination.port))
        return sock

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(safe_http, "_connect_pinned", connect)
    monkeypatch.setattr(
        safe_http,
        "_is_allowed_port",
        lambda scheme, port: scheme == "http" and port in (source.port, sink.port),
    )


def _source_url(source: _Server, path: str) -> str:
    return f"http://public.test:{source.port}{path}"


def _unsafe_target(address: str, sink: _Server) -> str:
    return f"http://{address}:{sink.port}/never"


UNSAFE_REDIRECT_HOSTS = (
    "127.0.0.1",
    "10.1.2.3",
    "192.168.4.5",
    "[::1]",
    "[fe80::1]",
    "169.254.10.20",
    "224.0.0.1",
    "240.0.0.1",
    "0.0.0.0",
)


@pytest.mark.parametrize("network_path", ("crawlee", "discovery"))
@pytest.mark.parametrize("unsafe_host", UNSAFE_REDIRECT_HOSTS)
def test_network_paths_reject_unsafe_redirects_before_request(monkeypatch, servers, network_path, unsafe_host):
    source, sink = servers
    _mock_public_transport(monkeypatch, source, sink)
    source.redirects["/start"] = _unsafe_target(unsafe_host, sink)
    url = _source_url(source, "/start")

    if network_path == "crawlee":
        pages = crawl_website_sync(
            url,
            CrawlConfig(
                max_pages=1,
                max_depth=0,
                timeout_seconds=3,
                respect_robots=False,
            ),
        )
        assert pages and pages[0].error is not None
    else:
        assert _fetch_html(url, timeout=3) is None

    assert source.requests["/start"] >= 1
    assert not sink.requests


def test_unsafe_intermediate_redirect_is_never_requested(monkeypatch, servers):
    source, sink = servers
    _mock_public_transport(monkeypatch, source, sink)
    source.redirects["/chain-start"] = f"http://middle.test:{source.port}/chain-middle"
    source.redirects["/chain-middle"] = _unsafe_target("10.0.0.7", sink)

    with pytest.raises(UnsafeUrlError):
        safe_request(_source_url(source, "/chain-start"), timeout=3)

    assert source.requests["/chain-start"] == 1
    assert source.requests["/chain-middle"] == 1
    assert not sink.requests


def test_redirect_loop_is_detected_before_repeated_request(monkeypatch, servers):
    source, sink = servers
    _mock_public_transport(monkeypatch, source, sink)
    source.redirects["/loop"] = _source_url(source, "/loop")

    with pytest.raises(RedirectLoopError):
        safe_request(_source_url(source, "/loop"), timeout=3)

    assert source.requests["/loop"] == 1
    assert not sink.requests


def test_redirect_limit_stops_before_requesting_next_hop(monkeypatch, servers):
    source, sink = servers
    _mock_public_transport(monkeypatch, source, sink)
    source.redirects["/excess-0"] = _source_url(source, "/excess-1")
    source.redirects["/excess-1"] = _source_url(source, "/excess-2")
    source.redirects["/excess-2"] = _source_url(source, "/excess-3")

    with pytest.raises(TooManyRedirectsError):
        safe_request(_source_url(source, "/excess-0"), max_redirects=2, timeout=3)

    assert source.requests["/excess-0"] == 1
    assert source.requests["/excess-1"] == 1
    assert source.requests["/excess-2"] == 1
    assert source.requests["/excess-3"] == 0
    assert not sink.requests


@pytest.mark.parametrize(
    "url",
    (
        "ftp://public.test/resource",
        "http://user:password@public.test/resource",
        "http://public.test:22/resource",
        "https://public.test:444/resource",
    ),
)
def test_rejects_unsafe_url_syntax_and_ports(url):
    with pytest.raises(UnsafeUrlError):
        safe_request(url)


def test_mixed_public_and_private_dns_answers_are_rejected(monkeypatch, servers):
    source, sink = servers
    _mock_public_transport(monkeypatch, source, sink)

    def mixed_answers(host, port, **_kwargs):
        assert host == "public.test"
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("8.8.8.8", port),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("10.0.0.4", port),
            ),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", mixed_answers)
    with pytest.raises(UnsafeUrlError):
        safe_request(_source_url(source, "/"))
    assert not source.requests
    assert not sink.requests


def test_connection_uses_single_validated_dns_answer(monkeypatch, servers):
    source, sink = servers
    _mock_public_transport(monkeypatch, source, sink)
    resolutions = 0

    def changing_answers(host, port, **_kwargs):
        nonlocal resolutions
        assert host == "public.test"
        resolutions += 1
        address = "8.8.8.8" if resolutions == 1 else "10.0.0.4"
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (address, port),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", changing_answers)
    response = safe_request(_source_url(source, "/"), timeout=3)

    assert response.status_code == 200
    assert resolutions == 1
    assert source.requests["/"] == 1
    assert not sink.requests


def test_pinned_https_connection_keeps_original_tls_hostname(monkeypatch):
    from app.engine.safe_http import _PinnedHTTPSConnection

    address = ResolvedAddress(
        socket.AF_INET,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        ("8.8.8.8", 443),
        ipaddress.ip_address("8.8.8.8"),
    )
    wrapped: list[str] = []

    class FakeSocket:
        def close(self):
            return None

    class FakeContext:
        def wrap_socket(self, _sock, *, server_hostname):
            wrapped.append(server_hostname)
            return FakeSocket()

    monkeypatch.setattr(safe_http, "_connect_pinned", lambda *_args: FakeSocket())
    connection = _PinnedHTTPSConnection("public.test", 443, address, 3, FakeContext())
    connection.connect()
    connection.close()

    assert wrapped == ["public.test"]


def test_crawlee_and_discovery_follow_safe_public_redirects(monkeypatch, servers):
    source, sink = servers
    _mock_public_transport(monkeypatch, source, sink)
    source.redirects["/start"] = _source_url(source, "/final")

    pages = crawl_website_sync(
        _source_url(source, "/start"),
        CrawlConfig(
            max_pages=1,
            max_depth=0,
            timeout_seconds=3,
            respect_robots=False,
        ),
    )
    assert pages and pages[0].final_url == _source_url(source, "/final")
    assert pages[0].error is None
    assert "Safe test page" in (_fetch_html(_source_url(source, "/start"), timeout=3) or "")
    assert source.requests["/start"] == 2
    assert source.requests["/final"] == 2
    assert not sink.requests


def test_public_search_adapter_rejects_unsafe_redirect(monkeypatch, servers):
    from app.engine.errors import ProviderUnavailable
    from app.engine.providers import public_discovery

    source, sink = servers
    _mock_public_transport(monkeypatch, source, sink)
    source.redirects["/search"] = _unsafe_target("192.168.1.10", sink)
    monkeypatch.setattr(public_discovery, "DUCKDUCKGO_HTML_URL", _source_url(source, "/search"))
    provider = public_discovery.PublicSearchDiscoveryProvider(max_retries=0)

    with pytest.raises(ProviderUnavailable):
        provider._fetch_search_results("example query", 5, 3)

    assert source.requests["/search"] == 1
    assert not sink.requests


def test_https_only_rejects_plain_http_before_connecting():
    with pytest.raises(UnsafeUrlError):
        safe_request("http://public.test/resource", require_https=True)


def test_sensitive_request_rejects_cross_origin_redirect(monkeypatch, servers):
    source, sink = servers
    _mock_public_transport(monkeypatch, source, sink)
    source.redirects["/start"] = f"http://middle.test:{source.port}/target"

    with pytest.raises(UnsafeUrlError):
        safe_request(_source_url(source, "/start"), same_origin_only=True, timeout=3)

    assert source.requests["/start"] == 1
    assert source.requests["/target"] == 0
    assert not sink.requests


# --------------------------------------------------------------------------- #
# TLS validation, downgrade policy and retry safety
# --------------------------------------------------------------------------- #


def _write_self_signed_certificate(directory: Path) -> tuple[str, str]:
    """Create a throwaway self-signed certificate for ``public.test``."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "public.test")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("public.test")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certificate_path = directory / "cert.pem"
    key_path = directory / "key.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return str(certificate_path), str(key_path)


class _TLSServer:
    """HTTPS server with a self-signed certificate that records SNI."""

    def __init__(self, certificate_path: str, key_path: str) -> None:
        self.requests: Counter[str] = Counter()
        self.sni: list[str | None] = []
        state = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):  # noqa: N802
                state.requests[self.path] += 1
                body = b"<html>untrusted</html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate_path, key_path)

        def record_sni(_socket, server_name, _context):
            state.sni.append(server_name)
            return None

        context.sni_callback = record_sni
        self.httpd.socket = context.wrap_socket(self.httpd.socket, server_side=True)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.thread.join(timeout=5)
        self.httpd.server_close()


def test_self_signed_certificate_is_rejected_and_sni_keeps_the_hostname(
    monkeypatch, tmp_path
):
    server = _TLSServer(*_write_self_signed_certificate(tmp_path))
    pinned = ipaddress.ip_address("8.8.8.8")

    def resolve(host, port, **_kwargs):
        assert host == "public.test"
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (str(pinned), port))
        ]

    def connect(_address, timeout):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(("127.0.0.1", server.port))
        return sock

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(safe_http, "_connect_pinned", connect)
    monkeypatch.setattr(
        safe_http, "_is_allowed_port", lambda scheme, port: scheme == "https"
    )
    try:
        with pytest.raises(ssl.SSLCertVerificationError):
            safe_request(f"https://public.test:{server.port}/secure", timeout=5)
        assert not server.requests
        assert server.sni == ["public.test"]
    finally:
        server.close()


def test_https_to_http_downgrade_is_blocked_before_the_target_is_requested(monkeypatch):
    requested: list[str] = []

    def fake_hop(url, *_args, **_kwargs):
        requested.append(url)
        return 302, {"location": "http://public.test/cleartext"}, b"", False

    monkeypatch.setattr(safe_http, "_send_hop", fake_hop)

    with pytest.raises(UnsafeUrlError):
        safe_request("https://public.test/start", timeout=3)

    assert requested == ["https://public.test/start"]


@pytest.mark.parametrize("method", ("GET", "POST"))
def test_connection_failures_retry_only_idempotent_methods(monkeypatch, servers, method):
    source, sink = servers
    attempts: list[str] = []
    addresses = (
        ResolvedAddress(
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            ("8.8.8.8", 80),
            ipaddress.ip_address("8.8.8.8"),
        ),
        ResolvedAddress(
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            ("8.8.4.4", 80),
            ipaddress.ip_address("8.8.4.4"),
        ),
    )

    def connect(address, _timeout):
        attempts.append(str(address.ip))
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(safe_http, "_resolve_host", lambda host, port: addresses)
    monkeypatch.setattr(safe_http, "_connect_pinned", connect)
    monkeypatch.setattr(safe_http, "_is_allowed_port", lambda scheme, port: True)

    with pytest.raises(ConnectionRefusedError):
        safe_request(
            _source_url(source, "/paid"),
            method=method,
            body=b"{}" if method == "POST" else None,
            timeout=3,
        )

    assert attempts == (["8.8.8.8", "8.8.4.4"] if method == "GET" else ["8.8.8.8"])
    assert not source.requests
    assert not sink.requests


def test_post_request_is_sent_exactly_once_across_addresses(monkeypatch, servers):
    source, sink = servers
    attempts: list[str] = []
    addresses = (
        ResolvedAddress(
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            ("8.8.8.8", 80),
            ipaddress.ip_address("8.8.8.8"),
        ),
        ResolvedAddress(
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            ("8.8.4.4", 80),
            ipaddress.ip_address("8.8.4.4"),
        ),
    )

    def connect(_address, timeout):
        attempts.append("connect")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(("127.0.0.1", source.port))
        return sock

    monkeypatch.setattr(safe_http, "_resolve_host", lambda host, port: addresses)
    monkeypatch.setattr(safe_http, "_connect_pinned", connect)
    monkeypatch.setattr(safe_http, "_is_allowed_port", lambda scheme, port: True)

    response = safe_request(
        _source_url(source, "/paid"), method="POST", body=b"{}", timeout=3
    )

    assert response.status_code == 200
    assert attempts == ["connect"]
    assert source.requests["/paid"] == 1
    assert not sink.requests


def test_response_body_is_capped_by_the_shared_transport(monkeypatch, servers):
    source, sink = servers
    _mock_public_transport(monkeypatch, source, sink)

    response = safe_request(
        _source_url(source, "/large"), timeout=3, max_response_bytes=1024
    )

    assert len(response.body) == 1024
    assert response.body_truncated is True
    assert not sink.requests


def test_search_api_uses_https_and_same_origin_transport(monkeypatch):
    import app.engine.providers.search_api as search_api

    captured: dict[str, object] = {}

    def fake_request(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return safe_http.SafeHttpResponse(
            status_code=200,
            headers={},
            body=b'{"results": []}',
            final_url=url,
        )

    monkeypatch.setattr(search_api, "safe_request", fake_request)
    assert search_api._post_json(
        "https://api.tavily.com/search",
        {"query": "example"},
        {"Content-Type": "application/json"},
        3,
    ) == {"results": []}
    assert captured["require_https"] is True
    assert captured["same_origin_only"] is True
