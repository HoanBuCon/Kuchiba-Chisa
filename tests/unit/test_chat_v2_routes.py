"""`/api/v2` stays closed behind its flag, and a failed turn exposes only a voice constant."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.interfaces.llm_provider import LLMError
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
