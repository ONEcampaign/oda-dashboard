"""Invariants: arithmetic identities the published views must satisfy.

Each invariant is a small map-reduce, so the same code runs on a whole view or on the
sectors view one recipient partition at a time (the only way its group sums fit in memory):

- ``partial(data, spec)`` reduces one partition to a small frame (offending rows, or
  partial sums);
- ``reduce(frame)`` folds the concatenated partials back to that size after each partition;
- ``finalize(frame, rows, spec)`` turns the folded frame into CheckResults.

``check_<x>(view)`` runs one invariant on one LoadedView. ``run_invariants(parts)`` runs
every invariant that applies, in one pass over the parts of a view::

    run_invariants([load_view(name, source)])                       # flat views
    run_invariants(v for _, v in iter_partitions("sectors_view", source))  # sectors

Every part must hold every donor for its recipients (``iter_partitions(by="recipient_slug")``
or a whole view): group sums and the share identities are evaluated within a part.

Tolerances: sums agree within 1e-6 of the summed absolute values plus half a rounding unit
per value compared; base-year constant equals current within 1e-6 plus one rounding unit;
share identities within 1e-4 (1e-3 for sectors); the currency ratio within 1e-5 relative,
on rows of at least 1e8 units, non-aggregate donors only.

Shares follow how the pipeline computes them (SHARE_BASES): a share outside [0, 1] blocks
unless a negative value in its denominator group explains it, and a null share blocks
unless its denominator is zero or absent. A check that finds nothing to check fails
rather than passing.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.data.config import (
    ALL_BILATERAL_DONORS,
    CURRENCIES,
    DAC_COUNTRIES_NAME,
    EU27_COUNTRIES_NAME,
    EU27_EUI_NAME,
    ODA_ELIGIBLE,
    TOTAL_ODA,
)
from src.data.validation.contracts import PRIMARY_VALUE_COLUMN, build_result
from src.data.validation.io import LoadedView
from src.data.validation.models import CheckResult, Severity
from src.data.validation.views import (
    AGGREGATE_DONORS,
    DONOR_GROUP_MEMBERS,
    ViewSpec,
    recipient_aggregates,
)

# The pipeline rounds every published value to 1e-4 million (100 units) after aggregating
# (widen_currency_price), so each value carries up to ROUNDING_UNIT / 2 of rounding error
# and a group or total need not equal the sum of its rounded terms exactly.
ROUNDING_UNIT: float = 100.0

# Sums: |total - sum(terms)| <= SUM_RELATIVE_TOLERANCE * sum(|values|)
#     + ROUNDING_UNIT / 2 * (n_terms + 1), the + 1 for the total's own rounding.
SUM_RELATIVE_TOLERANCE: float = 1e-6

# Recipients view: countries may fall short of ODA eligible countries (DAC2A totals carry
# codes no country row holds), but a shortfall above this share of the total is a WARNING.
RECIPIENT_GAP_WARNING: float = 0.01
# Donors whose DAC2A ODA-eligible total runs far above their recipient rows in most years
# (by 95% or more since 2018). Saudi Arabia reports most of its bilateral ODA to the DAC2A
# total without a recipient breakdown. Their gap is a known reporting gap, and every
# group that holds them inherits it.
RECIPIENT_GAP_KNOWN_DONORS: frozenset[str] = frozenset({"Saudi Arabia"})

# Config group members that report no ODA to DAC1, DAC2A or the CRS in any year of any
# view. They are listed in the DAC's Non-DAC countries group and absent from the data.
MEMBERS_WITHOUT_DATA: frozenset[str] = frozenset({"Algeria", "Iraq", "Libya", "Mexico"})

# Share range: a fraction in [0, 1], give or take float32 rounding.
SHARE_RANGE_TOLERANCE: float = 1e-4
SHARE_MIN: float = -SHARE_RANGE_TOLERANCE
SHARE_MAX: float = 1.0 + SHARE_RANGE_TOLERANCE
SHARE_SUM_TOLERANCE: float = 1e-4
SECTORS_SHARE_SUM_TOLERANCE: float = 1e-3

# Currency ratio: constant/current within a (donor, year) agrees to this relative spread,
# on rows whose value_usd_current is at least CURRENCY_RATIO_MIN_UNITS. Below that, the
# ROUNDING_UNIT rounding of both values alone can move the ratio by more than the tolerance.
CURRENCY_RATIO_TOLERANCE: float = 1e-5
CURRENCY_RATIO_MIN_UNITS: float = 1e8

# Base year: constant equals current within this relative tolerance plus ROUNDING_UNIT
# (each of the two values is rounded on its own).
BASE_YEAR_RELATIVE_TOLERANCE: float = 1e-6

NON_DAC_COUNTRIES_NAME: str = "Non-DAC countries"
EU_INSTITUTIONS_NAME: str = "EU Institutions"
BILATERAL_INDICATOR: str = "Bilateral"
# Financing indicators whose group rows the pipeline drops for years a member lacks the
# grants split, so they are not sums of the member rows that remain.
FINANCING_GROUP_SUM_EXCLUDED: frozenset[str] = frozenset({"Grants", "Non-grants"})

DONOR: str = "donor_name"
RECIPIENT: str = "recipient_name"
INDICATOR: str = "indicator_name"
YEAR: str = "year"


def _identity(frame: pd.DataFrame) -> pd.DataFrame:
    """The default reduce: keep the concatenated partials as they are."""
    return frame


@dataclass(frozen=True)
class _Invariant:
    """One invariant as partial -> reduce -> finalize (see the module docstring)."""

    views: frozenset[str]
    partial: Callable[[pd.DataFrame, ViewSpec], pd.DataFrame]
    finalize: Callable[[pd.DataFrame, int, ViewSpec], list[CheckResult]]
    reduce: Callable[[pd.DataFrame], pd.DataFrame] = _identity


def sum_tolerance(abs_total: pd.Series, n_terms: pd.Series) -> pd.Series:
    """The tolerance for a total compared with the sum of n_terms rounded values.

    Args:
        abs_total: Sum of the absolute values of the terms and the total.
        n_terms: Number of terms summed (the total itself is added here).
    """
    return SUM_RELATIVE_TOLERANCE * abs_total + ROUNDING_UNIT / 2 * (n_terms + 1)


def _without(keys: Iterable[str], *drop: str) -> list[str]:
    """Keys in order, minus some."""
    return [k for k in keys if k not in drop]


# --- Donor group sums ---------------------------------------------------------------------


@dataclass(frozen=True)
class _GroupIdentity:
    """A donor row that must equal the sum of other donor rows.

    Attributes:
        group: The aggregate donor name.
        members: The donor names it sums.
        views: Views where the identity holds; None for every view.
        indicators: Restrict to these indicators; None for all.
    """

    group: str
    members: frozenset[str]
    views: frozenset[str] | None = None
    indicators: frozenset[str] | None = None


GROUP_IDENTITIES: tuple[_GroupIdentity, ...] = (
    *(_GroupIdentity(g, m) for g, m in DONOR_GROUP_MEMBERS.items()),
    _GroupIdentity(
        ALL_BILATERAL_DONORS, frozenset({DAC_COUNTRIES_NAME, NON_DAC_COUNTRIES_NAME})
    ),
    # A plain sum only where the view builds it as one: gender sums the members, sectors
    # sums them for Bilateral but nets member contributions out of Imputed multilateral.
    # Financing reads the bloc from DAC1 and the recipients view from DAC2A, both net of
    # those contributions.
    _GroupIdentity(
        EU27_EUI_NAME,
        frozenset({EU27_COUNTRIES_NAME, EU_INSTITUTIONS_NAME}),
        views=frozenset({"gender_view"}),
    ),
    _GroupIdentity(
        EU27_EUI_NAME,
        frozenset({EU27_COUNTRIES_NAME, EU_INSTITUTIONS_NAME}),
        views=frozenset({"sectors_view"}),
        indicators=frozenset({BILATERAL_INDICATOR}),
    ),
)


def _group_sum_rows(data: pd.DataFrame, spec: ViewSpec) -> pd.DataFrame:
    """The rows group sums compare: financing without Grants/Non-grants."""
    if spec.name == "financing_view":
        return data.loc[~data[INDICATOR].isin(FINANCING_GROUP_SUM_EXCLUDED)]
    return data


def _group_sum_partial(data: pd.DataFrame, spec: ViewSpec) -> pd.DataFrame:
    """Cells where a group's value differs from its members' sum beyond tolerance."""
    keys = _without(spec.keys, DONOR)
    data = _group_sum_rows(data, spec)[[*keys, DONOR, PRIMARY_VALUE_COLUMN]]
    violations = []
    for identity in GROUP_IDENTITIES:
        if identity.views is not None and spec.name not in identity.views:
            continue
        rows = data
        if identity.indicators is not None:
            rows = rows.loc[rows[INDICATOR].isin(identity.indicators)]
        members = rows.loc[rows[DONOR].isin(identity.members)]
        member_sums = (
            members.assign(abs_value=members[PRIMARY_VALUE_COLUMN].abs())
            .groupby(keys, observed=True)
            .agg(
                members_sum=(PRIMARY_VALUE_COLUMN, "sum"),
                members_abs=("abs_value", "sum"),
                members_n=(DONOR, "size"),
            )
        )
        group = (
            rows.loc[rows[DONOR] == identity.group]
            .set_index(keys)[PRIMARY_VALUE_COLUMN]
            .rename("group_value")
        )
        # A missing group row or a missing member row counts as 0.
        joined = member_sums.join(group, how="outer").fillna(0)
        joined["difference"] = joined["group_value"] - joined["members_sum"]
        bad = joined["difference"].abs() > sum_tolerance(
            joined["members_abs"] + joined["group_value"].abs(), joined["members_n"]
        )
        if bad.any():
            violations.append(
                joined.loc[bad].reset_index().assign(group=identity.group)
            )
    if not violations:
        return pd.DataFrame()
    return pd.concat(violations, ignore_index=True)


def _group_sum_finalize(
    frame: pd.DataFrame, rows: int, spec: ViewSpec
) -> list[CheckResult]:
    """One ERROR result for every group sum in the view."""
    n = len(frame)
    by_group = (
        frame["group"].value_counts().to_dict() if n else {}
    )  # group -> failing cells
    details = (
        frame.assign(abs_difference=frame["difference"].abs()).sort_values(
            "abs_difference", ascending=False
        )
        if n
        else None
    )
    return [
        build_result(
            check="invariants.group_sums",
            view=spec.name,
            failures=n,
            severity=Severity.ERROR,
            passed_message="Every donor group equals the sum of its members",
            failed_message=f"{n:,} group cells differ from their members' sum: {by_group}",
            details=details,
        )
    ]


GROUP_SUMS = _Invariant(
    views=frozenset(
        {"financing_view", "recipients_view", "gender_view", "sectors_view"}
    ),
    partial=_group_sum_partial,
    finalize=_group_sum_finalize,
)


def _donors_partial(data: pd.DataFrame, spec: ViewSpec) -> pd.DataFrame:
    """The donor names in a part."""
    return pd.DataFrame({DONOR: data[DONOR].dropna().unique()})


def _drop_duplicates(frame: pd.DataFrame) -> pd.DataFrame:
    """Reduce by dropping duplicate rows."""
    return frame.drop_duplicates(ignore_index=True)


def _members_present_finalize(
    frame: pd.DataFrame, rows: int, spec: ViewSpec
) -> list[CheckResult]:
    """WARNING naming config group members with no rows anywhere in the view.

    Members in MEMBERS_WITHOUT_DATA are left out, since they never report. The passing
    message names any of them that now have rows, so the list can shrink.
    """
    present = set(frame[DONOR]) if len(frame) else set()
    missing = [
        (group, member)
        for group, members in DONOR_GROUP_MEMBERS.items()
        if group in present
        for member in sorted(members - present - MEMBERS_WITHOUT_DATA)
    ]
    reporting = sorted(MEMBERS_WITHOUT_DATA & present)
    stale = (
        f"; now reporting, drop from MEMBERS_WITHOUT_DATA: {reporting}"
        if reporting
        else ""
    )
    details = pd.DataFrame(missing, columns=["group", "member"])
    by_group = details["group"].value_counts().to_dict()
    return [
        build_result(
            check="invariants.group_members_present",
            view=spec.name,
            failures=len(missing),
            severity=Severity.WARNING,
            passed_message=(
                "Every config member of every donor group has rows, bar "
                f"{len(MEMBERS_WITHOUT_DATA)} that never report{stale}"
            ),
            failed_message=(
                f"{len(missing)} config group members have no rows in the view: {by_group}"
            ),
            details=details,
        )
    ]


GROUP_MEMBERS_PRESENT = _Invariant(
    views=GROUP_SUMS.views,
    partial=_donors_partial,
    finalize=_members_present_finalize,
    reduce=_drop_duplicates,
)


# --- Recipient sums -----------------------------------------------------------------------


def _recipient_sum_partial(data: pd.DataFrame, spec: ViewSpec) -> pd.DataFrame:
    """Per key without recipient: the countries' sum and absolute sum, and the total."""
    keys = _without(spec.keys, RECIPIENT)
    aggregates = recipient_aggregates(spec.name) | {ODA_ELIGIBLE}
    values = data[[*keys, RECIPIENT, PRIMARY_VALUE_COLUMN]]
    countries = values.loc[~values[RECIPIENT].isin(aggregates)]
    country_sums = (
        countries.assign(abs_value=countries[PRIMARY_VALUE_COLUMN].abs())
        .groupby(keys, observed=True)
        .agg(
            countries_sum=(PRIMARY_VALUE_COLUMN, "sum"),
            countries_abs=("abs_value", "sum"),
            countries_n=(RECIPIENT, "size"),
        )
    )
    total = (
        values.loc[values[RECIPIENT] == ODA_ELIGIBLE]
        .set_index(keys)[PRIMARY_VALUE_COLUMN]
        .rename("total")
    )
    return country_sums.join(total, how="outer").reset_index()


