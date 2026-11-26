"""Tests for the year-on-year anomaly check."""

from src.data.config import DAC_COUNTRIES_NAME, ODA_ELIGIBLE, TOTAL_ODA
from src.data.validation.anomalies import (
    CRITICAL_RATIO_MAX,
    CRITICAL_RATIO_MIN,
    MIN_FLAGGED_CHANGE,
    MIN_HISTORY_YEARS,
    MIN_MATERIAL_UNITS,
    check_critical_donor_change,
    check_yoy_anomalies,
    key_total_series,
    run_anomalies,
)
from src.data.validation.expected import DeltaKind, ExpectedDelta
from src.data.validation.models import Severity
from src.data.validation.views import get_spec
from tests.data.validation.conftest import MakeView

FIRST_YEAR = 2015
# Steady ~5% growth with some noise, so the history has a small but non-zero spread; in
# units of 1e8, so every series is material.
_UNIT = 1e8
STEADY_GROWTH = tuple(v * _UNIT for v in (100.0, 105.0, 111.0, 116.0, 122.0, 128.0))
LATEST = FIRST_YEAR + len(STEADY_GROWTH) - 1


def _recipient_rows(donor: str, values: tuple[float, ...]) -> list[dict]:
    """A donor's ODA to ODA eligible countries, one year per value, split over two
    indicators, plus a country row the key total must ignore."""
    rows = []
    for offset, value in enumerate(values):
        year = FIRST_YEAR + offset
        for indicator in ("Bilateral", "Imputed multilateral"):
            rows.append(
                {
                    "year": year,
                    "donor_name": donor,
                    "recipient_name": ODA_ELIGIBLE,
                    "indicator_name": indicator,
                    "value_usd_current": value / 2,
                }
            )
        rows.append(
            {
                "year": year,
                "donor_name": donor,
                "recipient_name": "Kenya",
                "indicator_name": "Bilateral",
                "value_usd_current": 1e9,
            }
        )
    return rows


def test_key_total_sums_indicators_at_oda_eligible(make_view: MakeView) -> None:
    """The recipients key total is ODA eligible countries summed over indicators."""
    view = make_view("recipients_view", _recipient_rows("France", (10.0, 20.0)))
    totals = key_total_series(view)
    assert totals["value_usd_current"].tolist() == [10.0, 20.0]


def _jump(donor: str, latest: float) -> list[dict]:
    """A donor with steady history and the given latest-year value."""
    return _recipient_rows(donor, (*STEADY_GROWTH[:-1], latest))


def test_groups_are_not_judged(make_view: MakeView) -> None:
    """A donor group's jump is left to its members."""
    view = make_view("recipients_view", _jump(DAC_COUNTRIES_NAME, 400.0 * _UNIT))
    [result] = check_yoy_anomalies(view)
    assert result.passed


def test_small_donors_are_not_judged(make_view: MakeView) -> None:
    """A donor below MIN_MATERIAL_UNITS in both recent years is left alone."""
    scale = MIN_MATERIAL_UNITS / (STEADY_GROWTH[-1] * 10)
    values = tuple(v * scale for v in (*STEADY_GROWTH[:-1], 400.0 * _UNIT))
    [result] = check_yoy_anomalies(
        make_view("recipients_view", _recipient_rows("A", values))
    )
    assert result.passed


def test_small_changes_are_not_flagged(make_view: MakeView) -> None:
    """A change under MIN_FLAGGED_CHANGE passes even with a large z."""
    latest = STEADY_GROWTH[-2] * (1 + MIN_FLAGGED_CHANGE * 0.9)
    [result] = check_yoy_anomalies(
        make_view("recipients_view", _jump("France", latest))
    )
    assert result.passed


def test_expected_anomaly_is_explained(make_view: MakeView) -> None:
    """An "anomaly" entry within max_rel turns the flag into an INFO with its reason."""
    rows = _jump("France", 400.0 * _UNIT)
    entry = ExpectedDelta(
        view="recipients_view",
        reason="France tripled its aid",
        kind=DeltaKind.ANOMALY,
        years=frozenset({LATEST}),
        donors=frozenset({"France"}),
        max_rel=3.0,
    )
    warning, info = check_yoy_anomalies(make_view("recipients_view", rows), [entry])
    assert warning.passed
    assert info.severity is Severity.INFO and not info.passed
    assert info.message.startswith("explained (France tripled its aid)")
    assert entry.hits == 1

    tight = ExpectedDelta(
        view="recipients_view",
        reason="r",
        kind=DeltaKind.ANOMALY,
        donors=frozenset({"France"}),
        max_rel=0.5,
    )
    [result] = check_yoy_anomalies(make_view("recipients_view", rows), [tight])
    assert not result.passed and result.severity is Severity.WARNING


def test_no_key_total_rows_is_an_error(make_view: MakeView) -> None:
    """A view without its key-total rows fails instead of passing on nothing."""
    rows = [
        r
        for r in _recipient_rows("France", STEADY_GROWTH)
        if r["recipient_name"] != ODA_ELIGIBLE
    ]
    [result] = check_yoy_anomalies(make_view("recipients_view", rows))
    assert not result.passed
    assert result.severity is Severity.ERROR and result.blocking


