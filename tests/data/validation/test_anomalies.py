"""Tests for the year-on-year anomaly check."""

from src.data.config import ODA_ELIGIBLE, TOTAL_ODA
from src.data.validation.anomalies import (
    MIN_HISTORY_YEARS,
    key_total_series,
    run_anomalies,
)
from src.data.validation.models import Severity
from tests.data.validation.conftest import MakeView

FIRST_YEAR = 2015
# Steady ~5% growth with some noise, so the history has a small but non-zero spread.
STEADY_GROWTH = (100.0, 105.0, 111.0, 116.0, 122.0, 128.0)


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


def test_steady_series_passes(make_view: MakeView) -> None:
    """A donor growing as usual raises nothing."""
    view = make_view("recipients_view", _recipient_rows("France", STEADY_GROWTH))
    [result] = run_anomalies(view)
    assert result.passed


def test_jump_is_flagged_as_warning(make_view: MakeView) -> None:
    """A latest-year jump far outside the donor's history is a non-blocking WARNING."""
    rows = _recipient_rows("France", (*STEADY_GROWTH[:-1], 400.0))
    rows += _recipient_rows("Germany", STEADY_GROWTH)
    [result] = run_anomalies(make_view("recipients_view", rows))
    assert not result.passed
    assert result.severity is Severity.WARNING and not result.blocking
    assert result.details["donor_name"].tolist() == ["France"]
    assert result.details["z"].iloc[0] > 3


def test_short_history_is_not_judged(make_view: MakeView) -> None:
    """Fewer than MIN_HISTORY_YEARS before the latest year: no verdict."""
    values = (*STEADY_GROWTH[: MIN_HISTORY_YEARS - 1], 400.0)
    [result] = run_anomalies(
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
    [result] = run_anomalies(make_view("financing_view", rows))
    assert result.details[["donor_name", "type"]].values.tolist() == [
        ["France", "Flows"]
    ]
