import os
import sys
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


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
    Convert DataFrame to Parquet
    Uses optimized schema with dictionary encoding for codes and float64 for values.
    """
    # Convert to efficient types
    df = df.copy()

    # 1) Ensure compact dtypes
    value_cols = [
        c for c in df.columns if c.startswith("value_") or c.startswith("pct")
    ]
    for c in value_cols:
        # keep Float32 end-to-end
        df[c] = df[c].astype("Float32")

    for col in [
        "year",
        "donor_code",
        "indicator",
    ]:
        if col in df.columns:
            df[col] = df[col].astype("Int16")

    for col in ["recipient_code"]:
        if col in df.columns:
            df[col] = df[col].astype("Int32")

    cat_cols = (
        "donor_name",
        "recipient_name",
        "indicator_name",
        "sub_sector",
        "price",
        "currency",
        "type",
    )
    for c in cat_cols:
        if c in df.columns:
            df[c] = df[c].astype("category")

    sort_keys = [
        c
        for c in ["donor_code", "recipient_code", "indicator", "year"]
        if c in df.columns
    ]
    if sort_keys:
        df = df.sort_values(sort_keys, kind="stable")

    table = pa.Table.from_pandas(df=df, preserve_index=False)

    bss_cols = {c: True for c in value_cols if c in df.columns}

    path = (
        file_path
        if file_path.suffix == ".parquet"
        else file_path.with_suffix(".parquet")
    )

    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=15,
        use_dictionary=True,
        use_byte_stream_split=bss_cols,
        write_statistics=True,
        data_page_size=1_048_576,
        row_group_size=100_000,
    )


def parquet_to_stdout(df: pd.DataFrame):
    """
    Convert DataFrame to Parquet
    Uses optimized schema with dictionary encoding for codes and float64 for values.
    """
    # Convert to efficient types
    df = df.copy()

    # 1) Ensure compact dtypes
    value_cols = [
        c for c in df.columns if c.startswith("value_") or c.startswith("pct")
    ]
    for c in value_cols:
        # keep Float32 end-to-end
        df[c] = df[c].round(6).astype("Float32")

    for col in [
        "year",
        "donor_code",
        "indicator",
    ]:
        if col in df.columns:
            df[col] = df[col].astype("Int16")

    for col in ["recipient_code"]:
        if col in df.columns:
            df[col] = df[col].astype("Int32")

    cat_cols = (
        "donor_name",
        "recipient_name",
        "indicator_name",
        "sub_sector",
        "price",
        "currency",
        "type",
    )
    for c in cat_cols:
        if c in df.columns:
            df[c] = df[c].astype("category")

    sort_keys = [
        c
        for c in ["donor_code", "recipient_code", "indicator", "year"]
        if c in df.columns
    ]
    if sort_keys:
        df = df.sort_values(sort_keys, kind="stable")

    table = pa.Table.from_pandas(df=df, preserve_index=False)

    bss_cols = {c: True for c in value_cols if c in df.columns}

    buf = pa.BufferOutputStream()

    pq.write_table(
        table,
        buf,
        compression="zstd",
        compression_level=15,
        use_dictionary=True,
        use_byte_stream_split=bss_cols,
        write_statistics=True,
        data_page_size=1_048_576,
        row_group_size=100_000,
    )

    # Write to stdout
    buf_bytes = buf.getvalue().to_pybytes()
    sys.stdout.buffer.write(buf_bytes)


def get_eui(df: pd.DataFrame) -> pd.DataFrame:
    eui_df = df.query("dac_code == 918").assign(dac_code=eui_bi_code)

    return eui_df
