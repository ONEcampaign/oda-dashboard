"""Parity: compare a candidate build of a view against a baseline snapshot.

Every difference is a delta. A delta that an expected_deltas.toml entry explains is
reported as INFO "explained (reason)"; the rest are ERROR. All parity results are
non-blocking (they block only under --strict, which the CLI applies).

Checks, each reported per reason (unexplained, or one result per explaining reason):

- ``parity.row_count``: row counts on each side.
- ``parity.unique_keys``: duplicate keys on either side (compared after dropping them).
- ``parity.partitions``: hive partitions present on one side only (sectors).
- ``parity.missing_in_candidate`` / ``parity.new_in_candidate``: keys on one side only.
- ``parity.value_usd_current``: per-key diffs beyond max(100 units, 1e-6 relative).
- ``parity.other_values``: the other 7 value columns, beyond max(100 units, 0.003
  relative).
- ``parity.shares``: share columns, beyond 1e-4 absolute.
- ``parity.donor_totals``: per (donor, year) totals of value_usd_current, within
  invariants' sum tolerance for the number of rows summed.
- ``parity.options``: options.json differences, root metadata keys
  (OPTIONS_METADATA_KEYS: provenance) left out.

Nulls: null against null is equal; null against a number is a delta, which an entry's
max_abs bounds by the number's absolute value (the null read as 0); max_rel cannot.

Renames: a baseline taken before a column or recipient was renamed is read under the new
names (BASELINE_COLUMN_RENAMES, BASELINE_RECIPIENT_RENAMES), so renamed rows are compared
value by value instead of showing up as one-sided keys or null-vs-number shares. Every
rename applied is reported once, as ``parity.baseline_renames`` (INFO, explained).
"""

from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import chain
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.analysis_tools.naming import slugify
from src.data.config import logger
from src.data.validation.expected import DeltaKind, ExpectedDelta, find_explanation
from src.data.validation.invariants import ROUNDING_UNIT, sum_tolerance
from src.data.validation.io import LoadedView, iter_partitions
from src.data.validation.models import MAX_DETAIL_ROWS, CheckResult, Severity
from src.data.validation.views import ViewSpec, get_spec

USD_CURRENT: str = "value_usd_current"
# The pipeline rounds every value to ROUNDING_UNIT, so two builds of the same underlying
# value can differ by one rounding step. That is the absolute floor for every value column.
VALUE_ABS_TOLERANCE: float = ROUNDING_UNIT
USD_CURRENT_REL_TOLERANCE: float = 1e-6
OTHER_VALUE_REL_TOLERANCE: float = 0.003
SHARE_ABS_TOLERANCE: float = 1e-4

# The dimensions deltas are summarised by, and that expected entries filter on.
SUMMARY_DIMENSIONS: tuple[str, ...] = ("year", "donor_name", "indicator_name")
# How many groups each "by year/donor/indicator" breakdown names in a message.
BREAKDOWN_TOP_N: int = 3
# Partitions between compactions of the running delta summaries (bounds memory).
COMPACT_EVERY: int = 256
PROGRESS_EVERY: int = 1_000
FLAT_PARTITION: str = "all"  # the key iter_partitions gives a flat source

UNEXPLAINED: str = ""  # the reason recorded for a delta no entry explains

_SIDES: tuple[str, str] = ("candidate", "baseline")
_TOTALS_CHECKS: frozenset[str] = frozenset(
    {
        "parity.missing_in_candidate",
        "parity.new_in_candidate",
        "parity.value_usd_current",
    }
)
_SUMMARY_KEYS: list[str] = ["reason", "column", *SUMMARY_DIMENSIONS]
_DIMENSION_LABELS: dict[str, str] = {
    "column": "column",
    "year": "year",
    "donor_name": "donor",
    "indicator_name": "indicator",
}
# options.json entries whose items name a donor, recipient or indicator, for matching.
_OPTION_DIMENSIONS: dict[str, str] = {
    "donor_name": "donor",
    "donor_slugs": "donor",
    "recipient_name": "recipient",
    "recipient_slugs": "recipient",
    "indicator_name": "indicator",
}
# Root options.json keys that describe how a build was made rather than what it shows.
# They differ between any two builds from different releases, so parity skips them;
# cross_view.provenance_consistency checks provenance across views instead.
OPTIONS_METADATA_KEYS: frozenset[str] = frozenset({"provenance"})
_AMOUNT_UNITS: tuple[tuple[float, str], ...] = ((1e9, "bn"), (1e6, "mn"))

# Renames made after the production baseline of 2026-11-20 (one canonical name per
# recipient code, and gender's share named for its denominator). Applied to the baseline
# side only. Delete both maps once the baseline is refreshed past that change; until then
# a rename that finds nothing to rename is simply not reported.
BASELINE_RENAMES_REASON: str = (
    "baseline predates the 2026-11 recipient and column renames; refresh it after merge"
)
BASELINE_COLUMN_RENAMES: dict[str, dict[str, str]] = {
    "gender_view": {"pct_of_total_oda": "pct_of_bilateral_allocable"},
}
BASELINE_RECIPIENT_RENAMES: dict[str, str] = {
    "Southern Asia, unspecified": "South Asia, unspecified",  # 679
    "States Ex-Yugoslavia, unspecified": "States ex-Yugoslavia, unspecified",  # 88
    "Côte d\u2019Ivoire": "Côte d'Ivoire",  # 247
    "Sint Maarten": "Netherlands Antilles",  # 361
    "Palestinian Authority or West Bank and Gaza Strip": "West Bank and Gaza Strip",  # 550
    "China (People\u2019s Republic of)": "China (People's Republic of)",  # 730
    "Democratic People\u2019s Republic of Korea": "Democratic People's Republic of Korea",
    "Lao People\u2019s Democratic Republic": "Lao People's Democratic Republic",  # 745
}
# The same renames as sectors partition slugs, where the slug itself changes.
BASELINE_SLUG_RENAMES: dict[str, str] = {
    slugify(old): slugify(new)
    for old, new in BASELINE_RECIPIENT_RENAMES.items()
    if slugify(old) != slugify(new)
}
RECIPIENT_COLUMN: str = "recipient_name"


