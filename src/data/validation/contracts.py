"""Contracts: the shape every published view must have, checked on one whole view.

Every check is ``check_<x>(view) -> list[CheckResult]`` and fails as an ERROR, except a
few nulls in the seven non-primary value columns, which are a WARNING (a missing
conversion factor for one donor-year must stay visible without blocking). Nulls above
VALUE_NULL_ERROR_FRACTION of a column's rows are an ERROR.

Magnitude has a floor as well as a ceiling: each view's anchor (DAC countries' key total
in the end year) must lie in [ANCHOR_MIN_UNITS, ANCHOR_MAX_UNITS], and pct_of_gni within
+/-PCT_OF_GNI_LIMIT, so a units slip in either direction blocks. On the anchor rows,
each other currency's current total per US dollar must lie in [CURRENCY_PER_USD_MIN,
CURRENCY_PER_USD_MAX], so a slip confined to one currency blocks too.

``run_contracts(view)`` runs them all. It needs the whole view in memory: for sectors that
means ``load_view("sectors_view", source)``, not a partition.
"""

from collections.abc import Iterable

import numpy as np
import pandas as pd

from src.data.config import (
    DAC_COUNTRIES_NAME,
    FINANCING_TYPES,
    ODA_ELIGIBLE,
    TOTAL_ODA,
)
from src.data.validation.io import LoadedView
from src.data.validation.models import CheckResult, Severity
from src.data.validation.views import CRITICAL_DONORS, CURRENCY_PAIRS

# Units guard: a value this large means millions were scaled twice, or worse.
MAX_SANE_VALUE: float = 1e15

# A value column with nulls in more than this fraction of its rows blocks: a missing
# conversion factor for one small donor-year touches far fewer rows, while a broken
# currency or price step nulls most of the column.
VALUE_NULL_ERROR_FRACTION: float = 0.001

# The anchor: DAC countries' key total in the view's end year, in current USD units. It
# ran between US$95bn (gender, 2019) and US$240bn (sectors, 2023) across the four views
# in 2019-2025; this band leaves room for a halving or a doubling and still blocks a
# thousandfold units slip either way.
ANCHOR_MIN_UNITS: float = 5e10
ANCHOR_MAX_UNITS: float = 5e11
ANCHOR_DONOR: str = DAC_COUNTRIES_NAME
# Per view, the (column, value) rows the anchor sums besides donor and end year. Financing
# is checked per type; the recipient views sum every indicator (and sector).
ANCHOR_ROWS: dict[str, tuple[str, str]] = {
    "financing_view": ("indicator_name", TOTAL_ODA),
    "recipients_view": ("recipient_name", ODA_ELIGIBLE),
    "gender_view": ("recipient_name", ODA_ELIGIBLE),
    "sectors_view": ("recipient_name", ODA_ELIGIBLE),
}

# Units of EUR, GBP or CAD per US dollar on the anchor rows. Annual rates in 1990-2025
# ran from about 0.5 (GBP) to 1.6 (CAD); this band blocks a units slip in one currency.
CURRENCY_PER_USD_MIN: float = 0.4
CURRENCY_PER_USD_MAX: float = 2.5

# ODA/GNI as a fraction. No donor in the 1990-2025 window gave more than 1.5% of GNI
# (Sweden 2015, 1.42%), and the most negative indicator share is -0.2%; 3% either way
# leaves headroom and still blocks a percent-vs-fraction slip (x100).
GNI_SHARE_COLUMN: str = "pct_of_gni"
PCT_OF_GNI_LIMIT: float = 0.03

# The value column the dashboard leads with; every other one is derived from it.
PRIMARY_VALUE_COLUMN: str = "value_usd_current"

# Label columns whose values options.json lists, by the same key.
OPTION_LIST_COLUMNS: tuple[str, ...] = (
    "donor_name",
    "recipient_name",
    "indicator_name",
    "sector_name",
)
SUB_SECTOR_COLUMN: str = "sub_sector_name"
# Sectors list their sub-sectors per sector rather than as a flat list.
SUB_SECTORS_KEY: str = "sub_sectors_by_sector"
YEAR_KEYS: tuple[str, ...] = ("start", "end", "base")
# The financing "type" labels the frontend filters on: exactly these, no others.
TYPE_COLUMN: str = "type"
FINANCING_TYPE_VALUES: frozenset[str] = frozenset(FINANCING_TYPES.values())

