"""Tests for parity between a candidate build and a baseline snapshot."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data.validation.expected import DeltaKind, ExpectedDelta
from src.data.validation.models import MAX_DETAIL_ROWS, CheckResult, Severity
from src.data.validation.parity import compare_views, run_parity
from tests.data.validation.conftest import MakeView, write_flat, write_hive

VIEW = "financing_view"
BILLION = 1_000_000_000


def _row(
    donor: str = "France",
    year: int = 2024,
    value: float = BILLION,
    indicator: str = "Total ODA",
) -> dict:
    """One financing_view row."""
    return {
        "year": year,
        "donor_name": donor,
        "indicator_name": indicator,
        "type": "Grant equivalents",
        "value_usd_current": value,
    }


def _failures(
    results: list[CheckResult], check: str | None = None
) -> list[CheckResult]:
    """Failed results, optionally of one check."""
    return [r for r in results if not r.passed and check in (None, r.check)]


def _only_failure(results: list[CheckResult], check: str) -> CheckResult:
    """The single failed result of a check."""
    failures = _failures(results, check)
    assert len(failures) == 1, failures
    return failures[0]


def _details(result: CheckResult) -> pd.DataFrame:
    """A result's detail rows, which must be present."""
    assert result.details is not None
    return result.details


def test_identical_views_pass(make_view: MakeView) -> None:
    """Self-parity: every check passes and every result is non-blocking."""
    view = make_view(VIEW, [_row(), _row("Germany")])

    results = compare_views(view, view, [])

    assert not _failures(results)
    assert {r.check for r in results} >= {
        "parity.row_count",
        "parity.missing_in_candidate",
        "parity.new_in_candidate",
        "parity.value_usd_current",
        "parity.other_values",
        "parity.shares",
        "parity.donor_totals",
        "parity.options",
    }
    assert all(not r.blocking for r in results)


@pytest.mark.parametrize(
    ("baseline", "candidate", "differs"),
    [
        (1_000.0, 1_100.0, False),  # ROUNDING_UNIT (100 units) floor
        (1_000.0, 1_101.0, True),
        (BILLION, BILLION + 900, False),  # within 1e-6 relative (1,000 units)
        (BILLION, BILLION + 1_100, True),
    ],
)
def test_usd_current_tolerance(
    make_view: MakeView, baseline: float, candidate: float, differs: bool
) -> None:
    """value_usd_current differs beyond max(100 units, 1e-6 relative)."""
    base = make_view(VIEW, [_row(value=baseline)])
    cand = make_view(VIEW, [_row(value=candidate)], options=base.options)

    results = compare_views(cand, base, [])

    assert bool(_failures(results, "parity.value_usd_current")) is differs


@pytest.mark.parametrize(("factor", "differs"), [(1.002, False), (1.004, True)])
def test_other_values_tolerance(
    make_view: MakeView, factor: float, differs: bool
) -> None:
    """The other value columns allow 0.003 relative."""
    base = make_view(VIEW, [_row()])
    cand = make_view(VIEW, [_row()], options=base.options)
    cand.data["value_eur_current"] = cand.data["value_eur_current"] * factor

    results = compare_views(cand, base, [])

    assert bool(_failures(results, "parity.other_values")) is differs
    assert not _failures(results, "parity.value_usd_current")


@pytest.mark.parametrize(("shift", "differs"), [(5e-5, False), (2e-4, True)])
def test_share_tolerance(make_view: MakeView, shift: float, differs: bool) -> None:
    """Shares allow 1e-4 absolute."""
    base = make_view(VIEW, [{**_row(), "pct_of_gni": 0.5}])
    cand = make_view(
        VIEW, [{**_row(), "pct_of_gni": 0.5 + shift}], options=base.options
    )

    results = compare_views(cand, base, [])

    assert bool(_failures(results, "parity.shares")) is differs


def test_nulls(make_view: MakeView) -> None:
    """Null against null is equal; null against a number is a delta."""
    rows = [{**_row(), "pct_of_gni": np.nan}, {**_row("Germany"), "pct_of_gni": 0.3}]
    base = make_view(VIEW, rows)
    cand = make_view(
        VIEW,
        [{**_row(), "pct_of_gni": np.nan}, {**_row("Germany"), "pct_of_gni": np.nan}],
        options=base.options,
    )

    failure = _only_failure(compare_views(cand, base, []), "parity.shares")

    assert failure.severity is Severity.ERROR
    assert _details(failure)["donor_name"].tolist() == ["Germany"]
    assert np.isnan(_details(failure)["candidate"].iat[0])


