"""MediaWiki client: pacing, Retry-After, maxlag, continuation guard, host and payload checks."""

from datetime import UTC, datetime

import httpx
import pytest

from app.domain.interfaces.entity_images import ImageDownloadError
from app.domain.interfaces.wiki_ingestion import WikiSourceError
from app.infrastructure.ingestion.mediawiki_client import MediaWikiClient, retry_after_seconds
from app.infrastructure.ingestion.wiki_sync_config import SourceSettings

SETTINGS = SourceSettings(
    api_url="https://wiki.test/api.php",
    page_url="https://wiki.test/wiki/{title}",
    license="CC BY-SA",
    user_agent="ChisaTest/1.0",
    timeout_seconds=5,
    min_interval_seconds=1.0,
    max_retries=2,
    max_wait_seconds=60,
    max_response_bytes=10_000,
)


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _client(handler, fake: FakeTime | None = None) -> MediaWikiClient:
    fake = fake or FakeTime()
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
    return MediaWikiClient(http, SETTINGS, sleep=fake.sleep, clock=fake.clock)


def _responses(*responses: httpx.Response):
    queue = list(responses)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0)

    handler.seen = seen
    return handler


async def test_requests_are_paced_start_to_start() -> None:
    fake = FakeTime()
    client = _client(_responses(httpx.Response(200, json={}), httpx.Response(200, json={})), fake)

    await client.api(action="query")
    fake.now += 0.25
    await client.api(action="query")

    assert fake.sleeps == [pytest.approx(0.75)]


async def test_retry_after_is_honoured_then_succeeds() -> None:
    fake = FakeTime()
    handler = _responses(
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(200, json={"ok": True}),
    )

    assert await _client(handler, fake).api(action="query") == {"ok": True}
    assert 7.0 in fake.sleeps


async def test_wait_longer_than_limit_fails_fast() -> None:
    handler = _responses(httpx.Response(503, headers={"Retry-After": "600"}))

    with pytest.raises(WikiSourceError, match="wait limit"):
        await _client(handler).api(action="query")


async def test_retry_budget_is_bounded() -> None:
    handler = _responses(*(httpx.Response(502) for _ in range(3)))

    with pytest.raises(WikiSourceError):
        await _client(handler).api(action="query")
    assert len(handler.seen) == SETTINGS.max_retries + 1


def test_retry_after_accepts_http_dates_and_falls_back_to_backoff() -> None:
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)

    assert retry_after_seconds("Sun, 01 Nov 2026 12:00:30 GMT", 0, now) == 30
    assert retry_after_seconds("garbage", 1, now) == 4
    assert retry_after_seconds(None, 0, now) == 2


async def test_maxlag_error_is_retried() -> None:
    fake = FakeTime()
    handler = _responses(
        httpx.Response(200, json={"error": {"code": "maxlag"}}),
        httpx.Response(200, json={"query": {}}),
    )

    assert await _client(handler, fake).api(action="query") == {"query": {}}
    assert 5.0 in fake.sleeps


async def test_other_api_errors_are_not_retried() -> None:
    handler = _responses(httpx.Response(200, json={"error": {"code": "badtoken"}}))

    with pytest.raises(WikiSourceError, match="badtoken"):
        await _client(handler).api(action="query")


async def test_repeated_continuation_token_stops_the_loop() -> None:
    page = {"query": {"allpages": []}, "continue": {"apcontinue": "B", "continue": "-||"}}
    handler = _responses(httpx.Response(200, json=page), httpx.Response(200, json=page))

    with pytest.raises(WikiSourceError, match="continuation"):
        await _client(handler).list_page_ids()


async def test_continuation_is_followed_until_exhausted() -> None:
    handler = _responses(
        httpx.Response(
            200,
            json={
                "query": {"allpages": [{"pageid": 1, "title": "A"}]},
                "continue": {"apcontinue": "B"},
            },
        ),
        httpx.Response(200, json={"query": {"allpages": [{"pageid": 2, "title": "B"}]}}),
    )

    assert await _client(handler).list_page_ids() == {1: "A", 2: "B"}
    assert handler.seen[1].url.params["apcontinue"] == "B"


