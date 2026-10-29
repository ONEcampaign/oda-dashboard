"""Contracts: the shape every published view must have, checked on one whole view.

Every check is ``check_<x>(view) -> list[CheckResult]`` and fails as an ERROR, except the
null count on the seven non-primary value columns, which is a WARNING (real data gaps, such
as a missing conversion factor, that must stay visible without blocking).

``run_contracts(view)`` runs them all. It needs the whole view in memory: for sectors that
means ``load_view("sectors_view", source)``, not a partition.
"""

from collections.abc import Iterable

import numpy as np
import pandas as pd

from src.data.validation.io import LoadedView
from src.data.validation.models import CheckResult, Severity
from src.data.validation.views import CRITICAL_DONORS

# Units guard: a value this large means millions were scaled twice, or worse.
MAX_SANE_VALUE: float = 1e15

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


def check_values(view: LoadedView) -> list[CheckResult]:
    """Value columns are populated and of sane magnitude.

    Three results: nulls in value_usd_current (ERROR), nulls in the other seven value
    columns (WARNING, with per-column counts and sample rows), and any non-finite value or
    one with absolute size above MAX_SANE_VALUE (ERROR).
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
            severity=Severity.WARNING,
            passed_message="No nulls in the other value columns",
            failed_message=f"Nulls in value columns ({counts_text})",
            details=data.loc[other_null, [*keys, *others]],
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


def check_critical_donors(view: LoadedView) -> list[CheckResult]:
    """Every donor in CRITICAL_DONORS has rows."""
    present = set(view.data["donor_name"].dropna().unique())
    missing = [d for d in CRITICAL_DONORS if d not in present]
    return [
        build_result(
            check="contracts.critical_donors",
            view=view.spec.name,
            failures=len(missing),
            severity=Severity.ERROR,
            passed_message=f"All {len(CRITICAL_DONORS)} critical donors present",
            failed_message=f"Critical donors missing: {missing}",
            details=pd.DataFrame({"donor_name": missing}),
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
        *check_critical_donors(view),
        *check_options(view),
    ]
