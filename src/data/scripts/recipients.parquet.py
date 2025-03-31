from oda_data import Indicators, set_data_path
from src.data.config import PATHS, time_range, logger

from src.data.analysis_tools.utils import get_dac_ids, add_index_column, convert_types, return_pa_table

set_data_path(PATHS.ODA_DATA)

donor_ids = get_dac_ids(PATHS.DONORS)
recipient_ids = get_dac_ids(PATHS.RECIPIENTS)

indicators_dac2a = {
    "DAC2A.10.206": "Bilateral",
    "DAC2A.10.106": "Imputed multilateral"
}

def filter_transform_recipients():

    dac2a_raw = Indicators(
        years=range(time_range["start"], time_range["end"] + 1),
        providers= donor_ids,
        recipients= recipient_ids,
        use_bulk_download=True
    ).get_indicators(
        list(indicators_dac2a.keys())
    )

    recipients = (
        dac2a_raw.query(
            "donor_code in @donor_ids and "
            "recipient_code in @recipient_ids"
        ).groupby(
            [
                'year',
                'donor_code',
                'recipient_code',
                'one_indicator'
            ],
            dropna=False, observed=True
        )['value']
        .sum()
        .reset_index()
        .assign(indicator=lambda d: d["one_indicator"].map(indicators_dac2a))
        .drop(columns=["one_indicator"])
    )

    recipients = recipients[recipients["value"] != 0]

    recipients = add_index_column(
        df=recipients,
        column='indicator',
        json_path=PATHS.TOOLS / 'recipients_indicators.json'
    )

    return recipients


def recipients_to_parquet():

    df = filter_transform_recipients()
    converted_df = convert_types(df)
    return_pa_table(converted_df)


if __name__ == "__main__":
    logger.info("Generating recipients table...")
    recipients_to_parquet()