# --- Explaining deltas ---------------------------------------------------------------


def _nullable_values(deltas: pd.DataFrame, column: str) -> list:
    """A column's values with missing ones (NaN, NA) as None; all None if absent."""
    if column not in deltas:
        return [None] * len(deltas)
    values = deltas[column]
    return values.astype(object).where(values.notna(), None).tolist()


def _abs_diff(
    diff: float | None, *, baseline: float | None, candidate: float | None
) -> float | None:
    """|diff|; for null against a number, the number's absolute value (null as 0).

    None when both sides are null or the row carries neither side.
    """
    if diff is not None:
        return abs(diff)
    if (baseline is None) == (candidate is None):
        return None
    present = baseline if candidate is None else candidate
    return abs(present)


def _explain(
    deltas: pd.DataFrame,
    *,
    view: str,
    kind: DeltaKind,
    expected: Sequence[ExpectedDelta],
) -> pd.Series:
    """The reason each delta row is expected, or UNEXPLAINED.

    Rows carry the SUMMARY_DIMENSIONS columns, optionally recipient_name, column,
    rel_diff, diff (whose absolute value is matched against max_abs), baseline and
    candidate. A null against a number is matched with abs_diff = |number| (null as 0)
    and no rel_diff, so max_abs can bound it and max_rel cannot.
    """
    relevant = [e for e in expected if e.view == view and e.kind == kind]
    if not relevant or deltas.empty:
        return pd.Series(UNEXPLAINED, index=deltas.index, dtype=object)

    reasons = []
    for year, donor, indicator, recipient, column, rel_diff, diff, base, cand in zip(
        _nullable_values(deltas, "year"),
        _nullable_values(deltas, "donor_name"),
        _nullable_values(deltas, "indicator_name"),
        _nullable_values(deltas, "recipient_name"),
        _nullable_values(deltas, "column"),
        _nullable_values(deltas, "rel_diff"),
        _nullable_values(deltas, "diff"),
        _nullable_values(deltas, "baseline"),
        _nullable_values(deltas, "candidate"),
        strict=True,
    ):
        abs_diff = _abs_diff(diff, baseline=base, candidate=cand)
        entry = find_explanation(
            relevant,
            view=view,
            kind=kind,
            year=year,
            donor=donor,
            indicator=indicator,
            recipient=recipient,
            column=column,
            rel_diff=rel_diff,
            abs_diff=abs_diff,
        )
        reasons.append(UNEXPLAINED if entry is None else entry.reason)
    return pd.Series(reasons, index=deltas.index, dtype=object)


# --- Running delta log -----------------------------------------------------------------


def _summarise(deltas: pd.DataFrame) -> pd.DataFrame:
    """Aggregate delta rows by reason, column, year, donor and indicator.

    A null against a number counts as |number| in max_abs_diff, as in _abs_diff.
    """
    # diff is null only where one side is; the other side's |value| fills it.
    abs_diff = (
        deltas["diff"]
        .abs()
        .fillna(deltas["baseline"].abs().fillna(deltas["candidate"].abs()))
    )
    with_abs = deltas.assign(abs_diff=abs_diff, abs_rel=deltas["rel_diff"].abs())
    return (
        with_abs.groupby(_SUMMARY_KEYS, observed=True, dropna=False)
        .agg(
            n=("diff", "size"),
            baseline=("baseline", "sum"),
            candidate=("candidate", "sum"),
            diff=("diff", "sum"),
            max_abs_diff=("abs_diff", "max"),
            max_abs_rel=("abs_rel", "max"),
        )
        .reset_index()
    )


def _resummarise(summary: pd.DataFrame) -> pd.DataFrame:
    """Re-aggregate concatenated summaries."""
    return (
        summary.groupby(_SUMMARY_KEYS, observed=True, dropna=False)
        .agg(
            n=("n", "sum"),
            baseline=("baseline", "sum"),
            candidate=("candidate", "sum"),
            diff=("diff", "sum"),
            max_abs_diff=("max_abs_diff", "max"),
            max_abs_rel=("max_abs_rel", "max"),
        )
        .reset_index()
    )


def _largest_examples(deltas: pd.DataFrame) -> pd.DataFrame:
    """The MAX_DETAIL_ROWS largest deltas per reason; null-vs-value counts as largest."""
    rank = deltas["diff"].abs().fillna(np.inf)
    return (
        deltas.assign(_rank=rank)
        .sort_values("_rank", ascending=False, kind="stable")
        .groupby("reason", sort=False)
        .head(MAX_DETAIL_ROWS)
        .drop(columns="_rank")
    )