async def test_redirect_to_another_host_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "wiki.test":
            return httpx.Response(302, headers={"Location": "https://evil.test/api.php"})
        return httpx.Response(200, json={})

    with pytest.raises(WikiSourceError, match="outside"):
        await _client(handler).api(action="query")


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(200, text="<html>challenge</html>"), "JSON"),
        (httpx.Response(200, json={"x": "y" * 20_000}), "byte limit"),
        (httpx.Response(200, json=[1, 2]), "object"),
        (httpx.Response(404), "HTTP 404"),
    ],
)
async def test_unsafe_payloads_are_rejected(response: httpx.Response, message: str) -> None:
    with pytest.raises(WikiSourceError, match=message):
        await _client(_responses(response)).api(action="query")


async def test_page_infos_skip_missing_pages_and_parse_timestamps() -> None:
    payload = {
        "query": {
            "pages": [
                {
                    "pageid": 7,
                    "title": "Chisa",
                    "lastrevid": 99,
                    "touched": "2026-10-30T01:02:03Z",
                    "revisions": [{"revid": 99, "timestamp": "2026-10-29T00:00:00Z"}],
                },
                {"pageid": 8, "title": "Gone", "missing": True},
            ]
        }
    }

    infos = await _client(_responses(httpx.Response(200, json=payload))).page_infos([7, 8])

    assert [(i.page_id, i.last_revid) for i in infos] == [(7, 99)]
    assert infos[0].touched == datetime(2026, 10, 30, 1, 2, 3, tzinfo=UTC)
    assert infos[0].revision_timestamp == datetime(2026, 10, 29, tzinfo=UTC)


async def test_parse_normalises_categories_templates_and_url() -> None:
    payload = {
        "parse": {
            "pageid": 7,
            "title": "Chisa/Backstory",
            "revid": 99,
            "text": "<p>hi</p>",
            "categories": [{"category": "Resonator_Backstory"}],
            "templates": [{"ns": 10, "title": "Template:Quote"}, {"ns": 828, "title": "Module:X"}],
            "sections": [{"line": "Story"}],
            "properties": {"infoboxes": "[]"},
        }
    }

    page = await _client(_responses(httpx.Response(200, json=payload))).parse(7)

    assert page.categories == ("Resonator Backstory",)
    assert page.templates == ("Template:Quote",)
    assert page.url == "https://wiki.test/wiki/Chisa%2FBackstory"
    assert page.properties == {"infoboxes": "[]"}


async def test_parse_without_html_is_an_error() -> None:
    handler = _responses(httpx.Response(200, json={"parse": {"pageid": 7, "title": "X"}}))

    with pytest.raises(WikiSourceError, match="missing parsed HTML"):
        await _client(handler).parse(7)


async def test_redirects_are_collected_per_target_page() -> None:
    payload = {
        "query": {
            "pages": [
                {"pageid": 7, "redirects": [{"title": "Kuchiba Chisa"}, {"title": "Chisa K."}]},
                {"pageid": 8},
            ]
        }
    }

    found = await _client(_responses(httpx.Response(200, json=payload))).redirects([7, 8])

    assert found == {7: ("Chisa K.", "Kuchiba Chisa"), 8: ()}


async def test_image_info_reads_files_and_skips_missing_ones() -> None:
    pages = [
        {
            "title": "File:A B.png",
            "lastrevid": 9,
            "imageinfo": [
                {
                    "url": "https://static.example/a.png/revision/latest?cb=1",
                    "sha1": "s",
                    "size": 3,
                    "mime": "image/png",
                    "descriptionurl": "https://w/File:A_B.png",
                }
            ],
        },
        {"title": "File:Gone.png", "missing": True},
    ]
    client = _client(_responses(httpx.Response(200, json={"query": {"pages": pages}})))

    infos = await client.image_info(["A B.png", "Gone.png"])

    assert [(i.name, i.sha1, i.revid) for i in infos] == [("A B.png", "s", 9)]
    assert infos[0].url == "https://static.example/a.png/revision/latest?cb=1&format=original"


async def test_download_returns_the_body() -> None:
    client = _client(_responses(httpx.Response(200, content=b"bytes")))

    assert await client.download("https://static.example/a.png") == b"bytes"


async def test_download_treats_a_redirect_as_a_failure() -> None:
    redirect = httpx.Response(302, headers={"Location": "http://169.254.169.254/"})
    client = _client(_responses(redirect))

    with pytest.raises(ImageDownloadError):
        await client.download("https://static.example/a.png")


async def test_download_stops_past_the_byte_limit() -> None:
    client = _client(_responses(httpx.Response(200, content=b"x" * 11)))
    client._settings = SETTINGS.model_copy(update={"max_image_bytes": 10})

    with pytest.raises(ImageDownloadError):
        await client.download("https://static.example/a.png")
