import json
from collections import defaultdict

import pandas as pd
from oda_data import DAC1Data, provider_groupings
from pydeflate import oecd_dac_deflate, oecd_dac_exchange, set_pydeflate_path

from src.data.analysis_tools.helper_functions import get_dac_ids
from src.data.config import (
    BASE_TIME,
    CURRENCIES,
    DONOR_GROUPS,
    PATHS,
    RECIPIENT_GROUPS,
    logger,
)

set_pydeflate_path(PATHS.PYDEFLATE)

EU_IDS = provider_groupings()["eu27_countries"]


def get_gni(start_year: int, end_year: int) -> pd.DataFrame:
    donor_ids = get_dac_ids(PATHS.DONORS)

    bilateral_df = DAC1Data(years=range(start_year, end_year + 1)).read(
        using_bulk_download=True,
        additional_filters=[
            ("amount_type", "==", "Current prices"),
            ("donor_code", "in", donor_ids),
            ("aidtype_code", "==", 1),
        ],
        columns=["donor_code", "year", "value"],
    )

    if all(code in bilateral_df.donor_code.unique() for code in EU_IDS):
        eu_df = (
            bilateral_df.loc[lambda d: d["donor_code"].isin(EU_IDS)]
            .groupby(["year"], observed=True, dropna=False)["value"]
            .sum()
            .reset_index()
            .assign(donor_code=918)
        )

    else:
        raise Exception("Not all EU countries present in df")

    df = pd.concat([bilateral_df, eu_df])

    return df


def add_currencies_and_prices(df: pd.DataFrame) -> pd.DataFrame:
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
            base_year=BASE_TIME["base"],
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
    df["value"] = df["value"].round(6).astype("float32")

    # Check for duplicates before pivoting and aggregate if found
    pivot_cols = list(index_cols) + ["currency", "price"]
    logger.info("Checking for duplicates before pivot...")
    duplicates = df[pivot_cols].duplicated()

    if duplicates.any():
        logger.warning(f"Found {duplicates.sum():,} duplicate rows before pivoting")
        logger.info("Aggregating duplicates by summing values...")
        # Aggregate duplicates by grouping and summing
        df = df.groupby(pivot_cols, dropna=False, observed=True)["value"].sum().reset_index()
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
        .filter(["year", "donor_code", "value_usd_current"])
        .rename(columns={"value_usd_current": "total_oda"})
    )

    merged = df.merge(total, on=["year", "donor_code"], how="left")

    merged["pct_of_total_oda"] = (
        merged["value_usd_current"] / merged["total_oda"]
    ).round(6)

    merged = merged.drop(columns=["total_oda"])

    return merged


def add_share_of_recipients_total_oda(df: pd.DataFrame) -> pd.DataFrame:
    """Add column for share of total ODA"""

    total = (
        df.loc[lambda d: d.recipient_code == 100_000]
        .groupby(["year", "donor_code"], dropna=False, observed=True)[
            "value_usd_current"
        ]
        .sum()
        .reset_index()
        .rename(columns={"value_usd_current": "total_oda"})
    )

    merged = df.merge(total, on=["year", "donor_code"], how="left")

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

    gni = add_donor_groupings(gni).rename(columns={"value": "gni"})

    merged = df.merge(gni, on=["year", "donor_code"], how="left")

    merged["pct_of_gni"] = (merged["value_usd_current"] / merged["gni"]).round(5)

    merged = merged.drop(columns=["gni"])

    return merged


def add_financing_indicator_codes(df: pd.DataFrame) -> pd.DataFrame:
    """Add indicator codes to the dataframe"""
    df = df.rename(columns={"indicator": "indicator_name"})
    with open(PATHS.FINANCING_INDICATORS_CODES, "r") as f:
        indicator_map = {v: int(k) for k, v in json.load(f).items()}
    df = df.assign(indicator=lambda d: d["indicator_name"].map(indicator_map))
    return df


def add_recipient_indicator_codes(df: pd.DataFrame) -> pd.DataFrame:
    """Add indicator codes to the dataframe"""
    df = df.rename(columns={"indicator": "indicator_name"})
    with open(PATHS.RECIPIENT_INDICATORS_CODES, "r") as f:
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
