import json
import pandas as pd

from oda_data import CRSData, add_sectors
from oda_data.tools import sector_lists
from oda_data.indicators.research.sector_imputations import (
    imputed_multilateral_by_purpose,
)

from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_donor_groupings,
    add_recipient_groupings,
    add_recipient_indicator_codes,
    add_donor_names,
    add_recipient_names,
    widen_currency_price,
    add_share_of_donors_total_oda,
)
from src.data.config import PATHS, SECTORS_TIME, DONOR_GROUPS, logger
from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
    get_dac_ids,
    write_partitioned_dataset,
    convert_values_to_units,
)

donor_ids = get_dac_ids(PATHS.DONORS)
recipient_ids = get_dac_ids(PATHS.RECIPIENTS)
set_cache_dir(oda_data=True, pydeflate=True)


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


def combined_sectors():
    logger.info("Fetching bilateral data...")
    sectors_bi = get_bilateral_by_sector()

    logger.info("Fetching imputed multilateral data...")
    sectors_multi = get_imputed_multi_by_sector()

    sectors = pd.concat([sectors_bi, sectors_multi], ignore_index=True)
    sectors = sectors[sectors["value"] != 0]

    logger.info("Adding currencies and prices...")
    sectors = add_currencies_and_prices(sectors)

    # Filter zeros after currency conversion
    sectors = sectors[sectors["value"] != 0]

    logger.info("Adding donor groupings...")
    sectors = add_donor_groupings(sectors)

    logger.info("Adding recipient groupings...")
    sectors = add_recipient_groupings(sectors)

    # Filter zeros after groupings
    sectors = sectors[sectors["value"] != 0]

    logger.info("Adding names and codes...")
    sectors = add_recipient_indicator_codes(sectors)
    sectors = add_donor_names(sectors)
    sectors = add_recipient_names(sectors)

    # Add sector code
    with open(PATHS.TOOLS / "sub_sectors.json", "r") as f:
        subsector_mapping = {v: int(k) for k, v in json.load(f).items()}

    sectors["sub_sector_code"] = sectors["sub_sector"].map(subsector_mapping)
    sectors = sectors.rename(columns={"sub_sector": "sub_sector_name"})
    sector_mapping = sector_lists.get_broad_sector_groups()
    sectors["sector_name"] = (
        sectors["sub_sector_name"]
        .map(sector_mapping)
        .fillna("Unallocated/ Unspecified")
    )

    logger.info("Pivoting to wide format...")
    sectors = widen_currency_price(
        df=sectors,
        index_cols=(
            "year",
            "donor_code",
            "donor_name",
            "recipient_code",
            "recipient_name",
            "indicator",
            "indicator_name",
            "sector_name",
            "sub_sector_code",
            "sub_sector_name",
        ),
    )

    valid_subsectors = set(subsector_mapping.values())
    sector_mapping_filtered = {
        k: v for k, v in sector_mapping.items() if k in valid_subsectors
    }

    with open(PATHS.TOOLS / "sectors.json", "w") as f:
        json.dump(sector_mapping_filtered, f, indent=2)

    # Add donor perspective share (share of donor's total ODA to developing countries)
    sectors = add_share_of_donors_total_oda(sectors)

    # Add recipient perspective share (share of ODA received by recipient from all donors).
    # Computed from individual donor codes only — aggregate group codes (20_000–20_005)
    # are excluded from the denominator to prevent double-counting and to include EU
    # Institutions (918), which is absent from the "All bilateral donors" (20_000) group.
    aggregate_codes = set(DONOR_GROUPS.values())
    total_received = (
        sectors.loc[~sectors["donor_code"].isin(aggregate_codes)]
        .groupby(["year", "recipient_code"], dropna=False, observed=True)["value_usd_current"]
        .sum()
        .reset_index()
        .rename(columns={"value_usd_current": "total_oda"})
    )
    sectors = sectors.merge(total_received, on=["year", "recipient_code"], how="left")
    sectors["pct_total_recipient"] = (
        sectors["value_usd_current"] / sectors["total_oda"]
    ).round(6)
    sectors = sectors.drop(columns=["total_oda"])

    # Convert values to units (integers) for better compression
    # NOTE: Frontend queries must divide value_* columns by 1e6 to get millions
    sectors = convert_values_to_units(sectors)

    return sectors


if __name__ == "__main__":
    logger.info("Generating sectors table...")
    set_cache_dir(oda_data=True, pydeflate=True)
    df = combined_sectors()

    logger.info("Writing partitioned dataset...")
    write_partitioned_dataset(df, "sectors_view")
    logger.info("Sectors view completed")
