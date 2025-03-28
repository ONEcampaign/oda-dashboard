import pandas as pd

from oda_data import Dac1Data, set_data_path

from src.data.config import PATHS, time_range, logger

from src.data.analysis_tools.utils import get_dac_ids, load_indicators, convert_types, return_pa_table

set_data_path(PATHS.ODA_DATA)


def get_dac1_flow():

    donor_ids = get_dac_ids(PATHS.DONORS)
    indicator_ids = load_indicators("financing")['flow']

    df_raw = (
        Dac1Data(years=range(time_range["start"], 2018))
        .read(
            using_bulk_download=True,
            additional_filters=[
                ("amount_type", "==", "Current prices"),
                ("donor_code", "in", donor_ids),
                ("aidtype_code", "in", indicator_ids.keys()),
                ("flows_code", "==", 1140),
            ],
        )
    )

    df = (
        df_raw.groupby(
            ["year", "donor_code", "aidtype_code"], dropna=False, observed=True
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator=lambda d: d["aidtype_code"].astype(str).map(indicator_ids))
        .drop(columns="aidtype_code")
    )

    df = df[df["value"] != 0]

    return df

def get_dac1_ge():

    donor_ids = get_dac_ids(PATHS.DONORS)
    indicator_ids = load_indicators("financing")['ge']

    df_raw = (
        Dac1Data(years=range(2018, time_range['end'] + 1))
        .read(
            using_bulk_download=True,
            additional_filters=[
                ("amount_type", "==", "Current prices"),
                ("donor_code", "in", donor_ids),
                ("aidtype_code", "in", indicator_ids.keys()),
                ("flows_code", "==", 1160),
            ],
        )
    )

    df = (
        df_raw.groupby(
            ["year", "donor_code", "aidtype_code"], dropna=False, observed=True
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator=lambda d: d["aidtype_code"].astype(str).map(indicator_ids))
        .drop(columns="aidtype_code")
    )

    df = df[df["value"] != 0]

    return df


def get_dac1_grants():

    donor_ids = get_dac_ids(PATHS.DONORS)
    indicator_ids = load_indicators("financing")['grant']

    df_raw = Dac1Data(years=range(time_range["start"], time_range["end"] + 1)).read(
        using_bulk_download=True,
        additional_filters=[
            ("amount_type", "==", "Current prices"),
            ("donor_code", "in", donor_ids),
            ("aidtype_code", "==", 1010),
            ("flows_code", "in", indicator_ids.keys()),
        ],
    )

    df = (
        df_raw.groupby(
            ["year", "donor_code", "flows_code"], dropna=False, observed=True
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator=lambda d: d["flows_code"].astype(str).map(indicator_ids))
        .drop(columns="flows_code")
    )

    df = df[df["value"] != 0]

    return df


def financing_to_parquet():

    flow = get_dac1_flow()
    ge = get_dac1_ge()
    grants = get_dac1_grants()

    financing_df = pd.concat([flow, ge, grants])

    converted_df = convert_types(financing_df)
    return_pa_table(converted_df)



if __name__ == "__main__":
    logger.info("Generating financing table...")
    financing_to_parquet()
