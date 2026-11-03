"""Entity images: infobox linking, unsafe files blocked, failures never touch text (ING-019)."""

import io
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from PIL import Image

from app.application.ingestion.image_stage import ImageStage
from app.domain.ingestion.entity_images import (
    ImageInfo,
    ImagePolicy,
    entities_by_file,
    infobox_image_files,
)
from app.domain.interfaces.entity_images import ImageDownloadError, ImageRejectedError
from app.infrastructure.ingestion.entity_image_store import (
    FileImageVault,
    PillowImageInspector,
    load_image_policy,
)

HOST = "static.wikia.nocookie.net"
POLICY = ImagePolicy(allowed_hosts=(HOST,), excluded_files=("Site-logo.png",), max_pixels=10_000)


def _box(*names: str) -> dict[str, str]:
    images = [{"name": name, "isVideo": "False"} for name in names]
    data = [{"type": "group", "data": [{"type": "image", "data": images}]}]
    return {"infoboxes": json.dumps([{"parser_tag_version": 5, "data": data}])}


def _png(size=(10, 10), mode="RGB") -> bytes:
    output = io.BytesIO()
    Image.new(mode, size).save(output, format="PNG")
    return output.getvalue()


def _info(name: str, *, sha1="s1", url=f"https://{HOST}/x.png", mime="image/png") -> ImageInfo:
    return ImageInfo(name, url, sha1, 100, mime, f"https://w/File:{name}", 7)


class FakeSource:
    def __init__(self, *infos: ImageInfo, content: bytes | None = None, error=None) -> None:
        self.infos = {info.name: info for info in infos}
        self.content = content or _png()
        self.error = error
        self.downloads = 0

    async def image_info(self, names):
        return [self.infos[name] for name in names if name in self.infos]

    async def download(self, url):
        self.downloads += 1
        if self.error:
            raise self.error
        return self.content


def _stage(tmp_path, source, pages=(("Chisa", _box("A.png")),), policy=POLICY) -> ImageStage:
    states = {
        index: SimpleNamespace(title=title, in_text_scope=True, bronze_key=title)
        for index, (title, _) in enumerate(pages)
    }
    properties = dict(pages)

    class Inventory:
        async def load(self):
            return states

    class Bronze:
        def load(self, key):
            return SimpleNamespace(properties=properties[key])

    return ImageStage(
        Inventory(),
        Bronze(),
        source,
        PillowImageInspector(policy),
        FileImageVault(tmp_path),
        policy,
    )


def test_images_are_found_at_any_depth_of_the_infobox() -> None:
    assert infobox_image_files(_box("A.png", "B.jpg")) == ("A.png", "B.jpg")


def test_videos_and_malformed_properties_are_skipped() -> None:
    video = {"infoboxes": json.dumps([{"type": "image", "data": [{"name": "V", "isVideo": True}]}])}

    assert infobox_image_files(video) == ()
    assert infobox_image_files({"infoboxes": "{broken"}) == ()
    assert infobox_image_files({}) == ()


def test_one_file_links_to_every_entity_and_placeholders_are_excluded() -> None:
    pages = [("Chisa", _box("A.png", "Site-logo.png")), ("Lynae", _box("A.png"))]

    assert entities_by_file(pages, ("Site-logo.png",)) == {"A.png": ("Chisa", "Lynae")}


def test_inspector_accepts_a_real_image_and_reports_its_size() -> None:
    inspected = PillowImageInspector(POLICY).inspect(_png((20, 30)), "image/png")

    assert (inspected.mime, inspected.width, inspected.height) == ("image/png", 20, 30)


@pytest.mark.parametrize(
    ("content", "mime"),
    [
        (b"<html>not an image</html>", "image/png"),
        (_png(), "image/jpeg"),
        (_png((200, 200)), "image/png"),
        (b"\x89PNG\r\n\x1a\n" + b"truncated", "image/png"),
    ],
)
def test_inspector_rejects_unsafe_files(content, mime) -> None:
    with pytest.raises(ImageRejectedError):
        PillowImageInspector(POLICY).inspect(content, mime)


def test_inspector_rejects_files_over_the_byte_limit() -> None:
    policy = replace(POLICY, max_bytes=10)

    with pytest.raises(ImageRejectedError):
        PillowImageInspector(policy).inspect(_png(), "image/png")