def test_steady_series_passes(make_view: MakeView) -> None:
    """A donor growing as usual raises nothing."""
    view = make_view("recipients_view", _recipient_rows("France", STEADY_GROWTH))
    [result] = check_yoy_anomalies(view)
    assert result.passed


def test_jump_is_flagged_as_warning(make_view: MakeView) -> None:
    """A latest-year jump far outside the donor's history is a non-blocking WARNING."""
    rows = _recipient_rows("France", (*STEADY_GROWTH[:-1], 400.0 * _UNIT))
    rows += _recipient_rows("Germany", STEADY_GROWTH)
    [result] = check_yoy_anomalies(make_view("recipients_view", rows))
    assert not result.passed
    assert result.severity is Severity.WARNING and not result.blocking
    assert result.details["donor_name"].tolist() == ["France"]
    assert result.details["z"].iloc[0] > 3


def test_short_history_is_not_judged(make_view: MakeView) -> None:
    """Fewer than MIN_HISTORY_YEARS before the latest year: no verdict."""
    values = (*STEADY_GROWTH[: MIN_HISTORY_YEARS - 1], 400.0 * _UNIT)
    [result] = check_yoy_anomalies(
        make_view("recipients_view", _recipient_rows("France", values))
    )
    assert result.passed


def test_financing_series_per_type(make_view: MakeView) -> None:
    """Financing judges Total ODA per donor and type; other indicators are ignored."""
    rows = [
        {
            "year": FIRST_YEAR + offset,
            "donor_name": "France",
            "indicator_name": indicator,
            "type": flow_type,
            "value_usd_current": value * (4 if last and flow_type == "Flows" else 1),
        }
        for offset, value in enumerate(STEADY_GROWTH)
        for last in [offset == len(STEADY_GROWTH) - 1]
        for indicator in (TOTAL_ODA, "Debt relief")
        for flow_type in ("Flows", "Grant equivalents")
    ]
    [result] = check_yoy_anomalies(make_view("financing_view", rows))
    assert result.details[["donor_name", "type"]].values.tolist() == [
        ["France", "Flows"]
    ]


RECIPIENTS_END = get_spec("recipients_view").time["end"]


def _two_years(donor: str, previous: float, latest: float) -> list[dict]:
    """A donor's key total in the recipients view's last two years."""
    return [
        {
            "year": year,
            "donor_name": donor,
            "recipient_name": ODA_ELIGIBLE,
            "indicator_name": "Bilateral",
            "value_usd_current": value,
        }
        for year, value in ((RECIPIENTS_END - 1, previous), (RECIPIENTS_END, latest))
    ]


def test_critical_donor_units_slip_blocks(make_view: MakeView) -> None:
    """A critical donor's end year scaled by 1e-3 is a blocking ERROR."""
    view = make_view("recipients_view", _two_years("United States", 6e10, 6e7))
    [result] = check_critical_donor_change(view)
    assert not result.passed and result.blocking
    assert result.details["donor_name"].tolist() == ["United States"]


def test_critical_donor_real_cut_passes(make_view: MakeView) -> None:
    """A halving, like the US cut in 2025, and the band's edges pass."""
    rows = [
        *_two_years("United States", 6e10, 6e10 * 0.44),
        *_two_years("France", 1e10, 1e10 * CRITICAL_RATIO_MIN),
        *_two_years("Germany", 1e10, 1e10 * CRITICAL_RATIO_MAX),
    ]
    [result] = check_critical_donor_change(make_view("recipients_view", rows))
    assert result.passed


def test_tenfold_rise_blocks_but_not_other_donors(make_view: MakeView) -> None:
    """A tenfold-plus rise blocks too; donors outside CRITICAL_DONORS are not judged."""
    rows = [
        *_two_years("Japan", 1e9, 1e9 * CRITICAL_RATIO_MAX * 1.1),
        *_two_years("Kuwait", 1e9, 1e6),
        *_two_years(DAC_COUNTRIES_NAME, 1e11, 1e8),
    ]
    [result] = check_critical_donor_change(make_view("recipients_view", rows))
    assert result.details["donor_name"].tolist() == ["Japan"]


def test_critical_donor_change_explained_by_entry(make_view: MakeView) -> None:
    """An "anomaly" entry whose max_rel covers the move clears the block."""
    entry = ExpectedDelta(
        view="recipients_view",
        reason="Japan reclassified its loans",
        kind=DeltaKind.ANOMALY,
        years=frozenset({RECIPIENTS_END}),
        donors=frozenset({"Japan"}),
        max_rel=0.995,
    )
    view = make_view("recipients_view", _two_years("Japan", 1e10, 1e8))
    [result] = check_critical_donor_change(view, [entry])
    assert result.passed and entry.hits == 1


def test_run_anomalies_includes_critical_donor_change(make_view: MakeView) -> None:
    """run_anomalies returns the yoy result and the critical donor result."""
    view = make_view("recipients_view", _two_years("United States", 6e10, 6e7))
    checks = {r.check: r for r in run_anomalies(view)}
    assert checks["anomalies.yoy"].passed  # too little history to judge
    assert not checks["anomalies.critical_donor_change"].passed
