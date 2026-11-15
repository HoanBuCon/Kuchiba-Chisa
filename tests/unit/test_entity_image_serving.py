"""Entity images are served only through signed server URLs, never from the wiki host (KNW-010)."""

import io
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.application.chat_turns import ENTITY_COLLECTION, AdvancedTurnService
from app.application.dependencies import get_entity_image_service
from app.application.entity_images import (
    FAIR_USE_NOTE,
    IMAGE_ROUTE_PREFIX,
    EntityImageService,
    InvalidImageLinkError,
)
from app.application.security.signed_image_url import ImageUrlSigner
from app.domain.ingestion.entity_images import ImagePolicy, ImageRecord
from app.infrastructure.ingestion.entity_image_store import FileImageVault, PillowImageInspector
from app.interface.api.routes import chat_v2

SHA = "a" * 64
FILE_PAGE = "https://wutheringwaves.fandom.com/wiki/File:Chisa.png"
SECRET = "unit-test-signing-secret-for-image-links"
TTL = 900


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


class Catalog:
    def __init__(self, records: list[ImageRecord], files: dict[str, bytes]) -> None:
        self._records = records
        self._files = files

    def load_index(self) -> dict[str, ImageRecord]:
        return {record.name: record for record in self._records}

    def read(self, relative_path: str) -> bytes | None:
        return self._files.get(relative_path)


def _record(name: str = "Chisa.png", sha: str = SHA, entities=("Chisa",)) -> ImageRecord:
    return ImageRecord(
        name=name,
        sha1="1" * 40,
        sha256=sha,
        mime="image/png",
        width=10,
        height=10,
        size=3,
        original_path=f"images/original/{sha}.png",
        display_path=f"images/display/{sha}.webp",
        file_page_url=FILE_PAGE,
        revid=1,
        entities=entities,
    )


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def service(clock) -> EntityImageService:
    files = {f"images/original/{SHA}.png": b"ORIGINAL", f"images/display/{SHA}.webp": b"DISPLAY"}
    signer = ImageUrlSigner(SECRET, TTL, clock)
    return EntityImageService(Catalog([_record()], files), signer, IMAGE_ROUTE_PREFIX)


def _query(url: str) -> dict[str, str]:
    return dict(pair.split("=") for pair in url.split("?")[1].split("&"))


def _serve(service, url: str, **override):
    query = _query(url)
    arguments = {
        "original": query.get("original") == "1",
        "expires": int(query["expires"]),
        "signature": query["sig"],
    }
    return service.serve(SHA, **{**arguments, **override})


def test_signature_is_valid_until_it_expires(clock) -> None:
    signer = ImageUrlSigner(SECRET, TTL, clock)
    expires, signature = signer.sign(SHA, original=False)
    assert signer.verify(SHA, original=False, expires=expires, signature=signature)
    clock.now += TTL + 1
    assert not signer.verify(SHA, original=False, expires=expires, signature=signature)


@pytest.mark.parametrize("field", ["sha", "variant", "expires", "signature"])
def test_a_tampered_link_is_rejected(clock, field) -> None:
    signer = ImageUrlSigner(SECRET, TTL, clock)
    expires, signature = signer.sign(SHA, original=False)
    arguments = {"sha256": SHA, "original": False, "expires": expires, "signature": signature}
    arguments["sha256"] = "b" * 64 if field == "sha" else SHA
    arguments["original"] = field == "variant"
    arguments["expires"] = expires + 1 if field == "expires" else expires
    arguments["signature"] = "0" * 64 if field == "signature" else signature
    sha256 = arguments.pop("sha256")
    assert not signer.verify(sha256, **arguments)


def test_another_secret_cannot_forge_a_link(clock) -> None:
    expires, signature = ImageUrlSigner(SECRET, TTL, clock).sign(SHA, original=False)
    other = ImageUrlSigner("a-different-signing-secret-value", TTL, clock)
    assert not other.verify(SHA, original=False, expires=expires, signature=signature)


def test_the_entity_image_names_its_source_and_never_the_wiki_host(service) -> None:
    image = service.for_entity("chisa")
    assert image is not None
    assert image["source_page"] == FILE_PAGE
    assert image["attribution"] == FAIR_USE_NOTE
    for link in (image["url"], image["original_url"]):
        assert link.startswith(f"{IMAGE_ROUTE_PREFIX}/{SHA}?")
        assert "wikia" not in link and "fandom" not in link
    assert "original=1" in image["original_url"] and "original=1" not in image["url"]


def test_an_entity_without_an_image_gets_none(service) -> None:
    assert service.for_entity("Nobody") is None


