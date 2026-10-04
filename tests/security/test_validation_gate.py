"""A second integration waits for recorded customer evidence."""

from pathlib import Path


def test_second_source_is_blocked_until_validation_is_recorded() -> None:
    root = Path(__file__).resolve().parents[2]
    document = (root / "docs" / "validation.md").read_text(encoding="utf-8")
    assert "status: blocked" in document
    assert "Do not invent interview results." in document
    package = root / "apps" / "api" / "src" / "pulse_api"
    sources = sorted(
        path.name
        for path in package.iterdir()
        if path.is_dir() and (path / "client.py").exists()
    )
    if "status: blocked" in document:
        assert sources == ["gmail"]
