import pandas as pd
from oda_data import OECDClient
from oda_data.tools.groupings import provider_groupings
from oda_data.indicators.research.eu import get_eui_plus_bilateral_providers_indicator

from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_donor_groupings,
    add_donor_names,
    widen_currency_price,
    add_recipient_indicator_codes,
    add_recipient_groupings,
    add_recipient_names,
    add_share_of_recipients_total_oda,
)
from src.data.config import PATHS, RECIPIENTS_INDICATORS, BASE_TIME, logger

from src.data.analysis_tools.helper_functions import (
    save_time_range_to_json,
    set_cache_dir,
    get_dac_ids,
    eui_bi_code,
    parquet_to_stdout,
    convert_values_to_units,
)

set_cache_dir(oda_data=True, pydeflate=True)
donor_ids = get_dac_ids(PATHS.DONORS)
recipient_ids = get_dac_ids(PATHS.RECIPIENTS)
eu_ids = provider_groupings()["eu27_total"]


def get_dac2a():
    dac2a_raw = OECDClient(
        years=range(BASE_TIME["start"], BASE_TIME["end"] + 1),
        providers=donor_ids,
        recipients=recipient_ids,
        use_bulk_download=False,
    ).get_indicators(list(RECIPIENTS_INDICATORS.keys()))

    dac2a = (
        dac2a_raw.groupby(
            ["year", "donor_code", "recipient_code", "one_indicator"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator=lambda d: d["one_indicator"].map(RECIPIENTS_INDICATORS))
        .drop(columns=["one_indicator"])
    )

    return dac2a


def get_dac2a_eui_eu27():
    dac2a_client = OECDClient(
        years=range(BASE_TIME["start"], BASE_TIME["end"] + 1),
        providers=donor_ids,
        recipients=recipient_ids,
        use_bulk_download=False,
    )

    eui_eu27_dac2a_raw = get_eui_plus_bilateral_providers_indicator(
        dac2a_client, indicator=list(RECIPIENTS_INDICATORS.keys())
    )

    eui_eu27_dac2a = (
        eui_eu27_dac2a_raw.query("donor_code == 918")
        .assign(donor_code=eui_bi_code)
        .assign(indicator=lambda d: d["one_indicator"].map(RECIPIENTS_INDICATORS))[
            ["year", "donor_code", "recipient_code", "indicator", "value"]
        ]
    )

    return eui_eu27_dac2a


def combined_recipients():
    dac2a = get_dac2a()
    eui_eu27_dac2a = get_dac2a_eui_eu27()

    recipients_raw = pd.concat([dac2a, eui_eu27_dac2a])

    recipients = recipients_raw[recipients_raw["value"] != 0]

    # Add currencies and prices
    recipients = add_currencies_and_prices(recipients)

    # Add donor groupings
    recipients = add_donor_groupings(recipients)

    # Add recipient groupings
    recipients = add_recipient_groupings(recipients)

    # Add indicator code
    recipients = add_recipient_indicator_codes(recipients)

    # Add donor name
    recipients = add_donor_names(recipients)

    # Add recipient name
    recipients = add_recipient_names(recipients)

    # Pivot values to columns
    recipients = widen_currency_price(
        df=recipients,
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
    recipients = add_share_of_recipients_total_oda(recipients)

    # Convert values to units (integers) for better compression
    # NOTE: Frontend queries must divide value_* columns by 1e6 to get millions
    recipients = convert_values_to_units(recipients)

    return recipients


if __name__ == "__main__":
    save_time_range_to_json(BASE_TIME, "base_time.json")
    logger.info("Generating recipients table...")
    df = combined_recipients()
    parquet_to_stdout(df)
