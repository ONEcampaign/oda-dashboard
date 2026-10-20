"""Testable frame logic for the financing loader, which Python cannot import by name."""

from collections import Counter

import pandas as pd

from src.data.analysis_tools.naming import map_config_values
from src.data.config import (
    ALL_FINANCING_INDICATORS,
    SUMMED_FINANCING_NAMES,
    TOTAL_ODA,
    logger,
)

# The indicators derived from splitting Total ODA by whether it is a grant.
GRANTS_SPLIT: tuple[str, ...] = ("Grants", "Non-grants")

# The DAC1 fund flows read for the split, by the indicator they become. The headline measure
# is net flows before 2018 and grant equivalents from then on.
GRANTS_FUND_FLOWS: dict[str, str] = {
    "Disbursements, net": TOTAL_ODA,
    "Grant equivalents": TOTAL_ODA,
    "Disbursements, grants": "Grants",
}

# A group's grants split is left out for a year when members that do not report it hold
# more than this share of the group's Total ODA.
MAX_MISSING_GRANTS_SHARE: float = 0.01


def resolve_indicator_duplicates(dac1_raw: pd.DataFrame) -> pd.DataFrame:
    """Drop the duplicate rows created by indicators that share a display name.

    The DAC renumbered several indicators when it moved to grant equivalents, so two codes can
    map to one name (1015 and 11015 are both "Bilateral ODA"). Where both are present for the
    same donor and year they report the same figure, and keeping both would double it. Names in
    SUMMED_FINANCING_NAMES are left alone: their codes are parts of one figure, to be added up.

    Args:
        dac1_raw: Raw DAC1 rows, with a one_indicator column.

    Returns:
        The rows with duplicates removed. Each set keeps a row with a value.

    Raises:
        ValueError: If two codes for one name disagree, since the two codes are then not
            interchangeable after all.
    """
    multi_code_names = {
        name
        for name, count in Counter(ALL_FINANCING_INDICATORS.values()).items()
        if count > 1 and name not in SUMMED_FINANCING_NAMES
    }

    annotated = dac1_raw.assign(
        _indicator=lambda d: d["one_indicator"].map(ALL_FINANCING_INDICATORS)
    )
    shared = annotated[annotated["_indicator"].isin(multi_code_names)]

    conflicts = []
    drop_indices = []

    for (year, donor_code, indicator), group in shared.groupby(
        ["year", "donor_code", "_indicator"], dropna=False, observed=True
    ):
        if len(group) <= 1:
            continue

        # Rows with a value first, so the row kept is never a missing copy of a figure another
        # code reports.
        ranked = group.sort_values(
            "value", key=lambda v: v.isna(), ascending=True, kind="stable"
        )
        drop_indices.extend(ranked.index[1:].tolist())

        if group["value"].dropna().nunique() > 1:
            conflicts.append((year, donor_code, indicator))

    if conflicts:
        lines = [
            f"  year={y}, donor_code={d}, indicator='{ind}'" for y, d, ind in conflicts
        ]
        message = (
            "Conflicting values for year-donor pairs with shared indicator codes:\n"
            + "\n".join(lines)
        )
        raise ValueError(message)

    return dac1_raw.drop(index=drop_indices)


def split_grants(df: pd.DataFrame, index_cols: list[str]) -> pd.DataFrame:
    """Split DAC1 Total ODA into Grants and Non-grants.

    The grant-only measure gives Grants, and the headline measure minus that gives
    Non-grants. Where a donor-year has no grants measure, both come out missing, and are
    dropped later with the other empty values.

    Args:
        df: Long DAC1.10.1010 rows with fund_flows and value, read under the grants measure
            and the headline measure.
        index_cols: Columns identifying one donor-year (and currency and price, if present).

    Returns:
        Long rows for Grants and Non-grants, keyed by index_cols and indicator_name.
    """
    return (
        df.assign(
            indicator_name=lambda d: map_config_values(
                d["fund_flows"], GRANTS_FUND_FLOWS, what="Fund flows"
            )
        )
        .groupby([*index_cols, "indicator_name"], dropna=False, observed=True)["value"]
        .sum()
        .reset_index()
        .pivot(index=index_cols, columns="indicator_name", values="value")
        .reset_index()
        .assign(**{"Non-grants": lambda d: d[TOTAL_ODA] - d["Grants"]})
        .melt(id_vars=index_cols, value_vars=list(GRANTS_SPLIT))
    )


def years_missing_grants(usd_current: pd.DataFrame, members: dict) -> dict[int, float]:
    """Find the years in which members without a grants split hold too much of Total ODA.

    Preliminary DAC1 data carry the grants measure for only a few donors, so a group's
    Grants and Non-grants summed over the members that report them would fall far short of
    the group's Total ODA. A few small donors never report the split, which a group can
    absorb up to MAX_MISSING_GRANTS_SHARE of its Total ODA.

    Args:
        usd_current: Long frame of individual donors in current USD, with donor_code.
        members: The group's donor codes.

    Returns:
        The years above the threshold, each with the share of Total ODA missing its split.
    """
    usd = usd_current.loc[lambda d: d["donor_code"].isin(members)]
    total = (
        usd.loc[lambda d: d["indicator_name"] == TOTAL_ODA]
        .groupby(["year", "donor_code"])["value"]
        .sum()
    )
    with_grants = (
        usd.loc[lambda d: (d["indicator_name"] == "Grants") & d["value"].notna()]
        .set_index(["year", "donor_code"])
        .index
    )

    missing = total[~total.index.isin(with_grants)].groupby(level="year").sum()
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