def _sum_by_key(frame: pd.DataFrame) -> pd.DataFrame:
    """Reduce partial sums: add them up per key, keeping a total absent everywhere NaN."""
    if frame.empty:
        return frame
    keys = [
        c
        for c in frame.columns
        if c not in {"countries_sum", "countries_abs", "countries_n", "total"}
    ]
    return (
        frame.groupby(keys, observed=True, dropna=False).sum(min_count=1).reset_index()
    )


def _recipient_sum_finalize(
    frame: pd.DataFrame, rows: int, spec: ViewSpec
) -> list[CheckResult]:
    """Countries vs ODA eligible countries: equal (CRS views) or at most (recipients)."""
    frame = frame.fillna(
        {"countries_sum": 0, "countries_abs": 0, "countries_n": 0, "total": 0}
    )
    frame = frame.assign(difference=frame["total"] - frame["countries_sum"])
    tolerance = sum_tolerance(
        frame["countries_abs"] + frame["total"].abs(), frame["countries_n"]
    )

    if spec.name != "recipients_view":
        bad = frame.loc[frame["difference"].abs() > tolerance]
        return [
            build_result(
                check="invariants.recipient_sums",
                view=spec.name,
                failures=len(bad),
                severity=Severity.ERROR,
                passed_message=f"{ODA_ELIGIBLE} equals the sum of its recipients",
                failed_message=(
                    f"{len(bad):,} cells where {ODA_ELIGIBLE} differs from the sum of "
                    "its recipients"
                ),
                details=_by_abs(bad, "difference"),
            )
        ]

    overshoot = frame.loc[-frame["difference"] > tolerance]
    # Groups' gaps are the sums of their members' (group_sums checks that), so only
    # reporting donors are judged, bar the known DAC2A total-only reporters.
    judged = ~frame[DONOR].isin(AGGREGATE_DONORS | RECIPIENT_GAP_KNOWN_DONORS)
    gap = frame.loc[
        judged & (frame["difference"] > RECIPIENT_GAP_WARNING * frame["total"].abs())
    ]
    gap = gap.assign(gap_share=gap["difference"] / gap["total"].abs())
    return [
        build_result(
            check="invariants.recipient_sum_overshoot",
            view=spec.name,
            failures=len(overshoot),
            severity=Severity.ERROR,
            passed_message=f"Countries never sum above {ODA_ELIGIBLE}",
            failed_message=(
                f"{len(overshoot):,} cells where countries sum above {ODA_ELIGIBLE}"
            ),
            details=_by_abs(overshoot, "difference"),
        ),
        build_result(
            check="invariants.recipient_sum_gap",
            view=spec.name,
            failures=len(gap),
            severity=Severity.WARNING,
            passed_message=(
                f"Countries within {RECIPIENT_GAP_WARNING:.0%} of {ODA_ELIGIBLE} for "
                f"every reporting donor bar {sorted(RECIPIENT_GAP_KNOWN_DONORS)}"
            ),
            failed_message=(
                f"{len(gap):,} cells where countries fall short of {ODA_ELIGIBLE} by "
                f"more than {RECIPIENT_GAP_WARNING:.0%}"
            ),
            details=_by_abs(gap, "difference"),
        ),
    ]