_INT_DTYPES: frozenset[str] = frozenset({"int8", "int16", "int32", "int64"})
_FLOAT_DTYPES: frozenset[str] = frozenset({"float32", "float64"})


def build_result(
    *,
    check: str,
    view: str,
    failures: int,
    severity: Severity,
    passed_message: str,
    failed_message: str,
    details: pd.DataFrame | None = None,
) -> CheckResult:
    """Build a CheckResult that fails when ``failures`` is positive.

    Shared by contracts, invariants and anomalies. Only ERROR results block. The CLI makes
    ERRORs block under --strict regardless.

    Args:
        check: Dotted check name.
        view: View name.
        failures: Number of offending items; 0 means the check passed.
        severity: Severity if the check fails.
        passed_message: Message when it passes.
        failed_message: Message when it fails.
        details: Offending rows, kept only on failure.
    """
    passed = failures == 0
    return CheckResult(
        check=check,
        view=view,
        passed=passed,
        severity=severity,
        message=passed_message if passed else failed_message,
        details=None if passed else details,
        blocking=severity is Severity.ERROR,
    )


def _dtypes_compatible(actual: str, expected: str) -> bool:
    """Whether a dtype matches the expected one, allowing int and float width changes."""
    actual, expected = actual.lower(), expected.lower()
    return (
        actual == expected
        or (actual in _INT_DTYPES and expected in _INT_DTYPES)
        or (actual in _FLOAT_DTYPES and expected in _FLOAT_DTYPES)
    )


def check_non_empty(view: LoadedView) -> list[CheckResult]:
    """The view has at least one row."""
    rows = len(view.data)
    return [
        build_result(
            check="contracts.non_empty",
            view=view.spec.name,
            failures=int(rows == 0),
            severity=Severity.ERROR,
            passed_message=f"{rows:,} rows",
            failed_message="The view has no rows",
        )
    ]


def check_columns(view: LoadedView) -> list[CheckResult]:
    """Every required column is present with its expected dtype (int/float width aside)."""
    problems = []
    for column, expected in view.spec.dtypes.items():
        if column not in view.data.columns:
            problems.append((column, expected, "missing"))
            continue
        actual = str(view.data[column].dtype)
        if not _dtypes_compatible(actual, expected):
            problems.append((column, expected, actual))
    details = pd.DataFrame(problems, columns=["column", "expected", "actual"])
    return [
        build_result(
            check="contracts.columns",
            view=view.spec.name,
            failures=len(problems),
            severity=Severity.ERROR,
            passed_message=f"All {len(view.spec.dtypes)} required columns present",
            failed_message=(
                f"{len(problems)} required columns missing or of the wrong dtype: "
                f"{[p[0] for p in problems]}"
            ),
            details=details,
        )
    ]


def has_required_columns(view: LoadedView) -> bool:
    """Whether every required column is present, so the other checks can run."""
    return set(view.spec.required_columns) <= set(view.data.columns)


def check_keys(view: LoadedView) -> list[CheckResult]:
    """Keys are populated (no nulls, no blank labels) and unique."""
    data, keys, name = view.data, list(view.spec.keys), view.spec.name

    unpopulated = data[keys].isna().any(axis=1)
    for key in keys:
        if pd.api.types.is_string_dtype(data[key]):
            unpopulated |= data[key].fillna("").str.strip().eq("")
    duplicated = data.duplicated(subset=keys, keep=False)
    n_unpopulated = int(unpopulated.sum())
    n_duplicated = int(duplicated.sum())

    return [
        build_result(
            check="contracts.keys_populated",
            view=name,
            failures=n_unpopulated,
            severity=Severity.ERROR,
            passed_message=f"No null or blank values in {keys}",
            failed_message=f"{n_unpopulated:,} rows with a null or blank key",
            details=data.loc[unpopulated, keys],
        ),
        build_result(
            check="contracts.unique_keys",
            view=name,
            failures=n_duplicated,
            severity=Severity.ERROR,
            passed_message=f"Rows unique on {keys}",
            failed_message=f"{n_duplicated:,} rows share their key with another row",
            details=data.loc[duplicated, keys].sort_values(keys),
        ),
    ]