def test_display_copy_is_webp_shrunk_but_never_enlarged() -> None:
    inspector = PillowImageInspector(replace(POLICY, display_edge=50))

    large = Image.open(io.BytesIO(inspector.display_copy(_png((100, 20), "RGBA"))))
    small = Image.open(io.BytesIO(inspector.display_copy(_png((10, 10)))))

    assert large.format == "WEBP"
    assert max(large.size) == 50
    assert small.size == (10, 10)


async def test_stage_stores_both_copies_with_attribution(tmp_path) -> None:
    report = await _stage(tmp_path, FakeSource(_info("A.png"))).run()

    record = FileImageVault(tmp_path).load_index()["A.png"]
    assert (report.referenced, report.downloaded, report.passed) == (1, 1, True)
    assert record.entities == ("Chisa",)
    assert (record.license, record.file_page_url) == ("fair_use", "https://w/File:A.png")
    assert (tmp_path / record.original_path).is_file()
    assert record.display_path.endswith(".webp")
    assert not record.original_path.startswith(str(tmp_path))


async def test_unchanged_sha1_is_not_downloaded_again(tmp_path) -> None:
    await _stage(tmp_path, FakeSource(_info("A.png"))).run()
    source = FakeSource(_info("A.png"))

    report = await _stage(tmp_path, source).run()

    assert (source.downloads, report.reused) == (0, 1)


async def test_changed_sha1_is_downloaded_again(tmp_path) -> None:
    await _stage(tmp_path, FakeSource(_info("A.png"))).run()
    source = FakeSource(_info("A.png", sha1="s2"))

    await _stage(tmp_path, source).run()

    assert source.downloads == 1
    assert FileImageVault(tmp_path).load_index()["A.png"].sha1 == "s2"


async def test_foreign_host_is_refused_before_any_download(tmp_path) -> None:
    source = FakeSource(_info("A.png", url="http://169.254.169.254/latest"))

    report = await _stage(tmp_path, source).run()

    assert source.downloads == 0
    assert "A.png" in report.failures


async def test_a_failed_file_is_reported_and_the_rest_continue(tmp_path) -> None:
    source = FakeSource(_info("A.png"), content=b"junk")

    report = await _stage(tmp_path, source).run()

    assert "ImageRejectedError" in report.failures["A.png"]
    assert FileImageVault(tmp_path).load_index() == {}
    assert not report.passed


async def test_download_failure_keeps_the_previous_good_copy(tmp_path) -> None:
    await _stage(tmp_path, FakeSource(_info("A.png"))).run()
    source = FakeSource(_info("A.png", sha1="s2"), error=ImageDownloadError("HTTP 503"))

    report = await _stage(tmp_path, source).run()

    assert "A.png" in report.failures
    assert FileImageVault(tmp_path).load_index()["A.png"].sha1 == "s1"


async def test_missing_file_is_a_failure_and_unlinked_file_an_orphan(tmp_path) -> None:
    await _stage(tmp_path, FakeSource(_info("A.png"))).run()

    report = await _stage(tmp_path, FakeSource(), pages=(("Chisa", _box("B.png")),)).run()

    assert report.failures == {"B.png": "missing on the wiki"}
    assert report.orphans == 1


def test_shipped_policy_loads_with_the_adr_limits() -> None:
    policy = load_image_policy()

    assert policy.max_bytes == 25 * 1024 * 1024
    assert policy.max_pixels == 60_000_000
    assert policy.display_edge == 1024
    assert HOST in policy.allowed_hosts


def test_display_copy_of_a_damaged_body_is_rejected() -> None:
    output = io.BytesIO()
    Image.new("RGB", (64, 64), "red").save(output, format="JPEG")
    damaged = output.getvalue()[:200]

    with pytest.raises(ImageRejectedError):
        PillowImageInspector(POLICY).display_copy(damaged)


def test_display_copy_keeps_the_transparency_of_palette_images() -> None:
    output = io.BytesIO()
    Image.new("P", (8, 8), 0).save(output, format="PNG", transparency=0)

    display = PillowImageInspector(POLICY).display_copy(output.getvalue())

    assert Image.open(io.BytesIO(display)).getchannel("A").getextrema() == (0, 0)