def test_one_sided_keys_are_summarised(make_view: MakeView) -> None:
    """Keys on one side only: counted, summed and broken down by year and donor."""
    base = make_view(VIEW, [_row(), _row("Germany", value=2 * BILLION)])
    cand = make_view(VIEW, [_row(), _row("Italy", year=2023)], options=base.options)

    results = compare_views(cand, base, [])

    missing = _only_failure(results, "parity.missing_in_candidate")
    assert missing.severity is Severity.ERROR
    assert missing.message.startswith("1 keys only in the baseline")
    assert "-2.00bn" in missing.message
    assert "by donor: Germany (1, -2.00bn)" in missing.message
    new = _only_failure(results, "parity.new_in_candidate")
    assert "by year: 2023 (1, +1.00bn)" in new.message
    assert _failures(results, "parity.donor_totals")
    assert _failures(results, "parity.row_count") == []  # 2 rows each side


def test_row_count_difference(make_view: MakeView) -> None:
    """Different row counts fail with the signed difference."""
    base = make_view(VIEW, [_row(), _row("Germany")])
    cand = make_view(VIEW, [_row()], options=base.options)

    failure = _only_failure(compare_views(cand, base, []), "parity.row_count")

    assert failure.message == "candidate 1 rows, baseline 2 rows (-1)"


def test_expected_delta_explains_value(make_view: MakeView) -> None:
    """A matching entry turns a delta into INFO with its reason; the rest stay ERROR."""
    base = make_view(VIEW, [_row(), _row("Germany")])
    cand = make_view(
        VIEW,
        [_row(value=1.02 * BILLION), _row("Germany", value=1.5 * BILLION)],
        options=base.options,
    )
    expected = [
        ExpectedDelta(
            view=VIEW,
            reason="PSI measure change",
            donors=frozenset({"France", "Germany"}),
            max_rel=0.05,
        )
    ]

    failures = _failures(
        compare_views(cand, base, expected), "parity.value_usd_current"
    )

    by_severity = {r.severity: r for r in failures}
    assert set(by_severity) == {Severity.INFO, Severity.ERROR}
    info = by_severity[Severity.INFO]
    assert info.message.startswith("explained (PSI measure change): 1 ")
    assert _details(info)["donor_name"].tolist() == ["France"]
    assert _details(by_severity[Severity.ERROR])["donor_name"].tolist() == ["Germany"]


def test_expected_entries_for_other_views_are_ignored(make_view: MakeView) -> None:
    """An entry for another view does not explain a delta."""
    base = make_view(VIEW, [_row()])
    cand = make_view(VIEW, [_row(value=2 * BILLION)], options=base.options)
    expected = [ExpectedDelta(view="gender_view", reason="other view")]

    failure = _only_failure(
        compare_views(cand, base, expected), "parity.value_usd_current"
    )

    assert failure.severity is Severity.ERROR


@pytest.mark.parametrize(("last_shift", "differs"), [(0.0, False), (1.0, True)])
def test_donor_totals_floor_scales_with_rows(
    make_view: MakeView, last_shift: float, differs: bool
) -> None:
    """Three rows summed allow ROUNDING_UNIT / 2 x (3 + 1) = 200 units (+ 1e-6 rel)."""
    indicators = ["Total ODA", "Core ODA", "Bilateral"]
    base = make_view(VIEW, [_row(value=1_000.0, indicator=i) for i in indicators])
    shifts = [100.0, 100.0, last_shift]  # each row within its own 100-unit floor
    cand = make_view(
        VIEW,
        [
            _row(value=1_000.0 + shift, indicator=i)
            for i, shift in zip(indicators, shifts, strict=True)
        ],
        options=base.options,
    )

    results = compare_views(cand, base, [])

    assert not _failures(results, "parity.value_usd_current")
    assert bool(_failures(results, "parity.donor_totals")) is differs


def test_donor_totals_follow_explained_rows(make_view: MakeView) -> None:
    """A (donor, year) total whose row deltas are all explained is explained too."""
    base = make_view(VIEW, [_row(), _row(indicator="Core ODA")])
    cand = make_view(
        VIEW,
        [_row(value=2 * BILLION), _row(indicator="Core ODA")],
        options=base.options,
    )
    expected = [
        ExpectedDelta(view=VIEW, reason="revised", indicators=frozenset({"Total ODA"}))
    ]

    totals = _only_failure(compare_views(cand, base, expected), "parity.donor_totals")

    assert totals.severity is Severity.INFO
    assert "follows row-level deltas: revised" in totals.message