def check_years(view: LoadedView) -> list[CheckResult]:
    """Every year lies in the spec's window, and the window's end year has rows."""
    start, end = view.spec.time["start"], view.spec.time["end"]
    years = view.data["year"]
    outside = ~years.between(start, end)
    n_outside = int(outside.sum())
    end_missing = not years.eq(end).any()

    problems = []
    if n_outside:
        problems.append(f"{n_outside:,} rows outside {start}-{end}")
    if end_missing:
        problems.append(f"no rows for the end year {end}")
    return [
        build_result(
            check="contracts.year_window",
            view=view.spec.name,
            failures=n_outside + int(end_missing),
            severity=Severity.ERROR,
            passed_message=f"Years within {start}-{end}, end year present",
            failed_message="; ".join(problems),
            details=(
                years[outside]
                .value_counts()
                .rename_axis("year")
                .reset_index(name="rows")
            ),
        )
    ]


def _null_counts(data: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Per-column null counts, keeping only columns that have nulls."""
    counts = pd.DataFrame(
        {"column": list(columns), "nulls": [int(data[c].isna().sum()) for c in columns]}
    )
    return counts.loc[counts["nulls"] > 0].reset_index(drop=True)


def _null_severity(counts: pd.DataFrame, rows: int) -> Severity:
    """ERROR when any column's nulls exceed VALUE_NULL_ERROR_FRACTION of rows."""
    worst = int(counts["nulls"].max()) if len(counts) else 0
    return (
        Severity.ERROR
        if worst > VALUE_NULL_ERROR_FRACTION * max(rows, 1)
        else Severity.WARNING
    )


def check_values(view: LoadedView) -> list[CheckResult]:
    """Value columns are populated, paired and of sane magnitude.

    Four results: nulls in value_usd_current (ERROR); nulls in the other seven value
    columns (WARNING, an ERROR above VALUE_NULL_ERROR_FRACTION of rows in any column);
    a constant value null where its current value is not, or the reverse (ERROR); any
    non-finite value or one with absolute size above MAX_SANE_VALUE (ERROR).
    """
    data, spec = view.data, view.spec
    keys = list(spec.keys)
    others = [c for c in spec.value_columns if c != PRIMARY_VALUE_COLUMN]

    primary_null = data[PRIMARY_VALUE_COLUMN].isna()
    n_primary_null = int(primary_null.sum())

    other_counts = _null_counts(data, others)
    other_null = data[others].isna().any(axis=1)
    counts_text = ", ".join(
        f"{r.column}: {r.nulls:,}" for r in other_counts.itertuples()
    )

    unpaired = pd.DataFrame(
        {
            f"{current}/{constant}": data[current].isna() != data[constant].isna()
            for current, constant in CURRENCY_PAIRS
        },
        index=data.index,
    )
    unpaired_counts = unpaired.sum()
    unpaired_counts = unpaired_counts[unpaired_counts > 0]
    unpaired_rows = unpaired.any(axis=1)

    values = data[list(spec.value_columns)]
    insane = (~np.isfinite(values) & values.notna()) | (values.abs() > MAX_SANE_VALUE)
    insane_rows = insane.any(axis=1)
    n_insane = int(insane.to_numpy().sum())

    return [
        build_result(
            check="contracts.primary_value_populated",
            view=spec.name,
            failures=n_primary_null,
            severity=Severity.ERROR,
            passed_message=f"{PRIMARY_VALUE_COLUMN} has no nulls",
            failed_message=f"{n_primary_null:,} nulls in {PRIMARY_VALUE_COLUMN}",
            details=data.loc[primary_null, keys],
        ),
        build_result(
            check="contracts.values_populated",
            view=spec.name,
            failures=int(other_counts["nulls"].sum()),
            severity=_null_severity(other_counts, len(data)),
            passed_message="No nulls in the other value columns",
            failed_message=(
                f"Nulls in value columns of {len(data):,} rows ({counts_text}); an "
                f"ERROR above {VALUE_NULL_ERROR_FRACTION:.1%} of rows in a column"
            ),
            details=data.loc[other_null, [*keys, *others]],
        ),
        build_result(
            check="contracts.value_null_pairs",
            view=spec.name,
            failures=int(unpaired_counts.sum()),
            severity=Severity.ERROR,
            passed_message="Every constant value is null exactly where its current one is",
            failed_message=(
                "Current and constant values null on different rows: "
                f"{unpaired_counts.to_dict()}"
            ),
            details=data.loc[unpaired_rows, [*keys, *spec.value_columns]],
        ),
        build_result(
            check="contracts.value_magnitude",
            view=spec.name,
            failures=n_insane,
            severity=Severity.ERROR,
            passed_message=f"Every value finite and at most {MAX_SANE_VALUE:.0e} units",
            failed_message=(
                f"{n_insane:,} values non-finite or above {MAX_SANE_VALUE:.0e} units"
            ),
            details=data.loc[insane_rows, [*keys, *spec.value_columns]],
        ),
    ]


def _anchor_totals(view: LoadedView) -> pd.DataFrame:
    """The anchor per series in the end year: one row (per type for financing).

    Columns: the series column (financing only), rows, and each current value column.
    """
    column, value = ANCHOR_ROWS[view.spec.name]
    data = view.data
    end = view.spec.time["end"]
    rows = data.loc[
        (data["donor_name"] == ANCHOR_DONOR)
        & (data[column] == value)
        & (data["year"] == end)
    ]
    current = [c for c, _ in CURRENCY_PAIRS]
    series = [TYPE_COLUMN] if TYPE_COLUMN in view.spec.keys else []
    if not series:
        totals = rows[current].sum().to_frame().T.assign(rows=len(rows))
        return totals.loc[totals["rows"] > 0, ["rows", *current]]
    grouped = rows.groupby(series, observed=True)
    return (
        grouped[current]
        .sum()
        .join(grouped.size().rename("rows"))
        .reset_index()[[*series, "rows", *current]]
    )


def check_anchor(view: LoadedView) -> list[CheckResult]:
    """DAC countries' end-year key total lies in [ANCHOR_MIN_UNITS, ANCHOR_MAX_UNITS].

    The floor that MAX_SANE_VALUE lacks: values scaled down by a units slip pass every
    other check. Missing anchor rows fail too.
    """
    column, value = ANCHOR_ROWS[view.spec.name]
    end = view.spec.time["end"]
    what = f"{ANCHOR_DONOR} {value} in {end}"
    totals = _anchor_totals(view)
    band = f"[{ANCHOR_MIN_UNITS:.0e}, {ANCHOR_MAX_UNITS:.0e}]"
    if totals.empty:
        failures, message = 1, f"No rows for the anchor {what}"
    else:
        outside = ~totals[PRIMARY_VALUE_COLUMN].between(
            ANCHOR_MIN_UNITS, ANCHOR_MAX_UNITS
        )
        failures = int(outside.sum())
        message = (
            f"{failures} anchor totals for {what} outside {band} units: "
            f"{totals.loc[outside, PRIMARY_VALUE_COLUMN].tolist()}"
        )
    shown = ", ".join(f"{v:,.0f}" for v in totals[PRIMARY_VALUE_COLUMN])
    return [
        build_result(
            check="contracts.anchor",
            view=view.spec.name,
            failures=failures,
            severity=Severity.ERROR,
            passed_message=f"{what}: {shown} units, within {band}",
            failed_message=message,
            details=totals,
        )
    ]


def check_anchor_currencies(view: LoadedView) -> list[CheckResult]:
    """Each non-USD current anchor total per USD lies in the CURRENCY_PER_USD band.

    The anchor band checks value_usd_current only; a units slip in one currency's
    conversion would pass it and every other blocking check. Missing anchor rows fail.
    """
    end = view.spec.time["end"]
    totals = _anchor_totals(view)
    band = f"[{CURRENCY_PER_USD_MIN}, {CURRENCY_PER_USD_MAX}]"
    others = [c for c, _ in CURRENCY_PAIRS if c != PRIMARY_VALUE_COLUMN]
    series = [c for c in totals.columns if c == TYPE_COLUMN]
    ratios = totals[series].assign(
        **{
            c: totals[c]
            / totals[PRIMARY_VALUE_COLUMN].where(totals[PRIMARY_VALUE_COLUMN] != 0)
            for c in others
        }
    )
    outside = ~ratios[others].apply(
        lambda r: r.between(CURRENCY_PER_USD_MIN, CURRENCY_PER_USD_MAX)
    )
    failures = int(outside.to_numpy().sum()) if len(totals) else 1
    shown = "; ".join(
        ", ".join(f"{c}: {r[c]:.3g}" for c in others) for _, r in ratios.iterrows()
    )
    return [
        build_result(
            check="contracts.anchor_currencies",
            view=view.spec.name,
            failures=failures,
            severity=Severity.ERROR,
            passed_message=f"Anchor in {end}, units per USD within {band}: {shown}",
            failed_message=(
                f"No anchor rows in {end}"
                if totals.empty
                else f"{failures} anchor currency totals per USD outside {band}: "
                f"{shown}"
            ),
            details=ratios,
        )
    ]


def check_gni_share(view: LoadedView) -> list[CheckResult]:
    """pct_of_gni within +/-PCT_OF_GNI_LIMIT, and set for critical donors' end year.

    Two ERROR results; nothing for a view without pct_of_gni. Other null pct_of_gni
    (donors or years without GNI in DAC1, groups whose GNI-reporting members lack an
    indicator) are structural and only counted in the passing message.
    """
    if GNI_SHARE_COLUMN not in view.spec.share_columns:
        return []
    data, keys, name = view.data, list(view.spec.keys), view.spec.name
    share = data[GNI_SHARE_COLUMN]
    outside = share.notna() & (share.abs() > PCT_OF_GNI_LIMIT)
    n_outside = int(outside.sum())

    end = view.spec.time["end"]
    critical_total = (
        data["donor_name"].isin(CRITICAL_DONORS)
        & (data["indicator_name"] == TOTAL_ODA)
        & (data["year"] == end)
    )
    unset = critical_total & share.isna()
    n_unset = int(unset.sum())
    return [
        build_result(
            check="contracts.gni_share_range",
            view=name,
            failures=n_outside,
            severity=Severity.ERROR,
            passed_message=f"Every {GNI_SHARE_COLUMN} within +/-{PCT_OF_GNI_LIMIT}",
            failed_message=(
                f"{n_outside:,} {GNI_SHARE_COLUMN} beyond +/-{PCT_OF_GNI_LIMIT} "
                f"(max |value| {share.abs().max():.4g}): a percent read as a fraction?"
            ),
            details=data.loc[outside, [*keys, GNI_SHARE_COLUMN]],
        ),
        build_result(
            check="contracts.gni_share_populated",
            view=name,
            failures=n_unset,
            severity=Severity.ERROR,
            passed_message=(
                f"{GNI_SHARE_COLUMN} set on every critical donor's {TOTAL_ODA} in {end}; "
                f"{int(share.isna().sum()):,} nulls elsewhere (no GNI in DAC1)"
            ),
            failed_message=(
                f"{n_unset:,} critical donor {TOTAL_ODA} rows in {end} without "
                f"{GNI_SHARE_COLUMN}"
            ),
            details=data.loc[unset, keys],
        ),
    ]


def check_types(view: LoadedView) -> list[CheckResult]:
    """Financing's type column holds exactly FINANCING_TYPE_VALUES; [] for other views."""
    if TYPE_COLUMN not in view.spec.keys:
        return []
    present = set(view.data[TYPE_COLUMN].dropna().unique())
    unknown = sorted(present - FINANCING_TYPE_VALUES)
    absent = sorted(FINANCING_TYPE_VALUES - present)
    problems = [(t, "unknown") for t in unknown] + [(t, "absent") for t in absent]
    return [
        build_result(
            check="contracts.types",
            view=view.spec.name,
            failures=len(problems),
            severity=Severity.ERROR,
            passed_message=f"{TYPE_COLUMN} is exactly {sorted(FINANCING_TYPE_VALUES)}",
            failed_message=(
                f"{TYPE_COLUMN} values not {sorted(FINANCING_TYPE_VALUES)}: "
                f"unknown {unknown}, absent {absent}"
            ),
            details=pd.DataFrame(problems, columns=[TYPE_COLUMN, "problem"]),
        )
    ]


def check_critical_donors(view: LoadedView) -> list[CheckResult]:
    """Every donor in CRITICAL_DONORS has rows in the end year (per type in financing).

    A donor missing from the latest year leaves the dashboard's default year without it,
    while its history still passes an any-year check.
    """
    data = view.data
    end = view.spec.time["end"]
    latest = data.loc[data["year"] == end]
    by_type = TYPE_COLUMN in view.spec.keys
    groups = (
        latest.groupby(TYPE_COLUMN, observed=True)["donor_name"]
        if by_type
        else [("all", latest["donor_name"])]
    )
    missing = [
        (series, donor)
        for series, donors in groups
        for donor in CRITICAL_DONORS
        if donor not in set(donors.dropna())
    ]
    if by_type:
        # a type with no end-year rows at all misses every critical donor
        covered = set(latest[TYPE_COLUMN].dropna().unique())
        missing += [
            (t, donor)
            for t in sorted(FINANCING_TYPE_VALUES - covered)
            for donor in CRITICAL_DONORS
        ]
    details = pd.DataFrame(missing, columns=["series", "donor_name"])
    by_series = details.groupby("series")["donor_name"].apply(list).to_dict()
    return [
        build_result(
            check="contracts.critical_donors",
            view=view.spec.name,
            failures=len(missing),
            severity=Severity.ERROR,
            passed_message=(
                f"All {len(CRITICAL_DONORS)} critical donors have rows in {end}"
                + (" for every type" if by_type else "")
            ),
            failed_message=f"Critical donors without rows in {end}: {by_series}",
            details=details,
        )
    ]


def _option_values(options: dict, column: str) -> set[str] | None:
    """The values options.json lists for a label column, or None if it lists none."""
    if column == SUB_SECTOR_COLUMN:
        by_sector = options.get(SUB_SECTORS_KEY)
        if not isinstance(by_sector, dict):
            return None
        return {sub for subs in by_sector.values() for sub in subs}
    listed = options.get(column)
    return set(listed) if isinstance(listed, list) else None


def _option_columns(view: LoadedView) -> list[str]:
    """The view's label columns that options.json must list."""
    return [c for c in (*OPTION_LIST_COLUMNS, SUB_SECTOR_COLUMN) if c in view.spec.keys]


def _sub_sector_pairs(view: LoadedView) -> tuple[set, set]:
    """(sector, sub-sector) pairs in options and in the data."""
    by_sector = view.options.get(SUB_SECTORS_KEY) or {}
    listed = {(sector, sub) for sector, subs in by_sector.items() for sub in subs}
    in_data = set(
        view.data[["sector_name", SUB_SECTOR_COLUMN]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    return listed, in_data


def _membership_problems(view: LoadedView) -> tuple[list[tuple], list[tuple]]:
    """(listed values with no rows, row values not listed), each as (column, value)."""
    unlisted_columns: list[tuple] = []
    no_rows: list[tuple] = []
    rows_unlisted: list[tuple] = []
    for column in _option_columns(view):
        listed = _option_values(view.options, column)
        if listed is None:
            unlisted_columns.append((column, "<no list in options.json>"))
            continue
        in_data = set(view.data[column].dropna().unique())
        no_rows += [(column, v) for v in sorted(listed - in_data)]
        rows_unlisted += [(column, v) for v in sorted(in_data - listed)]

    if SUB_SECTOR_COLUMN in view.spec.keys and SUB_SECTORS_KEY in view.options:
        listed_pairs, data_pairs = _sub_sector_pairs(view)
        no_rows += [
            ("sector_name/sub_sector_name", p)
            for p in sorted(listed_pairs - data_pairs)
        ]
        rows_unlisted += [
            ("sector_name/sub_sector_name", p)
            for p in sorted(data_pairs - listed_pairs)
        ]
    return no_rows, unlisted_columns + rows_unlisted


def _default_problems(view: LoadedView) -> list[tuple]:
    """Defaults that are not members of their option list, as (key, value)."""
    defaults = view.options.get("defaults")
    if not isinstance(defaults, dict):
        return [("defaults", "<missing or not an object>")]
    problems = []
    for key, value in defaults.items():
        listed = _option_values(view.options, key) or set()
        values = value if isinstance(value, list) else [value]
        problems += [(key, v) for v in values if v not in listed]
    return problems


def _year_problems(view: LoadedView) -> list[tuple]:
    """Disagreements between options year, the spec window and the data, as tuples."""
    year = view.options.get("year")
    if not isinstance(year, dict):
        return [("year", "options", "<missing or not an object>", None)]
    observed = {
        "start": int(view.data["year"].min()),
        "end": int(view.data["year"].max()),
    }
    problems = []
    for key in YEAR_KEYS:
        listed = year.get(key)
        if listed != view.spec.time[key]:
            problems.append((key, "spec", listed, view.spec.time[key]))
        if key in observed and listed != observed[key]:
            problems.append((key, "data", listed, observed[key]))
    return problems


def check_options(view: LoadedView) -> list[CheckResult]:
    """options.json agrees with the data and the spec.

    Four results: every listed value has rows; every row value is listed (sub-sectors via
    their per-sector lists, as pairs); defaults are members of their lists; the options
    year start/end/base equal the spec window and the data's first and last years.
    """
    name = view.spec.name
    no_rows, unlisted = _membership_problems(view)
    defaults = _default_problems(view)
    years = _year_problems(view)
    return [
        build_result(
            check="contracts.options_listed_have_rows",
            view=name,
            failures=len(no_rows),
            severity=Severity.ERROR,
            passed_message="Every value options.json lists has rows",
            failed_message=f"{len(no_rows)} values listed in options.json have no rows",
            details=pd.DataFrame(no_rows, columns=["column", "value"]),
        ),
        build_result(
            check="contracts.options_rows_listed",
            view=name,
            failures=len(unlisted),
            severity=Severity.ERROR,
            passed_message="Every value in the data is listed in options.json",
            failed_message=f"{len(unlisted)} values in the data not listed in options.json",
            details=pd.DataFrame(unlisted, columns=["column", "value"]),
        ),
        build_result(
            check="contracts.options_defaults",
            view=name,
            failures=len(defaults),
            severity=Severity.ERROR,
            passed_message="Every default is in its option list",
            failed_message=f"{len(defaults)} defaults not in their option list",
            details=pd.DataFrame(defaults, columns=["key", "value"]),
        ),
        build_result(
            check="contracts.options_years",
            view=name,
            failures=len(years),
            severity=Severity.ERROR,
            passed_message="options.json years match the spec and the data",
            failed_message=f"{len(years)} options.json years disagree with spec or data",
            details=pd.DataFrame(
                years, columns=["key", "against", "options", "expected"]
            ),
        ),
    ]


def run_contracts(view: LoadedView) -> list[CheckResult]:
    """Run every contract on one whole view.

    If the view is empty or misses a required column, only those two results are returned:
    the other checks would fail for the same reason, or could not run.

    Args:
        view: The whole view, e.g. ``load_view(name, source)``.

    Returns:
        One or more results per contract.
    """
    results = [*check_non_empty(view), *check_columns(view)]
    if view.data.empty or not has_required_columns(view):
        return results
    return [
        *results,
        *check_keys(view),
        *check_years(view),
        *check_values(view),
        *check_anchor(view),
        *check_anchor_currencies(view),
        *check_gni_share(view),
        *check_types(view),
        *check_critical_donors(view),
        *check_options(view),
    ]
