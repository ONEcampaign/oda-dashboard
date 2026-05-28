import json
from collections import defaultdict

import pandas as pd
from oda_data import OECDClient
from pydeflate import oecd_dac_deflate, oecd_dac_exchange, set_pydeflate_path

from src.data.config import (
    BASE_TIME,
    CURRENCIES,
    ALL_DONORS,
    BILATERAL_DONORS,
    EU_COUNTRIES,
    PATHS,
    RECIPIENT_GROUPS,
    logger, DONOR_GROUPS,
)

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

    eu27_df = get_group_total(gni_df, EU_COUNTRIES, ["year"], donor_name="EU27 countries")
    eu27_eui_df = get_group_total(gni_df, EU_COUNTRIES, ["year"], donor_name="EU & EU Institutions")
    bilateral_df = get_group_total(
        gni_df,
        BILATERAL_DONORS,
        ["year"],
        check_all_keys=False,
        donor_name="All bilateral donors"
    )

    return (
        pd.concat([gni_df, eu27_df, eu27_eui_df, bilateral_df])
        .rename(columns={"value": "gni"})
        .drop(columns="donor_code")
    )



def get_group_total(
        df: pd.DataFrame,
        group_dict: dict,
        group_cols: list,
        check_all_keys: bool = True,
        donor_name: str = None,
        donor_code: str = None
) -> pd.DataFrame:

    if check_all_keys & ~all(code in df.donor_code.unique() for code in group_dict):

            raise Exception("Not all countries present in df")

    df = (
        df.loc[lambda d: d["donor_code"].isin(group_dict)]
        .groupby(group_cols, observed=True, dropna=False)["value"]
        .sum()
        .reset_index()
    )

    if donor_name:
        df["donor_name"] = donor_name
    if donor_code:
        df["donor_code"] = donor_code

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


def add_share_of_recipients_total_oda(df: pd.DataFrame) -> pd.DataFrame:
    """Add column for each donor's share of total ODA received by a recipient."""

    all_bilateral_code = DONOR_GROUPS["All bilateral donors"]

    total = (
        df.loc[lambda d: d.donor_code == all_bilateral_code]
        .groupby(["year", "recipient_code"], dropna=False, observed=True)[
            "value_usd_current"
        ]
        .sum()
        .reset_index()
        .rename(columns={"value_usd_current": "total_oda"})
    )

    merged = df.merge(total, on=["year", "recipient_code"], how="left")

    merged["pct_total_recipient"] = (
        merged["value_usd_current"] / merged["total_oda"]
    ).round(6)

    merged = merged.drop(columns=["total_oda"])

    return merged


def add_share_of_donors_total_oda(df: pd.DataFrame) -> pd.DataFrame:
    """Add column for each recipient's share of total ODA given by a donor.

    Denominator is the donor's total ODA to Developing countries, per indicator.
    """

    developing_countries_code = RECIPIENT_GROUPS["Developing countries"]

    total = (
        df.loc[lambda d: d.recipient_code == developing_countries_code]
        .groupby(["year", "donor_code"], dropna=False, observed=True)[
            "value_usd_current"
        ]
        .sum()
        .reset_index()
        .rename(columns={"value_usd_current": "total_oda"})
    )

    merged = df.merge(total, on=["year", "donor_code"], how="left")

    merged["pct_total_donor"] = (
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