def _by_abs(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Sort a frame by a column's absolute value, largest first."""
    return frame.sort_values(
        column, key=lambda values: values.abs(), ascending=False, na_position="last"
    )


RECIPIENT_SUMS = _Invariant(
    views=frozenset({"recipients_view", "gender_view", "sectors_view"}),
    partial=_recipient_sum_partial,
    finalize=_recipient_sum_finalize,
    reduce=_sum_by_key,
)


# --- Shares -------------------------------------------------------------------------------


@dataclass(frozen=True)
class _ShareBasis:
    """How the pipeline computes a share column: value_usd_current over a denominator.

    Attributes:
        column: The share column.
        by: The keys of the denominator group.
        where: The (column, value) rows whose sum per ``by`` is the denominator; None when
            the denominator is the sum of the group's own rows.
        bounded: Whether the share must lie in [0, 1] when no row of its ``by`` group is
            negative. With every value in the group non-negative, a row cannot exceed the
            total it is part of; a negative value anywhere in the group (net flows) can
            push shares either side.
        outside_reference: Donors whose rows are not part of the ``where`` reference, so
            nothing bounds their share by 1.
    """

    column: str
    by: tuple[str, ...]
    where: tuple[str, str] | None
    bounded: bool = True
    outside_reference: frozenset[str] = frozenset()


# EU Institutions are not a member of All bilateral donors (DAC countries plus Non-DAC
# countries), so EU rows can exceed a recipient's bilateral total.
_EU_INSTITUTION_DONORS: frozenset[str] = frozenset(
    {EU_INSTITUTIONS_NAME, EU27_EUI_NAME}
)
_REFERENCE_SHARES: tuple[_ShareBasis, ...] = (
    _ShareBasis("pct_total_donor", by=(YEAR, DONOR), where=(RECIPIENT, ODA_ELIGIBLE)),
    _ShareBasis(
        "pct_total_recipient",
        by=(YEAR, RECIPIENT),
        where=(DONOR, ALL_BILATERAL_DONORS),
        outside_reference=_EU_INSTITUTION_DONORS,
    ),
)
# Per view, the share columns the share invariants check. contracts.py bounds pct_of_gni.
SHARE_BASES: dict[str, tuple[_ShareBasis, ...]] = {
    # Grants above 1 and Non-grants below 0 of Total ODA are normal (loan repayments), so
    # financing is held only to its Total ODA = 1 identity (SHARE_IDENTITIES).
    "financing_view": (
        _ShareBasis(
            "pct_of_total_oda",
            by=(YEAR, DONOR),
            where=(INDICATOR, TOTAL_ODA),
            bounded=False,
        ),
    ),
    "recipients_view": _REFERENCE_SHARES,
    "gender_view": (
        _ShareBasis(
            "pct_of_bilateral_allocable", by=(YEAR, DONOR, RECIPIENT), where=None
        ),
    ),
    "sectors_view": _REFERENCE_SHARES,
}

_CELL, _NEGATIVE, _DENOMINATOR = "cell", "negative", "denominator"
_SHARE_RECORD_COLUMNS: tuple[str, ...] = (
    "record",
    "column",
    "group",
    "problem",
    "share",
    "denominator",
    "denominator_abs",
    "denominator_n",
)


# Joins a group's key values into one label. No view label contains it.
_GROUP_SEPARATOR: str = "\x1f"


def _group_labels(data: pd.DataFrame, by: tuple[str, ...]) -> pd.Series:
    """Each row's ``by`` key as one string label, so groups of any width share a column."""
    labels = data[by[0]].astype(str)
    for key in by[1:]:
        labels = labels + _GROUP_SEPARATOR + data[key].astype(str)
    return labels.astype(object)


def _share_cells(
    data: pd.DataFrame, spec: ViewSpec, basis: _ShareBasis
) -> pd.DataFrame:
    """Null and out-of-range cells of one share column, with their group."""
    share = data[basis.column]
    null = share.isna()
    outside = ~null & ~share.between(SHARE_MIN, SHARE_MAX)
    flagged = null | outside
    if not flagged.any():
        return pd.DataFrame()
    cells = data.loc[flagged]
    return cells[list(spec.keys)].assign(
        record=_CELL,
        column=basis.column,
        group=_group_labels(cells, basis.by),
        problem=np.where(null[flagged], "null", "out_of_range"),
        share=share[flagged],
    )


def _share_negative_groups(data: pd.DataFrame, basis: _ShareBasis) -> pd.DataFrame:
    """The ``by`` groups of a part that hold a negative value."""
    negative = data.loc[data[PRIMARY_VALUE_COLUMN] < 0]
    if negative.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "record": _NEGATIVE,
            "column": basis.column,
            "group": _group_labels(negative, basis.by),
        }
    ).drop_duplicates(subset=["group"])


