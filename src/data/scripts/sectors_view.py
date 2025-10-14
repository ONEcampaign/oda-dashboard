import json
import shutil
import pandas as pd

from oda_data import CRSData
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
)
from src.data.config import PATHS, SECTORS_TIME, logger
from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
    get_dac_ids,
)
import pyarrow as pa
import pyarrow.dataset as ds

donor_ids = get_dac_ids(PATHS.DONORS)
recipient_ids = get_dac_ids(PATHS.RECIPIENTS)
set_cache_dir(oda_data=True)


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
    sectors_bi = get_bilateral_by_sector()
    sectors_multi = get_imputed_multi_by_sector()

    sectors = pd.concat([sectors_bi, sectors_multi], ignore_index=True)
    sectors = sectors[sectors["value"] != 0]

    # Add currencies and prices
    sectors = add_currencies_and_prices(sectors)

    # Add donor groupings
    sectors = add_donor_groupings(sectors)

    # Add recipient groupings
    sectors = add_recipient_groupings(sectors)

    # Add indicator code
    sectors = add_recipient_indicator_codes(sectors)

    # Add donor name
    sectors = add_donor_names(sectors)

    # Add recipient name
    sectors = add_recipient_names(sectors)

    # Add sector code
    with open(PATHS.TOOLS / "sub_sectors.json", "r") as f:
        subsector_mapping = {v: int(k) for k, v in json.load(f).items()}

    sectors["sub_sector_code"] = sectors["sub_sector"].map(subsector_mapping)
    sectors = sectors.rename(columns={"sub_sector": "sub_sector_name"})
    sector_mapping = sector_lists.get_broad_sector_groups()
    sectors["sector_name"] = sectors["sub_sector_name"].map(sector_mapping)

    # Pivot values to columns
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

    return sectors


def _optimise_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    optimised = df.copy()

    value_cols = [
        c for c in optimised.columns if c.startswith("value_") or c.startswith("pct")
    ]
    for col in value_cols:
        optimised[col] = optimised[col].astype("Float32")

    for col in ["year"]:
        if col in optimised.columns:
            optimised[col] = optimised[col].astype("Int16")

    for col in ["donor_code", "recipient_code", "indicator", "sub_sector_code"]:
        if col in optimised.columns:
            optimised[col] = optimised[col].astype("Int32")

    categorical_cols = [
        "donor_name",
        "recipient_name",
        "indicator_name",
        "sector_name",
        "sub_sector_name",
    ]
    for col in categorical_cols:
        if col in optimised.columns:
            optimised[col] = optimised[col].astype("category")

    sort_keys = [
        c
        for c in [
            "donor_code",
            "recipient_code",
            "indicator",
            "year",
            "sub_sector_code",
        ]
        if c in optimised.columns
    ]
    if sort_keys:
        optimised = optimised.sort_values(sort_keys, kind="stable")

    return optimised


def write_partitioned_dataset(df: pd.DataFrame, base_dir) -> None:
    optimised = _optimise_for_parquet(df)
    table = pa.Table.from_pandas(optimised, preserve_index=False)

    output_dir = PATHS.CDN_FILES / base_dir
    if output_dir.exists():
        logger.info("Clearing existing partitioned dataset at %s", output_dir)
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    partition_schema = pa.schema(
        [
            pa.field("donor_code", pa.int32()),
            pa.field("recipient_code", pa.int32()),
        ]
    )

    parquet_format = ds.ParquetFileFormat()
    file_options = parquet_format.make_write_options(
        compression="zstd",
        compression_level=15,
        use_dictionary=True,
        write_statistics=True,
    )

    ds.write_dataset(
        data=table,
        base_dir=str(output_dir),
        format="parquet",
        partitioning=ds.partitioning(partition_schema, flavor="hive"),
        basename_template="part-{i}.parquet",
        file_options=file_options,
        existing_data_behavior="delete_matching",
        max_rows_per_file=1_000_000,
        max_rows_per_group=100_000,
        min_rows_per_group=100_000,
    )


if __name__ == "__main__":
    logger.info("Generating sectors table...")
    set_cache_dir(oda_data=True)
    df = combined_sectors()
    logger.info("Writing partitioned dataset...")
    write_partitioned_dataset(df, "sectors_view")
