"""Deterministic tests for the safe crawler and SSRF guards."""

import http.server
import ipaddress
import socket
import threading

import pytest

import app.engine.safe_http as safe_http
from app.engine.crawler import (
    CrawlConfig,
    crawl_website_sync,
    extract_links,
    is_safe_url,
)
from app.engine.providers.crawlee_people import (
    extract_decision_makers_from_html,
    extract_decision_makers_from_text,
)
from app.engine.providers.multi_discovery import (
    CompositeDiscoveryProvider,
)
from app.engine.safe_http import ResolvedAddress


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        if self.path == "/":
            body = (
                "<html><head><title>Home</title></head><body>"
                "<p>Acme builds workflow automation for operations teams.</p>"
                "<a href='/about'>About</a>"
                "<a href='/products'>Products</a>"
                "<a href='http://127.0.0.1/evil'>evil</a>"
                "</body></html>"
            )
        elif self.path == "/about":
            body = (
                "<html><head><title>About Acme</title></head><body>"
                "<p>Jane Doe, CEO leads the company. John Smith - Head of Marketing.</p>"
                "</body></html>"
            )
        elif self.path == "/products":
            body = (
                "<html><head><title>Products</title></head><body>"
                "<p>Workflow automation platform for operations leaders.</p>"
                "</body></html>"
            )
        elif self.path == "/large":
            body = "x" * 100_000
        elif self.path == "/binary":
            self._respond(200, "application/octet-stream", b"binary")
            return
        else:
            self._respond(404, "text/plain", b"not found")
            return
        self._respond(200, "text/html; charset=utf-8", body.encode())

    def _respond(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


@pytest.fixture
def mock_site():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://public.test:{port}", port
    httpd.shutdown()
    thread.join(timeout=5)


def _route_test_host(monkeypatch, port):
    def resolve(host, requested_port):
        assert host == "public.test"
        assert requested_port == port
        return (
            ResolvedAddress(
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                ("8.8.8.8", port),
                ipaddress.ip_address("8.8.8.8"),
            ),
        )

    def connect(address, timeout):
        assert str(address.ip) == "8.8.8.8"
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    monkeypatch.setattr(safe_http, "_resolve_host", resolve)
    monkeypatch.setattr(safe_http, "_connect_pinned", connect)
    monkeypatch.setattr(
        safe_http,
        "_is_allowed_port",
        lambda scheme, candidate_port: (
            (scheme == "http" and candidate_port == port) or (scheme == "https" and candidate_port == 443)
        ),
    )


def test_is_safe_url_rejects_internal():
    assert is_safe_url("http://localhost/x") is False
    assert is_safe_url("http://127.0.0.1/x") is False
    assert is_safe_url("http://169.254.169.254/latest/meta-data") is False
    assert is_safe_url("ftp://example.com/x") is False


def test_is_safe_url_accepts_mocked_public_hostname(monkeypatch):
    _route_test_host(monkeypatch, 443)
    assert is_safe_url("https://public.test/") is True


def test_crawler_extracts_pages_and_text(monkeypatch, mock_site):
    site, port = mock_site
    _route_test_host(monkeypatch, port)
    pages = crawl_website_sync(
        site + "/",
        CrawlConfig(max_pages=5, max_depth=1, timeout_seconds=5, respect_robots=False),
        ["about", "product"],
    )
    assert any(p.title == "Home" for p in pages)
    assert any("workflow automation" in (p.text or "").lower() for p in pages)
    assert all(p.error is None for p in pages if p.status_code == 200)


def test_crawler_respects_page_limit(monkeypatch, mock_site):
    site, port = mock_site
    _route_test_host(monkeypatch, port)
    pages = crawl_website_sync(
        site + "/",
        CrawlConfig(max_pages=1, max_depth=2, timeout_seconds=5, respect_robots=False),
        None,
    )
    assert len(pages) <= 1


def test_extract_links_filters_unsafe(monkeypatch):
    _route_test_host(monkeypatch, 443)
    html = "<a href='https://public.test/a'>a</a><a href='http://127.0.0.1/b'>b</a>"
    links = extract_links(html, "https://public.test/")
    assert "https://public.test/a" in links
    assert all("127.0.0.1" not in link for link in links)


def test_extract_decision_makers_from_text():
    text = "Jane Doe, CEO leads Acme.\nJohn Smith - Head of Marketing\n"
    result = extract_decision_makers_from_text(text, "https://acme.example/about")
    names = {r.full_name for r in result}
    assert "Jane Doe" in names
    assert "John Smith" in names
    titles = {r.job_title for r in result}
    assert any("CEO" in t for t in titles)


def test_extract_decision_makers_from_html_jsonld():
    html = """
    <html><body>
    <script type="application/ld+json">
    {"@type":"Person","name":"Jane Doe","jobTitle":"CEO"}
    </script>
    <div class="team-card"><h3>John Smith</h3><p>Head of Marketing</p></div>
    </body></html>
    """
    result = extract_decision_makers_from_html(html, "https://acme.example/team")
    names = {r.full_name for r in result}
    assert "Jane Doe" in names
    titles = {r.job_title for r in result}
    assert any("CEO" in t for t in titles)


def test_composite_discovery_deduplicates(monkeypatch):
    from app.engine.contracts import CompanyCandidate, DiscoveryRequest, ICPQuery

    class FakeAdapter:
        name = "fake"
        synthetic = False

        def __init__(self, items):
            self._items = items

        def status(self):
            from app.engine.contracts import ProviderStatus

            return ProviderStatus(name=self.name, capability="company_discovery", state="ready", synthetic=False)

        def discover(self, request):
            return list(self._items)

    icp = ICPQuery(industries=["Technology"], countries=["United States"])
    a = CompanyCandidate(name="Acme", website="https://acme.com", source_name="a", identity_confidence=0.2)
    b = CompanyCandidate(
        name="Acme LLC", website="https://www.acme.com/about", source_name="b", identity_confidence=0.4
    )
    composite = CompositeDiscoveryProvider([FakeAdapter([a]), FakeAdapter([b])])
    req = DiscoveryRequest(icp=icp, limit=10)
    out = composite.discover(req)
    assert len(out) == 1
    assert out[0].identity_confidence == 0.4
