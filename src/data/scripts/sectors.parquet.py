import json
import pandas as pd

from oda_data import CRSData
from oda_data.tools import sector_lists
from oda_data.indicators.research.sector_imputations import (
    imputed_multilateral_by_purpose,
)

from src.data.config import PATHS, SECTORS_TIME, logger
from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
    get_dac_ids,
    add_index_column,
    df_to_parquet,
)

donor_ids = get_dac_ids(PATHS.DONORS)
recipient_ids = get_dac_ids(PATHS.RECIPIENTS)


def get_bilateral_by_sector():

    raw_bilateral = CRSData(years=range(2013, SECTORS_TIME["end"] + 1)).read(
        using_bulk_download=True,
        additional_filters=[
            ("donor_code", "in", donor_ids),
            ("recipient_code", "in", recipient_ids),
            ("category", "in", [10, 60]),
        ],
        columns=[
            "year",
            "donor_code",
            "recipient_code",
            "purpose_code",
            "usd_disbursement",
        ],
    )

    sub_sectors = sector_lists.get_sector_groups()

    for name, codes in sub_sectors.items():
        raw_bilateral.loc[raw_bilateral.purpose_code.isin(codes), "sub_sector"] = name

    sectors_bi = (
        raw_bilateral.groupby(
            [
                "year",
                "donor_code",
                "recipient_code",
                "sub_sector",
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
        .assign(indicator="Bilateral")
    )

    sectors_bi = sectors_bi[sectors_bi["value"] != 0]

    return sectors_bi


def get_imputed_multi_by_sector():

    raw_multi = imputed_multilateral_by_purpose(
        years=range(2013, SECTORS_TIME["end"] + 1),
        providers=donor_ids,
        measure="gross_disbursement",
        currency="USD",
        base_year=None,
    )

    raw_multi = raw_multi[raw_multi["recipient_code"].isin(recipient_ids)]

    sub_sectors = sector_lists.get_sector_groups()

    for name, codes in sub_sectors.items():
        raw_multi.loc[raw_multi.purpose_code.isin(codes), "sub_sector"] = name

    raw_multi["sub_sector"] = raw_multi["sub_sector"].fillna("Unallocated/unspecificed")

    sectors_multi = (
        raw_multi.groupby(
            ["year", "donor_code", "recipient_code", "sub_sector"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator="Imputed multilateral")
    )

    sectors_multi = sectors_multi[sectors_multi["value"] != 0]

    return sectors_multi


def merge_transform_sectors():

    sectors_bi = get_bilateral_by_sector()
    sectors_multi = get_imputed_multi_by_sector()

    sectors = pd.concat([sectors_bi, sectors_multi])

    sectors = add_index_column(
        df=sectors,
        column="indicator",
        json_path=PATHS.TOOLS / "sectors_indicators.json",
    )
    sectors = add_index_column(
        df=sectors,
        column="sub_sector",
        json_path=PATHS.TOOLS / "sub_sectors.json"
    )

    with open(PATHS.TOOLS / "sub_sectors.json", 'r') as f:
        subsector_mapping = json.load(f)

    sector_mapping = sector_lists.get_broad_sector_groups()
    valid_subsectors = set(subsector_mapping.values())
    sector_mapping_filtered = {
        k: v for k, v in sector_mapping.items() if k in valid_subsectors
    }

    with open(PATHS.TOOLS / "sectors.json", 'w') as f:
        json.dump(sector_mapping_filtered, f, indent=2)

    return sectors


def sectors_to_parquet():
    df = merge_transform_sectors()
    df_to_parquet(df)


if __name__ == "__main__":
    logger.info("Generating sectors table...")
    set_cache_dir(oda_data=True)
    sectors_to_parquet()
