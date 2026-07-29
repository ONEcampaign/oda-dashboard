import json
from collections import defaultdict

import pandas as pd
from oda_data import OECDClient
from pydeflate import oecd_dac_deflate, oecd_dac_exchange, set_pydeflate_path

from src.data.config import (
    logger,
    BASE_TIME,
    CURRENCIES,
    ALL_DONORS,
    AGGREGATE_DONORS,
    BILATERAL_DONORS,
    EU_COUNTRIES,
    PATHS,
    RECIPIENT_GROUPS,
    DONOR_GROUPS,
)

from src.data.analysis_tools.helper_functions import apply_name_overrides

set_pydeflate_path(PATHS.PYDEFLATE)


def get_gni(start_year: int, end_year: int) -> pd.DataFrame:

    gni_raw = OECDClient(
        years=range(start_year, end_year + 1),
        providers=list(ALL_DONORS),
        measure="net_disbursement",
        use_bulk_download=True,
    ).get_indicators("DAC1.40.1")[["donor_code", "donor_name", "year", "value"]]

    # Deduplicate - raw data may have duplicate rows with identical GNI values
    gni_df = gni_raw.drop_duplicates(subset=["donor_code", "year"])

    gni_df = apply_name_overrides(gni_df, AGGREGATE_DONORS, "donor")

    eu27_df = get_group_total(gni_df, EU_COUNTRIES, ["year"], group_name="EU27 countries")
    # Label must match the donor_name used by the views, or the GNI merge silently
    # yields NaN. EU institutions have no GNI of their own, so the denominator for
    # the EU27 + institutions aggregate is the member states' combined GNI.
    eu27_eui_df = get_group_total(
        gni_df, EU_COUNTRIES, ["year"], group_name="EU27 & EU Institutions"
    )
    bilateral_df = get_group_total(
        gni_df,
        BILATERAL_DONORS,
        ["year"],
        group_name="All bilateral donors"
    )

    return (
        pd.concat([gni_df, eu27_df, eu27_eui_df, bilateral_df])
        .rename(columns={"value": "gni"})
        .drop(columns="donor_code")
    )



def _default_coverage_cols(df: pd.DataFrame, column: str) -> list[str]:
    """Pick the combinations to assess group coverage over.

    Completeness is judged per year and per counterpart entity: when aggregating donors
    that means year x recipient, and when aggregating recipients it means year x donor.
    Columns absent from the data are skipped.

    Args:
        df: Frame being aggregated.
        column: Entity being aggregated over, "donor" or "recipient".

    Returns:
        Column names to group by when checking coverage.
    """
    counterpart = "recipient" if column == "donor" else "donor"
    candidates = ["year", f"{counterpart}_code", f"{counterpart}_name"]

    cols = ["year"] if "year" in df.columns else []
    for candidate in candidates[1:]:
        if candidate in df.columns:
            cols.append(candidate)
            break

    return cols


def _warn_missing_group_members(
    df: pd.DataFrame,
    group_dict: dict,
    code_col: str,
    coverage_cols: list[str],
    label: str,
) -> None:
    """Warn about group members missing from the data being aggregated.

    Members that never appear are reported separately from members missing out of
    individual combinations: the former means the total silently omits them, while the
    latter is usually genuine sparsity (a donor simply gave nothing that year).

    Args:
        df: Frame being aggregated, before filtering to the group.
        group_dict: Mapping of {member code: member name} defining the group.
        code_col: Column holding the member codes.
        coverage_cols: Columns whose combinations are checked for completeness.
        label: Name of the total being built, used in the log message.
    """
    members = set(group_dict)
    present = df.loc[df[code_col].isin(members), [code_col, *coverage_cols]].drop_duplicates()
    found = set(present[code_col].dropna().unique())

    never = sorted(members - found)
    if never:
        logger.warning(
            "%s: %d of %d members never appear in the data, so the total excludes them: %s",
            label, len(never), len(members), {code: group_dict[code] for code in never},
        )

    if not coverage_cols:
        return

    per_combination = present.groupby(
        coverage_cols, dropna=False, observed=True
    )[code_col].nunique()
    incomplete = int((per_combination < len(members)).sum())
    if not incomplete:
        return

    total = len(per_combination)
    appearances = present.groupby(code_col, dropna=False, observed=True).size()
    gaps = sorted(
        ((total - int(appearances.get(code, 0)), code) for code in members), reverse=True
    )
    worst = ", ".join(
        f"{group_dict[code]} ({missing:,})" for missing, code in gaps[:5] if missing
    )
    logger.warning(
        "%s: %d of %d %s combinations are missing at least one member. Members absent "
        "from the most combinations: %s. This is expected where a member reported "
        "nothing, but a sharp change here means lost coverage.",
        label, incomplete, total, " x ".join(coverage_cols), worst,
    )


