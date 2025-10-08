import os
import sys
import json
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from collections import defaultdict

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


def df_to_parquet(df: pd.DataFrame):
    """
    Convert DataFrame to Parquet and write to stdout.
    Uses optimized schema with dictionary encoding for codes and float64 for values.
    No Decimal conversion - frontend can work directly with float64.
    """
    # Convert to efficient types
    df = df.copy()

    # Convert codes to categorical (for dictionary encoding)
    if "year" in df.columns:
        df["year"] = df["year"].astype("category")
    if "donor_code" in df.columns:
        df["donor_code"] = df["donor_code"].astype("category")
    if "recipient_code" in df.columns:
        df["recipient_code"] = df["recipient_code"].astype("category")
    if "indicator" in df.columns:
        df["indicator"] = df["indicator"].astype("category")
    if "sub_sector" in df.columns:
        df["sub_sector"] = df["sub_sector"].astype("category")

    # Use float64 for values (standard, no conversion needed in frontend)
    if "value" in df.columns:
        df["value"] = df["value"].astype("float64")

    # Create optimized schema with dictionary encoding
    schema_fields = []
    for col in df.columns:
        if col == "value":
            schema_fields.append(pa.field(col, pa.float64()))
        elif isinstance(df[col].dtype, pd.CategoricalDtype):
            # Use dictionary encoding with auto-selected int types
            categories = df[col].cat.categories
            if len(categories) <= 127:
                index_type = pa.int8()
            elif len(categories) <= 32767:
                index_type = pa.int16()
            else:
                index_type = pa.int32()

            # Determine value type based on category values
            cat_min, cat_max = categories.min(), categories.max()
            if cat_min >= 0 and cat_max <= 65535:
                value_type = pa.int16()
            else:
                value_type = pa.int32()

            schema_fields.append(pa.field(col, pa.dictionary(index_type, value_type)))

    schema = pa.schema(schema_fields)
    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
    buf = pa.BufferOutputStream()
    pq.write_table(table, buf, compression="ZSTD", compression_level=6)

    # Write to stdout
    buf_bytes = buf.getvalue().to_pybytes()
    sys.stdout.buffer.write(buf_bytes)


def add_index_column(
    df: pd.DataFrame, column: str, json_path, ordered_list: list = None
) -> pd.DataFrame:
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
    eui_df = df.query("dac_code == 918").assign(dac_code=eui_bi_code)

    return eui_df