def test_the_display_copy_is_served_by_default_and_the_original_on_request(service) -> None:
    image = service.for_entity("Chisa")
    assert _serve(service, image["url"]).content == b"DISPLAY"
    assert _serve(service, image["url"]).mime == "image/webp"
    original = _serve(service, image["original_url"])
    assert (original.content, original.mime) == (b"ORIGINAL", "image/png")


def test_a_display_link_cannot_open_the_original(service) -> None:
    image = service.for_entity("Chisa")
    with pytest.raises(InvalidImageLinkError):
        _serve(service, image["url"], original=True)


def test_an_expired_link_is_refused(service, clock) -> None:
    image = service.for_entity("Chisa")
    clock.now += TTL + 1
    with pytest.raises(InvalidImageLinkError):
        _serve(service, image["url"])


def test_the_image_named_after_the_entity_is_preferred(clock) -> None:
    other = "c" * 64
    records = [
        _record("Banner.png", other, ("Chisa", "Yinlin")),
        _record("Chisa_Icon.png", SHA),
    ]
    signer = ImageUrlSigner(SECRET, TTL, clock)
    image = EntityImageService(Catalog(records, {}), signer, IMAGE_ROUTE_PREFIX).for_entity("Chisa")
    assert SHA in image["url"]


def _tiny_png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_the_display_copy_is_a_webp_within_the_size_cap() -> None:
    inspector = PillowImageInspector(ImagePolicy(allowed_hosts=("example.test",)))
    display = inspector.display_copy(_tiny_png(3000, 1500))
    with Image.open(io.BytesIO(display)) as image:
        assert image.format == "WEBP"
        assert max(image.size) <= 1024


def test_the_vault_refuses_paths_outside_its_root(tmp_path) -> None:
    root = tmp_path / "ingestion"
    root.mkdir()
    (tmp_path / "secret.txt").write_bytes(b"outside")
    (root / "inside.bin").write_bytes(b"inside")
    vault = FileImageVault(root)
    assert vault.read("inside.bin") == b"inside"
    assert vault.read("../secret.txt") is None
    assert vault.read("missing.bin") is None


@pytest.fixture
def client(service, monkeypatch) -> TestClient:
    monkeypatch.setattr(chat_v2.settings, "CHAT_V2_ENABLED", True)
    app = FastAPI()
    app.include_router(chat_v2.router, prefix="/api/v2")
    app.dependency_overrides[get_entity_image_service] = lambda: service
    return TestClient(app)


def test_the_route_serves_a_signed_link_without_a_bearer_token(client, service) -> None:
    image = service.for_entity("Chisa")
    response = client.get(image["url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.content == b"DISPLAY"


def test_the_route_refuses_a_forged_or_malformed_link(client, service) -> None:
    image = service.for_entity("Chisa")
    forged = image["url"].replace("sig=", "sig=0")
    assert client.get(forged).status_code == 403
    assert client.get(image["url"].replace(SHA, "../etc")).status_code in (404, 422)
    assert client.get(image["url"].replace(SHA, "b" * 64)).status_code == 403


def _evidence(source_id: str, collection: str = ENTITY_COLLECTION):
    provenance = SimpleNamespace(source_id=source_id, collection=collection)
    return SimpleNamespace(provenance=provenance)


def _turn_service(service) -> AdvancedTurnService:
    return AdvancedTurnService(SimpleNamespace(), SimpleNamespace(), SimpleNamespace(), images=service)


def _found(*evidence, abstain=False, listed=()):
    return SimpleNamespace(evidence=evidence, abstain=abstain, listed=listed)


def _answer(abstained=False):
    return SimpleNamespace(abstained=abstained)


def test_a_grounded_answer_about_one_entity_carries_its_image(service) -> None:
    turns = _turn_service(service)
    image = turns._entity_image(_found(_evidence("Chisa"), _evidence("Chisa")), _answer())
    assert image is not None and image["source_page"] == FILE_PAGE


@pytest.mark.parametrize(
    "found,answer",
    [
        (_found(_evidence("Chisa"), _evidence("Yinlin")), _answer()),
        (_found(_evidence("Chisa", "kb_quests")), _answer()),
        (_found(_evidence("Chisa"), abstain=True), _answer()),
        (_found(_evidence("Chisa"), listed=(object(),)), _answer()),
        (_found(_evidence("Chisa")), _answer(abstained=True)),
    ],
)
def test_other_answers_carry_no_image(service, found, answer) -> None:
    assert _turn_service(service)._entity_image(found, answer) is None