def get_group_total(
        df: pd.DataFrame,
        group_dict: dict,
        group_cols: list,
        column: str = "donor",
        check_all_keys: bool = True,
        group_name: str = None,
        group_code: str = None,
        coverage_cols: list[str] = None,
) -> pd.DataFrame:
    """Sum a group of donors or recipients into a single aggregate row per group_cols.

    Args:
        df: Long-form frame with a "value" column.
        group_dict: Mapping of {member code: member name} defining the group.
        group_cols: Columns to group by when summing.
        column: Entity being aggregated over, "donor" or "recipient".
        check_all_keys: Log a warning naming group members missing from the data. Never
            raises: members legitimately absent from a source must not break the build.
        group_name: Value to assign to the aggregate's name column.
        group_code: Value to assign to the aggregate's code column.
        coverage_cols: Combinations to check coverage over. Defaults to year plus the
            counterpart entity, e.g. year x recipient when aggregating donors.

    Returns:
        The aggregated frame.
    """
    code_col = f"{column}_code"
    name_col = f"{column}_name"

    if check_all_keys:
        _warn_missing_group_members(
            df,
            group_dict,
            code_col,
            coverage_cols if coverage_cols is not None
            else _default_coverage_cols(df, column),
            group_name or f"{column} group total",
        )

    df = (
        df.loc[lambda d: d[code_col].isin(group_dict)]
        .groupby(group_cols, observed=True, dropna=False)["value"]
        .sum()
        .reset_index()
    )

    if group_name:
        df[name_col] = group_name
    if group_code:
        df[code_col] = group_code

    return df




def add_currencies_and_prices(
    df: pd.DataFrame, base_year: int = BASE_TIME["base"]
) -> pd.DataFrame:
    """
    Adds copies of the data in different currencies and prices
    """
    # do the currency conversions first
    current_dfs = []

    df = df.assign(currency="USD", price="current")

    for currency in CURRENCIES:
        logger.info(f"Converting to {currency}")
        if currency == "USD":
            current_dfs.append(df.assign(currency=currency, price="current"))
        else:
            converted = oecd_dac_exchange(
                data=df.copy(),
                source_currency="USA",
                target_currency=currency,
                id_column="donor_code",
                use_source_codes=True,
            )
            current_dfs.append(converted.assign(currency=currency, price="current"))

    constant_dfs = []
    for currency in CURRENCIES:
        converted = oecd_dac_deflate(
            data=df.copy(),
            base_year=base_year,
            source_currency="USA",
            target_currency=currency,
            id_column="donor_code",
            use_source_codes=True,
        )
        constant_dfs.append(converted.assign(currency=currency, price="constant"))

    # Don't include df in concat since USD/current is already in current_dfs[0]
    return pd.concat(current_dfs + constant_dfs, ignore_index=True)


def donor_groups() -> dict:
    """Invert donor JSON structure to map group names to lists of numeric codes."""
    group_map = defaultdict(list)
    with open(PATHS.DONORS, "r") as f:
        data = json.load(f)

    for code, info in data.items():
        for group in info.get("groups", []):
            group_map[group].append(int(code))

    return {DONOR_GROUPS[group]: sorted(codes) for group, codes in group_map.items()}


def recipient_groups() -> dict:
    """Invert donor JSON structure to map group names to lists of numeric codes."""
    group_map = defaultdict(list)
    with open(PATHS.RECIPIENTS, "r") as f:
        data = json.load(f)

    for code, info in data.items():
        for group in info.get("groups", []):
            group_map[group].append(int(code))

    return {
        RECIPIENT_GROUPS[group]: sorted(codes) for group, codes in group_map.items()
    }


def add_donor_groupings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add donor groupings (DAC countries, G7, etc.) by aggregating member countries.

    Optimized to minimize copies and use pre-computed column lists.
    """
    # Pre-compute groupby columns once (much faster than in loop)
    groupby_cols = [c for c in df.columns if c != "value"]

    groups = []
    for group, members in donor_groups().items():
        # Create boolean mask without copying dataframe
        mask = df["donor_code"].isin(members)

        if mask.any():
            # Only copy the filtered subset (not entire dataframe)
            filtered = df.loc[mask].copy()
            filtered["donor_code"] = group

            # Aggregate using pre-computed column list
            aggregated = (
                filtered.groupby(groupby_cols, dropna=False, observed=True)["value"]
                .sum()
                .reset_index()
            )
            groups.append(aggregated)

    return pd.concat([df] + groups, ignore_index=True)


def add_recipient_groupings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add recipient groupings (Africa, LDCs, etc.) by aggregating member countries.

    Optimized to minimize copies and use pre-computed column lists.
    """
    # Pre-compute groupby columns once (much faster than in loop)
    groupby_cols = [c for c in df.columns if c != "value"]

    groups = []
    for group, members in recipient_groups().items():
        # Create boolean mask without copying dataframe
        # Convert to set once for faster lookup
        members_set = set(members)
        mask = df["recipient_code"].isin(members_set)

        if mask.any():
            # Only copy the filtered subset (not entire dataframe)
            filtered = df.loc[mask].copy()
            filtered["recipient_code"] = group

            # Aggregate using pre-computed column list
            aggregated = (
                filtered.groupby(groupby_cols, dropna=False, observed=True)["value"]
                .sum()
                .reset_index()
            )
            groups.append(aggregated)

    return pd.concat([df] + groups, ignore_index=True)


