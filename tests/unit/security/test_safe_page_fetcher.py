"""B-1 regression: the web-search page fetcher must not become an SSRF primitive."""

from __future__ import annotations

import httpx
import pytest

from app.infrastructure.search.safe_page_fetcher import SafePageFetcher, resolve_pinned_target
from app.shared.security.network_destinations import NetworkDestinationError

PUBLIC_IP = "93.184.216.34"
DNS = {
    "public.example.test": (PUBLIC_IP,),
    "metadata.example.test": ("169.254.169.254",),
    "internal.example.test": ("10.0.0.7",),
    "rebinding.example.test": (PUBLIC_IP, "127.0.0.1"),
}


async def fake_resolver(hostname: str, port: int) -> tuple[str, ...]:
    from app.shared.security.network_destinations import is_forbidden_ip

    addresses = DNS.get(hostname)
    if not addresses or any(is_forbidden_ip(address) for address in addresses):
        raise NetworkDestinationError("network destination is not public")
    return addresses


class Recorder:
    def __init__(self, routes: dict[str, httpx.Response]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = f"{request.headers['host']}{request.url.raw_path.decode()}"
        return self.routes.get(key, httpx.Response(404))


def make_fetcher(recorder: Recorder, *, max_bytes: int = 4096) -> SafePageFetcher:
    client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    return SafePageFetcher(
        client,
        max_bytes=max_bytes,
        max_redirects=2,
        timeout_seconds=1.0,
        resolver=fake_resolver,
    )


def html(body: str, **headers: str) -> httpx.Response:
    return httpx.Response(
        200, headers={"content-type": "text/html; charset=utf-8", **headers}, text=body
    )


@pytest.mark.asyncio
async def test_public_page_is_fetched_through_a_pinned_validated_address() -> None:
    recorder = Recorder({"public.example.test/lore": html("<p>Chisa lore</p>")})

    text = await make_fetcher(recorder).fetch("https://public.example.test/lore")

    assert text == "<p>Chisa lore</p>"
    request = recorder.requests[0]
    assert request.url.host == PUBLIC_IP
    assert request.headers["host"] == "public.example.test"
    assert request.extensions["sni_hostname"] == "public.example.test"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    (
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:8000/health",
        "http://[::1]/",
        "http://10.0.0.5/",
        "http://metadata.example.test/",
        "http://internal.example.test/",
        "http://rebinding.example.test/",
        "http://qdrant:6333/collections",
        "file:///etc/passwd",
        "gopher://public.example.test/",
        "https://user:secret@public.example.test/",
    ),
)
async def test_non_public_destinations_are_refused_before_any_request(url: str) -> None:
    recorder = Recorder({})

    assert await make_fetcher(recorder).fetch(url) == ""
    assert recorder.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "location",
    (
        "http://169.254.169.254/latest/meta-data/iam/",
        "http://127.0.0.1:8000/api/v1/chat/history/x",
        "http://internal.example.test/secret",
        "file:///etc/passwd",
    ),
)
async def test_redirect_to_internal_destination_is_never_followed(location: str) -> None:
    recorder = Recorder(
        {"public.example.test/start": httpx.Response(302, headers={"location": location})}
    )

    assert await make_fetcher(recorder).fetch("https://public.example.test/start") == ""
    assert len(recorder.requests) == 1


@pytest.mark.asyncio
async def test_public_redirect_is_revalidated_and_followed() -> None:
    recorder = Recorder(
        {
            "public.example.test/old": httpx.Response(301, headers={"location": "/new"}),
            "public.example.test/new": html("moved"),
        }
    )

    assert await make_fetcher(recorder).fetch("https://public.example.test/old") == "moved"
    assert len(recorder.requests) == 2


@pytest.mark.asyncio
async def test_redirect_loop_is_bounded() -> None:
    recorder = Recorder(
        {"public.example.test/loop": httpx.Response(302, headers={"location": "/loop"})}
    )

    assert await make_fetcher(recorder).fetch("https://public.example.test/loop") == ""
    assert len(recorder.requests) == 3  # initial request + max_redirects


@pytest.mark.asyncio
async def test_response_body_is_capped() -> None:
    recorder = Recorder({"public.example.test/big": html("A" * 50_000)})

    text = await make_fetcher(recorder, max_bytes=1024).fetch("https://public.example.test/big")

    assert len(text) == 1024


@pytest.mark.asyncio
async def test_streaming_body_is_truncated_without_buffering_everything() -> None:
    chunks_served: list[int] = []

    async def body():
        for _ in range(100):
            chunks_served.append(1)
            yield b"B" * 1024

    recorder = Recorder(
        {
            "public.example.test/stream": httpx.Response(
                200, headers={"content-type": "text/plain"}, content=body()
            )
        }
    )

    text = await make_fetcher(recorder, max_bytes=2048).fetch("https://public.example.test/stream")

    assert text == "B" * 2048
    assert len(chunks_served) < 100  # stopped reading once the budget was reached


@pytest.mark.asyncio
async def test_non_textual_content_is_not_read() -> None:
    recorder = Recorder(
        {
            "public.example.test/blob": httpx.Response(
                200, headers={"content-type": "application/octet-stream"}, content=b"\x00" * 10
            )
        }
    )

    assert await make_fetcher(recorder).fetch("https://public.example.test/blob") == ""


@pytest.mark.asyncio
async def test_pinned_target_keeps_non_default_port_in_host_header() -> None:
    target = await resolve_pinned_target("http://public.example.test:8080/a?b=1", fake_resolver)

    assert target.request_url == f"http://{PUBLIC_IP}:8080/a?b=1"
    assert target.host_header == "public.example.test:8080"
    assert target.sni_hostname is None


def test_container_fetcher_no_longer_uses_auto_redirects() -> None:
    from pathlib import Path

    source = Path("app/application/dependencies.py").read_text(encoding="utf-8")
    fetch_block = source[source.index("async def fetch_page") : source.index("agent_tools = [")]
    assert "follow_redirects=True" not in fetch_block
    assert "safe_page_fetcher.fetch" in fetch_block
