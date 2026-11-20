"""Tests for loading views and parsing topic_page strings."""

import math
from pathlib import Path

import pandas as pd
import pytest

from src.data.config import PATHS
from src.data.validation import io
from src.data.validation.io import (
    default_sources,
    iter_partitions,
    load_topic_page,
    load_view,
    parse_amount,
    parse_percent,
)
from tests.data.validation.conftest import MakeView, write_flat, write_hive

FINANCING_ROWS = [
    {
        "year": 2024,
        "donor_name": "France",
        "indicator_name": "Total ODA",
        "type": "Grant equivalents",
        "value_usd_current": 15_000_000_000,
    },
    {
        "year": 2024,
        "donor_name": "Germany",
        "indicator_name": "Total ODA",
        "type": "Grant equivalents",
        "value_usd_current": 32_000_000_000,
    },
]


def _assert_loader_dtypes(df: pd.DataFrame) -> None:
    """Labels are arrow-backed strings; year and values keep their widths."""
    assert str(df["donor_name"].dtype) == "string"
    assert df["donor_name"].dtype.storage == "pyarrow"
    assert str(df["year"].dtype) == "int16"
    assert str(df["value_usd_current"].dtype) == "float64"


def test_load_flat(tmp_path: Path, make_view: MakeView) -> None:
    """Layout 1: data.parquet + options.json, dictionary labels decoded to strings."""
    view = make_view("financing_view", FINANCING_ROWS)
    write_flat(view, tmp_path / "financing_view")

    loaded = load_view("financing_view", tmp_path / "financing_view")

    assert loaded.spec.name == "financing_view"
    assert loaded.options == view.options
    assert loaded.source == tmp_path / "financing_view"
    assert len(loaded.data) == 2
    _assert_loader_dtypes(loaded.data)
    assert str(loaded.data["pct_of_gni"].dtype) == "float32"
    pd.testing.assert_frame_equal(loaded.data, view.data)


def test_null_values_load_as_nan(tmp_path: Path, make_view: MakeView) -> None:
    """A null in an int64 value column is NaN, and the dtype is float64 either way."""
    rows = [
        {**FINANCING_ROWS[0], "value_eur_current": 5},
        {**FINANCING_ROWS[1], "value_eur_current": None},
    ]
    write_flat(make_view("financing_view", rows), tmp_path / "f")
    with_null = load_view("financing_view", tmp_path / "f").data
    assert with_null["value_eur_current"].isna().tolist() == [False, True]
    assert str(with_null["value_eur_current"].dtype) == "float64"
    assert str(with_null["value_eur_constant"].dtype) == "float64"


def test_load_hive_options_inside(
    tmp_path: Path, make_view: MakeView, sector_rows: list[dict]
) -> None:
    """Layout 2: hive partitions + options.json inside; slug columns dropped."""
    view = make_view("sectors_view", sector_rows)
    write_hive(view, tmp_path / "sectors_view")

    loaded = load_view("sectors_view", tmp_path / "sectors_view")

    assert len(loaded.data) == 4
    assert not {"donor_slug", "recipient_slug"} & set(loaded.data.columns)
    assert set(loaded.data.columns) == set(view.data.columns)
    _assert_loader_dtypes(loaded.data)
    assert loaded.data["value_usd_current"].sum() == 10_000_000
    assert loaded.options == view.options


@pytest.mark.parametrize("pass_parent", [False, True])
def test_load_hive_options_beside(
    tmp_path: Path, make_view: MakeView, sector_rows: list[dict], pass_parent: bool
) -> None:
    """Layout 3 (CDN): options beside the hive dir; the parent dir also works."""
    view = make_view("sectors_view", sector_rows)
    hive = write_hive(view, tmp_path / "sectors_view", options_beside=True)

    loaded = load_view("sectors_view", tmp_path if pass_parent else hive)

    assert len(loaded.data) == 4
    assert loaded.options == view.options


def test_missing_data_names_paths(tmp_path: Path) -> None:
    """No data: FileNotFoundError names the paths tried."""
    with pytest.raises(FileNotFoundError, match="data.parquet"):
        load_view("financing_view", tmp_path)


def test_missing_options_names_paths(tmp_path: Path, make_view: MakeView) -> None:
    """Data but no options: FileNotFoundError names both option paths tried."""
    write_flat(make_view("financing_view", FINANCING_ROWS), tmp_path / "financing_view")
    (tmp_path / "financing_view" / "options.json").unlink()
    with pytest.raises(FileNotFoundError, match="financing_view_options.json"):
        load_view("financing_view", tmp_path / "financing_view")


def test_options_must_be_object(tmp_path: Path, make_view: MakeView) -> None:
    """A non-object options.json is rejected."""
    write_flat(make_view("financing_view", FINANCING_ROWS), tmp_path / "f")
    (tmp_path / "f" / "options.json").write_text("[]")
    with pytest.raises(ValueError, match="JSON object"):
        load_view("financing_view", tmp_path / "f")


