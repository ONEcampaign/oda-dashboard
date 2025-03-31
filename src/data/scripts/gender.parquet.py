import pandas as pd

from oda_data import CrsData, set_data_path
from src.data.config import PATHS, time_range, logger

from src.data.analysis_tools.utils import get_dac_ids, add_index_column, convert_types, return_pa_table

set_data_path(PATHS.ODA_DATA)

donor_ids = get_dac_ids(PATHS.DONORS)
recipient_ids = get_dac_ids(PATHS.RECIPIENTS)

indicators_gender = {
    "2.0": "Main target",
    "1.0": "Secondary target",
    "0.0": "Not targeted",
    pd.NA: "Not screened"
}

def filter_transform_gender():


    crs = CrsData(years=range(time_range["start"], time_range["end"] + 1)).read(
        using_bulk_download=True,
        additional_filters=[
            ("donor_code", "in", donor_ids),
            ("recipient_code", "in", recipient_ids),
        ],
        columns=["year", "donor_code", "recipient_code", "gender", "usd_disbursement"]
    )

    # Format gender df including all flows (flow_name)
    gender = (
        crs.assign(indicator=lambda d: d["gender"].map(indicators_gender))
        .groupby(
            [
                "year",
                "donor_code",
                "recipient_code",
                "indicator",
            ],
            dropna=False,
            observed=True,
        )["usd_disbursement"]
        .sum()
        .reset_index()
        .rename(columns={"usd_disbursement": "value"})
    )

    gender = gender[gender["value"] != 0]

    gender = add_index_column(
        df=gender,
        column='indicator',
        json_path=PATHS.TOOLS / 'gender_indicators.json'
    )

    return gender


def gender_to_parquet():

    df = filter_transform_gender()

    converted_df = convert_types(df)

    return_pa_table(converted_df)


if __name__ == "__main__":
    logger.info("Generating gender table...")
    gender_to_parquet()


