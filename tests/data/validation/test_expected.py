"""Tests for the expected deltas file and matching."""

from pathlib import Path

import pytest

from src.data.validation.cross_view import VIEW as CROSS_VIEW
from src.data.validation.expected import (
    DEFAULT_EXPECTED_DELTAS_PATH,
    DeltaKind,
    ExpectedDelta,
    find_explanation,
    load_expected_deltas,
    unused_entries,
)
from src.data.validation.views import VIEWS

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


def test_shipped_file_parses_with_known_views() -> None:
    """The shipped file parses, and every entry names a view or cross_view."""
    known = {*VIEWS, CROSS_VIEW}
    for entry in load_expected_deltas(DEFAULT_EXPECTED_DELTAS_PATH):
        assert entry.view in known, entry


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
    """View, reason and one filter suffice; the rest default to any."""
    text = '[[delta]]\nview = "cross_view"\nreason = "r"\nyears = [2024]\n'
    [entry] = load_expected_deltas(_write(tmp_path, text))
    assert entry.kind is DeltaKind.VALUE
    assert entry.donors is None
    assert entry.max_rel is None


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ("", "at least one of"),  # no filter or bound: would explain everything
        ("years = []", "years is empty"),
        ("donors = []", "donors is empty"),
    ],
)
def test_entries_must_be_scoped(tmp_path: Path, body: str, error: str) -> None:
    """An entry without a filter or bound, or with an empty filter, is rejected."""
    text = f'[[delta]]\nview = "gender_view"\nreason = "r"\n{body}\n'
    with pytest.raises(ValueError, match=error):
        load_expected_deltas(_write(tmp_path, text))


def test_unknown_view_is_rejected(tmp_path: Path) -> None:
    """A misspelt view fails to load instead of never matching."""
    text = '[[delta]]\nview = "financing"\nreason = "r"\nyears = [2024]\n'
    with pytest.raises(ValueError, match="unknown view 'financing'"):
        load_expected_deltas(_write(tmp_path, text))


def test_anomaly_entries_take_max_rel_only(tmp_path: Path) -> None:
    """Kind "anomaly" reads max_rel and rejects max_abs."""
    base = '[[delta]]\nview = "financing_view"\nreason = "r"\nkind = "anomaly"\n'
    [entry] = load_expected_deltas(_write(tmp_path, base + "max_rel = 0.6\n"))
    assert entry.kind is DeltaKind.ANOMALY and entry.max_rel == 0.6
    with pytest.raises(ValueError, match="does not apply"):
        load_expected_deltas(_write(tmp_path, base + "max_abs = 1\n"))


