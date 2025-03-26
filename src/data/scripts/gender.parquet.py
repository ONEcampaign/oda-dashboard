from oda_data import CrsData, set_data_path
from src.data.config import PATHS, time_range, logger

from src.data.analysis_tools.utils import get_dac_ids, to_decimal, return_pa_table

set_data_path(PATHS.ODA_DATA)


def get_filter_crs():

    donor_ids = get_dac_ids(PATHS.DONORS)
    recipient_ids = get_dac_ids(PATHS.RECIPIENTS)

    df = CrsData(years=range(time_range["start"], time_range["end"] + 1)).read(
        using_bulk_download=True,
        additional_filters=[
            ("donor_code", "in", donor_ids),
            ("recipient_code", "in", recipient_ids),
        ],
    )

    return df


def transform_gender():

    crs = get_filter_crs()

    # Format gender df including all flows (flow_name)
    gender = (
        crs.fillna({"gender": "9"})
        .groupby(
            [
                "year",
                "donor_code",
                "recipient_code",
                "gender",
            ],
            dropna=False,
            observed=True,
        )["usd_disbursement"]
        .sum()
        .reset_index()
        .rename(columns={"gender": "indicator", "usd_disbursement": "value"})
    )

    gender = gender[gender["value"] != 0]

    gender["indicator"] = gender["indicator"].astype(float).astype("int16[pyarrow]")

    return gender


def convert_types(df):

    df["year"] = df["year"].astype("category")
    df["donor_code"] = df["donor_code"].astype("category")
    df["recipient_code"] = df["recipient_code"].astype("category")
    df["indicator"] = df["indicator"].astype("category")
    df["value"] = df["value"].apply(lambda x: to_decimal(x))

    return df


def create_parquet():
    df = transform_gender()
    converted_df = convert_types(df)
    return_pa_table(converted_df)


if __name__ == "__main__":
    logger.info("Generating gender table...")
    create_parquet()
