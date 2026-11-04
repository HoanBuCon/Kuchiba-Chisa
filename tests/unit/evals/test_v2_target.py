"""v2 evaluation target: SSE parsing, page ids, and the server's abstention signal."""

import json

import httpx
import pytest

from evals.dataset import Category, GoldenCase, Language, Turn
from evals.targets import HttpChatV2Target, TargetError, pages_from_v2_events, parse_sse


def _sse(*events) -> str:
    return "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in events)


CASE = GoldenCase(
    id="lore-001",
    category=Category.LORE_SINGLE_HOP,
    language=Language.VI,
    turns=(Turn(message="Hỏi một"), Turn(message="Hỏi hai")),
    expected_facts=(("a",),),
)


def _client(completed: dict) -> tuple[httpx.AsyncClient, list]:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("anonymous-session"):
            return httpx.Response(200, json={"access_token": "t"})
        bodies.append(json.loads(request.content))
        events = [
            ("turn.started", {"thread_id": "th-1"}),
            ("evidence.added", {"evidence_id": "kb:v1:quests:7"}),
            ("evidence.added", {"evidence_id": "wiki:9:abc"}),
            ("evidence.added", {"evidence_id": "wiki:7:def"}),
        ]
        if completed:
            events.append(("turn.completed", completed))
        return httpx.Response(200, text=_sse(*events))

    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url="http://test"), bodies


def test_pages_keep_rank_order_without_duplicates() -> None:
    ids = ["kb:2026.11.03-4:quests:7", "wiki:9:abc", "wiki:7:def", "wiki:9:xyz:2", "other"]

    assert pages_from_v2_events(ids) == (7, 9)


def test_sse_is_parsed_in_order() -> None:
    text = _sse(("a", {"x": 1}), ("b", {"y": 2}))

    assert parse_sse(text) == [("a", {"x": 1}), ("b", {"y": 2})]


async def test_answer_keeps_one_thread_and_reads_status() -> None:
    client, bodies = _client({"response": "Đáp.", "status": "answered", "citations": []})

    observation = await HttpChatV2Target(client).answer(CASE)

    assert "thread_id" not in bodies[0]
    assert bodies[1]["thread_id"] == "th-1"
    assert observation.answer == "Đáp."
    assert observation.abstained is False
    assert observation.evidence_pages == (7, 9)


async def test_server_abstention_is_read_from_the_status() -> None:
    client, _ = _client({"response": "Em chưa...", "status": "no_evidence", "citations": []})

    assert (await HttpChatV2Target(client).answer(CASE)).abstained is True


async def test_listed_answer_is_not_an_abstention() -> None:
    client, _ = _client({"response": "- A", "status": "listed", "citations": []})

    assert (await HttpChatV2Target(client).answer(CASE)).abstained is False


async def test_turn_without_completion_is_a_target_error() -> None:
    client, _ = _client({})

    with pytest.raises(TargetError):
        await HttpChatV2Target(client).answer(CASE)
