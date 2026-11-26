"""Anomalies: year-on-year changes in a view's key total that break with a donor's history.

Results are WARNINGs, since an unusual year is worth a look but not a block. Two cases
are ERRORs: a view with no key-total rows at all (the check would otherwise pass on
nothing), and a critical donor whose end-year key total moved by more than
MAX_CRITICAL_DONOR_CHANGE with no "anomaly" entry to explain it (a units slip in one
donor, carried consistently into its groups, passes every other blocking check).
``run_anomalies(view)`` reads only the key-total rows (below), so for sectors the
"oda-eligible-countries" recipient partition is enough. The whole view also works.

Only material moves by reporting donors are flagged (see the constants), and a move that
an expected_deltas.toml entry of kind "anomaly" explains is reported as INFO with its
reason, so a clean build stays quiet and a new warning means something.

Key totals, in value_usd_current per donor and year:

- financing: Total ODA, one series per type (flows and grant equivalents differ in level);
- recipients, gender, sectors: everything to "ODA eligible countries", summed over
  indicators (and sectors).
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.data.config import ODA_ELIGIBLE, TOTAL_ODA
from src.data.validation.contracts import PRIMARY_VALUE_COLUMN, build_result
from src.data.validation.expected import DeltaKind, ExpectedDelta, find_explanation
from src.data.validation.io import LoadedView
from src.data.validation.models import CheckResult, Severity
from src.data.validation.views import AGGREGATE_DONORS, CRITICAL_DONORS

# A year-on-year change this many standard deviations from the donor's mean change is flagged.
Z_SCORE_THRESHOLD: float = 3.0
# Years of history before the latest year needed to judge it.
MIN_HISTORY_YEARS: int = 4
# Only donors with at least this much (current USD units) in the latest or the previous
# year are judged: a small donor's total swings several-fold with one loan or project
# (Kuwait, Malta), which says nothing about the build.
MIN_MATERIAL_UNITS: float = 1e9
# Only changes of at least this size (relative) are flagged: a donor with a steady
# history gets a large z from an ordinary 20-40% policy swing. A halving, or a rise by
# half, is worth a look whatever the history.
MIN_FLAGGED_CHANGE: float = 0.5
# A critical donor's end-year key total below (1 - this) or above 1 / (1 - this) times
# the year before blocks: a tenfold move is a units slip, not policy. The largest real
# move so far, the US cut in 2025 financing, was -56%.
MAX_CRITICAL_DONOR_CHANGE: float = 0.9
CRITICAL_RATIO_MIN: float = 1 - MAX_CRITICAL_DONOR_CHANGE
CRITICAL_RATIO_MAX: float = 1 / CRITICAL_RATIO_MIN


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


def _judged(yearly: pd.Series, latest: int) -> bool:
    """Whether a series is large enough in the latest or previous year to judge."""
    recent = yearly.reindex([latest - 1, latest]).abs()
    return bool((recent >= MIN_MATERIAL_UNITS).any())


def _flag_series(totals: pd.DataFrame, series_cols: list[str]) -> list[dict]:
    """Reporting donors' series whose latest-year change is both unusual and material."""
    latest = int(totals["year"].max())
    flagged = []
    for series, group in totals.groupby(series_cols, observed=True):
        labels = dict(zip(series_cols, series, strict=True))
        if labels["donor_name"] in AGGREGATE_DONORS:
            continue  # a group moves with its members, which are judged themselves
        yearly = group.set_index("year")[PRIMARY_VALUE_COLUMN].sort_index()
        if not _judged(yearly, latest):
            continue
        stats = _latest_change_z(yearly, latest)
        if (
            stats is not None
            and abs(stats["z"]) > Z_SCORE_THRESHOLD
            and abs(stats["change"]) >= MIN_FLAGGED_CHANGE
        ):
            flagged.append({**labels, "year": latest, **stats})
    return flagged


def _explain_flags(
    flagged: pd.DataFrame, view: str, expected: Sequence[ExpectedDelta]
) -> pd.Series:
    """The reason an expected "anomaly" entry gives each flagged series, or None."""
    reasons = []
    for row in flagged.itertuples(index=False):
        entry = find_explanation(
            list(expected),
            view=view,
            kind=DeltaKind.ANOMALY,
            year=int(row.year),
            donor=row.donor_name,
            indicator=getattr(row, "type", None),
            rel_diff=float(row.change),
        )
        reasons.append(None if entry is None else entry.reason)
    return pd.Series(reasons, index=flagged.index, dtype=object)


