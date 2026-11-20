"""Tests for per-file version handling in register_bulk_files, with no network."""

import json
from pathlib import Path

import oda_reader
import pytest

from src.data.analysis_tools import oda as oda_tools
from src.data.scripts import register_bulk_files
from src.data.scripts.register_bulk_files import (
    BULK_FILES,
    RELEASE_TOKEN_PREFIX,
    parse_versions,
    register_all,
)

ASSET_TIMES = {
    spec.file_name: f"2026-10-{15 + i}T13:08:35Z" for i, spec in enumerate(BULK_FILES)
}


@pytest.fixture
def bulk_dir(tmp_path: Path) -> Path:
    """A folder holding an empty stand-in for each bulk file."""
    for spec in BULK_FILES:
        (tmp_path / spec.file_name).touch()
    return tmp_path


@pytest.fixture
def registered(monkeypatch, tmp_path: Path) -> list[dict[str, str]]:
    """Replace oda_reader.register_bulk_file with a recorder; keep the cache in tmp."""
    calls: list[dict[str, str]] = []

    def fake_register(path: Path, *, dataset: str, url: str, version: str) -> Path:
        calls.append({"file": path.name, "dataset": dataset, "version": version})
        return path

    monkeypatch.setattr(oda_reader, "register_bulk_file", fake_register)
    monkeypatch.setattr(oda_tools, "ODA_CACHE_DIR", tmp_path / "cache")
    return calls


def test_parse_versions_prefixes_each_token():
    parsed = parse_versions(json.dumps(ASSET_TIMES))
    assert parsed == {k: f"{RELEASE_TOKEN_PREFIX}{v}" for k, v in ASSET_TIMES.items()}


@pytest.mark.parametrize(
    "raw", ["not json", "[1, 2]", '{"CRS.parquet": ""}', '{"a": 1}']
)
def test_parse_versions_rejects_bad_input(raw):
    with pytest.raises(ValueError, match="--versions"):
        parse_versions(raw)


def test_each_file_registers_with_its_own_token(bulk_dir, registered):
    register_all(bulk_dir, versions=parse_versions(json.dumps(ASSET_TIMES)))

    assert [c["file"] for c in registered] == [s.file_name for s in BULK_FILES]
    for call in registered:
        assert call["version"] == f"{RELEASE_TOKEN_PREFIX}{ASSET_TIMES[call['file']]}"
    assert len({c["version"] for c in registered}) == len(BULK_FILES)


def test_a_file_without_a_version_raises_before_registering_any(bulk_dir, registered):
    versions = parse_versions(json.dumps(ASSET_TIMES))
    del versions["Table2a_Data.zip"]

    with pytest.raises(ValueError, match="Table2a_Data.zip"):
        register_all(bulk_dir, versions=versions)
    assert registered == []


def test_main_version_applies_one_token_to_every_file(bulk_dir, registered):
    register_bulk_files.main(["--dir", str(bulk_dir), "--version", "local-test"])
    assert {c["version"] for c in registered} == {"local-test"}
    assert len(registered) == len(BULK_FILES)