@dataclass
class _DeltaLog:
    """One check's deltas so far: an aggregate summary and the largest example rows."""

    summaries: list[pd.DataFrame] = field(default_factory=list)
    examples: list[pd.DataFrame] = field(default_factory=list)

    def add(self, deltas: pd.DataFrame) -> None:
        """Record classified delta rows (with a reason column)."""
        if deltas.empty:
            return
        self.summaries.append(_summarise(deltas))
        self.examples.append(_largest_examples(deltas))
        if len(self.summaries) >= COMPACT_EVERY:
            self.compact()

    def compact(self) -> None:
        """Merge the pending pieces into one summary and one examples frame."""
        if len(self.summaries) > 1:
            self.summaries = [_resummarise(pd.concat(self.summaries))]
            self.examples = [_largest_examples(pd.concat(self.examples))]

    def finish(self) -> tuple[pd.DataFrame, pd.DataFrame] | None:
        """(summary, examples), or None if no deltas were recorded."""
        if not self.summaries:
            return None
        self.compact()
        return self.summaries[0], self.examples[0]


# --- Formatting ------------------------------------------------------------------------


def _fmt_amount(value: float, *, signed: bool = False) -> str:
    """A unit amount as "3.21bn", "4.5mn" or "12,345"."""
    sign = "+" if signed else ""
    for size, suffix in _AMOUNT_UNITS:
        if abs(value) >= size:
            return f"{value / size:{sign},.2f}{suffix}"
    return f"{value:{sign},.0f}"


def _breakdown(summary: pd.DataFrame, dimension: str, *, amounts: bool) -> str | None:
    """'by year: 2024 (1,200, +3.1bn), ... (+N more)', largest first; None if empty."""
    grouped = (
        summary.dropna(subset=[dimension])
        .groupby(dimension, observed=True)
        .agg(n=("n", "sum"), diff=("diff", "sum"))
    )
    if grouped.empty:
        return None
    order = grouped["diff"].abs() if amounts else grouped["n"]
    top = grouped.loc[order.sort_values(ascending=False).index[:BREAKDOWN_TOP_N]]
    items = [
        f"{label} ({int(row['n']):,}, {_fmt_amount(row['diff'], signed=True)})"
        if amounts
        else f"{label} ({int(row['n']):,})"
        for label, row in top.iterrows()
    ]
    more = len(grouped) - len(top)
    suffix = f" (+{more} more)" if more else ""
    return f"by {_DIMENSION_LABELS[dimension]}: {', '.join(items)}{suffix}"


def _delta_message(summary: pd.DataFrame, what: str, *, amounts: bool) -> str:
    """A one-line summary of one reason's deltas, with breakdowns."""
    parts = [f"{int(summary['n'].sum()):,} {what}"]
    if amounts:
        parts.append(
            f"net diff {_fmt_amount(summary['diff'].sum(), signed=True)}"
            f" (baseline {_fmt_amount(summary['baseline'].sum())},"
            f" candidate {_fmt_amount(summary['candidate'].sum())})"
        )
    else:
        parts.append(
            f"max |diff| {summary['max_abs_diff'].max():.4g},"
            f" max |rel| {summary['max_abs_rel'].max():.4g}"
        )
    dimensions = ["column", *SUMMARY_DIMENSIONS] if not amounts else SUMMARY_DIMENSIONS
    parts.extend(
        text
        for dimension in dimensions
        if (text := _breakdown(summary, dimension, amounts=amounts)) is not None
    )
    return "; ".join(parts)


def _explained_prefix(reason: str) -> str:
    """The message prefix for an explained group."""
    return f"explained ({reason}): "


def _log_results(
    check: str,
    view: str,
    log: _DeltaLog,
    *,
    what: str,
    amounts: bool,
    pass_message: str,
) -> list[CheckResult]:
    """One result per reason: ERROR for unexplained deltas, INFO per explained reason."""
    finished = log.finish()
    if finished is None:
        return [_passed(check, view, pass_message)]
    summary, examples = finished
    results = []
    for reason in sorted(summary["reason"].unique()):
        message = _delta_message(
            summary[summary["reason"] == reason], what, amounts=amounts
        )
        explained = reason != UNEXPLAINED
        results.append(
            CheckResult(
                check=check,
                view=view,
                passed=False,
                severity=Severity.INFO if explained else Severity.ERROR,
                message=_explained_prefix(reason) + message if explained else message,
                details=examples[examples["reason"] == reason]
                .drop(columns="reason")
                .reset_index(drop=True),
                blocking=False,
            )
        )
    return results


def _passed(check: str, view: str, message: str) -> CheckResult:
    """A passing parity result."""
    return CheckResult(
        check=check,
        view=view,
        passed=True,
        severity=Severity.ERROR,
        message=message,
        blocking=False,
    )


def _failed(
    check: str,
    view: str,
    message: str,
    *,
    reason: str = UNEXPLAINED,
    details: pd.DataFrame | None = None,
) -> CheckResult:
    """A failing parity result: INFO when explained by reason, else ERROR."""
    explained = reason != UNEXPLAINED
    return CheckResult(
        check=check,
        view=view,
        passed=False,
        severity=Severity.INFO if explained else Severity.ERROR,
        message=_explained_prefix(reason) + message if explained else message,
        details=details,
        blocking=False,
    )


# --- Baseline renames ------------------------------------------------------------------


