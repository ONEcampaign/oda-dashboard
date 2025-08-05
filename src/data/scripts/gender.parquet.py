import pandas as pd

from oda_data import bilateral_policy_marker

from src.data.config import PATHS, BASE_TIME, GENDER_INDICATORS, logger

from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
    get_dac_ids,
    add_index_column,
    df_to_parquet,
)

donor_ids = get_dac_ids(PATHS.DONORS)
recipient_ids = get_dac_ids(PATHS.RECIPIENTS)


def get_transform_gender():

    dfs = []
    for scr in GENDER_INDICATORS.keys():
        df = bilateral_policy_marker(
            years=range(BASE_TIME["start"], BASE_TIME["end"] + 1),
            providers=donor_ids,
            recipients=recipient_ids,
            measure="gross_disbursement",
            marker="gender",
            marker_score=scr,
        )

        dfs.append(df)

    gender_raw = pd.concat(dfs, ignore_index=True)

    gender = (
        gender_raw.assign(indicator=lambda d: d["gender"].map(GENDER_INDICATORS))
        .groupby(
            [
                "year",
                "donor_code",
                "recipient_code",
                "indicator",
            ],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
    )

    gender = gender[gender["value"] != 0]

    gender = add_index_column(
        df=gender,
        column="indicator",
        json_path=PATHS.TOOLS / "gender_indicators.json",
        ordered_list=list(GENDER_INDICATORS.values()),
    )

    return gender


def gender_to_parquet():
    df = get_transform_gender()
    # Use a lightweight compression setting so DuckDB can read the files
    # in the browser without incurring heavy decompression costs.
    df_to_parquet(df, compression="zstd", compression_level=1)


if __name__ == "__main__":
    logger.info("Generating gender table...")
    set_cache_dir(oda_data=True)
    gender_to_parquet()
