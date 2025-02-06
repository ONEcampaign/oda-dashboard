from functools import partial

import pandas as pd
from oda_data import set_data_path
from oda_data.tools.groupings import donor_groupings
from pydeflate import set_pydeflate_path

from scripts import config
from scripts.analysis.common import (
    DASHBOARD_DONORS,
    add_sectors_and_subsectors,
    add_share_of_indicator,
    add_share_of_sector,
    add_share_of_total,
    create_donor_groups_flows,
    get_crs_indicators_usd_current,
    indicator_recipients_pipeline,
)
from scripts.analysis_tools.sector_lists import get_broad_sector_groups

# Set the path to the raw data folder
set_data_path(config.PATHS.raw_data)
set_pydeflate_path(config.PATHS.raw_data)

# ------ Functions for the pipeline ------
_get_gender_data_usd_current = partial(
    get_crs_indicators_usd_current,
    start_year=config.SECTORS_YEARS["start"],
    end_year=config.SECTORS_YEARS["end"],
    indicators=config.GENDER_INDICATORS,
)

gender_recipients_pipeline = partial(
    indicator_recipients_pipeline, _get_gender_data_usd_current
)


def _summarise_sectors(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["share_of_total", "share_of_indicator", "value"]

    df = (
        df.assign(purpose_code=lambda d: d.purpose_code.map(get_broad_sector_groups()))
        .groupby(
            [c for c in df.columns if c not in cols],
            as_index=False,
            dropna=False,
            observed=True,
        )
        .sum(numeric_only=True)
        .loc[lambda d: d.value.notna()]
        .loc[lambda d: d.value > 0]
    )

    # add "All sectors" total
    df_total = (
        df.assign(purpose_code="All sectors")
        .groupby(
            [c for c in df.columns if c not in cols],
            as_index=False,
            dropna=False,
            observed=True,
        )
        .sum(numeric_only=True)
    )

    return pd.concat([df, df_total], ignore_index=True)


def export_sectors_data() -> None:
    individual_flows_data = gender_recipients_pipeline(
        donors=donor_groupings()["all_official"]
    )

    # create groups
    groups_flows_data = create_donor_groups_flows(flows_df=individual_flows_data)

    # combine data
    flows = pd.concat([individual_flows_data, groups_flows_data], ignore_index=True)

    cols = ["year", "Prices", "Currency", "Donor Code", "Recipient", "Indicator"]

    # add shares
    flows = (
        flows.pipe(add_sectors_and_subsectors)
        .pipe(add_share_of_total, total_indicator="Gender Allocable")
        .pipe(add_share_of_indicator, grouper=cols)
        .pipe(_summarise_sectors)
        .pipe(add_share_of_sector, total_indicator="Gender Allocable")
    )

    # clean
    combined = (
        flows.rename(columns=config.COLUMNS)
        .replace(config.VALUES, regex=False)
        .loc[lambda d: d["Donor Code"].isin(DASHBOARD_DONORS)]
    )

    combined["Donor"] = combined["Donor Code"].map(
        donor_groupings()["all_official"]
        | donor_groupings()["dac1_aggregates"]
        | {90027: "EU27 countries, total"}
    )

    combined = combined.drop(["Donor Code"], axis=1).rename(columns={"year": "Year"})

    # Export the data
    combined.to_csv(config.PATHS.output / "gender.csv", index=False)


if __name__ == "__main__":
    export_sectors_data()