import pandas as pd
from oda_data import ODAData
from oda_data.tools.groupings import donor_groupings, recipient_groupings
from pydeflate import oecd_dac_deflate, oecd_dac_exchange

from scripts import config
from scripts.analysis_tools import sector_lists
from scripts.analysis_tools.versions import versions_dictionary


def individual_dashboard_donors() -> dict:
    dac_members = donor_groupings()["dac_members"]

    key_agg = [20001, 20005, 20006, 20003]

    select_aggregates = {
        k: v for k, v in donor_groupings()["dac1_aggregates"].items() if k in key_agg
    }

    return dac_members | select_aggregates


# -------------------------- Export configuration -------------------------- #
# -------------------------------------------------------------------------- #

DASHBOARD_DONORS: dict = individual_dashboard_donors()
EU27: dict = donor_groupings()["eu27_countries"]

RECIPIENT_GROUPS = {
    "Developing countries, total": None,
    "Africa": recipient_groupings()["african_countries_regional"],
    "Sahel countries": recipient_groupings()["sahel"],
    "Least developed countries": recipient_groupings()["ldc_countries"],
    "France priority countries": recipient_groupings()["france_priority"],
}

CURRENCIES: dict = {"USD": "USA", "EUR": "EUI", "GBP": "GBR", "CAD": "CAN"}


def get_crs_indicators_usd_current(
        donors: dict,
        start_year: int,
        end_year: int,
        indicators: dict,
        recipients_group_name: str,
        recipients: dict,
) -> pd.DataFrame:
    """Get CRS indicators in USD current prices."""

    cols = [
        "year",
        "indicator",
        "donor_code",
        "purpose_code",
        "currency",
        "prices",
    ]

    if recipients is not None:
        recipients = list(recipients)

    oda = ODAData(
        years=range(start_year, end_year + 1),
        donors=list(donors),
        recipients=recipients,
        include_names=False,
    )

    oda.load_indicator(list(indicators))

    data = (
        oda.get_data()
        .groupby(cols, observed=True, dropna=False, as_index=False)["value"]
        .sum()
        .assign(
            indicator=lambda d: d.indicator.map(indicators),
            recipient_name=recipients_group_name,
        )
    )

    return data


def convert_crs_to_version(df: pd.DataFrame) -> pd.DataFrame:
    """Convert an indicator from the CRS in USD current prices to other
    currency-prices combinations.
    """

    data = []

    for version in versions_dictionary().values():
        if version["prices"] == "constant":
            data.append(
                oecd_dac_deflate(
                    data=df,
                    base_year=version["base_year"],
                    source_currency="USA",
                    target_currency=CURRENCIES[version["currency"]],
                    id_column="Donor Code",
                    use_source_codes=True,
                    year_column="year",
                    value_column="value",
                ).assign(Prices=version["prices"], Currency=version["currency"])
            )
        elif version["currency"] != "USD":
            data.append(
                oecd_dac_exchange(
                    data=df,
                    source_currency="USA",
                    target_currency=CURRENCIES[version["currency"]],
                    id_column="Donor Code",
                    use_source_codes=True,
                    year_column="year",
                    value_column="value",
                ).assign(Prices=version["prices"], Currency=version["currency"])
            )

    return pd.concat(data, ignore_index=True)


def add_total_indicator(df: pd.DataFrame) -> pd.DataFrame:
    """Add a total indicator to the data"""

    cols = [c for c in df.columns if c not in ["Value", "Indicator"]]

    total = (
        df.groupby(cols, observed=True, dropna=False)
        .sum(numeric_only=True)
        .reset_index()
        .assign(Indicator="Total")
    )

    return pd.concat([df, total], ignore_index=True)


def indicator_recipient_total(df: pd.DataFrame, grouper: list) -> pd.DataFrame:
    return (
        df.groupby(grouper, observed=True, dropna=False)
        .sum(numeric_only=True)
        .reset_index()
        .filter(grouper + ["Value"], axis=1)
    )


def add_share_of_indicator(df: pd.DataFrame, grouper: list) -> pd.DataFrame:
    total = indicator_recipient_total(df=df, grouper=grouper)

    return (
        df.merge(total, on=grouper, how="left", suffixes=("", "_total"))
        .assign(share_of_indicator=lambda d: round(100 * d.value / d.value_total, 6))
        .reset_index(drop=True)
        .drop("value_total", axis=1)
    )


def indicator_recipients_pipeline(
        usd_data_callable: callable,
        donors: dict,
) -> pd.DataFrame:
    """Pipeline for individual donors to groups of recipients"""

    # Empty list to store the data
    data = []

    # Get the USD current data for each group
    for recipient, codes in RECIPIENT_GROUPS.items():
        data.append(
            usd_data_callable(
                recipients=codes,
                donors=donors,
                recipients_group_name=recipient,
            )
        )

    usd_data = (
        pd.concat(data, ignore_index=True)
        .drop_duplicates()
        .rename(columns=config.COLUMNS)
        .replace(config.VALUES, regex=False)
    )

    # Convert to different currencies
    converted_data = convert_crs_to_version(df=usd_data)

    return pd.concat([usd_data, converted_data], ignore_index=True)


def create_donor_groups_flows(flows_df: pd.DataFrame) -> pd.DataFrame:
    flows = []

    flows_cols = [c for c in flows_df.columns if c not in ["Value", "Donor code"]]

    groups = {
        20001: donor_groupings()["dac_countries"],
        20006: donor_groupings()["non_dac_countries"],
        20003: donor_groupings()["g7"],
        90027: donor_groupings()["eu27_countries"],
    }

    for name, group in groups.items():
        flows.append(
            flows_df.query(f"`Donor code` in {list(group)}")
            .groupby(flows_cols, observed=True, dropna=False)
            .sum(numeric_only=True)
            .drop("Donor Code", axis=1)
            .reset_index()
            .assign(donor_code=name)
            .rename(columns={"donor_code": "Donor code"})
        )

    return pd.concat(flows, ignore_index=True)


