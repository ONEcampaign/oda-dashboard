import json

from oda_data import CrsData, set_data_path
from src.data.config import PATHS, time_range, logger

from src.data.analysis_tools.utils import get_dac_ids, add_index_column, convert_types, return_pa_table
from src.data.analysis_tools import sector_lists

set_data_path(PATHS.ODA_DATA)

def filter_transform_sectors():

    donor_ids = get_dac_ids(PATHS.DONORS)
    recipient_ids = get_dac_ids(PATHS.RECIPIENTS)

    crs = CrsData(
        years=range(time_range["start"], time_range["end"] + 1)
    ).read(
        using_bulk_download=True,
        additional_filters=[
            ("donor_code", "in", donor_ids),
            ("recipient_code", "in", recipient_ids),
            ("category", "in", [10, 60])
        ],
        columns=["year", "donor_code", "recipient_code", "purpose_code", "usd_disbursement"]
    )

    sub_sectors = sector_lists.get_sector_groups()

    for name, codes in sub_sectors.items():
        crs.loc[
            crs.purpose_code.isin(codes), "indicator"
        ] = name

    sectors = (
        crs.groupby(
            [
                "year",
                "donor_code",
                "recipient_code",
                "indicator",
            ],
            dropna=False,
            observed=True,
        )["usd_disbursement"]
        .sum()
        .reset_index()
        .rename(
            columns={
                "usd_disbursement": "value",
            }
        )
    )

    sectors = sectors[sectors["value"] != 0]

    sectors = add_index_column(
        df=sectors,
        column='indicator',
        json_path=PATHS.TOOLS / 'sub_sectors.json'
    )

    sector_mapping = sector_lists.get_broad_sector_groups()

    with open(PATHS.TOOLS / "sectors.json", "w") as f:
        json.dump(sector_mapping, f, indent=2)

    return sectors

def sectors_to_parquet():

    df = filter_transform_sectors()
    converted_df = convert_types(df)
    return_pa_table(converted_df)


if __name__ == "__main__":
    logger.info("Generating sectors table...")
    sectors_to_parquet()