def _share_denominators(data: pd.DataFrame, basis: _ShareBasis) -> pd.DataFrame:
    """A part's contribution to each ``by`` group's denominator: sum, |sum| and terms."""
    rows = data
    if basis.where is not None:
        column, value = basis.where
        rows = rows.loc[rows[column] == value]
    if rows.empty:
        return pd.DataFrame()
    frame = pd.DataFrame(
        {
            "group": _group_labels(rows, basis.by),
            "denominator": rows[PRIMARY_VALUE_COLUMN],
            "denominator_abs": rows[PRIMARY_VALUE_COLUMN].abs(),
            "denominator_n": 1,
        }
    )
    return (
        frame.groupby("group", sort=False)
        .sum()
        .reset_index()
        .assign(record=_DENOMINATOR, column=basis.column)
    )


def _share_partial(data: pd.DataFrame, spec: ViewSpec) -> pd.DataFrame:
    """Flagged share cells, negative groups and denominator sums, as tagged records."""
    pieces = [
        piece
        for basis in SHARE_BASES[spec.name]
        for piece in (
            _share_cells(data, spec, basis),
            _share_negative_groups(data, basis),
            _share_denominators(data, basis),
        )
        if not piece.empty
    ]
    if not pieces:
        return pd.DataFrame()
    return pd.concat(pieces, ignore_index=True)