def test_explained_one_sided_keys_explain_row_count(make_view: MakeView) -> None:
    """New keys matched by a new_in_candidate entry explain the row count change."""
    base = make_view(VIEW, [_row()])
    cand = make_view(VIEW, [_row(), _row("Italy")], options=base.options)
    expected = [
        ExpectedDelta(
            view=VIEW,
            reason="Italy added",
            kind=DeltaKind.NEW_IN_CANDIDATE,
            donors=frozenset({"Italy"}),
        )
    ]

    results = compare_views(cand, base, expected)

    assert _only_failure(results, "parity.new_in_candidate").severity is Severity.INFO
    row_count = _only_failure(results, "parity.row_count")
    assert row_count.severity is Severity.INFO
    assert "Italy added" in row_count.message


def test_options_differences(make_view: MakeView) -> None:
    """A new donor in the options is an ERROR unless an entry explains it."""
    base = make_view(VIEW, [_row()])
    cand = make_view(
        VIEW, [_row()], options={**base.options, "donor_name": ["France", "Italy"]}
    )
    cand.options["year"] = {**cand.options["year"], "end": 2099}

    failures = _failures(compare_views(cand, base, []), "parity.options")
    assert len(failures) == 1
    assert "donor_name new_in_candidate 'Italy'" in failures[0].message
    assert "year.end changed" in failures[0].message

    expected = [
        ExpectedDelta(
            view=VIEW,
            reason="Italy added",
            kind=DeltaKind.NEW_IN_CANDIDATE,
            donors=frozenset({"Italy"}),
        )
    ]
    severities = {
        r.severity
        for r in _failures(compare_views(cand, base, expected), "parity.options")
    }
    assert severities == {Severity.INFO, Severity.ERROR}


@pytest.mark.parametrize(
    ("kind", "path", "edit"),
    [
        (DeltaKind.VALUE, "year.start", lambda o: o["year"].update(start=1900)),
        (DeltaKind.NEW_IN_CANDIDATE, "note_year", lambda o: o.update(note_year=2023)),
        (DeltaKind.MISSING_IN_CANDIDATE, "year.base", lambda o: o["year"].pop("base")),
    ],
)
def test_options_paths_explain_changes_and_keys(
    make_view: MakeView, kind: DeltaKind, path: str, edit
) -> None:
    """A changed scalar, a new key and a removed key are explained by an entry's path."""
    base = make_view(VIEW, [_row()])
    options = {**base.options, "year": dict(base.options["year"])}
    edit(options)
    cand = make_view(VIEW, [_row()], options=options)
    assert _only_failure(compare_views(cand, base, []), "parity.options").severity is (
        Severity.ERROR
    )

    wrong = ExpectedDelta(view=VIEW, reason="r", kind=kind, paths=frozenset({"other"}))
    right = ExpectedDelta(view=VIEW, reason="ok", kind=kind, paths=frozenset({path}))
    unpathed = ExpectedDelta(view=VIEW, reason="any", kind=kind)
    assert (
        _only_failure(
            compare_views(cand, base, [wrong, unpathed]), "parity.options"
        ).severity
        is Severity.ERROR
    )
    result = _only_failure(compare_views(cand, base, [right]), "parity.options")
    assert result.severity is Severity.INFO
    assert result.message.startswith("explained (ok)")


def test_options_list_items_still_match_by_dimension(make_view: MakeView) -> None:
    """A donor list item is explained by donors, not by a path entry."""
    base = make_view(VIEW, [_row()])
    cand = make_view(
        VIEW, [_row()], options={**base.options, "donor_name": ["France", "Italy"]}
    )
    by_path = ExpectedDelta(
        view=VIEW,
        reason="r",
        kind=DeltaKind.NEW_IN_CANDIDATE,
        paths=frozenset({"donor_name.Italy"}),
    )
    assert (
        _only_failure(compare_views(cand, base, [by_path]), "parity.options").severity
        is Severity.ERROR
    )


def test_details_capped_largest_first(make_view: MakeView) -> None:
    """Details hold at most MAX_DETAIL_ROWS example rows, largest delta first."""
    n = MAX_DETAIL_ROWS + 10
    base = make_view(VIEW, [_row(f"Donor {i}") for i in range(n)])
    cand = make_view(
        VIEW,
        [_row(f"Donor {i}", value=BILLION + 10_000 * (i + 1)) for i in range(n)],
        options=base.options,
    )

    failure = _only_failure(compare_views(cand, base, []), "parity.value_usd_current")

    assert failure.message.startswith(f"{n} value_usd_current diffs")
    assert len(_details(failure)) == MAX_DETAIL_ROWS
    assert _details(failure)["donor_name"].iat[0] == f"Donor {n - 1}"


