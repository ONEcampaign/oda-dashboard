import os
import sys
import json
import shutil
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.dataset as ds


from oda_data import set_data_path
from pydeflate import set_pydeflate_path

from src.data.config import PATHS, logger, eui_bi_code


def save_time_range_to_json(time_dict: dict, file_name: str):
    logger.info(f"Saving time range to {PATHS.TOOLS}/{file_name}")
    with open(PATHS.TOOLS / file_name, "w") as f:
        json.dump(time_dict, f, indent=2)


def set_cache_dir(path=PATHS.DATA, oda_data: bool = False, pydeflate: bool = False):
    if not os.path.exists(path):
        logger.info(f"Creating directory for cached data: {path}")
        os.makedirs(path)

    if oda_data:
        set_data_path(path)
    if pydeflate:
        set_pydeflate_path(path)


def get_dac_ids(path, remove_eui_bi: bool = True) -> list:
    with open(path, "r") as f:
        data = json.load(f)

    dac_ids = [int(key) for key in data.keys()]

    if remove_eui_bi:
        dac_ids = [x for x in dac_ids if x != 919]

    return dac_ids


def export_parquet(df: pd.DataFrame, file_path: Path):
    """
    Export DataFrame to Parquet file with optimized types and compression.

    Args:
        df: DataFrame to export
        file_path: Output file path (with or without .parquet extension)
    """
    # Convert to Arrow table with optimized types
    table, value_cols = dataframe_to_arrow_table(df, optimize_types=True)

    # Prepare byte stream split for value columns
    bss_cols = {c: True for c in value_cols}

    # Ensure .parquet extension
    path = (
        file_path
        if file_path.suffix == ".parquet"
        else file_path.with_suffix(".parquet")
    )

    # Write with standard options
    write_options = get_parquet_write_options()
    pq.write_table(
        table,
        path,
        use_byte_stream_split=bss_cols,
        **write_options,
    )


def parquet_to_stdout(df: pd.DataFrame):
    """
    Export DataFrame to stdout as Parquet (for Observable Framework data loaders).

    Args:
        df: DataFrame to export
    """
    # Convert to Arrow table with optimized types
    table, value_cols = dataframe_to_arrow_table(df, optimize_types=True)

    # Prepare byte stream split for value columns
    bss_cols = {c: True for c in value_cols}

    # Write to buffer
    buf = pa.BufferOutputStream()

    write_options = get_parquet_write_options()
    pq.write_table(
        table,
        buf,
        use_byte_stream_split=bss_cols,
        **write_options,
    )

    # Write to stdout
    buf_bytes = buf.getvalue().to_pybytes()
    sys.stdout.buffer.write(buf_bytes)


def get_eui(df: pd.DataFrame) -> pd.DataFrame:
    eui_df = df.query("dac_code == 918").assign(dac_code=eui_bi_code)

    return eui_df


# ============================================================================
# Shared Parquet Utilities
# ============================================================================


def optimize_dataframe_types(
    df: pd.DataFrame,
    additional_int32_cols: list[str] = None,
    additional_categorical_cols: list[str] = None,
) -> pd.DataFrame:
    """
    Optimize DataFrame column types for efficient parquet storage.

    Args:
        df: DataFrame to optimize
        additional_int32_cols: Extra columns to convert to Int32 (e.g., ['sub_sector_code'])
        additional_categorical_cols: Extra columns to convert to category (e.g., ['sector_name'])

    Returns:
        Optimized DataFrame with efficient dtypes
    """
    df = df.copy()

    # Value columns → Float32
    value_cols = [
        c for c in df.columns if c.startswith("value_") or c.startswith("pct")
    ]
    for col in value_cols:
        df[col] = df[col].round(5).astype("Float32")

    # Standard Int16 columns
    for col in ["year", "donor_code", "indicator"]:
        if col in df.columns:
            df[col] = df[col].astype("Int16")

    # Standard Int32 columns
    int32_cols = ["recipient_code"]
    if additional_int32_cols:
        int32_cols.extend(additional_int32_cols)
    for col in int32_cols:
        if col in df.columns:
            df[col] = df[col].astype("Int32")

    # Standard categorical columns
    cat_cols = [
        "donor_name",
        "recipient_name",
        "indicator_name",
        "sub_sector",
        "price",
        "currency",
        "type",
    ]
    if additional_categorical_cols:
        cat_cols.extend(additional_categorical_cols)
    for col in cat_cols:
        if col in df.columns:
            df[col] = df[col].astype("category")

    # Sort by standard keys for better compression and groupby performance
    sort_keys = [
        c
        for c in [
            "donor_code",
            "recipient_code",
            "indicator",
            "year",
            "sub_sector_code",
        ]
        if c in df.columns
    ]
    if sort_keys:
        df = df.sort_values(sort_keys, kind="stable")

    return df


