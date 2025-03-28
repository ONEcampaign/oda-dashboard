from oda_data import Dac2aData, set_data_path
from src.data.config import PATHS, time_range, logger

from src.data.analysis_tools.utils import get_dac_ids, load_indicators, convert_types, return_pa_table

set_data_path(PATHS.ODA_DATA)


def filter_transform_recipients():

    donor_ids = get_dac_ids(PATHS.DONORS)
    recipient_ids = get_dac_ids(PATHS.RECIPIENTS)
    indicator_ids = load_indicators("recipients")

    dac2a = Dac2aData(years=range(time_range["start"], time_range["end"] + 1)).read(
        using_bulk_download=True,
        additional_filters=[
            ("amount_type", "==", "Current prices"),
            ("donor_code", "in", donor_ids),
            ("recipient_code", "in", recipient_ids),
            ("aidtype_code", "in", indicator_ids.keys()),
        ],
    )

    recipients_df = (
        dac2a.groupby(
            [
                "year",
                "donor_code",
                "recipient_code",
                "aidtype_code",
            ],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator=lambda d: d["aidtype_code"].astype(str).map(indicator_ids))
        .drop(columns="aidtype_code")
    )

    recipients_df = recipients_df[recipients_df["value"] != 0]

    return recipients_df


def recipients_to_parquet():

    df = filter_transform_recipients()

    converted_df = convert_types(df)

    return_pa_table(converted_df)


if __name__ == "__main__":
    logger.info("Generating recipients table...")
    recipients_to_parquet()
