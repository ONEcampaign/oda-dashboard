import pandas as pd

from oda_data import bilateral_policy_marker

from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_donor_groupings,
    add_recipient_groupings,
    add_donor_names,
    add_recipient_names,
    widen_currency_price,
    add_gender_indicator_codes,
    add_gender_share_of_total_oda,
)
from src.data.config import PATHS, BASE_TIME, GENDER_INDICATORS, logger
from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
    get_dac_ids,
    parquet_to_stdout,
)

donor_ids = get_dac_ids(PATHS.DONORS)
recipient_ids = get_dac_ids(PATHS.RECIPIENTS)
set_cache_dir(oda_data=True)


def get_transform_gender():
    """Fetch and combine all gender marker scores"""
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

    # Map gender scores to indicator names
    gender = (
        gender_raw.assign(indicator=lambda d: d["gender"].map(GENDER_INDICATORS))
        .groupby(
            ["year", "donor_code", "recipient_code", "indicator"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
    )

    # Remove zero values
    gender = gender[gender["value"] != 0]

    return gender


def combined_gender():
    """Create comprehensive gender view with all transformations"""
    gender = get_transform_gender()

    # Add currencies and prices (USD/EUR/GBP/CAD x current/constant)
    gender = add_currencies_and_prices(gender)

    # Add donor groupings (DAC countries, G7, etc.)
    gender = add_donor_groupings(gender)

    # Add recipient groupings (Developing countries, Africa, etc.)
    gender = add_recipient_groupings(gender)

    # Add donor names
    gender = add_donor_names(gender)

    # Add recipient names
    gender = add_recipient_names(gender)

    # Add indicator codes
    gender = add_gender_indicator_codes(gender)

    # Pivot currency/price to wide columns
    gender = widen_currency_price(
        df=gender,
        index_cols=(
            "year",
            "donor_code",
            "donor_name",
            "recipient_code",
            "recipient_name",
            "indicator",
            "indicator_name",
        ),
    )

    # Add share of total ODA
    gender = add_gender_share_of_total_oda(gender)

    return gender


if __name__ == "__main__":
    logger.info("Generating gender view table...")
    set_cache_dir(oda_data=True)
    df = combined_gender()
    logger.info("Writing parquet to stdout...")
    parquet_to_stdout(df)
