import sys
import json
import pandas as pd
from bblocks import add_iso_codes_column
from pydeflate import imf_gdp_deflate, set_pydeflate_path

from src.data.config import logger, PATHS, time_range, base_year

set_pydeflate_path(PATHS.PYDEFLATE)


def create_df():
    with open(PATHS.DONORS) as f:
        data = json.load(f)

    country_codes = pd.DataFrame([
        {"dac_code": code, "country": details["name"]}
        for code, details in data.items()
    ])

    years = range(time_range[0], time_range[1] + 1)

    df = country_codes.assign(key=1).merge(
        pd.DataFrame({"year": years, "key": 1}),
        on="key"
    ).drop(columns="key")

    df = add_iso_codes_column(df, "country", id_type="regex")

    df["value"] = 1

    return df


def deflate_current_usd():

    df = create_df()

    codes = {"USA": "usd", "CAN": "cad", "FRA": "eur", "GBR": "gbp"}
    for country, code in codes.items():
        df = imf_gdp_deflate(
            data=df,
            base_year=base_year,
            source_currency="USA",
            target_currency=country,
            year_column="year",
            id_column="iso_code",
            value_column="value",
            target_value_column=f"{code}_constant",
        )

    return df.drop(columns=["value", "iso_code", "country"]).dropna(thresh=4, axis="rows")


def get_conversion_table():
    constant_df = deflate_current_usd()

    constant_df.to_csv(sys.stdout, index=False)


if __name__ == "__main__":
    logger.info("Creating constant conversions table")
    get_conversion_table()
