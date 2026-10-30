"""Tests for the cross-view checks of the dashboard views against topic_page outputs."""

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest

from src.data.validation import cross_view
from src.data.validation.cross_view import (
    CROSS_CHECKS,
    CrossCheck,
    Tolerance,
    ViewReader,
    compare,
    run_cross_view,
)
from src.data.validation.expected import DeltaKind, ExpectedDelta
from src.data.validation.models import Severity
from tests.data.validation.conftest import MakeView, write_flat, write_hive

DAC = "DAC countries"
ELIGIBLE = "ODA eligible countries"
MILLION = 1_000_000


def _topic_reader(files: dict[str, pd.DataFrame]) -> Callable[[str], pd.DataFrame]:
    """A read_topic stand-in serving in-memory frames as raw strings, like load_topic_page."""

    def read(name: str) -> pd.DataFrame:
        if name not in files:
            raise FileNotFoundError(f"No topic_page file {name}")
        return files[name].astype(str)

    return read


def _simple_check(
    topic: list[dict], view: list[dict], tolerance: Tolerance = Tolerance(relative=0.01)
) -> CrossCheck:
    """A (year, donor) comparison over fixed frames."""
    return CrossCheck(
        name="simple",
        topic=lambda _read: pd.DataFrame(topic),
        view=lambda _views: pd.DataFrame(view),
        keys=("year", "donor"),
        tolerance=tolerance,
        note="test",
    )


def _run(check: CrossCheck, expected: list[ExpectedDelta] | None = None) -> list:
    """Run one check with no sources."""
    return run_cross_view(
        {}, expected or [], checks=(check,), read_topic=_topic_reader({})
    )


# ---------------------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------------------


def test_tolerance_takes_the_larger_of_absolute_and_relative() -> None:
    """max(absolute, relative × |topic|) is the allowed gap."""
    tol = Tolerance(absolute=50.0, relative=0.01)
    topic = pd.Series([1_000.0, 10_000.0, 10_000.0])
    view = pd.Series([1_049.0, 10_099.0, 10_101.0])
    assert tol.allows(topic, view).tolist() == [True, True, False]


def test_cross_check_rejects_unknown_keys() -> None:
    """Keys must come from KEY_COLUMNS and include year."""
    with pytest.raises(ValueError, match="keys must include 'year'"):
        CrossCheck(
            name="bad",
            topic=lambda _r: pd.DataFrame(),
            view=lambda _v: pd.DataFrame(),
            keys=("donor", "sector"),
            tolerance=Tolerance(),
            note="",
        )


def test_every_registered_check_has_a_unique_name() -> None:
    """Check names identify results in the report."""
    names = [c.check for c in CROSS_CHECKS]
    assert len(names) == len(set(names))
    assert all(name.startswith("cross_view.") for name in names)


def test_compare_flags_missing_view_rows_and_ignores_extra_ones() -> None:
    """A topic row without a view row is outside tolerance; view-only rows are dropped."""
    check = _simple_check([], [])
    topic = pd.DataFrame(
        {"year": [2024, 2025], "donor": [DAC, DAC], "value": [1.0, 2.0]}
    )
    view = pd.DataFrame(
        {"year": [2024, 2023], "donor": [DAC, DAC], "value": [1.0, 9.0]}
    )
    out = compare(check, topic, view)
    assert out["year"].tolist() == [2024, 2025]
    assert out["within"].tolist() == [True, False]
    assert pd.isna(out.loc[1, "view"])


def test_compare_rejects_duplicate_keys() -> None:
    """A side with duplicate keys would silently fan out the join."""
    check = _simple_check([], [])
    topic = pd.DataFrame(
        {"year": [2024, 2024], "donor": [DAC, DAC], "value": [1.0, 2.0]}
    )
    with pytest.raises(ValueError, match="duplicate topic keys"):
        compare(check, topic, topic.head(1))


# ---------------------------------------------------------------------------------------
# Results and expected deltas
# ---------------------------------------------------------------------------------------


def test_pass_is_recorded_and_non_blocking() -> None:
    """All values within tolerance gives one passing result."""
    check = _simple_check(
        [{"year": 2024, "donor": DAC, "value": 100.0}],
        [{"year": 2024, "donor": DAC, "value": 100.5}],
    )
    [result] = _run(check)
    assert result.passed
    assert result.check == "cross_view.simple"
    assert result.view == "cross_view"
    assert not result.blocking


