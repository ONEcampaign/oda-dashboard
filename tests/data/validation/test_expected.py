"""Tests for the expected deltas file and matching."""

from pathlib import Path

import pytest

from src.data.validation.expected import (
    DEFAULT_EXPECTED_DELTAS_PATH,
    DeltaKind,
    ExpectedDelta,
    find_explanation,
    load_expected_deltas,
)

FULL_ENTRY = """
[[delta]]
view = "financing_view"
kind = "value"
reason = "PSI measure change"
years = [2023, 2024]
donors = ["France"]
indicators = ["Private sector instruments"]
max_rel = 0.05
"""


def _write(tmp_path: Path, text: str) -> Path:
    """Write a TOML file and return its path."""
    path = tmp_path / "expected.toml"
    path.write_text(text)
    return path


def test_shipped_file_is_empty() -> None:
    """The shipped skeleton parses and holds no entries."""
    assert load_expected_deltas(DEFAULT_EXPECTED_DELTAS_PATH) == []


def test_load_full_entry(tmp_path: Path) -> None:
    """Every field is read into the dataclass."""
    [entry] = load_expected_deltas(_write(tmp_path, FULL_ENTRY))
    assert entry == ExpectedDelta(
        view="financing_view",
        reason="PSI measure change",
        kind=DeltaKind.VALUE,
        years=frozenset({2023, 2024}),
        donors=frozenset({"France"}),
        indicators=frozenset({"Private sector instruments"}),
        recipients=None,
        max_rel=0.05,
    )


def test_minimal_entry_defaults(tmp_path: Path) -> None:
    """Only view and reason are required; empty filter lists mean any."""
    text = '[[delta]]\nview = "cross_view"\nreason = "r"\nyears = []\n'
    [entry] = load_expected_deltas(_write(tmp_path, text))
    assert entry.kind is DeltaKind.VALUE
    assert entry.years is None
    assert entry.max_rel is None


def test_missing_file(tmp_path: Path) -> None:
    """A missing file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_expected_deltas(tmp_path / "nope.toml")


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("[[delta]\n", "invalid TOML"),
        ("other = 1\n", "top-level"),
        ('delta = "x"\n', "array of tables"),
        ('[[delta]]\nview = "v"\n', "reason"),
        ('[[delta]]\nview = "v"\nreason = " "\n', "reason"),
        ('[[delta]]\nview = "v"\nreason = "r"\ntypo = 1\n', "unknown fields"),
        ('[[delta]]\nview = "v"\nreason = "r"\nkind = "x"\n', "kind must be"),
        ('[[delta]]\nview = "v"\nreason = "r"\nyears = ["2024"]\n', "years"),
        ('[[delta]]\nview = "v"\nreason = "r"\ndonors = "France"\n', "donors"),
        ('[[delta]]\nview = "v"\nreason = "r"\nmax_rel = -1\n', "max_rel"),
        ('[[delta]]\nview = "v"\nreason = "r"\nmax_rel = "a"\n', "max_rel"),
        (
            '[[delta]]\nview = "v"\nreason = "r"\nkind = "new_in_candidate"\nmax_rel = 0.1\n',
            "only to kind",
        ),
    ],
)
def test_invalid(tmp_path: Path, text: str, error: str) -> None:
    """Malformed files and entries are rejected with the reason."""
    with pytest.raises(ValueError, match=error):
        load_expected_deltas(_write(tmp_path, text))


ENTRY = ExpectedDelta(
    view="financing_view",
    reason="r",
    years=frozenset({2024}),
    donors=frozenset({"France"}),
    max_rel=0.05,
)


@pytest.mark.parametrize(
    ("kwargs", "matched"),
    [
        ({"year": 2024, "donor": "France", "rel_diff": 0.01}, True),
        ({"year": 2024, "donor": "France", "rel_diff": -0.05}, True),
        ({"year": 2024, "donor": "France", "rel_diff": 0.06}, False),
        ({"year": 2024, "donor": "France"}, False),  # max_rel needs a rel_diff
        ({"year": 2023, "donor": "France", "rel_diff": 0.0}, False),
        ({"donor": "France", "rel_diff": 0.0}, False),  # filtered dimension not given
        ({"year": 2024, "donor": "France", "indicator": "any", "rel_diff": 0.0}, True),
    ],
)
def test_matches(kwargs: dict, matched: bool) -> None:
    """Filters and max_rel decide a match."""
    assert ENTRY.matches(view="financing_view", kind="value", **kwargs) is matched


def test_matches_view_and_kind() -> None:
    """View and kind must agree; kind accepts plain strings."""
    entry = ExpectedDelta(
        view="cross_view", reason="r", kind=DeltaKind.NEW_IN_CANDIDATE
    )
    assert entry.matches(view="cross_view", kind="new_in_candidate")
    assert not entry.matches(view="cross_view", kind="value")
    assert not entry.matches(view="financing_view", kind="new_in_candidate")


def test_find_explanation() -> None:
    """The first matching entry is returned, None when nothing matches."""
    catch_all = ExpectedDelta(view="financing_view", reason="any")
    assert (
        find_explanation([ENTRY, catch_all], view="financing_view", kind="value")
        is catch_all
    )
    assert find_explanation([ENTRY], view="gender_view", kind="value") is None