def rename_baseline_frame(
    view: str, df: pd.DataFrame, applied: Counter[tuple[str, str, str]]
) -> pd.DataFrame:
    """The baseline frame under the current names; counts each rename in ``applied``.

    Args:
        view: The view name, for its column renames.
        df: Baseline rows.
        applied: (what, old, new) -> rows renamed, updated in place.
    """
    columns = {
        old: new
        for old, new in BASELINE_COLUMN_RENAMES.get(view, {}).items()
        if old in df.columns and new not in df.columns
    }
    for old, new in columns.items():
        applied[("column", old, new)] += len(df)
    df = df.rename(columns=columns)
    if RECIPIENT_COLUMN not in df.columns:
        return df
    recipients = df[RECIPIENT_COLUMN]
    renamed = recipients.isin(list(BASELINE_RECIPIENT_RENAMES))
    if not renamed.any():
        return df
    for old, n in recipients[renamed].value_counts().items():
        applied[("recipient", str(old), BASELINE_RECIPIENT_RENAMES[str(old)])] += int(n)
    return df.assign(
        **{
            RECIPIENT_COLUMN: recipients.astype(object)
            .replace(BASELINE_RECIPIENT_RENAMES)
            .astype(recipients.dtype)
        }
    )


def _rename_option_value(value: object) -> object:
    """An options.json value with renamed recipient names and slugs, at any depth."""
    if isinstance(value, dict):
        return {
            _rename_option_value(k): _rename_option_value(v) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_rename_option_value(v) for v in value]
    if isinstance(value, str):
        return BASELINE_RECIPIENT_RENAMES.get(
            value, BASELINE_SLUG_RENAMES.get(value, value)
        )
    return value


def rename_baseline_options(options: dict) -> dict:
    """Baseline options.json under the current recipient names and slugs."""
    renamed = _rename_option_value(options)
    assert isinstance(renamed, dict)  # a dict maps to a dict
    return renamed


def renamed_option_lists(options: object, path: str = "") -> set[str]:
    """Dotted paths of the lists in options.json that hold a renamed recipient.

    Renaming moves a name within a sorted list, so such a list reorders.
    """
    if isinstance(options, dict):
        return {
            found
            for key, value in options.items()
            for found in renamed_option_lists(value, f"{path}.{key}" if path else key)
        }
    if isinstance(options, list) and any(
        isinstance(v, str) and v in BASELINE_RECIPIENT_RENAMES for v in options
    ):
        return {path}
    return set()


def _renames_result(view: str, applied: Mapping[tuple[str, str, str], int]) -> list:
    """One explained parity.baseline_renames result, or nothing when none applied."""
    if not applied:
        return []
    table = pd.DataFrame(
        [(what, old, new, n) for (what, old, new), n in sorted(applied.items())],
        columns=["what", "baseline", "candidate", "rows"],
    )
    listed = "; ".join(
        f"{row.what} {row.baseline!r} -> {row.candidate!r}"
        for row in table.itertuples(index=False)
    )
    return [
        _failed(
            "parity.baseline_renames",
            view,
            f"baseline read under {len(table)} renames: {listed}",
            reason=BASELINE_RENAMES_REASON,
            details=table,
        )
    ]


# --- Comparing one pair of frames ------------------------------------------------------


def _value_tolerance(baseline: pd.Series, *, rel: float) -> pd.Series:
    """max(VALUE_ABS_TOLERANCE, rel x |baseline|)."""
    return (rel * baseline.abs()).clip(lower=VALUE_ABS_TOLERANCE)


def _share_tolerance(baseline: pd.Series) -> pd.Series:
    """SHARE_ABS_TOLERANCE everywhere."""
    return pd.Series(SHARE_ABS_TOLERANCE, index=baseline.index)


def _column_deltas(
    merged: pd.DataFrame,
    keys: list[str],
    column: str,
    *,
    tolerance: Callable[[pd.Series], pd.Series],
) -> pd.DataFrame:
    """Rows of merged (shared keys) where column differs beyond tolerance, long form."""
    candidate = merged[f"{column}_c"].astype("float64")
    baseline = merged[f"{column}_b"].astype("float64")
    one_null = candidate.isna() != baseline.isna()
    diff = candidate - baseline
    differs = one_null | (diff.abs() > tolerance(baseline))
    if not differs.any():
        return pd.DataFrame()
    with np.errstate(divide="ignore", invalid="ignore"):
        rel_diff = diff / baseline.abs()
    return merged.loc[differs, keys].assign(
        column=column,
        baseline=baseline[differs],
        candidate=candidate[differs],
        diff=diff[differs],
        rel_diff=rel_diff[differs].replace([np.inf, -np.inf], np.nan),
    )


def _one_sided(merged: pd.DataFrame, keys: list[str], side: str) -> pd.DataFrame:
    """Keys present only on one side, with their value_usd_current, long form."""
    only = merged["_merge"] == ("left_only" if side == "candidate" else "right_only")
    value = merged.loc[only, f"{USD_CURRENT}_{side[0]}"].astype("float64")
    present = value if side == "candidate" else -value
    return merged.loc[only, keys].assign(
        column=USD_CURRENT,
        baseline=value if side == "baseline" else np.nan,
        candidate=value if side == "candidate" else np.nan,
        diff=present,
        rel_diff=np.nan,
    )


def _drop_duplicate_keys(df: pd.DataFrame, keys: list[str]) -> tuple[pd.DataFrame, int]:
    """(df without repeated keys, number of rows dropped)."""
    duplicated = df.duplicated(keys)
    n = int(duplicated.sum())
    return (df[~duplicated], n) if n else (df, 0)