def test_unknown_view(tmp_path: Path) -> None:
    """An unknown view name raises KeyError before touching disk."""
    with pytest.raises(KeyError):
        load_view("nope", tmp_path)


@pytest.mark.parametrize(
    ("by", "expected"),
    [
        (
            "recipient_slug",
            {"kenya": {"France", "Germany"}, "mali": {"France", "Germany"}},
        ),
        ("donor_slug", {"france": {"France"}, "germany": {"Germany"}}),
    ],
)
def test_iter_partitions(
    tmp_path: Path,
    make_view: MakeView,
    sector_rows: list[dict],
    by: str,
    expected: dict[str, set[str]],
) -> None:
    """Each partition value yields its rows; together they make up the view."""
    view = make_view("sectors_view", sector_rows)
    write_hive(view, tmp_path / "sectors_view")

    parts = list(iter_partitions("sectors_view", tmp_path / "sectors_view", by=by))

    assert [slug for slug, _ in parts] == sorted(expected)
    for slug, part in parts:
        assert set(part.data["donor_name"]) == expected[slug]
        assert not {"donor_slug", "recipient_slug"} & set(part.data.columns)
        _assert_loader_dtypes(part.data)
        assert part.options == view.options
    assert sum(len(p.data) for _, p in parts) == 4


def test_iter_partitions_flat_yields_once(tmp_path: Path, make_view: MakeView) -> None:
    """A flat source yields the whole view once, keyed "all"."""
    write_flat(make_view("financing_view", FINANCING_ROWS), tmp_path / "f")
    parts = list(iter_partitions("financing_view", tmp_path / "f"))
    assert [slug for slug, _ in parts] == ["all"]
    assert len(parts[0][1].data) == 2


def test_iter_partitions_bad_by(tmp_path: Path) -> None:
    """Only the two slug columns are valid partition keys."""
    with pytest.raises(ValueError, match="by must be"):
        next(iter_partitions("sectors_view", tmp_path, by="year"))  # type: ignore[arg-type]  # invalid on purpose


def test_default_sources() -> None:
    """Observable cache for archive views, cdn_files for sectors."""
    sources = default_sources()
    assert set(sources) == {
        "financing_view",
        "recipients_view",
        "gender_view",
        "sectors_view",
    }
    assert sources["sectors_view"] == PATHS.CDN_FILES / "sectors_view"
    assert sources["financing_view"].parts[-5:] == (
        ".observablehq",
        "cache",
        "data",
        "scripts",
        "financing_view",
    )


def test_load_topic_page_raw_strings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cells stay strings; blanks are empty strings, not NaN; ".csv" is optional."""
    (tmp_path / "t.csv").write_text(
        'Year,Donor,Share,Annual change\n2010,"DAC Countries, Total","36.7%",\n'
    )
    monkeypatch.setattr(io.PATHS, "TOPIC_PAGE", tmp_path)

    for name in ("t", "t.csv"):
        df = load_topic_page(name)
        assert df.to_dict("records") == [
            {
                "Year": "2010",
                "Donor": "DAC Countries, Total",
                "Share": "36.7%",
                "Annual change": "",
            }
        ]


def test_load_topic_page_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing file raises with its path."""
    monkeypatch.setattr(io.PATHS, "TOPIC_PAGE", tmp_path)
    with pytest.raises(FileNotFoundError, match="nope.csv"):
        load_topic_page("nope")


@pytest.mark.parametrize(
    ("text", "millions"),
    [
        ("59.0 billion", 59_000.0),
        ("US$27.0 billion", 27_000.0),
        ("US$ 0.8 billion", 800.0),
        ("694.2 million", 694.2),
        ("0.0 million", 0.0),
        ("1,234.5 million", 1_234.5),
        ("5.67 Billion", 5_670.0),
        ("-3.5 billion", -3_500.0),
    ],
)
def test_parse_amount(text: str, millions: float) -> None:
    """Amounts come back in USD millions."""
    assert math.isclose(parse_amount(text), millions)


@pytest.mark.parametrize("text", ["", "55.3", "302 trillion", "billion", "US$"])
def test_parse_amount_rejects(text: str) -> None:
    """No number or no unit word is an error."""
    with pytest.raises(ValueError, match="amount"):
        parse_amount(text)


@pytest.mark.parametrize(
    ("text", "fraction"),
    [("26.8%", 0.268), ("-23.1 %", -0.231), ("0.26%", 0.0026), ("100%", 1.0)],
)
def test_parse_percent(text: str, fraction: float) -> None:
    """Percentages come back as fractions."""
    assert math.isclose(parse_percent(text), fraction)


@pytest.mark.parametrize("text", ["", "26.8", "%", "abc%"])
def test_parse_percent_rejects(text: str) -> None:
    """Anything but a number followed by % is an error."""
    with pytest.raises(ValueError, match="percentage"):
        parse_percent(text)
