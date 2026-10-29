"""Testable frame logic for the financing loader, which Python cannot import by name."""

from collections.abc import Iterable

import pandas as pd

from src.data.analysis_tools.naming import map_config_values
from src.data.config import (
    FINANCING_TYPES,
    SUMMED_FINANCING_NAMES,
    logger,
)

# The indicators derived from splitting Total ODA by whether it is a grant.
GRANTS_SPLIT: tuple[str, ...] = ("Grants", "Non-grants")

# Columns of every financing row before currency conversion.
FINANCING_COLUMNS: list[str] = [
    "year",
    "donor_code",
    "donor_name",
    "indicator_name",
    "type",
    "value",
]
SERIES_KEY: list[str] = ["year", "donor_code", "indicator_name"]

# A group's grants split is left out for a year when members that do not report it hold
# more than this share of the group's Total ODA.
MAX_MISSING_GRANTS_SHARE: float = 0.01


def to_financing_rows(raw: pd.DataFrame, names: str | pd.Series) -> pd.DataFrame:
    """Name a query result's rows and label their type from the basis they were read on.

    Args:
        raw: A run_query result with year, donor_code, donor_name, basis and value.
        names: The indicator name for every row, or one per row.

    Returns:
        The rows in FINANCING_COLUMNS.

    Raises:
        ValueError: If a row's basis has no financing type.
    """
    return raw.assign(
        indicator_name=names,
        type=map_config_values(raw["basis"].astype(str), FINANCING_TYPES, what="Bases"),
    )[FINANCING_COLUMNS]


def sum_by_name(rows: pd.DataFrame) -> pd.DataFrame:
    """Add up the parts of names read in several parts, one row per series and type.

    Args:
        rows: Financing rows from to_financing_rows.

    Returns:
        One row per year, donor, indicator name and type.

    Raises:
        ValueError: If a name outside SUMMED_FINANCING_NAMES has more than one row for a
            donor and year, which would mean two reads overlap and the sum double counts.
    """
    repeated = rows[rows.duplicated(SERIES_KEY, keep=False)]
    overlapping = repeated.loc[~repeated["indicator_name"].isin(SUMMED_FINANCING_NAMES)]
    if not overlapping.empty:
        raise ValueError(
            "Financing series read more than once: "
            f"{overlapping[SERIES_KEY].drop_duplicates().head(10).values.tolist()}"
        )
    return (
        rows.groupby(
            ["year", "donor_code", "donor_name", "indicator_name", "type"],
            observed=True,
        )["value"]
        .sum(min_count=1)
        .reset_index()
    )


def split_grants(total_oda: pd.DataFrame, grants: pd.DataFrame) -> pd.DataFrame:
    """Split each donor's Total ODA into Grants and Non-grants.

    Grants is the grants flow, and Non-grants Total ODA minus it. Both take Total ODA's type,
    the headline basis of their year. Where a donor-year has no grants, both come out
    missing, and are dropped later with the other empty values.

    Args:
        total_oda: Financing rows for Total ODA, one per donor and year.
        grants: The grants flow (run_query result), with donor_code, year and value.

    Returns:
        Financing rows for Grants and Non-grants.

    Raises:
        ValueError: If a donor has grants in a year with no Total ODA, or more than one
            grants row in a year.
    """
    key = ["year", "donor_code"]
    if grants.duplicated(key).any():
        raise ValueError("More than one grants row for a donor and year")

    merged = total_oda.merge(
        grants[[*key, "value"]].rename(columns={"value": "Grants"}),
        on=key,
        how="outer",
        validate="1:1",
        indicator=True,
    )
    orphans = merged.loc[merged["_merge"] == "right_only", key]
    if not orphans.empty:
        raise ValueError(
            f"Grants for donor-years with no Total ODA: {orphans.values.tolist()[:10]}"
        )

    return (
        merged.assign(**{"Non-grants": lambda d: d["value"] - d["Grants"]})
        .drop(columns=["indicator_name", "value", "_merge"])
        .melt(
            id_vars=["year", "donor_code", "donor_name", "type"],
            value_vars=list(GRANTS_SPLIT),
            var_name="indicator_name",
        )[FINANCING_COLUMNS]
    )


def years_missing_grants(
    total_oda: pd.DataFrame, grants: pd.DataFrame, members: Iterable[int]
) -> dict[int, float]:
    """Find the years in which members without a grants split hold too much of Total ODA.

    A member misses its split in a year when it has Total ODA but DAC1 has no grants value
    for it. A grants value of zero is a reported split. Preliminary DAC1 data carry grants
    for only a few donors, so a group's Grants and Non-grants summed over the members that
    report them would fall far short of the group's Total ODA. A few small donors never
    report the split, which a group can absorb up to MAX_MISSING_GRANTS_SHARE of its Total
    ODA.

    Args:
        total_oda: Individual donors' Total ODA in current USD, with donor_code, year, value.
        grants: The grants flow as read (run_query result), with donor_code, year, value.
        members: The group's donor codes.

    Returns:
        The years above the threshold, each with the share of Total ODA missing its split.
    """
    members = set(members)
    total = (
        total_oda.loc[lambda d: d["donor_code"].isin(members)]
        .groupby(["year", "donor_code"])["value"]
        .sum()
    )
    reported = (
        grants.loc[lambda d: d["value"].notna(), ["year", "donor_code"]]
        .set_index(["year", "donor_code"])
        .index
    )

    missing = total[~total.index.isin(reported)].groupby(level="year").sum()
    share = (missing / total.groupby(level="year").sum()).dropna()

    return share[share > MAX_MISSING_GRANTS_SHARE].to_dict()


def drop_grants_split(group: pd.DataFrame, years: dict[int, float]) -> pd.DataFrame:
    """Drop a group's Grants and Non-grants rows for the given years, logging which.

    Args:
        group: Long frame for one donor group.
        years: Years whose grants split is incomplete, with the share of Total ODA missing it.

    Returns:
        The group without its grants split in those years.
    """
    incomplete = group["indicator_name"].isin(GRANTS_SPLIT) & group["year"].isin(years)
    if incomplete.any():
        logger.info(
            "%s: grants split left out where members without it hold this share of "
            "Total ODA: %s",
            group["donor_name"].iloc[0],
            {year: round(share, 3) for year, share in sorted(years.items())},
        )
    return group.loc[~incomplete]


def check_one_type_per_series(financing: pd.DataFrame) -> None:
    """Raise if a row has no type, or a series has two types in one year.

    Every row needs the basis it was read on, and one per year: two would split a series.

    Args:
        financing: Long financing frame with year, donor_name, indicator_name and type.

    Raises:
        ValueError: On a missing type or a series with more than one type in a year.
    """
    if financing["type"].isna().any():
        raise ValueError("Financing rows without a type")
    types_per_series = financing.groupby(
        ["year", "donor_name", "indicator_name"], observed=True
    )["type"].nunique()
    clashes = types_per_series[types_per_series > 1]
    if not clashes.empty:
        raise ValueError(
            f"Financing series read in more than one basis: {clashes.index.tolist()[:10]}"
        )