def test_unexplained_mismatch_is_a_non_blocking_error() -> None:
    """A gap no entry explains is an ERROR with the offending rows."""
    check = _simple_check(
        [{"year": 2024, "donor": DAC, "value": 100.0}],
        [{"year": 2024, "donor": DAC, "value": 110.0}],
    )
    [result] = _run(check)
    assert not result.passed
    assert result.severity is Severity.ERROR
    assert not result.blocking
    assert "+10.00%" in result.message
    assert result.details is not None and len(result.details) == 1


def test_explained_mismatch_is_info_with_reason() -> None:
    """An entry matching the year, donor and size turns the delta into INFO."""
    check = _simple_check(
        [
            {"year": 2024, "donor": DAC, "value": 100.0},
            {"year": 2024, "donor": "France", "value": 100.0},
        ],
        [
            {"year": 2024, "donor": DAC, "value": 104.0},
            {"year": 2024, "donor": "France", "value": 104.0},
        ],
    )
    expected = [
        ExpectedDelta(
            view="cross_view",
            reason="known gap",
            years=frozenset({2024}),
            donors=frozenset({DAC}),
            indicators=frozenset({"simple"}),
            max_rel=0.05,
        )
    ]
    results = _run(check, expected)
    by_severity = {r.severity: r for r in results}
    assert set(by_severity) == {Severity.INFO, Severity.ERROR}
    assert "explained (known gap)" in by_severity[Severity.INFO].message
    assert by_severity[Severity.INFO].details["donor"].tolist() == [DAC]
    assert by_severity[Severity.ERROR].details["donor"].tolist() == ["France"]
    assert all(not r.blocking for r in results)


def test_entries_for_other_views_do_not_explain_cross_view_deltas() -> None:
    """Only view = "cross_view" entries apply."""
    check = _simple_check(
        [{"year": 2024, "donor": DAC, "value": 100.0}],
        [{"year": 2024, "donor": DAC, "value": 104.0}],
    )
    expected = [ExpectedDelta(view="financing_view", reason="parity only")]
    [result] = _run(check, expected)
    assert result.severity is Severity.ERROR


def test_missing_view_row_matches_missing_in_candidate_entries() -> None:
    """A topic row the view lacks is a missing_in_candidate delta."""
    check = CrossCheck(
        name="simple",
        topic=lambda _r: pd.DataFrame([{"year": 2010, "donor": DAC, "value": 1.0}]),
        view=lambda _v: pd.DataFrame(columns=["year", "donor", "value"]),
        keys=("year", "donor"),
        tolerance=Tolerance(relative=0.01),
        note="",
    )
    expected = [
        ExpectedDelta(
            view="cross_view",
            reason="view starts later",
            kind=DeltaKind.MISSING_IN_CANDIDATE,
        )
    ]
    [result] = _run(check, expected)
    assert result.severity is Severity.INFO
    assert "view starts later" in result.message


def test_unreadable_source_becomes_an_error_result() -> None:
    """A missing topic file is reported, not raised, so other checks still run."""
    [result] = run_cross_view(
        {}, [], checks=CROSS_CHECKS[:1], read_topic=_topic_reader({})
    )
    assert not result.passed
    assert result.severity is Severity.ERROR
    assert "could not run" in result.message
    assert not result.blocking


# ---------------------------------------------------------------------------------------
# The real comparisons on synthetic views
# ---------------------------------------------------------------------------------------


def _financing_rows() -> list[dict]:
    """DAC Total ODA: flows in 2017, grant equivalents in 2018, with a decoy each year."""
    rows = []
    for year, real_type, decoy_type in [
        (2017, "Flows", "Grant equivalents"),
        (2018, "Grant equivalents", "Flows"),
    ]:
        rows += [
            {
                "year": year,
                "donor_name": DAC,
                "indicator_name": "Total ODA",
                "type": real_type,
                "value_usd_constant": 150_000 * MILLION,
                "value_usd_current": 140_000 * MILLION,
                "pct_of_gni": 0.0031,
            },
            {
                "year": year,
                "donor_name": DAC,
                "indicator_name": "Total ODA",
                "type": decoy_type,
                "value_usd_constant": 1 * MILLION,
                "value_usd_current": 1 * MILLION,
                "pct_of_gni": 0.0,
            },
        ]
    return rows


