import os
import sys
import json
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN

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

def load_indicators(page: str):
    with open(PATHS.INDICATORS, "r") as f:
        data = json.load(f)

    name_to_code = {}
    name_set = set()
    filtered_entries = []

    has_type = False  # Track whether type is present for this page

    for key, entry in data.items():
        if entry.get("page") != page or not entry.get("name"):
            continue

        entry_name = entry["name"]
        entry_types = entry.get("type")

        # Determine if this entry has a type (and normalize)
        if entry_types:
            has_type = True
            if isinstance(entry_types, str):
                entry_types = [entry_types]
        else:
            entry_types = [None]  # fallback for flat structure

        filtered_entries.append((key, entry_name, entry_types))
        name_set.add(entry_name)

    # Assign unique code per name in alphabetical order
    for idx, name in enumerate(sorted(name_set)):
        name_to_code[name] = idx

    if has_type:
        result = defaultdict(dict)
        for key, name, types in filtered_entries:
            code = name_to_code[name]
            for t in types:
                result[t][key] = code
        return dict(result)
    else:
        result = {}
        for key, name, _ in filtered_entries:
            code = name_to_code[name]
            result[key] = code
        return result


def return_pa_table(
    df: pd.DataFrame,
    *,
    compression: str | None = "snappy",
    compression_level: int | None = None,
):
    """Return a PyArrow table to STDOUT as a parquet file.

    Parameters
    ----------
    df:
        DataFrame to serialise.
    compression:
        Compression codec used by :func:`pyarrow.parquet.write_table`.  The
        default remains ``"snappy"`` to preserve the previous behaviour, but it
        can now be tuned by callers in order to trade off size vs. read speed
        (e.g. ``"zstd"`` or ``None`` for uncompressed output which is faster for
        DuckDB to load).
    compression_level:
        Optional compression level passed through to PyArrow.  Lower values
        generally favour faster decompression which is beneficial for the
        in-browser DuckDB instance used by the dashboard.
    """

    schema = get_schema(df)

    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)

    # Write PyArrow Table to Parquet
    buf = pa.BufferOutputStream()
    pq.write_table(
        table,
        buf,
        compression=compression,
        compression_level=compression_level,
    )

    # Get the Parquet bytes
    buf_bytes = buf.getvalue().to_pybytes()
    sys.stdout.buffer.write(buf_bytes)


def get_schema(df: pd.DataFrame):
    def choose_int_type(min_val, max_val):
        if min_val >= 0:
            if max_val <= 255:
                return pa.uint8()
            elif max_val <= 65535:
                return pa.uint16()
            elif max_val <= 4294967295:
                return pa.uint32()
            else:
                return pa.uint64()
        else:
            if -128 <= min_val and max_val <= 127:
                return pa.int8()
            elif -32768 <= min_val and max_val <= 32767:
                return pa.int16()
            elif -2147483648 <= min_val and max_val <= 2147483647:
                return pa.int32()
            else:
                return pa.int64()

    fields = []

    for col in df.columns:
        series = df[col]

        if isinstance(series.dtype, pd.CategoricalDtype):
            idx_min = series.cat.codes.min()
            idx_max = series.cat.codes.max()
            idx_type = choose_int_type(idx_min, idx_max)

            val_min = series.cat.categories.astype(int).min()
            val_max = series.cat.categories.astype(int).max()
            val_type = choose_int_type(val_min, val_max)

            field_type = pa.dictionary(index_type=idx_type, value_type=val_type)

        elif series.dropna().apply(type).eq(Decimal).all():

            def total_digits(d):
                sign, digits, exponent = d.as_tuple()
                int_digits = len(digits) + exponent if exponent < 0 else len(digits)
                return max(int_digits, 1) + 2  # 2 decimal places

            precision = series.dropna().apply(total_digits).max()
            field_type = pa.decimal128(precision, 2)

        else:
            raise TypeError(
                f"Column '{col}' is not a supported type. "
                "Expected either a categorical of integers or a Decimal column."
            )

        fields.append(pa.field(col, field_type))

    return pa.schema(fields)


def to_decimal(val: float, precision: int =2):
    quantizer = Decimal("1." + "0" * precision)
    return Decimal(str(val)).quantize(quantizer, rounding=ROUND_HALF_EVEN)


def convert_types(df: pd.DataFrame) -> pd.DataFrame:
    type_map = {
        "year": "category",
        "donor_code": "category",
        "recipient_code": "category",
        "indicator": "category",
        "sub_sector": "category",
    }

    for col, dtype in type_map.items():
        if col in df.columns:
            df[col] = df[col].astype(dtype)

    if "value" in df.columns:
        df["value"] = df["value"].apply(to_decimal)

    return df


def df_to_parquet(
    df: pd.DataFrame,
    *,
    compression: str | None = "snappy",
    compression_level: int | None = None,
):
    """Serialise ``df`` to parquet and write the bytes to STDOUT.

    ``df_to_parquet`` previously wrote all parquet files using ``snappy``
    compression.  This helper now exposes the compression parameters so that
    callers can reduce compression (or disable it altogether) when optimising
    for faster loading times in DuckDB.
    """

    converted_df = convert_types(df)
    return_pa_table(
        converted_df, compression=compression, compression_level=compression_level
    )


def add_index_column(df: pd.DataFrame, column: str, json_path, ordered_list: list = None) -> pd.DataFrame:
    # If no custom order is provided, use unique values in appearance order
    if ordered_list is None:
        ordered_list = list(df[column].unique())

    # Create string-to-index and index-to-string mappings
    str_to_idx = {name: idx for idx, name in enumerate(ordered_list)}
    idx_to_str = {str(idx): name for idx, name in enumerate(ordered_list)}

    # Map column to index values
    df = df.copy()
    df[column] = df[column].map(str_to_idx)

    # Save index-to-string mapping as JSON
    with open(json_path, "w") as f:
        json.dump(idx_to_str, f, indent=2)

    return df

def get_eui(df: pd.DataFrame) -> pd.DataFrame:

    eui_df = (
        df
        .query("dac_code == 918")
        .assign(dac_code=eui_bi_code)
    )

    return eui_df