@dataclass
class _ParityRun:
    """Accumulates deltas over one or more partition pairs of one view."""

    spec: ViewSpec
    expected: list[ExpectedDelta]
    rows: dict[str, int] = field(default_factory=lambda: dict.fromkeys(_SIDES, 0))
    duplicates: dict[str, int] = field(default_factory=lambda: dict.fromkeys(_SIDES, 0))
    shared_rows: int = 0
    logs: dict[str, _DeltaLog] = field(default_factory=dict)
    totals: list[pd.DataFrame] = field(default_factory=list)
    # (donor, year) -> reasons of its row-level value_usd_current and key deltas
    donor_year_reasons: dict[tuple[str, int], set[str]] = field(default_factory=dict)
    partitions: int = 0
    one_sided_partitions: list[dict] = field(default_factory=list)
    renames: Counter[tuple[str, str, str]] = field(default_factory=Counter)

    @property
    def view(self) -> str:
        """The view name."""
        return self.spec.name

    @property
    def keys(self) -> list[str]:
        """The view's key columns."""
        return list(self.spec.keys)

    def log(self, check: str) -> _DeltaLog:
        """The running log of one check."""
        return self.logs.setdefault(check, _DeltaLog())

    def _prepare(self, df: pd.DataFrame, side: str) -> pd.DataFrame:
        """Keep keys, values and shares (absent columns as nulls); drop repeated keys."""
        columns = [*self.spec.keys, *self.spec.value_columns, *self.spec.share_columns]
        df, n_duplicates = _drop_duplicate_keys(df.reindex(columns=columns), self.keys)
        self.duplicates[side] += n_duplicates
        return df

    def _record(self, check: str, deltas: pd.DataFrame, kind: DeltaKind) -> set[str]:
        """Classify, log and return the reasons of a check's delta rows."""
        if deltas.empty:
            return set()
        deltas = deltas.assign(
            reason=_explain(deltas, view=self.view, kind=kind, expected=self.expected)
        )
        self.log(check).add(deltas)
        # value_usd_current and one-sided keys feed the (donor, year) totals
        if check in _TOTALS_CHECKS:
            for (donor, year), reasons in deltas.groupby(
                ["donor_name", "year"], observed=True
            )["reason"]:
                self.donor_year_reasons.setdefault((donor, int(year)), set()).update(
                    reasons
                )
        return set(deltas["reason"])

    def add(self, candidate: pd.DataFrame, baseline: pd.DataFrame) -> set[str]:
        """Compare one pair of frames; returns the reasons of its one-sided keys."""
        baseline = rename_baseline_frame(self.view, baseline, self.renames)
        self.rows["candidate"] += len(candidate)
        self.rows["baseline"] += len(baseline)
        merged = self._prepare(candidate, "candidate").merge(
            self._prepare(baseline, "baseline"),
            on=self.keys,
            how="outer",
            suffixes=("_c", "_b"),
            indicator=True,
        )
        key_reasons = self._record(
            "parity.missing_in_candidate",
            _one_sided(merged, self.keys, "baseline"),
            DeltaKind.MISSING_IN_CANDIDATE,
        ) | self._record(
            "parity.new_in_candidate",
            _one_sided(merged, self.keys, "candidate"),
            DeltaKind.NEW_IN_CANDIDATE,
        )
        self.totals.append(
            merged.groupby(["donor_name", "year"], observed=True).agg(
                candidate=(f"{USD_CURRENT}_c", "sum"),
                baseline=(f"{USD_CURRENT}_b", "sum"),
                rows=(f"{USD_CURRENT}_b", "size"),
            )
        )
        if len(self.totals) >= COMPACT_EVERY:
            self.totals = [pd.concat(self.totals).groupby(level=[0, 1]).sum()]

        shared = merged[merged["_merge"] == "both"]
        self.shared_rows += len(shared)
        self._record(
            "parity.value_usd_current",
            _column_deltas(
                shared,
                self.keys,
                USD_CURRENT,
                tolerance=lambda b: _value_tolerance(b, rel=USD_CURRENT_REL_TOLERANCE),
            ),
            DeltaKind.VALUE,
        )
        others = [
            _column_deltas(
                shared,
                self.keys,
                column,
                tolerance=lambda b: _value_tolerance(b, rel=OTHER_VALUE_REL_TOLERANCE),
            )
            for column in self.spec.value_columns
            if column != USD_CURRENT
        ]
        shares = [
            _column_deltas(shared, self.keys, column, tolerance=_share_tolerance)
            for column in self.spec.share_columns
        ]
        for check, pieces in (
            ("parity.other_values", others),
            ("parity.shares", shares),
        ):
            pieces = [p for p in pieces if not p.empty]
            if pieces:
                self._record(
                    check, pd.concat(pieces, ignore_index=True), DeltaKind.VALUE
                )
        return key_reasons

    def add_partition(
        self, slug: str, candidate: pd.DataFrame | None, baseline: pd.DataFrame | None
    ) -> None:
        """Compare one partition; a partition on one side only is compared to nothing."""
        self.partitions += 1
        if candidate is not None and baseline is not None:
            self.add(candidate, baseline)
            return
        if candidate is not None:
            side, present = "candidate", candidate
            reasons = self.add(candidate, candidate.iloc[0:0])
        elif baseline is not None:
            side, present = "baseline", baseline
            reasons = self.add(baseline.iloc[0:0], baseline)
        else:
            raise ValueError(f"partition {slug!r} has no data on either side")
        explained = bool(reasons) and UNEXPLAINED not in reasons
        self.one_sided_partitions.append(
            {
                "partition": slug,
                "only_in": side,
                "rows": len(present),
                "reason": "; ".join(sorted(reasons)) if explained else UNEXPLAINED,
            }
        )

    # --- results -----------------------------------------------------------------------

    def _row_count_result(self, key_reasons: set[str]) -> CheckResult:
        """Row counts; a difference is explained when every one-sided key is."""
        c, b = self.rows["candidate"], self.rows["baseline"]
        message = f"candidate {c:,} rows, baseline {b:,} rows"
        if c == b:
            return _passed("parity.row_count", self.view, message)
        explained = bool(key_reasons) and UNEXPLAINED not in key_reasons
        reason = "; ".join(sorted(key_reasons)) if explained else UNEXPLAINED
        return _failed(
            "parity.row_count", self.view, f"{message} ({c - b:+,})", reason=reason
        )

    def _duplicates_result(self) -> CheckResult | None:
        """An ERROR when either side repeats keys; None when neither does."""
        if not any(self.duplicates.values()):
            return None
        counts = ", ".join(f"{side} {n:,}" for side, n in self.duplicates.items())
        return _failed(
            "parity.unique_keys",
            self.view,
            f"repeated keys dropped before comparing (first kept): {counts}",
        )

    def _partition_results(self) -> list[CheckResult]:
        """Partitions on one side only, grouped by reason; nothing for a flat view."""
        if not self.one_sided_partitions:
            if self.partitions > 1:
                return [
                    _passed(
                        "parity.partitions",
                        self.view,
                        f"same {self.partitions:,} partitions on both sides",
                    )
                ]
            return []
        table = pd.DataFrame(self.one_sided_partitions)
        results = []
        for reason, group in table.groupby("reason", sort=True):
            counts = group["only_in"].value_counts()
            listed = ", ".join(
                f"{n:,} only in {side}" for side, n in counts.sort_index().items()
            )
            results.append(
                _failed(
                    "parity.partitions",
                    self.view,
                    f"{listed} (of {self.partitions:,}): "
                    f"{', '.join(group['partition'].head(BREAKDOWN_TOP_N * 3))}",
                    reason=str(reason),
                    details=group.drop(columns="reason").reset_index(drop=True),
                )
            )
        return results

    def _totals_deltas(self) -> pd.DataFrame:
        """Per (donor, year) value_usd_current totals that differ, classified."""
        if not self.totals:
            return pd.DataFrame()
        totals = pd.concat(self.totals).groupby(level=[0, 1]).sum().reset_index()
        diff = totals["candidate"] - totals["baseline"]
        # Each side sums `rows` values rounded to ROUNDING_UNIT: invariants' sum tolerance.
        tolerance = sum_tolerance(totals["baseline"].abs(), totals["rows"])
        deltas = (
            totals[diff.abs() > tolerance]
            .drop(columns="rows")
            .assign(column=USD_CURRENT, indicator_name=pd.NA)
        )
        if deltas.empty:
            return deltas
        deltas["diff"] = deltas["candidate"] - deltas["baseline"]
        with np.errstate(divide="ignore", invalid="ignore"):
            rel = deltas["diff"] / deltas["baseline"].abs()
        deltas["rel_diff"] = rel.replace([np.inf, -np.inf], np.nan)

        direct = _explain(
            deltas, view=self.view, kind=DeltaKind.VALUE, expected=self.expected
        )
        reasons = []
        for donor, year, reason in zip(
            deltas["donor_name"], deltas["year"], direct, strict=True
        ):
            row_reasons = self.donor_year_reasons.get((donor, int(year)), set())
            if reason == UNEXPLAINED and row_reasons and UNEXPLAINED not in row_reasons:
                reason = "follows row-level deltas: " + "; ".join(sorted(row_reasons))
            reasons.append(reason)
        return deltas.assign(reason=reasons)

    def results(self, options_results: list[CheckResult]) -> list[CheckResult]:
        """Every parity result for the view."""
        key_reasons: set[str] = set()
        for check in ("parity.missing_in_candidate", "parity.new_in_candidate"):
            log = self.logs.get(check)
            if log is not None and log.summaries:
                key_reasons |= set(pd.concat(log.summaries)["reason"])

        totals_log = _DeltaLog()
        totals_log.add(self._totals_deltas())

        results = [
            *_renames_result(self.view, self.renames),
            self._row_count_result(key_reasons),
        ]
        if (duplicates := self._duplicates_result()) is not None:
            results.append(duplicates)
        results += self._partition_results()
        results += _log_results(
            "parity.missing_in_candidate",
            self.view,
            self.log("parity.missing_in_candidate"),
            what="keys only in the baseline (value_usd_current)",
            amounts=True,
            pass_message="no baseline keys missing from the candidate",
        )
        results += _log_results(
            "parity.new_in_candidate",
            self.view,
            self.log("parity.new_in_candidate"),
            what="keys only in the candidate (value_usd_current)",
            amounts=True,
            pass_message="no keys new in the candidate",
        )
        results += _log_results(
            "parity.value_usd_current",
            self.view,
            self.log("parity.value_usd_current"),
            what=f"{USD_CURRENT} diffs beyond max({VALUE_ABS_TOLERANCE:g} units, "
            f"{USD_CURRENT_REL_TOLERANCE:g} relative)",
            amounts=True,
            pass_message=f"{USD_CURRENT} matches on {self.shared_rows:,} shared keys",
        )
        results += _log_results(
            "parity.other_values",
            self.view,
            self.log("parity.other_values"),
            what=f"value diffs beyond max({VALUE_ABS_TOLERANCE:g} units, "
            f"{OTHER_VALUE_REL_TOLERANCE:g} relative)",
            amounts=False,
            pass_message=f"other value columns match on {self.shared_rows:,} shared keys",
        )
        if self.spec.share_columns:
            results += _log_results(
                "parity.shares",
                self.view,
                self.log("parity.shares"),
                what=f"share diffs beyond {SHARE_ABS_TOLERANCE:g}",
                amounts=False,
                pass_message=f"shares match on {self.shared_rows:,} shared keys",
            )
        results += _log_results(
            "parity.donor_totals",
            self.view,
            totals_log,
            what=f"(donor, year) {USD_CURRENT} totals differ",
            amounts=True,
            pass_message=f"(donor, year) {USD_CURRENT} totals match",
        )
        return results + options_results


