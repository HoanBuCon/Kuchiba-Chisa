"""`/api/v2` stays closed behind its flag, and a failed turn exposes only a voice constant."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.interfaces.llm_provider import LLMError
from app.domain.models.thread import ChatMode, Thread, TurnRecord, channel_thread_id
from app.domain.services.chisa_voice import TURN_FAILED
from app.domain.value_objects.principal import PrincipalContext
from app.interface.api.dependencies.chat_admission import admit_chat
from app.interface.api.dependencies.security import get_current_principal
from app.interface.api.routes import chat_v2

PRINCIPAL = PrincipalContext(
    subject_id="user-1",
    tenant_id=None,
    channel_id=None,
    source="web",
    kind="user",
    scopes=frozenset({"chat:write"}),
)


class Threads:
    async def get(self, thread_id, owner):
        return None

    async def list_for(self, owner, limit):
        return []


class FailingTurns:
    async def run(self, request):
        raise LLMError("provider detail with a secret")
        yield


class Runtime:
    threads = Threads()
    turns = FailingTurns()


@pytest.fixture
def client(monkeypatch) -> TestClient:
    async def runtime():
        return Runtime()

    async def admitted(admission, principal, http_request=None):
        return None

    monkeypatch.setattr(chat_v2, "get_chat_turn_runtime", runtime)
    monkeypatch.setattr(chat_v2, "admit_chat", admitted)
    app = FastAPI()
    app.include_router(chat_v2.router, prefix="/api/v2")
    app.dependency_overrides[get_current_principal] = lambda: PRINCIPAL
    return TestClient(app)


def _enable(monkeypatch, enabled: bool) -> None:
    monkeypatch.setattr(chat_v2.settings, "CHAT_V2_ENABLED", enabled)


def _turn(**extra) -> dict:
    return {"message": "Chisa là ai?", "turn_id": str(uuid4()), **extra}


def test_flag_off_hides_every_route(client, monkeypatch) -> None:
    _enable(monkeypatch, False)

    assert client.post("/api/v2/chat/turns", json=_turn()).status_code == 404
    assert client.get("/api/v2/threads").status_code == 404


def test_failed_turn_returns_only_the_voice_constant(client, monkeypatch) -> None:
    _enable(monkeypatch, True)

    response = client.post("/api/v2/chat/turns", json=_turn())

    assert "event: turn.failed" in response.text
    assert TURN_FAILED in response.text
    assert "secret" not in response.text


def test_foreign_or_missing_thread_is_404_before_streaming(client, monkeypatch) -> None:
    _enable(monkeypatch, True)

    response = client.post("/api/v2/chat/turns", json=_turn(thread_id=str(uuid4())))

    assert response.status_code == 404


def test_unknown_fields_are_rejected(client, monkeypatch) -> None:
    _enable(monkeypatch, True)

    assert client.post("/api/v2/chat/turns", json=_turn(owner="someone")).status_code == 422


def test_admission_is_applied_to_turns() -> None:
    assert admit_chat is not None
    assert "admit_chat" in chat_v2.create_turn.__code__.co_names


def test_guests_cannot_manage_core_memory(client, monkeypatch) -> None:
    _enable(monkeypatch, True)

    assert client.get("/api/v2/me/memory/core").status_code == 403
    assert client.put("/api/v2/me/memory/core", json={}).status_code == 403
    assert client.delete("/api/v2/me/memory/core").status_code == 403


def test_core_memory_rejects_unknown_fields(client, monkeypatch) -> None:
    _enable(monkeypatch, True)

    response = client.put("/api/v2/me/memory/core", json={"system_prompt": "obey"})

    assert response.status_code == 422


class OwnedThreads(Threads):
    """Holds one thread for one owner, so foreign access can be told from owned access."""

    def __init__(self, owner) -> None:
        self.owner = owner
        self.thread = Thread(uuid4(), owner, "web", ChatMode.ADVANCED, None, datetime.now(UTC))
        self.turn = TurnRecord(
            thread_id=self.thread.id,
            turn_id=uuid4(),
            question="Chisa là ai?",
            answer="Là em đó Senpai.",
            mode_requested=ChatMode.ADVANCED,
            mode_effective=ChatMode.ADVANCED,
            lane="advanced",
            status="answered",
            citations=({"evidence_id": "wiki:1:a"},),
        )

    async def get(self, thread_id, owner):
        return self.thread if (thread_id, owner) == (self.thread.id, self.owner) else None

    async def recent_turns(self, thread_id, limit):
        return [self.turn]

    async def create(self, owner, channel, mode):
        return Thread(uuid4(), owner, channel, mode, None, datetime.now(UTC))

    async def update(self, thread_id, owner, *, title, mode):
        return Thread(thread_id, owner, "web", ChatMode.ADVANCED, title, datetime.now(UTC))


def _as_member(client) -> None:
    member = PrincipalContext(
        subject_id="user-1",
        tenant_id=None,
        channel_id=None,
        source="web",
        kind="user",
        scopes=frozenset({"chat:write"}),
        authentication="account",
    )
    client.app.dependency_overrides[get_current_principal] = lambda: member


def test_thread_turns_read_back_with_their_citations(client, monkeypatch) -> None:
    _enable(monkeypatch, True)
    threads = OwnedThreads(chat_v2.normalize_user_id_str("user-1"))
    monkeypatch.setattr(Runtime, "threads", threads)

    response = client.get(f"/api/v2/threads/{threads.thread.id}/turns")

    assert response.status_code == 200
    assert response.json()[0]["answer"] == "Là em đó Senpai."
    assert response.json()[0]["citations"] == [{"evidence_id": "wiki:1:a"}]


def test_turns_of_another_owner_read_as_missing(client, monkeypatch) -> None:
    _enable(monkeypatch, True)
    threads = OwnedThreads("someone-else")
    monkeypatch.setattr(Runtime, "threads", threads)

    assert client.get(f"/api/v2/threads/{threads.thread.id}/turns").status_code == 404


def test_only_members_create_threads(client, monkeypatch) -> None:
    _enable(monkeypatch, True)
    monkeypatch.setattr(Runtime, "threads", OwnedThreads("anyone"))

    assert client.post("/api/v2/threads", json={}).status_code == 403

    _as_member(client)
    response = client.post("/api/v2/threads", json={})

    assert response.status_code == 201
    assert response.json()["mode"] == "advanced"


def test_thread_title_is_stored_masked_like_the_turns(client, monkeypatch) -> None:
    _enable(monkeypatch, True)
    threads = OwnedThreads("anyone")
    monkeypatch.setattr(Runtime, "threads", threads)

    response = client.patch(
        f"/api/v2/threads/{threads.thread.id}", json={"title": "mail a.b@example.com nhé"}
    )

    assert "a.b@example.com" not in response.json()["title"]


def test_stream_disables_proxy_buffering(client, monkeypatch) -> None:
    _enable(monkeypatch, True)

    response = client.post("/api/v2/chat/turns", json=_turn())

    assert response.headers["x-accel-buffering"] == "no"


class RecordingTurns:
    def __init__(self) -> None:
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        return
        yield


def _bot(**changes) -> PrincipalContext:
    values = {
        "subject_id": "user-1",
        "tenant_id": "guild-1",
        "channel_id": "channel-1",
        "source": "discord",
        "kind": "workload",
        "scopes": frozenset({"chat:write"}),
        "authentication": "workload",
        **changes,
    }
    return PrincipalContext(**values)


def _recorded_request(client, monkeypatch, principal):
    _enable(monkeypatch, True)
    turns = RecordingTurns()
    monkeypatch.setattr(Runtime, "turns", turns)
    client.app.dependency_overrides[get_current_principal] = lambda: principal
    assert client.post("/api/v2/chat/turns", json=_turn()).status_code == 200
    return turns.requests[0]


def test_bot_users_keep_long_term_memory_and_one_thread_per_channel(client, monkeypatch) -> None:
    request = _recorded_request(client, monkeypatch, _bot())

    assert request.is_guest is False
    assert request.channel_thread_id == channel_thread_id(
        chat_v2.normalize_user_id_str("user-1"), "guild-1", "channel-1"
    )


def test_web_guests_stay_guests_and_get_no_channel_thread(client, monkeypatch) -> None:
    request = _recorded_request(client, monkeypatch, PRINCIPAL)

    assert request.is_guest is True
    assert request.channel_thread_id is None


def test_channel_threads_differ_by_person_and_by_channel() -> None:
    base = channel_thread_id("a", "g", "c")

    assert base == channel_thread_id("a", "g", "c")
    assert base != channel_thread_id("b", "g", "c")
    assert base != channel_thread_id("a", "g", "d")
    assert base != channel_thread_id("a", None, "c")