def _fold_share_records(frame: pd.DataFrame) -> pd.DataFrame:
    """Reduce: keep cells, dedupe negative groups, add up denominators per group."""
    frame = _with_record_columns(frame)
    record = frame["record"]
    cells = frame.loc[record == _CELL]
    negatives = frame.loc[record == _NEGATIVE].drop_duplicates(
        subset=["column", "group"]
    )
    denominators = frame.loc[record == _DENOMINATOR]
    if not denominators.empty:
        denominators = (
            denominators.groupby(["column", "group"], sort=False)[
                ["denominator", "denominator_abs", "denominator_n"]
            ]
            .sum()
            .reset_index()
            .assign(record=_DENOMINATOR)
        )
    pieces = [p for p in (cells, negatives, denominators) if not p.empty]
    return pd.concat(pieces, ignore_index=True) if pieces else frame.iloc[0:0]


def _with_record_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """The frame with every record column, absent ones as nulls."""
    missing = [c for c in _SHARE_RECORD_COLUMNS if c not in frame.columns]
    return frame.reindex(columns=[*frame.columns, *missing])


def _classify_share_cells(frame: pd.DataFrame, spec: ViewSpec) -> pd.DataFrame:
    """The flagged cells, each marked ``allowed`` when the pipeline's rule explains it.

    An out-of-range share is allowed in an unbounded column, in a group with a negative
    value, or for a donor outside the reference. A null share is allowed when its
    denominator is absent or zero within rounding (the pipeline's safe_share gives NaN).
    """
    columns = [*spec.keys, "column", "problem", "share", "allowed"]
    frame = _with_record_columns(frame)
    cells = frame.loc[frame["record"] == _CELL].copy()
    if cells.empty:
        return pd.DataFrame(columns=columns)
    negative = set(
        frame.loc[frame["record"] == _NEGATIVE, ["column", "group"]].itertuples(
            index=False, name=None
        )
    )
    denominator_rows = frame.loc[frame["record"] == _DENOMINATOR]
    denominators = {
        (column, group): (total, total_abs, n)
        for column, group, total, total_abs, n in denominator_rows[
            ["column", "group", "denominator", "denominator_abs", "denominator_n"]
        ].itertuples(index=False, name=None)
    }
    bases = {b.column: b for b in SHARE_BASES[spec.name]}
    allowed = []
    for column, group, problem, donor in zip(
        cells["column"], cells["group"], cells["problem"], cells[DONOR], strict=True
    ):
        basis = bases[column]
        if problem == "out_of_range":
            allowed.append(
                not basis.bounded
                or (column, group) in negative
                or donor in basis.outside_reference
            )
            continue
        if (column, group) not in denominators:
            allowed.append(True)
            continue
        total, total_abs, n = denominators[(column, group)]
        tolerance = sum_tolerance(pd.Series([total_abs]), pd.Series([n])).iloc[0]
        allowed.append(abs(total) <= tolerance)
    return cells.assign(allowed=allowed)[columns]


