import sys
import json
import pandas as pd
from pydeflate import oecd_dac_deflate

from src.data.config import logger, PATHS, BASE_TIME
from src.data.analysis_tools.helper_functions import set_cache_dir, get_eui


def create_df():
    with open(PATHS.DONORS) as f:
        donor_dict = json.load(f)

    donor_codes = [int(k) for k in donor_dict.keys()]

    years = range(BASE_TIME["start"], BASE_TIME["end"] + 1)

    df = pd.DataFrame(
        index=pd.MultiIndex.from_product(
            [years, donor_codes], names=["year", "dac_code"]
        )
    ).reset_index()

    df["value"] = 1

    return df


def deflate_current_usd():

    df = create_df()

    codes = {"USA": "usd", "CAN": "cad", "FRA": "eur", "GBR": "gbp"}
    for country, code in codes.items():
        df = oecd_dac_deflate(
            data=df,
            base_year=BASE_TIME["base"],
            source_currency="USA",
            target_currency=country,
            year_column="year",
            id_column="dac_code",
            use_source_codes=True,
            value_column="value",
            target_value_column=f"{code}_constant",
        )

    df = df.drop(columns=["value"])

    eui_df = get_eui(df)

    df = pd.concat([df, eui_df])

    return df


def get_conversion_table():
    constant_df = deflate_current_usd()
    constant_df.to_csv(sys.stdout, index=False)


if __name__ == "__main__":
    logger.info("Creating constant conversions table")
    set_cache_dir(pydeflate=True)
    get_conversion_table()