def test_hits_and_unused_entries() -> None:
    """find_explanation counts hits, and unused_entries lists in-scope entries never hit."""
    used = ExpectedDelta(view="financing_view", reason="u", years=frozenset({2024}))
    idle = ExpectedDelta(view="gender_view", reason="i", years=frozenset({2024}))
    cross = ExpectedDelta(view="cross_view", reason="c", years=frozenset({2024}))
    anomaly = ExpectedDelta(
        view="gender_view", reason="a", kind=DeltaKind.ANOMALY, max_rel=1.0
    )
    entries = [used, idle, cross, anomaly]
    assert find_explanation(entries, view="financing_view", kind="value", year=2024)
    assert used.hits == 1 and idle.hits == 0

    def unused(**scope: object) -> list[str]:
        return [e.reason for e in unused_entries(entries, **scope)]

    assert unused(anomaly_views=[], parity_views=[], cross_view=False) == []
    assert unused(anomaly_views=["gender_view"], parity_views=[], cross_view=True) == [
        "c",
        "a",
    ]
    assert unused(
        anomaly_views=[],
        parity_views=["financing_view", "gender_view"],
        cross_view=False,
    ) == ["i"]


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
        ('[[delta]]\nview = "gender_view"\nreason = "r"\ntypo = 1\n', "unknown fields"),
        ('[[delta]]\nview = "gender_view"\nreason = "r"\nkind = "x"\n', "kind must be"),
        ('[[delta]]\nview = "gender_view"\nreason = "r"\nyears = ["2024"]\n', "years"),
        (
            '[[delta]]\nview = "gender_view"\nreason = "r"\ndonors = "France"\n',
            "donors",
        ),
        ('[[delta]]\nview = "gender_view"\nreason = "r"\nmax_rel = -1\n', "max_rel"),
        ('[[delta]]\nview = "gender_view"\nreason = "r"\nmax_rel = "a"\n', "max_rel"),
        ('[[delta]]\nview = "gender_view"\nreason = "r"\nmax_abs = -1\n', "max_abs"),
        (
            '[[delta]]\nview = "gender_view"\nreason = "r"\ncolumns = "pct_of_gni"\n',
            "columns",
        ),
        (
            '[[delta]]\nview = "gender_view"\nreason = "r"\nkind = "new_in_candidate"\nmax_abs = 1\n',
            "does not apply to kind",
        ),
        (
            '[[delta]]\nview = "gender_view"\nreason = "r"\nkind = "new_in_candidate"\nmax_rel = 0.1\n',
            "does not apply to kind",
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


ROUNDING = ExpectedDelta(
    view="financing_view",
    reason="rounding",
    columns=frozenset({"value_usd_current"}),
    max_rel=0.001,
    max_abs=100.0,
)


@pytest.mark.parametrize(
    ("kwargs", "matched"),
    [
        ({"rel_diff": 0.5, "abs_diff": 50.0}, True),  # within max_abs only
        ({"rel_diff": 0.0005, "abs_diff": 5_000.0}, True),  # within max_rel only
        ({"rel_diff": 0.5, "abs_diff": 5_000.0}, False),  # within neither
        ({"rel_diff": None, "abs_diff": -50.0}, True),  # sign ignored, no rel needed
        ({"rel_diff": 0.5, "abs_diff": None}, False),
    ],
)
def test_max_abs_or_max_rel(kwargs: dict, matched: bool) -> None:
    """With both bounds set, a delta within either is explained."""
    assert (
        ROUNDING.matches(
            view="financing_view", kind="value", column="value_usd_current", **kwargs
        )
        is matched
    )


def test_columns_filter() -> None:
    """A columns filter needs the delta's column, and that column in the filter."""
    kwargs = {"view": "financing_view", "kind": "value", "abs_diff": 1.0}
    assert not ROUNDING.matches(column="pct_of_gni", **kwargs)
    assert not ROUNDING.matches(**kwargs)


def test_load_max_abs_and_columns(tmp_path: Path) -> None:
    """max_abs and columns are read from the file."""
    text = (
        '[[delta]]\nview = "financing_view"\nreason = "r"\nmax_abs = 11000\n'
        'columns = ["value_usd_current"]\n'
    )
    [entry] = load_expected_deltas(_write(tmp_path, text))
    assert entry.max_abs == 11_000.0
    assert entry.columns == frozenset({"value_usd_current"})


def test_load_paths(tmp_path: Path) -> None:
    """paths is read as a set of dotted options paths."""
    text = '[[delta]]\nview = "gender_view"\nreason = "r"\npaths = ["year.start"]\n'
    [entry] = load_expected_deltas(_write(tmp_path, text))
    assert entry.paths == frozenset({"year.start"})


@pytest.mark.parametrize(
    "extra", ['paths = "year.start"', 'paths = ["year.start"]\nmax_abs = 1']
)
def test_invalid_paths(tmp_path: Path, extra: str) -> None:
    """paths must be a list of strings and takes no bounds."""
    text = f'[[delta]]\nview = "gender_view"\nreason = "r"\n{extra}\n'
    with pytest.raises(ValueError, match="paths"):
        load_expected_deltas(_write(tmp_path, text))


def test_paths_filter() -> None:
    """An entry with paths matches only a delta at one of those paths."""
    entry = ExpectedDelta(
        view="gender_view", reason="r", paths=frozenset({"year.start"})
    )
    assert entry.matches(view="gender_view", kind="value", path="year.start")
    assert not entry.matches(view="gender_view", kind="value", path="year.end")
    assert not entry.matches(view="gender_view", kind="value", year=2024)