def widen_currency_price(
    df: pd.DataFrame,
    index_cols: tuple[str, ...] = ("year", "donor_code", "indicator"),
) -> pd.DataFrame:
    """Pivot currency/price pairs into wide value columns.

    Args:
        df: Long-form DataFrame with columns: year, donor_code, indicator, currency, price, value.
        index_cols: Columns to keep as the row index in the wide table.

    Returns:
        Wide DataFrame where columns are like 'USD_current_value', 'USD_constant_value', etc.
    """
    # Pre-process values in long format (much faster than on wide data)
    df["value"] = df["value"].round(4).astype("float32")

    # Check for duplicates before pivoting and aggregate if found
    pivot_cols = list(index_cols) + ["currency", "price"]
    logger.info("Checking for duplicates before pivot...")
    duplicates = df[pivot_cols].duplicated()

    if duplicates.any():
        logger.warning(f"Found {duplicates.sum():,} duplicate rows before pivoting")
        logger.info("Aggregating duplicates by summing values...")
        # Aggregate duplicates by grouping and summing
        df = (
            df.groupby(pivot_cols, dropna=False, observed=True)["value"]
            .sum()
            .reset_index()
        )
        logger.info(f"After aggregation: {len(df):,} rows")
    else:
        logger.info("No duplicates detected - proceeding with pivot")

    wide = df.pivot(
        index=list(index_cols),
        columns=["currency", "price"],
        values="value",
    )

    # Flatten MultiIndex columns -> "value_usd_current"
    wide.columns = [
        f"value_{cur.lower()}_{price}" for cur, price in wide.columns.to_list()
    ]
    wide = wide.reset_index()

    # Reorder columns: index cols first, then sorted value cols
    value_cols = sorted([c for c in wide.columns if c not in index_cols])
    return wide[list(index_cols) + value_cols]


def add_share_of_total_oda(df: pd.DataFrame) -> pd.DataFrame:
    """Add column for share of total ODA"""

    total = (
        df.loc[lambda d: d["indicator_name"] == "Total ODA"]
        .copy()
        .filter(["year", "donor_name", "value_usd_current"])
        .rename(columns={"value_usd_current": "total_oda"})
    )

    merged = df.merge(total, on=["year", "donor_name"], how="left")

    merged["pct_of_total_oda"] = (
        merged["value_usd_current"] / merged["total_oda"]
    ).round(6)

    merged = merged.drop(columns=["total_oda"])

    return merged


def add_gender_share_of_total_oda(df: pd.DataFrame) -> pd.DataFrame:
    """Add column for share of total ODA"""

    total = (
        df.groupby(
            ["year", "donor_code", "recipient_code"], dropna=False, observed=True
        )["value_usd_current"]
        .sum()
        .reset_index()
        .rename(columns={"value_usd_current": "total_oda"})
    )

    merged = df.merge(total, on=["year", "donor_code", "recipient_code"], how="left")

    merged["pct_of_total_oda"] = (
        merged["value_usd_current"] / merged["total_oda"]
    ).round(6)

    merged = merged.drop(columns=["total_oda"])

    return merged


def add_share_of_gni(df: pd.DataFrame) -> pd.DataFrame:
    """Add column for share of GNI"""

    gni = get_gni(start_year=df["year"].min(), end_year=df["year"].max())

    merged = df.merge(gni, on=["year", "donor_name"], how="left")

    merged["pct_of_gni"] = (merged["value_usd_current"] / merged["gni"]).round(5)

    merged = merged.drop(columns=["gni"])

    return merged


def add_recipient_indicator_codes(df: pd.DataFrame) -> pd.DataFrame:
    """Add indicator codes to the dataframe"""
    df = df.rename(columns={"indicator": "indicator_name"})
    with open(PATHS.SECTORS_INDICATORS_CODES, "r") as f:
        indicator_map = {v: int(k) for k, v in json.load(f).items()}
    df = df.assign(indicator=lambda d: d["indicator_name"].map(indicator_map))
    return df


def add_gender_indicator_codes(df: pd.DataFrame) -> pd.DataFrame:
    with open(PATHS.TOOLS / "gender_indicators.json", "r") as f:
        indicator_mapping = {v: int(k) for k, v in json.load(f).items()}

    df["indicator_code"] = df["indicator"].map(indicator_mapping)
    return df.rename(
        columns={"indicator": "indicator_name", "indicator_code": "indicator"}
    )


def add_donor_names(df: pd.DataFrame) -> pd.DataFrame:
    from oda_data import provider_groupings

    providers = provider_groupings()["all_official"] | {
        v: k for k, v in DONOR_GROUPS.items()
    }

    return df.assign(donor_name=lambda d: d["donor_code"].map(providers))


def add_recipient_names(df: pd.DataFrame) -> pd.DataFrame:
    from oda_data import recipient_groupings

    recipients = recipient_groupings()["all_recipients"] | {
        v: k for k, v in RECIPIENT_GROUPS.items()
    }

    return df.assign(recipient_name=lambda d: d["recipient_code"].map(recipients))