def get_parquet_write_options() -> dict:
    """
    Get standard parquet write options for consistent compression/encoding.

    Returns:
        Dictionary of write options for pyarrow.parquet.write_table
    """
    return {
        "compression": "zstd",
        "compression_level": 15,
        "use_dictionary": True,
        "write_statistics": True,
        "data_page_size": 1_048_576,
        "row_group_size": 100_000,
    }


def dataframe_to_arrow_table(
    df: pd.DataFrame,
    optimize_types: bool = True,
    additional_int32_cols: list[str] = None,
    additional_categorical_cols: list[str] = None,
) -> pa.Table:
    """
    Convert DataFrame to Arrow table with optional type optimization.

    Args:
        df: DataFrame to convert
        optimize_types: Whether to optimize column types first
        additional_int32_cols: Extra Int32 columns for optimization
        additional_categorical_cols: Extra categorical columns for optimization

    Returns:
        PyArrow Table
    """
    if optimize_types:
        df = optimize_dataframe_types(
            df,
            additional_int32_cols=additional_int32_cols,
            additional_categorical_cols=additional_categorical_cols,
        )

    # Compute byte stream split columns (value columns benefit from this)
    value_cols = [
        c for c in df.columns if c.startswith("value_") or c.startswith("pct")
    ]

    return pa.Table.from_pandas(df, preserve_index=False), value_cols


def write_partitioned_dataset(
    df: pd.DataFrame,
    base_dir: str,
    partition_cols: list[str] = None,
) -> None:
    """
    Write DataFrame as a partitioned parquet dataset (for large datasets like sectors).

    Args:
        df: DataFrame to write
        base_dir: Base directory name (will be created under PATHS.CDN_FILES)
        partition_cols: Columns to partition by (defaults to ['donor_code', 'recipient_code'])
    """
    if partition_cols is None:
        partition_cols = ["donor_code", "recipient_code"]

    # Optimize types with additional columns for sectors
    # Include sub_sector_code as Int32 and sector_name/sub_sector_name as categorical
    optimized = optimize_dataframe_types(
        df,
        additional_int32_cols=["sub_sector_code"],
        additional_categorical_cols=["sector_name", "sub_sector_name"],
    )

    # Convert to Arrow table
    table = pa.Table.from_pandas(optimized, preserve_index=False)

    # Setup output directory
    output_dir = PATHS.CDN_FILES / base_dir
    if output_dir.exists():
        logger.info("Clearing existing partitioned dataset at %s", output_dir)
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Define partition schema (all partition cols must be int32 for Hive partitioning)
    partition_fields = [pa.field(col, pa.int32()) for col in partition_cols]
    partition_schema = pa.schema(partition_fields)

    # Configure parquet format with write options
    parquet_format = ds.ParquetFileFormat()
    file_options = parquet_format.make_write_options(
        compression="zstd",
        compression_level=15,
        use_dictionary=True,
        write_statistics=True,
    )

    # Write partitioned dataset
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