# --- options.json ----------------------------------------------------------------------


def _options_deltas(candidate: object, baseline: object, path: str = "") -> list[dict]:
    """Differences between two options trees: one-sided items, changes, reorders."""
    if isinstance(candidate, dict) and isinstance(baseline, dict):
        deltas = []
        for key in sorted(baseline.keys() - candidate.keys()):
            deltas.append(_option_delta(path, "missing_in_candidate", item=key))
        for key in sorted(candidate.keys() - baseline.keys()):
            deltas.append(_option_delta(path, "new_in_candidate", item=key))
        for key in sorted(baseline.keys() & candidate.keys()):
            child = f"{path}.{key}" if path else str(key)
            deltas += _options_deltas(candidate[key], baseline[key], child)
        return deltas
    if isinstance(candidate, list) and isinstance(baseline, list):
        if candidate == baseline:
            return []
        if not all(isinstance(v, str | int | float) for v in [*candidate, *baseline]):
            return [
                _option_delta(path, "changed", baseline=baseline, candidate=candidate)
            ]
        missing = [v for v in baseline if v not in set(candidate)]
        new = [v for v in candidate if v not in set(baseline)]
        deltas = [_option_delta(path, "missing_in_candidate", item=v) for v in missing]
        deltas += [_option_delta(path, "new_in_candidate", item=v) for v in new]
        if not deltas:
            deltas.append(_option_delta(path, "reordered"))
        return deltas
    if candidate != baseline:
        return [_option_delta(path, "changed", baseline=baseline, candidate=candidate)]
    return []