def _share_finalize(
    frame: pd.DataFrame, rows: int, spec: ViewSpec
) -> list[CheckResult]:
    """share_range and share_nulls: ERRORs for cells the pipeline's rule cannot explain."""
    cells = _classify_share_cells(frame, spec)
    results = []
    for problem, check, passed_text, failed_text in (
        (
            "out_of_range",
            "invariants.share_range",
            "Every share within [0, 1] where the rule requires it; {n_allowed:,} "
            "outside it from net flows, unbounded columns or donors outside the "
            "reference",
            "{n_bad:,} shares outside [0, 1] whose group has no negative value: "
            "{by_column}",
        ),
        (
            "null",
            "invariants.share_nulls",
            "No null share with a non-zero denominator; {n_allowed:,} null where the "
            "denominator is zero or absent",
            "{n_bad:,} null shares of {rows:,} rows whose denominator is not zero: "
            "{by_column}",
        ),
    ):
        mine = cells.loc[cells["problem"] == problem]
        bad = mine.loc[~mine["allowed"].astype(bool)]
        fields = {
            "n_allowed": len(mine) - len(bad),
            "n_bad": len(bad),
            "rows": rows,
            "by_column": bad["column"].value_counts().to_dict(),
        }
        results.append(
            build_result(
                check=check,
                view=spec.name,
                failures=len(bad),
                severity=Severity.ERROR,
                passed_message=passed_text.format(**fields),
                failed_message=failed_text.format(**fields),
                details=_by_abs(bad.drop(columns="allowed"), "share")
                if problem == "out_of_range"
                else bad.drop(columns="allowed"),
            )
        )
    return results


SHARE_RANGE = _Invariant(
    views=frozenset(SHARE_BASES),
    partial=_share_partial,
    finalize=_share_finalize,
    reduce=_fold_share_records,
)


@dataclass(frozen=True)
class _ShareIdentity:
    """Shares in ``column`` that sum to 1 per ``by`` over the rows ``where`` selects."""

    label: str
    column: str
    by: tuple[str, ...]
    where: tuple[str, str] | None
    tolerance: float = SHARE_SUM_TOLERANCE


SHARE_IDENTITIES: dict[str, tuple[_ShareIdentity, ...]] = {
    "financing_view": (
        _ShareIdentity(
            f"pct_of_total_oda of {TOTAL_ODA}",
            "pct_of_total_oda",
            by=(YEAR, DONOR, "type"),
            where=(INDICATOR, TOTAL_ODA),
        ),
    ),
    "recipients_view": (
        _ShareIdentity(
            f"pct_total_donor at {ODA_ELIGIBLE}",
            "pct_total_donor",
            by=(YEAR, DONOR),
            where=(RECIPIENT, ODA_ELIGIBLE),
        ),
        _ShareIdentity(
            f"pct_total_recipient of {ALL_BILATERAL_DONORS}",
            "pct_total_recipient",
            by=(YEAR, RECIPIENT),
            where=(DONOR, ALL_BILATERAL_DONORS),
        ),
    ),
    "gender_view": (
        _ShareIdentity(
            "pct_of_bilateral_allocable over the four markers",
            "pct_of_bilateral_allocable",
            by=(YEAR, DONOR, RECIPIENT),
            where=None,
        ),
    ),
    "sectors_view": (
        _ShareIdentity(
            f"pct_total_donor at {ODA_ELIGIBLE}",
            "pct_total_donor",
            by=(YEAR, DONOR),
            where=(RECIPIENT, ODA_ELIGIBLE),
            tolerance=SECTORS_SHARE_SUM_TOLERANCE,
        ),
    ),
}


def _share_sum_partial(data: pd.DataFrame, spec: ViewSpec) -> pd.DataFrame:
    """Every group's share sum, per identity. Each group lies within one recipient part."""
    sums = []
    for identity in SHARE_IDENTITIES.get(spec.name, ()):
        rows = data
        if identity.where is not None:
            column, value = identity.where
            rows = rows.loc[rows[column] == value]
        if rows.empty:
            continue
        sums.append(
            rows.groupby(list(identity.by), observed=True)[identity.column]
            .agg(share_sum=lambda s: s.sum(min_count=1), rows="size")
            .dropna(subset=["share_sum"])
            .reset_index()
            .assign(identity=identity.label)
        )
    if not sums:
        return pd.DataFrame()
    return pd.concat(sums, ignore_index=True)


def _share_sum_finalize(
    frame: pd.DataFrame, rows: int, spec: ViewSpec
) -> list[CheckResult]:
    """One ERROR result for the view's share identities.

    An identity with no group to check fails too: its ``where`` rows are missing, so the
    identity would otherwise pass without checking anything.
    """
    labels = [i.label for i in SHARE_IDENTITIES[spec.name]]
    checked = frame["identity"].value_counts().to_dict() if len(frame) else {}
    unchecked = [label for label in labels if not checked.get(label)]
    bad = (
        frame.loc[(frame["share_sum"] - 1).abs() > _identity_tolerances(frame, spec)]
        if len(frame)
        else frame
    )
    n = len(bad)
    by_identity = bad["identity"].value_counts().to_dict() if n else {}
    problems = []
    if n:
        problems.append(f"{n:,} groups whose shares do not sum to 1: {by_identity}")
    if unchecked:
        problems.append(f"no rows to check for {unchecked}")
    return [
        build_result(
            check="invariants.share_sums",
            view=spec.name,
            failures=n + len(unchecked),
            severity=Severity.ERROR,
            passed_message=f"Shares sum to 1 in {sum(checked.values()):,} groups: {labels}",
            failed_message="; ".join(problems),
            details=(
                bad.assign(off_by=bad["share_sum"] - 1).pipe(_by_abs, "off_by")
                if n
                else None
            ),
        )
    ]


