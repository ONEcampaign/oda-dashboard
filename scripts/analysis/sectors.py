from functools import partial

import pandas as pd
from oda_data import set_data_path
from oda_data.tools.groupings import donor_groupings
from pydeflate import set_pydeflate_path

from scripts import config
from scripts.analysis_tools.get_unique_values import get_unique_values
from scripts.analysis.common import (
    DASHBOARD_DONORS,
    add_sectors_and_subsectors,
    add_share_of_indicator,
    add_total_indicator,
    create_donor_groups_flows,
    create_donor_groups_gni,
    get_crs_indicators_usd_current,
    indicator_recipients_pipeline,
)

# Set the path to the raw data folder
set_data_path(config.PATHS.raw_data)
set_pydeflate_path(config.PATHS.raw_data)

# ------ Functions for the pipeline ------
_get_sectors_data_usd_current = partial(
    get_crs_indicators_usd_current,
    start_year=config.SECTORS_YEARS["start"],
    end_year=config.SECTORS_YEARS["end"],
    indicators=config.SECTORS_INDICATORS,
)

sectors_recipients_pipeline = partial(
    indicator_recipients_pipeline, _get_sectors_data_usd_current
)


def add_indicator_descriptions(df: pd.DataFrame) -> pd.DataFrame:
    import json

    # Read the indicators.json file
    with open(config.PATHS.scripts / "analysis_tools/indicators.json", "r") as f:
        indicators = json.load(f)

    names = config.SECTORS_INDICATORS
    indicators = {names[k]: v for k, v in indicators.items() if k in names}

    return df.assign(description=lambda d: d.Indicator.map(indicators).fillna(""))


def add_share_of_total(df: pd.DataFrame) -> pd.DataFrame:
    """Add a share of total indicator to the data"""

    total = (
        df.groupby(
            ["Year", "Indicator", "Donor code", "Recipient", "Prices", "Currency"],
            observed=True,
            dropna=False,
        )
        .sum(numeric_only=True)
        .reset_index()
        .loc[lambda d: d.Indicator == "Total"]
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
        on=["Year", "Prices", "Currency", "Donor code", "Recipient name"],
        how="left",
        suffixes=("", "_total"),
    ).assign(share_of_total=lambda d: round(100 * d.value / d.value_total, 6))

    return combined.reset_index(drop=True).drop("value_total", axis=1)


def _add_dac_total(df: pd.DataFrame) -> pd.DataFrame:
    dac = donor_groupings()["dac_countries"]

    data = df.query(f"donor_code in {list(dac)}").copy()
    idx = [c for c in data.columns if c not in ["Value", "donor_code", "donor_name"]]

    data = (
        data.groupby(idx, observed=True, dropna=False)
        .sum(numeric_only=True)
        .reset_index()
        .assign(donor_code=20001, donor_name="DAC countries, total")
    )

    return pd.concat([df, data], ignore_index=True)


def export_sectors_data() -> None:
    individual_donors = sectors_recipients_pipeline(
        donors=donor_groupings()["all_official"]
    )

    individual_gni_data = individual_donors.loc[lambda d: d["Indicator"] == "GNI"].drop(
        ["Indicator", "Recipient", "purpose_code"], axis=1
    )
    individual_flows_data = individual_donors.loc[lambda d: d["Indicator"] != "GNI"]

    # create groups
    groups_flows_data = create_donor_groups_flows(flows_df=individual_flows_data)
    groups_gni_data = create_donor_groups_gni(gni_df=individual_gni_data)

    # combine data
    flows = pd.concat([individual_flows_data, groups_flows_data], ignore_index=True)
    gni = pd.concat(
        [individual_gni_data, groups_gni_data], ignore_index=True
    ).drop_duplicates()

    cols = ["Year", "Prices", "Currency", "Donor code", "Recipient", "Indicator"]

    # add shares
    flows = (
        flows.pipe(add_sectors_and_subsectors)
        .pipe(add_total_indicator)
        .pipe(add_share_of_total)
        .pipe(add_share_of_indicator, grouper=cols)
    )

    # combine with gni data and calculate share
    combined = (
        flows.merge(
            gni,
            on=["Year", "Donor code", "Currency", "Prices"],
            how="left",
            suffixes=("", "_gni"),
        )
        .assign(gni_share=lambda d: round(100 * d.value / d.value_gni, 6))
        .drop("value_gni", axis=1)
    )

    # clean
    combined = (
        combined.rename(columns=config.COLUMNS)
        .replace(config.VALUES, regex=False)
        .loc[lambda d: d["Donor code"].isin(DASHBOARD_DONORS)]
    )

    combined["Donor name"] = combined["Donor code"].map(
        donor_groupings()["all_official"]
        | donor_groupings()["dac1_aggregates"]
        | {90027: "EU27 countries, total"}
    )

    combined = (
        combined.drop(["Donor code"], axis=1)
        .loc[lambda d: d.year > config.SECTORS_YEARS["start"] + 1]
    )

    # Export the data
    combined.to_csv(config.PATHS.output / "sectors.csv", index=False)

    get_unique_values(combined, "Sectors")


if __name__ == "__main__":
    ...
    export_sectors_data() # df = pd.read_csv(settings.PATHS.output / "sectors.csv")