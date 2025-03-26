from oda_data import Dac1Data, set_data_path

from src.data.config import PATHS, time_range, logger

from src.data.analysis_tools.utils import get_dac_ids, to_decimal, return_pa_table

set_data_path(PATHS.ODA_DATA)


def get_gni():

    donor_ids = get_dac_ids(PATHS.DONORS)

    df = Dac1Data(years=range(time_range["start"], time_range["end"] + 1)).read(
        using_bulk_download=True,
        additional_filters=[
            ("amount_type", "==", "Current prices"),
            ("donor_code", "in", donor_ids),
            ("aidtype_code", "==", 1),
        ],
        columns=[
            "donor_code",
            "year",
            "value",
        ],
    )

    return df


def convert_types(df):

    df["year"] = df["year"].astype("category")
    df["donor_code"] = df["donor_code"].astype("category")
    df["value"] = df["value"].apply(lambda x: to_decimal(x))

    return df


def create_parquet():
    df = get_gni()
    converted_df = convert_types(df)
    return_pa_table(converted_df)


if __name__ == "__main__":
    logger.info("Generating GNI table...")
    create_parquet()