def check_yoy_anomalies(
    view: LoadedView, expected: Sequence[ExpectedDelta] = ()
) -> list[CheckResult]:
    """Flag reporting donors whose latest-year change is unusual and material.

    Unusual: |z| > Z_SCORE_THRESHOLD against MIN_HISTORY_YEARS or more of history.
    Material: the donor had MIN_MATERIAL_UNITS in the latest or the previous year, and the
    change is at least MIN_FLAGGED_CHANGE. The latest year is the last year in the view.
    For financing, an anomaly entry's ``indicators`` filter matches the type.

    Args:
        view: The view, or for sectors its "oda-eligible-countries" partition.
        expected: Expected deltas; "anomaly" entries for this view explain flags.

    Returns:
        A WARNING for unexplained flags (or a pass), one INFO per explaining reason, or an
        ERROR when the view has no key-total rows.
    """
    name = view.spec.name
    key_total = KEY_TOTALS[name]
    totals = key_total_series(view)
    if totals.empty:
        column, value = key_total.where
        return [
            build_result(
                check="anomalies.yoy",
                view=name,
                failures=1,
                severity=Severity.ERROR,
                passed_message="",
                failed_message=f"No {column} = {value!r} rows: nothing to check",
            )
        ]

    series_cols = list(key_total.series)
    details = pd.DataFrame(_flag_series(totals, series_cols))
    if not details.empty:
        details = details.iloc[details["z"].abs().argsort()[::-1]]
        details = details.assign(reason=_explain_flags(details, name, expected))
    unexplained = details.loc[details["reason"].isna()] if len(details) else details
    criteria = (
        f"|z| > {Z_SCORE_THRESHOLD}, |change| >= {MIN_FLAGGED_CHANGE:.0%}, "
        f"donors with >= {MIN_MATERIAL_UNITS:.0e} units"
    )
    results = [
        build_result(
            check="anomalies.yoy",
            view=name,
            failures=len(unexplained),
            severity=Severity.WARNING,
            passed_message=f"No unexplained latest-year change in {key_total.label} "
            f"({criteria})",
            failed_message=(
                f"{len(unexplained)} series with an unusual latest-year change in "
                f"{key_total.label} ({criteria})"
            ),
            details=unexplained.drop(columns="reason", errors="ignore"),
        )
    ]
    if len(details):
        for reason, group in details.dropna(subset=["reason"]).groupby("reason"):
            donors = ", ".join(group["donor_name"].astype(str))
            results.append(
                CheckResult(
                    check="anomalies.yoy",
                    view=name,
                    passed=False,
                    severity=Severity.INFO,
                    message=f"explained ({reason}): {donors}",
                    details=group.drop(columns="reason").reset_index(drop=True),
                    blocking=False,
                )
            )
    return results


def _critical_changes(
    totals: pd.DataFrame, series_cols: list[str], end: int
) -> pd.DataFrame:
    """Critical donors' end-year key total against the year before, per series.

    Series without both years, or with a zero previous year, are left out.

    Returns:
        Columns: the series columns, year, previous, latest, ratio, change.
    """
    critical = totals.loc[totals["donor_name"].isin(CRITICAL_DONORS)]
    wide = critical.pivot_table(
        index=series_cols,
        columns="year",
        values=PRIMARY_VALUE_COLUMN,
        observed=True,
    )
    if end not in wide.columns or end - 1 not in wide.columns:
        return pd.DataFrame(
            columns=[*series_cols, "year", "previous", "latest", "ratio", "change"]
        )
    pair = wide[[end - 1, end]].dropna()
    pair = pair.loc[pair[end - 1] != 0]
    ratio = pair[end] / pair[end - 1]
    return pd.DataFrame(
        {
            "year": end,
            "previous": pair[end - 1],
            "latest": pair[end],
            "ratio": ratio,
            "change": ratio - 1,
        }
    ).reset_index()


def check_critical_donor_change(
    view: LoadedView, expected: Sequence[ExpectedDelta] = ()
) -> list[CheckResult]:
    """Block a critical donor whose end-year key total moved tenfold or more.

    The end year is the spec's. A move outside [CRITICAL_RATIO_MIN, CRITICAL_RATIO_MAX]
    times the year before is an ERROR unless an "anomaly" entry explains it (as for
    check_yoy_anomalies; max_rel bounds the change). A view with no key-total rows is
    left to check_yoy_anomalies.

    Args:
        view: The view, or for sectors its "oda-eligible-countries" partition.
        expected: Expected deltas; "anomaly" entries for this view explain moves.

    Returns:
        One ERROR result (a pass when nothing moved that far).
    """
    name = view.spec.name
    key_total = KEY_TOTALS[name]
    totals = key_total_series(view)
    if totals.empty:
        return []
    series_cols = list(key_total.series)
    end = view.spec.time["end"]
    changes = _critical_changes(totals, series_cols, end)
    moved = changes.loc[
        ~changes["ratio"].between(CRITICAL_RATIO_MIN, CRITICAL_RATIO_MAX)
    ]
    if len(moved):
        moved = moved.assign(reason=_explain_flags(moved, name, expected))
        moved = moved.loc[moved["reason"].isna()].drop(columns="reason")
    band = f"[{CRITICAL_RATIO_MIN:.2g}x, {CRITICAL_RATIO_MAX:.2g}x]"
    listed = ", ".join(
        f"{r.donor_name} {r.ratio:.3g}x" for r in moved.itertuples(index=False)
    )
    return [
        build_result(
            check="anomalies.critical_donor_change",
            view=name,
            failures=len(moved),
            severity=Severity.ERROR,
            passed_message=(
                f"Every critical donor's {key_total.label} in {end} within {band} of "
                f"{end - 1} ({len(changes)} series)"
            ),
            failed_message=(
                f"{len(moved)} critical donor series moved beyond {band} from "
                f"{end - 1} to {end} with no anomaly entry: {listed}"
            ),
            details=moved,
        )
    ]


def run_anomalies(
    view: LoadedView, expected: Sequence[ExpectedDelta] = ()
) -> list[CheckResult]:
    """Run every anomaly check on a view.

    Args:
        view: The whole view, or for sectors just its "oda-eligible-countries" partition.
        expected: Expected deltas; "anomaly" entries explain flags.

    Returns:
        WARNING and INFO results; ERRORs when there is nothing to check or a critical
        donor moved tenfold.
    """
    return [
        *check_yoy_anomalies(view, expected),
        *check_critical_donor_change(view, expected),
    ]