def _identity_tolerances(frame: pd.DataFrame, spec: ViewSpec) -> pd.Series:
    """Each group's tolerance, from its identity."""
    tolerances = {i.label: i.tolerance for i in SHARE_IDENTITIES[spec.name]}
    return frame["identity"].map(tolerances)


SHARE_SUMS = _Invariant(
    views=frozenset(SHARE_IDENTITIES),
    partial=_share_sum_partial,
    finalize=_share_sum_finalize,
)


# --- Currencies ---------------------------------------------------------------------------


def _value_column(currency: str, price: str) -> str:
    """The value column for a currency and price, e.g. value_eur_constant."""
    return f"value_{currency.lower()}_{price}"


def _currency_ratio_partial(data: pd.DataFrame, spec: ViewSpec) -> pd.DataFrame:
    """Per (donor, year, currency): min and max constant/current ratio, and row count.

    Rows where one side is null have no ratio and are left out here. The blocking
    contracts.value_null_pairs check fails them.
    """
    rows = data.loc[
        ~data[DONOR].isin(AGGREGATE_DONORS)
        & (data[PRIMARY_VALUE_COLUMN].abs() >= CURRENCY_RATIO_MIN_UNITS)
    ]
    ranges = []
    for currency in CURRENCIES:
        current = rows[_value_column(currency, "current")]
        ratio = rows[_value_column(currency, "constant")] / current.where(current != 0)
        ranges.append(
            pd.DataFrame({DONOR: rows[DONOR], YEAR: rows[YEAR], "ratio": ratio})
            .dropna(subset=["ratio"])
            .groupby([DONOR, YEAR], observed=True)["ratio"]
            .agg(ratio_min="min", ratio_max="max", rows="size")
            .reset_index()
            .assign(currency=currency)
        )
    return pd.concat(ranges, ignore_index=True)


def _fold_ratio_ranges(frame: pd.DataFrame) -> pd.DataFrame:
    """Reduce ratio ranges: min of mins, max of maxes, sum of rows."""
    return (
        frame.groupby([DONOR, YEAR, "currency"], observed=True)
        .agg(
            ratio_min=("ratio_min", "min"),
            ratio_max=("ratio_max", "max"),
            rows=("rows", "sum"),
        )
        .reset_index()
    )


def _currency_ratio_finalize(
    frame: pd.DataFrame, rows: int, spec: ViewSpec
) -> list[CheckResult]:
    """WARNING for (donor, year, currency) whose constant/current ratio varies."""
    frame = _fold_ratio_ranges(frame) if len(frame) else frame
    spread = (frame["ratio_max"] - frame["ratio_min"]) / np.maximum(
        frame["ratio_max"].abs(), frame["ratio_min"].abs()
    )
    bad = frame.assign(relative_spread=spread).loc[spread > CURRENCY_RATIO_TOLERANCE]
    by_currency = bad["currency"].value_counts().to_dict()
    return [
        build_result(
            check="invariants.currency_ratio",
            view=spec.name,
            failures=len(bad),
            severity=Severity.WARNING,
            passed_message=(
                "constant/current is one ratio per donor, year and currency "
                f"(to {CURRENCY_RATIO_TOLERANCE:.0e})"
            ),
            failed_message=(
                f"{len(bad):,} (donor, year, currency) with more than one "
                f"constant/current ratio: {by_currency}"
            ),
            details=bad.sort_values("relative_spread", ascending=False),
        )
    ]


CURRENCY_RATIO = _Invariant(
    views=GROUP_SUMS.views,
    partial=_currency_ratio_partial,
    finalize=_currency_ratio_finalize,
    reduce=_fold_ratio_ranges,
)


def _base_year_partial(data: pd.DataFrame, spec: ViewSpec) -> pd.DataFrame:
    """Base-year cells where constant differs from current beyond tolerance."""
    rows = data.loc[data[YEAR] == spec.time["base"]]
    keys = list(spec.keys)
    cells = []
    for currency in CURRENCIES:
        current = rows[_value_column(currency, "current")]
        constant = rows[_value_column(currency, "constant")]
        tolerance = BASE_YEAR_RELATIVE_TOLERANCE * current.abs() + ROUNDING_UNIT
        # A null against a number differs, since NaN > tolerance alone would read as equal.
        bad = ((constant - current).abs() > tolerance) | (
            constant.isna() != current.isna()
        )
        if bad.any():
            cells.append(
                rows.loc[bad, keys].assign(
                    currency=currency, current=current[bad], constant=constant[bad]
                )
            )
    if not cells:
        return pd.DataFrame()
    return pd.concat(cells, ignore_index=True)


