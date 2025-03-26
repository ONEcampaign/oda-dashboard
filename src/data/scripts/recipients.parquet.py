from oda_data import Dac2aData, set_data_path
from src.data.config import PATHS, time_range, logger

from src.data.analysis_tools.utils import get_dac_ids, load_indicators, to_decimal, return_pa_table

set_data_path(PATHS.ODA_DATA)


def filter_transform_dac2a():

    donor_ids = get_dac_ids(PATHS.DONORS)
    recipient_ids = get_dac_ids(PATHS.RECIPIENTS)
    indicator_ids = load_indicators("recipients")

    df_raw = Dac2aData(years=range(time_range["start"], time_range["end"] + 1)).read(
        using_bulk_download=True,
        additional_filters=[
            ("amount_type", "==", "Current prices"),
            ("donor_code", "in", donor_ids),
            ("recipient_code", "in", recipient_ids),
            ("aidtype_code", "in", indicator_ids.keys()),
        ],
    )

    df = (
        df_raw.groupby(
            [
                "year",
                "donor_code",
                "recipient_code",
                "aidtype_code",
            ],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator=lambda d: d["aidtype_code"].astype(str).map(indicator_ids))
        .drop(columns="aidtype_code")
    )

    df = df[df["value"] != 0]

    return df


def convert_types(df):

    df["year"] = df["year"].astype("category")
    df["donor_code"] = df["donor_code"].astype("category")
    df["recipient_code"] = df["recipient_code"].astype("category")
    df["indicator"] = df["indicator"].astype("category")
    df["value"] = df["value"].apply(lambda x: to_decimal(x))

    return df


def create_parquet():

    df = filter_transform_dac2a()
    converted_df = convert_types(df)
    return_pa_table(converted_df)


if __name__ == "__main__":
    logger.info("Generating recipients table...")
    create_parquet()
