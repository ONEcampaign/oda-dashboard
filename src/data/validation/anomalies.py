"""Anomalies: year-on-year changes in a view's key total that break with a donor's history.

Results are WARNINGs, since an unusual year is worth a look but not a block.
``run_anomalies(view)`` reads only the key-total rows (below), so for sectors the
"oda-eligible-countries" recipient partition is enough. The whole view also works.

Key totals, in value_usd_current per donor and year:

- financing: Total ODA, one series per type (flows and grant equivalents differ in level);
- recipients, gender, sectors: everything to "ODA eligible countries", summed over
  indicators (and sectors).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.data.config import ODA_ELIGIBLE, TOTAL_ODA
from src.data.validation.contracts import PRIMARY_VALUE_COLUMN, build_result
from src.data.validation.io import LoadedView
from src.data.validation.models import CheckResult, Severity

# A year-on-year change this many standard deviations from the donor's mean change is flagged.
Z_SCORE_THRESHOLD: float = 3.0
# Years of history before the latest year needed to judge it.
MIN_HISTORY_YEARS: int = 4


@dataclass(frozen=True)
class _KeyTotal:
    """The rows a view's key total sums, and the columns that split it into series."""

    label: str
    where: tuple[str, str]
    series: tuple[str, ...]


KEY_TOTALS: dict[str, _KeyTotal] = {
    "financing_view": _KeyTotal(
        TOTAL_ODA, ("indicator_name", TOTAL_ODA), ("donor_name", "type")
    ),
    "recipients_view": _KeyTotal(
        f"ODA to {ODA_ELIGIBLE}", ("recipient_name", ODA_ELIGIBLE), ("donor_name",)
    ),
    "gender_view": _KeyTotal(
        f"Screened ODA to {ODA_ELIGIBLE}",
        ("recipient_name", ODA_ELIGIBLE),
        ("donor_name",),
    ),
    "sectors_view": _KeyTotal(
        f"Sector-allocable ODA to {ODA_ELIGIBLE}",
        ("recipient_name", ODA_ELIGIBLE),
        ("donor_name",),
    ),
}


def key_total_series(view: LoadedView) -> pd.DataFrame:
    """A view's key total per series and year.

    Returns:
        Columns: the series columns, year, value_usd_current.
    """
    key_total = KEY_TOTALS[view.spec.name]
    column, value = key_total.where
    rows = view.data.loc[view.data[column] == value]
    return (
        rows.groupby([*key_total.series, "year"], observed=True)[PRIMARY_VALUE_COLUMN]
        .sum()
        .reset_index()
    )


def _latest_change_z(yearly: pd.Series, latest: int) -> dict | None:
    """The latest year's change against the series' history, or None if it can't be judged.

    Args:
        yearly: Values indexed by year, sorted.
        latest: The year to judge.

    Returns:
        change, mean_change, std_change and z for the latest year, or None when the series
        lacks the latest year, the year before it, MIN_HISTORY_YEARS of history, or any
        variation in its history.
    """
    if latest not in yearly.index or latest - 1 not in yearly.index:
        return None
    history = yearly.loc[yearly.index < latest]
    if len(history) < MIN_HISTORY_YEARS:
        return None
    # A change from 0 is infinite: not a usable reference.
    changes = history.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    mean, std = changes.mean(), changes.std()
    previous = yearly.loc[latest - 1]
    if pd.isna(std) or std == 0 or previous == 0:
        return None
    change = (yearly.loc[latest] - previous) / previous
    return {
        "change": change,
        "mean_change": mean,
        "std_change": std,
        "z": (change - mean) / std,
    }


def check_yoy_anomalies(view: LoadedView) -> list[CheckResult]:
    """Flag series whose latest-year change has |z| > Z_SCORE_THRESHOLD (WARNING).

    The latest year is the last year in the view. Each series needs MIN_HISTORY_YEARS of
    history before it.
    """
    key_total = KEY_TOTALS[view.spec.name]
    totals = key_total_series(view)
    flagged = []
    if not totals.empty:
        latest = int(totals["year"].max())
        series_cols = list(key_total.series)
        for series, group in totals.groupby(series_cols, observed=True):
            yearly = group.set_index("year")[PRIMARY_VALUE_COLUMN].sort_index()
            stats = _latest_change_z(yearly, latest)
            if stats is not None and abs(stats["z"]) > Z_SCORE_THRESHOLD:
                flagged.append({**dict(zip(series_cols, series, strict=True)), **stats})
    details = pd.DataFrame(flagged)
    if flagged:
        details = details.iloc[details["z"].abs().argsort()[::-1]]
    return [
        build_result(
            check="anomalies.yoy",
            view=view.spec.name,
            failures=len(flagged),
            severity=Severity.WARNING,
            passed_message=(
                f"No unusual latest-year change in {key_total.label} "
                f"(|z| <= {Z_SCORE_THRESHOLD})"
            ),
            failed_message=(
                f"{len(flagged)} series with an unusual latest-year change in "
                f"{key_total.label} (|z| > {Z_SCORE_THRESHOLD})"
            ),
            details=details,
        )
    ]


def run_anomalies(view: LoadedView) -> list[CheckResult]:
    """Run every anomaly check on a view.

    Args:
        view: The whole view, or for sectors just its "oda-eligible-countries" partition.

    Returns:
        WARNING results only.
    """
    return check_yoy_anomalies(view)