def _option_delta(
    path: str,
    change: str,
    *,
    item: object = None,
    baseline: object = None,
    candidate: object = None,
) -> dict:
    """One options delta as a row; values as strings so the details frame is uniform."""
    return {
        "path": path,
        "change": change,
        "item": None if item is None else str(item),
        "baseline": None if baseline is None else str(baseline),
        "candidate": None if candidate is None else str(candidate),
    }


def _option_path(delta: dict) -> str:
    """The dotted options.json path a delta is about: the item's own path when one-sided."""
    if delta["change"] == "changed" or delta["item"] is None:
        return delta["path"]
    return f"{delta['path']}.{delta['item']}" if delta["path"] else delta["item"]


def _explain_option(delta: dict, view: str, expected: Sequence[ExpectedDelta]) -> str:
    """The reason for an options delta, else UNEXPLAINED.

    A one-sided donor, recipient or indicator list item is matched by that dimension. A
    changed value, or any other key or item added or removed, is matched by its dotted
    path against entries with paths. Reorders are never explained.
    """
    change = delta["change"]
    dimension = _OPTION_DIMENSIONS.get(delta["path"])
    one_sided = change in (DeltaKind.MISSING_IN_CANDIDATE, DeltaKind.NEW_IN_CANDIDATE)
    if dimension is not None and one_sided:
        entry = find_explanation(
            list(expected), view=view, kind=change, **{dimension: delta["item"]}
        )
    elif one_sided or change == "changed":
        entry = find_explanation(
            [e for e in expected if e.paths is not None],
            view=view,
            kind=DeltaKind.VALUE if change == "changed" else change,
            path=_option_path(delta),
        )
    else:
        entry = None
    return UNEXPLAINED if entry is None else entry.reason


def _without_metadata(options: dict) -> dict:
    """options.json without its root OPTIONS_METADATA_KEYS."""
    return {k: v for k, v in options.items() if k not in OPTIONS_METADATA_KEYS}


def _options_results(
    view: str, candidate: dict, baseline: dict, expected: Sequence[ExpectedDelta]
) -> list[CheckResult]:
    """Compare two options.json dicts, without OPTIONS_METADATA_KEYS; one per reason."""
    baseline = _without_metadata(baseline)
    deltas = _options_deltas(
        _without_metadata(candidate), rename_baseline_options(baseline)
    )
    if not deltas:
        return [_passed("parity.options", view, "options.json identical")]
    reordered_by_rename = renamed_option_lists(baseline)
    table = pd.DataFrame(deltas)
    table["reason"] = [
        BASELINE_RENAMES_REASON
        if d["change"] == "reordered" and d["path"] in reordered_by_rename
        else _explain_option(d, view, expected)
        for d in deltas
    ]
    results = []
    for reason, group in table.groupby("reason", sort=True):
        listed = "; ".join(
            f"{row.path or '<root>'} {row.change}"
            + (f" {row.item!r}" if row.item is not None else "")
            for row in group.head(BREAKDOWN_TOP_N * 2).itertuples()
        )
        more = len(group) - min(len(group), BREAKDOWN_TOP_N * 2)
        results.append(
            _failed(
                "parity.options",
                view,
                f"{len(group):,} options differences: {listed}"
                + (f" (+{more} more)" if more else ""),
                reason=str(reason),
                details=group.drop(columns="reason").reset_index(drop=True),
            )
        )
    return results


