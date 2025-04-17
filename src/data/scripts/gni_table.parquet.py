import pandas as pd

from oda_data import DAC1Data
from oda_data.tools.groupings import provider_groupings

from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
    get_dac_ids,
    df_to_parquet,
)
from src.data.config import PATHS, FINANCING_TIME, logger

eu_ids = provider_groupings()["eu27_countries"]


def get_gni():
    donor_ids = get_dac_ids(PATHS.DONORS)

    bilateral_df = DAC1Data(
        years=range(FINANCING_TIME["start"], FINANCING_TIME["end"] + 1)
    ).read(
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

    if all(code in bilateral_df.donor_code.values for code in eu_ids):

        eu_df = (
            bilateral_df.query("donor_code in @eu_ids")
            .groupby(
                [
                    "year",
                ],
                observed=True,
                dropna=False,
            )["value"]
            .sum()
            .reset_index()
            .assign(donor_code=918)
        )

    else:
        raise Exception("Not all EU countries present in df")

    df = pd.concat([bilateral_df, eu_df])

    return df


def gni_to_parquet():
    df = get_gni()
    df_to_parquet(df)


if __name__ == "__main__":
    logger.info("Generating GNI table...")
    set_cache_dir(oda_data=True)
    gni_to_parquet()