def test_duplicate_keys_reported(make_view: MakeView) -> None:
    """Repeated keys are reported and dropped before comparing."""
    base = make_view(VIEW, [_row()])
    cand = make_view(VIEW, [_row(), _row()], options=base.options)

    results = compare_views(cand, base, [])

    assert "candidate 1" in _only_failure(results, "parity.unique_keys").message
    assert not _failures(results, "parity.value_usd_current")


def test_different_views_rejected(make_view: MakeView) -> None:
    """Comparing two different views is a programming error."""
    financing = make_view(VIEW, [_row()])
    gender = make_view(
        "gender_view",
        [
            {
                "year": 2024,
                "donor_name": "France",
                "recipient_name": "Mali",
                "indicator_name": "Main target",
                "value_usd_current": 1.0,
            }
        ],
    )

    with pytest.raises(ValueError, match="Cannot compare"):
        compare_views(financing, gender, [])


def test_run_parity_flat(tmp_path: Path, make_view: MakeView) -> None:
    """Flat sources are compared whole."""
    base = make_view(VIEW, [_row()])
    cand = make_view(VIEW, [_row(value=2 * BILLION)], options=base.options)
    write_flat(base, tmp_path / "baseline" / VIEW)
    write_flat(cand, tmp_path / "candidate" / VIEW)

    results = run_parity(
        VIEW, tmp_path / "candidate" / VIEW, tmp_path / "baseline" / VIEW, []
    )

    assert _failures(results, "parity.value_usd_current")
    assert not any(r.check == "parity.partitions" for r in results)


def test_run_parity_hive_self(
    tmp_path: Path, make_view: MakeView, sector_rows: list[dict]
) -> None:
    """A partitioned view compared with itself has no deltas."""
    source = write_hive(
        make_view("sectors_view", sector_rows), tmp_path / "sectors_view"
    )

    results = run_parity("sectors_view", source, source, [])

    assert not _failures(results)
    partitions = next(r for r in results if r.check == "parity.partitions")
    assert partitions.message == "same 2 partitions on both sides"


def test_run_parity_hive_one_sided_partition(
    tmp_path: Path, make_view: MakeView, sector_rows: list[dict]
) -> None:
    """A partition on one side only is a delta, and its keys are one-sided keys."""
    base = make_view("sectors_view", sector_rows)
    cand = make_view(
        "sectors_view",
        [r for r in sector_rows if r["recipient_name"] == "Kenya"],
        options=base.options,
    )
    base_dir = write_hive(base, tmp_path / "baseline" / "sectors_view")
    cand_dir = write_hive(cand, tmp_path / "candidate" / "sectors_view")

    results = run_parity("sectors_view", cand_dir, base_dir, [])

    partitions = _only_failure(results, "parity.partitions")
    assert partitions.message.startswith("1 only in baseline (of 2): mali")
    missing = _only_failure(results, "parity.missing_in_candidate")
    assert _details(missing)["recipient_name"].tolist() == ["Mali", "Mali"]
    assert not _failures(results, "parity.value_usd_current")


def test_run_parity_layout_mismatch(
    tmp_path: Path, make_view: MakeView, sector_rows: list[dict]
) -> None:
    """A flat source cannot be compared with a partitioned one."""
    view = make_view("sectors_view", sector_rows)
    flat = write_flat(view, tmp_path / "flat" / "sectors_view")
    hive = write_hive(view, tmp_path / "hive" / "sectors_view")

    with pytest.raises(ValueError, match="single-file source"):
        run_parity("sectors_view", flat, hive, [])


def test_max_abs_entry_explains_small_absolute_deltas(make_view: MakeView) -> None:
    """max_abs is matched against the delta's |diff| in the column's unit."""
    base = make_view(VIEW, [_row(value=1_000_000), _row("Germany", value=1_000_000)])
    cand = make_view(
        VIEW,
        [_row(value=1_005_000), _row("Germany", value=1_020_000)],
        options=base.options,
    )
    expected = [
        ExpectedDelta(
            view=VIEW,
            reason="rounding",
            columns=frozenset({"value_usd_current"}),
            max_abs=11_000,
        )
    ]

    failures = _failures(
        compare_views(cand, base, expected), "parity.value_usd_current"
    )

    by_severity = {r.severity: r for r in failures}
    assert _details(by_severity[Severity.INFO])["donor_name"].tolist() == ["France"]
    assert _details(by_severity[Severity.ERROR])["donor_name"].tolist() == ["Germany"]


def test_options_provenance_is_not_compared(make_view: MakeView) -> None:
    """The root provenance key is build metadata, so parity leaves it out."""
    base = make_view(VIEW, [_row()])
    cand = make_view(
        VIEW,
        [_row()],
        options={**base.options, "provenance": {"tables": {"dac1": {"token": "x"}}}},
    )
    assert not _failures(compare_views(cand, base, []), "parity.options")
