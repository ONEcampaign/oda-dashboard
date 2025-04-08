from oda_data import Dac1Data

from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
    get_dac_ids,
    df_to_parquet,
)
from src.data.config import PATHS, TIME_RANGE, logger


def get_gni():
    donor_ids = get_dac_ids(PATHS.DONORS)

    df = Dac1Data(years=range(TIME_RANGE["start"], TIME_RANGE["end"] + 1)).read(
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


def gni_to_parquet():
    df = get_gni()
    df_to_parquet(df)


if __name__ == "__main__":
    logger.info("Generating GNI table...")
    set_cache_dir(oda_data=True)
    gni_to_parquet()