def _base_year_finalize(
    frame: pd.DataFrame, rows: int, spec: ViewSpec
) -> list[CheckResult]:
    """ERROR for base-year cells where constant prices differ from current, or one is null."""
    n = len(frame)
    base = spec.time["base"]
    by_currency = frame["currency"].value_counts().to_dict() if n else {}
    return [
        build_result(
            check="invariants.base_year_prices",
            view=spec.name,
            failures=n,
            severity=Severity.ERROR,
            passed_message=f"Constant equals current in the base year {base}",
            failed_message=(
                f"{n:,} cells where constant differs from current in {base}: "
                f"{by_currency}"
            ),
            details=(
                frame.assign(difference=frame["constant"] - frame["current"]).pipe(
                    _by_abs, "difference"
                )
                if n
                else None
            ),
        )
    ]


BASE_YEAR_PRICES = _Invariant(
    views=GROUP_SUMS.views,
    partial=_base_year_partial,
    finalize=_base_year_finalize,
)


# --- Running ------------------------------------------------------------------------------

INVARIANTS: tuple[_Invariant, ...] = (
    GROUP_SUMS,
    GROUP_MEMBERS_PRESENT,
    RECIPIENT_SUMS,
    SHARE_RANGE,
    SHARE_SUMS,
    CURRENCY_RATIO,
    BASE_YEAR_PRICES,
)


def _fold(
    acc: pd.DataFrame | None, part: pd.DataFrame, invariant: _Invariant
) -> pd.DataFrame:
    """Add one partial to the accumulator and reduce."""
    if acc is None or acc.empty:
        return invariant.reduce(part) if not part.empty else part
    if part.empty:
        return acc
    return invariant.reduce(pd.concat([acc, part], ignore_index=True))


def _run(
    invariants: Iterable[_Invariant], parts: Iterable[LoadedView]
) -> list[CheckResult]:
    """Run invariants over the parts of one view in a single pass."""
    spec: ViewSpec | None = None
    rows = 0
    selected: list[_Invariant] = []
    accumulators: list[pd.DataFrame | None] = []
    for part in parts:
        if spec is None:
            spec = part.spec
            selected = [i for i in invariants if spec.name in i.views]
            accumulators = [None] * len(selected)
        elif part.spec.name != spec.name:
            raise ValueError(
                f"Parts of different views: {spec.name} and {part.spec.name}"
            )
        rows += len(part.data)
        for index, invariant in enumerate(selected):
            accumulators[index] = _fold(
                accumulators[index], invariant.partial(part.data, spec), invariant
            )
    if spec is None:
        raise ValueError("run_invariants needs at least one part")
    return [
        result
        for invariant, acc in zip(selected, accumulators, strict=True)
        for result in invariant.finalize(
            acc if acc is not None else pd.DataFrame(), rows, spec
        )
    ]


def run_invariants(parts: Iterable[LoadedView]) -> list[CheckResult]:
    """Run every invariant that applies to a view, in one pass over its parts.

    Args:
        parts: The view whole (``[load_view(name, source)]``), or its recipient partitions
            (``v for _, v in iter_partitions(name, source)``). All parts must be of the
            same view, and each must hold every donor for its recipients.

    Returns:
        The results of every applicable invariant.

    Raises:
        ValueError: No parts, or parts of different views.
    """
    return _run(INVARIANTS, parts)


def _check(invariant: _Invariant, view: LoadedView) -> list[CheckResult]:
    """Run one invariant on one view; [] if it does not apply to the view."""
    return _run([invariant], [view])


def check_group_sums(view: LoadedView) -> list[CheckResult]:
    """Each donor group equals the sum of its members, in value_usd_current (ERROR).

    Compared per view key without donor. A missing group or member row counts as 0.
    Financing skips Grants and Non-grants; "EU27 & EU Institutions" is checked only where
    the view builds it as a plain sum (gender; sectors' Bilateral).
    """
    return _check(GROUP_SUMS, view)


def check_group_members_present(view: LoadedView) -> list[CheckResult]:
    """Every config member of each published donor group has rows (WARNING)."""
    return _check(GROUP_MEMBERS_PRESENT, view)


def check_recipient_sums(view: LoadedView) -> list[CheckResult]:
    """Countries vs "ODA eligible countries", per key without recipient.

    Gender and sectors: equal (ERROR). Recipients: never above (ERROR), and short by at
    most 1% of the total for each reporting donor outside RECIPIENT_GAP_KNOWN_DONORS
    (WARNING).
    """
    return _check(RECIPIENT_SUMS, view)


def check_share_range(view: LoadedView) -> list[CheckResult]:
    """Shares in [0, 1] and populated, by the rule in SHARE_BASES (two ERROR results).

    Range: a share outside [0, 1] fails unless its column is unbounded (financing), its
    ``by`` group holds a negative value, or its donor is outside the reference. Nulls: a
    null share fails unless its denominator is absent or zero within rounding.
    """
    return _check(SHARE_RANGE, view)


def check_share_sums(view: LoadedView) -> list[CheckResult]:
    """Each view's share identities sum to 1 (ERROR); see SHARE_IDENTITIES."""
    return _check(SHARE_SUMS, view)


def check_currency_ratio(view: LoadedView) -> list[CheckResult]:
    """One constant/current ratio per (donor, year, currency) across rows (WARNING)."""
    return _check(CURRENCY_RATIO, view)


def check_base_year_prices(view: LoadedView) -> list[CheckResult]:
    """Constant equals current in the base year, for every currency (ERROR)."""
    return _check(BASE_YEAR_PRICES, view)