def test_total_oda_and_oda_gni_use_the_headline_measure(
    tmp_path: Path, make_view: MakeView
) -> None:
    """Flows before 2018 and grant equivalents from 2018, both against oda_gni_ts."""
    write_flat(make_view("financing_view", _financing_rows()), tmp_path / "fin")
    topic = {
        "oda_gni_ts": pd.DataFrame(
            {
                "name": [DAC, DAC],
                "year": [2017, 2018],
                "ODA (left-axis)": [150_100.0, 149_900.0],
                "ODA/GNI (right-axis)": [0.31, 0.31],
            }
        ),
    }
    names = {"cross_view.total_oda", "cross_view.oda_gni"}
    results = run_cross_view(
        {"financing_view": tmp_path / "fin"},
        [],
        checks=tuple(c for c in CROSS_CHECKS if c.check in names),
        read_topic=_topic_reader(topic),
    )
    assert {r.check for r in results} == names
    assert all(r.passed for r in results), [r.message for r in results]


def test_latest_year_files(tmp_path: Path, make_view: MakeView) -> None:
    """sm_total_oda (USD units) and oda_gni_sm (fraction) take the year from first_line."""
    write_flat(make_view("financing_view", _financing_rows()), tmp_path / "fin")
    topic = {
        "sm_total_oda": pd.DataFrame(
            {"first_line": ["As of 2018"], "value": [150_000 * MILLION]}
        ),
        "oda_gni_sm": pd.DataFrame({"first_line": ["As of 2018"], "oda_gni": [0.0031]}),
    }
    names = {"cross_view.total_oda_latest", "cross_view.oda_gni_latest"}
    results = run_cross_view(
        {"financing_view": tmp_path / "fin"},
        [],
        checks=tuple(c for c in CROSS_CHECKS if c.check in names),
        read_topic=_topic_reader(topic),
    )
    assert all(r.passed for r in results), [r.message for r in results]


def _sector_rows() -> list[dict]:
    """DAC at ODA eligible (Health 30, Education 70, split across both indicators), plus a
    country partition that must not be read."""
    rows = []
    for recipient, scale in [(ELIGIBLE, 1), ("Kenya", 1_000)]:
        for indicator, health, education in [
            ("Bilateral", 20, 50),
            ("Imputed multilateral", 10, 20),
        ]:
            for sector, value in [("Health", health), ("Education", education)]:
                rows.append(
                    {
                        "year": 2024,
                        "donor_name": DAC,
                        "recipient_name": recipient,
                        "indicator_name": indicator,
                        "sector_name": sector,
                        "sub_sector_name": sector,
                        "value_usd_current": value * scale * MILLION,
                        "value_usd_constant": value * scale * MILLION,
                    }
                )
    return rows


@pytest.mark.parametrize("options_beside", [False, True])
def test_sectors_reader_reads_only_oda_eligible(
    tmp_path: Path, make_view: MakeView, options_beside: bool
) -> None:
    """Only the ODA eligible partition is read, from either hive layout or its parent."""
    hive = write_hive(
        make_view("sectors_view", _sector_rows()),
        tmp_path / "sectors_view",
        options_beside=options_beside,
    )
    for source in (hive, tmp_path):
        data = ViewReader({"sectors_view": source}).sectors_oda_eligible
        assert set(data["recipient_name"]) == {ELIGIBLE}
        assert data["value_usd_constant"].sum() == 100 * MILLION
        assert str(data["donor_name"].dtype) == "string"


def test_sectors_reader_raises_without_partitions(tmp_path: Path) -> None:
    """No ODA eligible partitions is a FileNotFoundError naming the pattern."""
    with pytest.raises(FileNotFoundError, match="oda-eligible-countries"):
        _ = ViewReader({"sectors_view": tmp_path}).sectors_oda_eligible


