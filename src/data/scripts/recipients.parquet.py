from oda_data import OECDClient
from src.data.config import PATHS, RECIPIENTS_INDICATORS, BASE_TIME, logger

from src.data.analysis_tools.helper_functions import (
    save_time_range_to_json,
    set_cache_dir,
    get_dac_ids,
    add_index_column,
    df_to_parquet,
)

donor_ids = get_dac_ids(PATHS.DONORS)
recipient_ids = get_dac_ids(PATHS.RECIPIENTS)


def filter_transform_recipients():

    dac2a_raw = OECDClient(
        years=range(BASE_TIME["start"], BASE_TIME["end"] + 1),
        providers=donor_ids,
        recipients=recipient_ids,
        use_bulk_download=True,
    ).get_indicators(list(RECIPIENTS_INDICATORS.keys()))

    recipients = (
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

    recipients = recipients[recipients["value"] != 0]

    recipients = add_index_column(
        df=recipients,
        column="indicator",
        json_path=PATHS.TOOLS / "recipients_indicators.json",
        ordered_list=list(RECIPIENTS_INDICATORS.values()),
    )

    return recipients


def recipients_to_parquet():
    df = filter_transform_recipients()
    df_to_parquet(df)


if __name__ == "__main__":
    save_time_range_to_json(BASE_TIME, "base_time.json")
    logger.info("Generating recipients table...")
    set_cache_dir(oda_data=True)
    recipients_to_parquet()