def create_donor_groups_gni(gni_df: pd.DataFrame) -> pd.DataFrame:
    gni = []

    gni_cols = [c for c in gni_df.columns if c not in ["Value", "Donor code"]]

    groups = {
        20001: donor_groupings()["dac_countries"],
        20006: donor_groupings()["non_dac_countries"],
        20003: donor_groupings()["g7"],
        90027: donor_groupings()["eu27_countries"],
    }

    for name, group in groups.items():
        gni.append(
            gni_df.query(f"`Donor code` in {list(group)}")
            .groupby(gni_cols, observed=True, dropna=False)
            .sum(numeric_only=True)
            .drop("Donor code", axis=1)
            .reset_index()
            .assign(donor_code=name)
            .rename(columns={"donor_code": "Donor code"})
        )

    return pd.concat(gni, ignore_index=True)


def add_sectors_and_subsectors(flows: pd.DataFrame) -> pd.DataFrame:
    """Group data by subsectors and sectors, given mappings to group by."""

    # Track columns to group by
    cols = [
        c
        for c in flows.columns
        if c not in ["Value", "Share of total", "Share of indicator", "purpose_code"]
    ]

    # Load the sector and broad sector mappings
    sectors = sector_lists.get_sector_groups()
    broad_sectors = sector_lists.get_broad_sector_groups()

    # Add subsector column (based on sector mappings)
    for name, codes in sectors.items():
        flows.loc[flows.purpose_code.isin(codes), "Sub-sector"] = name

    # Add sector column (based on broad sector mappings)
    flows["Sector"] = flows["Sub-sector"].map(broad_sectors)

    # Group by the original columns + subsector and sector
    flows = (
        flows.groupby(cols + ["Sub-sector", "Sector"], observed=True, dropna=False)
        .sum(numeric_only=True)
        .drop("purpose_code", axis=1)
        .loc[lambda d: d.value != 0]
        .reset_index(drop=False)
    )

    return flows


def add_share_of_total(
        df: pd.DataFrame, total_indicator: str, group_by: list | None = None
) -> pd.DataFrame:
    """Add a share of total indicator to the data"""

    if group_by is None:
        group_by = [
            "Year",
            "Indicator",
            "Donor code",
            "Recipient",
            "Prices",
            "Currency",
        ]

    total = (
        df.groupby(group_by, observed=True, dropna=False)
        .sum(numeric_only=True)
        .reset_index()
        .loc[lambda d: d.Indicator == total_indicator]
        .filter(
            [
                "Year",
                "Donor code",
                "Recipient",
                "Prices",
                "Currency",
                "Value",
            ]
        )
    )

    combined = df.merge(
        total,
        on=["Year", "Prices", "Currency", "Donor code", "Recipient"],
        how="left",
        suffixes=("", "_total"),
    ).assign(share_of_total=lambda d: round(100 * d.value / d.value_total, 6))

    return combined.reset_index(drop=True).drop("value_total", axis=1)


def add_share_of_sector(
        df: pd.DataFrame, total_indicator: str, group_by: list | None = None
) -> pd.DataFrame:
    """Add a share of total indicator to the data"""

    if group_by is None:
        group_by = [
            "Year",
            "Indicator",
            "Donor code",
            "Recipient",
            "Sector",
            "Prices",
            "Currency",
        ]

    total = (
        df.groupby(group_by, observed=True, dropna=False)
        .sum(numeric_only=True)
        .reset_index()
        .loc[lambda d: d.Indicator == total_indicator]
        .filter(
            [
                "Year",
                "Donor code",
                "Recipient",
                "Sector",
                "Prices",
                "Currency",
                "Value",
            ]
        )
    )

    combined = df.merge(
        total,
        on=[
            "Year",
            "Prices",
            "Currency",
            "Donor code",
            "Recipient",
            "Sector",
        ],
        how="left",
        suffixes=("", "_total"),
    ).assign(share_of_sector_total=lambda d: round(100 * d.value / d.value_total, 6))

    return combined.reset_index(drop=True).drop("value_total", axis=1)

def add_share_of_subsector(
        df: pd.DataFrame, total_indicator: str, group_by: list | None = None
) -> pd.DataFrame:
    """
    Add a share of subsector to the data.

    Parameters:
        df (pd.DataFrame): The input DataFrame.
        total_indicator (str): The total indicator used for calculations.
        group_by (list | None): Columns to group by. Defaults to a standard set of columns.

    Returns:
        pd.DataFrame: The modified DataFrame with a share_of_subsector_total column.
    """
    if group_by is None:
        group_by = [
            "Year",
            "Indicator",
            "Donor code",
            "Recipient",
            "Sector",
            "Sub-sector",
            "Prices",
            "Currency",
        ]

    subsector_total = (
        df.groupby(group_by, observed=True, dropna=False)
        .sum(numeric_only=True)
        .reset_index()
        .loc[lambda d: d.Indicator == total_indicator]
        .filter(
            [
                "Year",
                "Donor code",
                "Recipient",
                "Sector",
                "Sub-sector",
                "Prices",
                "Currency",
                "Value",
            ]
        )
        .rename(columns={"Value": "value_subsector_total"})
    )

    combined = (
        df.merge(
            subsector_total,
            on=[
                "Year",
                "Prices",
                "Currency",
                "Donor Code",
                "Recipient Name",
                "Sector",
                "Sub-sector",
            ],
            how="left",
        )
        .assign(
            share_of_subsector_total=lambda d: round(100 * d.value / d.value_subsector_total, 6)
        )
    )

    return combined
