import sys
import json
import pandas as pd
from pydeflate import oecd_dac_deflate, set_pydeflate_path

from src.data.config import logger, PATHS, time_range, base_year

set_pydeflate_path(PATHS.PYDEFLATE)


def create_df():
    with open(PATHS.DONORS) as f:
        donor_dict = json.load(f)

    donor_codes = [int(k) for k in donor_dict.keys()]

    years = range(time_range["start"], time_range["end"] + 1)

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
            base_year=base_year,
            source_currency="USA",
            target_currency=country,
            year_column="year",
            id_column="dac_code",
            use_source_codes=True,
            value_column="value",
            target_value_column=f"{code}_constant",
        )

    return df.drop(columns=["value"])


def get_conversion_table():
    constant_df = deflate_current_usd()

    constant_df.to_csv(sys.stdout, index=False)


if __name__ == "__main__":
    logger.info("Creating constant conversions table")
    get_conversion_table()
