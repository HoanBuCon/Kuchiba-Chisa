import pytest

from app.domain.ingestion.field_labels import field_label


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("voiceEN", "English voice actor"),
        ("voiceCN", "Chinese voice actor"),
        ("age", "Age"),
        ("birthPlace", "Birth place"),
        ("firstAppearance", "First appearance"),
        ("release_date", "Release date"),
        ("HPBonus", "HP bonus"),
        ("", ""),
    ],
)
def test_field_label_is_readable(key: str, expected: str) -> None:
    assert field_label(key) == expected
