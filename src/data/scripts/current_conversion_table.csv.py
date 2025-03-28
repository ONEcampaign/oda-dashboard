import sys

import pandas as pd
from pydeflate import oecd_dac_exchange, set_pydeflate_path

from src.data.config import logger, PATHS, time_range

set_pydeflate_path(PATHS.PYDEFLATE)

codes = {"USA": "usd", "CAN": "cad", "FRA": "eur", "GBR": "gbp"}


def create_df():
    return pd.DataFrame(
        {"year": range(time_range["start"], time_range["end"] + 1), "value": 1}
    )


def convert_currencies():
    df = create_df()

    for country, code in codes.items():
        df["iso_code"] = country

        df = oecd_dac_exchange(
            data=df,
            source_currency="USA",
            target_currency=country,
            year_column="year",
            id_column="iso_code",
            value_column="value",
            target_value_column=f"{code}_current",
        )

    df.drop(columns=["value", "iso_code"], inplace=True)

    return df


def get_conversion_table():
    df = convert_currencies()

    df.to_csv(sys.stdout, index=False)


if __name__ == "__main__":
    logger.info("Creating exchange conversions table")
    get_conversion_table()