# --- Public API ------------------------------------------------------------------------


def _check_same_view(candidate: LoadedView, baseline: LoadedView) -> None:
    """Raise if the two sides are different views."""
    if candidate.spec.name != baseline.spec.name:
        raise ValueError(
            f"Cannot compare {candidate.spec.name} with {baseline.spec.name}"
        )


def compare_views(
    candidate: LoadedView,
    baseline: LoadedView,
    expected: Sequence[ExpectedDelta],
) -> list[CheckResult]:
    """Compare two whole loaded copies of one view.

    Args:
        candidate: The build under test.
        baseline: The reference snapshot.
        expected: Expected deltas; entries for other views are ignored.

    Returns:
        Non-blocking results (see the module docstring for the checks).

    Raises:
        ValueError: The two sides are different views.
    """
    _check_same_view(candidate, baseline)
    run = _ParityRun(spec=candidate.spec, expected=list(expected))
    run.add(candidate.data, baseline.data)
    return run.results(
        _options_results(run.view, candidate.options, baseline.options, expected)
    )


type _PartitionPair = tuple[str, LoadedView | None, LoadedView | None]


def _set_aside(
    partitions: Iterator[tuple[str, LoadedView]],
    slugs: Mapping[str, str],
    held: dict[str, LoadedView],
) -> Iterator[tuple[str, LoadedView]]:
    """Yield partitions, keeping those whose slug is in ``slugs`` in ``held`` instead.

    ``held`` is keyed by ``slugs[slug]``: the name both sides share after renaming.
    """
    for slug, view in partitions:
        if slug in slugs:
            held[slugs[slug]] = view
        else:
            yield slug, view


def _merge_join(
    candidates: Iterator[tuple[str, LoadedView]],
    baselines: Iterator[tuple[str, LoadedView]],
) -> Iterator[_PartitionPair]:
    """Merge-join two sorted partition streams by slug; a missing side is None."""
    c, b = next(candidates, None), next(baselines, None)
    while c is not None or b is not None:
        if c is not None and (b is None or c[0] < b[0]):
            yield c[0], c[1], None
            c = next(candidates, None)
        elif b is not None and (c is None or b[0] < c[0]):
            yield b[0], None, b[1]
            b = next(baselines, None)
        elif c is not None and b is not None:
            yield c[0], c[1], b[1]
            c, b = next(candidates, None), next(baselines, None)


def _paired_partitions(
    name: str, candidate_source: Path, baseline_source: Path
) -> Iterator[_PartitionPair]:
    """Pair the two sides' partitions by slug; a missing side is None.

    Partitions under a renamed slug (BASELINE_SLUG_RENAMES; a handful of recipients) sort
    elsewhere on each side, so both sides' copies are held back and paired at the end
    under the new slug.

    Raises:
        ValueError: One side is a single file and the other is partitioned.
    """
    candidates = iter_partitions(name, candidate_source)
    baselines = iter_partitions(name, baseline_source)
    c, b = next(candidates, None), next(baselines, None)
    if (c is not None and b is not None) and (
        (c[0] == FLAT_PARTITION) != (b[0] == FLAT_PARTITION)
    ):
        raise ValueError(
            f"{name}: cannot compare a single-file source with a partitioned one "
            f"({candidate_source} vs {baseline_source})"
        )
    held_candidates: dict[str, LoadedView] = {}
    held_baselines: dict[str, LoadedView] = {}
    new_slugs = {new: new for new in BASELINE_SLUG_RENAMES.values()}
    yield from _merge_join(
        _set_aside(
            chain([c] if c is not None else [], candidates), new_slugs, held_candidates
        ),
        _set_aside(
            chain([b] if b is not None else [], baselines),
            BASELINE_SLUG_RENAMES,
            held_baselines,
        ),
    )
    for slug in sorted(held_candidates.keys() | held_baselines.keys()):
        yield slug, held_candidates.get(slug), held_baselines.get(slug)


def run_parity(
    view_name: str,
    candidate_source: Path,
    baseline_source: Path,
    expected: Sequence[ExpectedDelta],
) -> list[CheckResult]:
    """Compare a view's candidate build against a baseline, partition by partition.

    A flat source is compared whole; a hive source (sectors) one recipient partition at
    a time, so memory holds one partition pair. A partition on one side only is reported
    under parity.partitions and its keys as one-sided keys.

    Args:
        view_name: A key of VIEWS.
        candidate_source: The candidate view's directory (see io for layouts).
        baseline_source: The baseline view's directory.
        expected: Expected deltas; entries for other views are ignored.

    Returns:
        Non-blocking results (see the module docstring for the checks).

    Raises:
        KeyError: Unknown view.
        FileNotFoundError: No data or options on either side.
        ValueError: One side is flat and the other partitioned.
    """
    run = _ParityRun(spec=get_spec(view_name), expected=list(expected))
    options: dict[str, dict] = {}
    for slug, candidate, baseline in _paired_partitions(
        view_name, candidate_source, baseline_source
    ):
        if candidate is not None:
            options.setdefault("candidate", candidate.options)
        if baseline is not None:
            options.setdefault("baseline", baseline.options)
        run.add_partition(
            slug,
            None if candidate is None else candidate.data,
            None if baseline is None else baseline.data,
        )
        if run.partitions % PROGRESS_EVERY == 0:
            logger.info("parity %s: %d partitions compared", view_name, run.partitions)

    # iter_partitions raises on a source without data, so both sides gave options
    return run.results(
        _options_results(view_name, options["candidate"], options["baseline"], expected)
    )
