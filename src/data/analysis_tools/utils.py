import sys
import json
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN

from src.data.config import PATHS


def get_dac_ids(path):
    with open(path, "r") as f:
        data = json.load(f)
    return [int(key) for key in data.keys()]


import json
from collections import defaultdict

def load_indicators(page):
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




def return_pa_table(df):

    schema = get_schema(df)

    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)

    # Write PyArrow Table to Parquet
    buf = pa.BufferOutputStream()
    pq.write_table(table, buf, compression="snappy")

    # Get the Parquet bytes
    buf_bytes = buf.getvalue().to_pybytes()
    sys.stdout.buffer.write(buf_bytes)


def get_schema(df):
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


def to_decimal(val, precision=2):
    quantizer = Decimal("1." + "0" * precision)
    return Decimal(str(val)).quantize(quantizer, rounding=ROUND_HALF_EVEN)
