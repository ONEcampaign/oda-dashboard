import pandas as pd
from oda_data import OECDClient
from oda_data.tools.groupings import provider_groupings
from oda_data.indicators.research.eu import get_eui_plus_bilateral_providers_indicator

from src.data.config import PATHS, RECIPIENTS_INDICATORS, BASE_TIME, logger

from src.data.analysis_tools.helper_functions import (
    save_time_range_to_json,
    set_cache_dir,
    get_dac_ids,
    add_index_column,
    df_to_parquet,
    eui_bi_code
)

donor_ids = get_dac_ids(PATHS.DONORS)
recipient_ids = get_dac_ids(PATHS.RECIPIENTS)
eu_ids = provider_groupings()["eu27_total"]


def get_dac2a():

    dac2a_raw = OECDClient(
        years=range(BASE_TIME["start"], BASE_TIME["end"] + 1),
        providers=donor_ids,
        recipients=recipient_ids,
        use_bulk_download=True,
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
        use_bulk_download=True,
    )

    eui_eu27_dac2a_raw = get_eui_plus_bilateral_providers_indicator(
        dac2a_client,
        indicator=list(RECIPIENTS_INDICATORS.keys())
    )

    eui_eu27_dac2a = (
        eui_eu27_dac2a_raw.query("donor_code == 918")
        .assign(donor_code=eui_bi_code)
        .assign(indicator=lambda d: d["one_indicator"].map(RECIPIENTS_INDICATORS))
        [["year", "donor_code", "recipient_code", "indicator", "value"]]
    )

    return eui_eu27_dac2a


def combine_recipients():


    dac2a = get_dac2a()
    eui_eu27_dac2a = get_dac2a_eui_eu27()

    recipients_raw = pd.concat([dac2a, eui_eu27_dac2a])

    recipients = recipients_raw[recipients_raw["value"] != 0]

    recipients = add_index_column(
        df=recipients,
        column="indicator",
        json_path=PATHS.TOOLS / "recipients_indicators.json",
        ordered_list=list(RECIPIENTS_INDICATORS.values()),
    )

    return recipients


def recipients_to_parquet():
    df = combine_recipients()
    df_to_parquet(df)


if __name__ == "__main__":
    save_time_range_to_json(BASE_TIME, "base_time.json")
    logger.info("Generating recipients table...")
    set_cache_dir(oda_data=True)
    recipients_to_parquet()