def test_sector_shares_and_amounts(tmp_path: Path, make_view: MakeView) -> None:
    """Shares over both indicators and all sectors; amounts in billions; pre-2013 dropped."""
    write_hive(make_view("sectors_view", _sector_rows()), tmp_path / "sectors_view")
    topic = {
        "key_sector_shares": pd.DataFrame(
            {
                "Year": [2010, 2024],
                "name": ["DAC Countries, Total"] * 2,
                "Humanitarian": ["", ""],
                "Education": [0.5, 0.7],
                "Health": [0.5, 0.3],
                "Refugees in Donor Countries": ["", ""],
                "Environment Protection": ["", ""],
            }
        ),
        "aid_to_health_ts": pd.DataFrame(
            {
                "Year": [2012, 2024],
                "Donor": ["DAC Countries, Total"] * 2,
                "Recipient": ["All Developing Countries"] * 2,
                "Sector": ["Health"] * 2,
                "Total aid to health": ["99.0", "0.0"],
                "Share of total ODA": ['"30.0%"'] * 2,
            }
        ),
    }
    names = {"cross_view.sector_shares", "cross_view.health"}
    results = run_cross_view(
        {"sectors_view": tmp_path},
        [],
        checks=tuple(c for c in CROSS_CHECKS if c.check in names),
        read_topic=_topic_reader(topic),
    )
    by_check = {r.check: r for r in results}
    assert by_check["cross_view.sector_shares"].passed
    assert "2 values" in by_check["cross_view.sector_shares"].message
    # 30 USD mn vs a topic "0.0" billion: within the 0.05bn rounding floor; 2012 dropped.
    assert by_check["cross_view.health"].passed
    assert "1 values" in by_check["cross_view.health"].message


def _recipient_rows() -> list[dict]:
    """DAC to Africa, ODA eligible and LICs in 2024, over both indicators."""
    rows = []
    for recipient, bilateral, imputed in [
        ("Africa", 30, 10),
        (ELIGIBLE, 100, 60),
        ("Low Income Countries (LICs)", 20_000, 7_000),
    ]:
        for indicator, value in [
            ("Bilateral", bilateral),
            ("Imputed multilateral", imputed),
        ]:
            rows.append(
                {
                    "year": 2024,
                    "donor_name": DAC,
                    "recipient_name": recipient,
                    "indicator_name": indicator,
                    "value_usd_current": value * MILLION,
                    "value_usd_constant": value * MILLION,
                }
            )
    return rows


def test_africa_share_and_income_groups(tmp_path: Path, make_view: MakeView) -> None:
    """Africa / ODA eligible as a share; income groups from "US$x billion" strings."""
    write_flat(make_view("recipients_view", _recipient_rows()), tmp_path / "rec")
    topic = {
        "aid_to_africa_ts": pd.DataFrame(
            {
                "Year": [2024],
                "Donor": ["DAC Countries, Total"],
                "Aid to Africa": ["0.0"],
                "Share of total ODA": ['"25.0%"'],
                "Annual change": [""],
            }
        ),
        "aid_to_income_latest": pd.DataFrame(
            {
                "Year": [2024, 2024],
                "Donor": ["DAC Countries, Total"] * 2,
                "Recipient": ["Low income", "Not classified by income"],
                "ODA": ["US$27.0 billion", "US$88.3 billion"],
                "Share of total ODA": [12.9, 42.2],
                "Label": ["", ""],
            }
        ),
    }
    names = {"cross_view.africa_share", "cross_view.income_groups"}
    results = run_cross_view(
        {"recipients_view": tmp_path / "rec"},
        [],
        checks=tuple(c for c in CROSS_CHECKS if c.check in names),
        read_topic=_topic_reader(topic),
    )
    assert all(r.passed for r in results), [r.message for r in results]
    assert {r.check for r in results} == names


def test_views_are_loaded_once(
    tmp_path: Path, make_view: MakeView, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Several checks on one view share a single load."""
    write_flat(make_view("financing_view", _financing_rows()), tmp_path / "fin")
    calls: list[str] = []
    real_load = cross_view.load_view

    def counting_load(name: str, source: Path):
        calls.append(name)
        return real_load(name, source)

    monkeypatch.setattr(cross_view, "load_view", counting_load)
    reader = ViewReader({"financing_view": tmp_path / "fin"})
    reader.data("financing_view")
    reader.data("financing_view")
    assert calls == ["financing_view"]
