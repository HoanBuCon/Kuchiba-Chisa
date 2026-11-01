"""Wiki sync config: the shipped YAML loads, classifies real titles, rejects unknown keys."""

import shutil
from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.infrastructure.ingestion.wiki_sync_config import CONFIG_DIR, load_wiki_sync_config


@pytest.fixture(scope="module")
def config():
    return load_wiki_sync_config()


@pytest.mark.parametrize(
    ("title", "categories", "family"),
    [
        ("Chisa", ["Category:Resonators"], "resonator"),
        ("Chisa/Backstory", ["Category:Resonator Backstory"], "resonator_backstory"),
        ("Chisa/Gallery", ["Category:Resonators"], None),
        ("Some Echo", ["Category:Echoes"], None),
    ],
)
def test_shipped_catalog_classifies_tier_a_only(config, title, categories, family) -> None:
    rule = config.catalog.classify(title, categories)

    assert (rule.name if rule else None) == family


def test_navboxes_are_chrome_and_infoboxes_content(config) -> None:
    assert not config.classifier.is_content("Template:Resonator Navbox")
    assert config.classifier.is_content("Template:Infobox Resonator")
    assert config.classifier.is_content("Template:Never Seen Before")


def test_release_mode_only_shortens_stabilisation(config) -> None:
    assert (
        config.release_mode_policy.stabilization
        < config.policy.stabilization
        == timedelta(hours=24)
    )
    assert config.release_mode_policy.budget == config.policy.budget


def test_unknown_keys_are_rejected(tmp_path) -> None:
    for name in ("families.yaml", "templates.yaml", "sync.yaml"):
        shutil.copy(CONFIG_DIR / name, tmp_path / name)
    sync = tmp_path / "sync.yaml"
    sync.write_text(sync.read_text(encoding="utf-8") + "surprise: true\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_wiki_sync_config(tmp_path)
