import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import sys

from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

file_path = Path.cwd() / "scripts" / "output" / "sectors.csv"

df = pd.read_csv(file_path)

def to_decimal(val, precision=2):
    quantizer = Decimal("1." + "0" * precision)
    return Decimal(str(val)).quantize(quantizer, rounding=ROUND_HALF_EVEN)

df['year'] = df['year'].astype('category')
df['Indicator'] = df['Indicator'].astype('category')
df['Donor Name'] = df['Donor Name'].astype('category')
df['Recipient Name'] = df['Recipient Name'].astype('category')
df['Currency'] = df['Currency'].astype('category')
df['Prices'] = df['Prices'].astype('category')
df['Sector'] = df['Sector'].astype('category')
df['Subsector'] = df['Subsector'].astype('category')
df["value"] = df["value"].apply(lambda x: to_decimal(x))
df["share_of_total"] = df["share_of_total"].apply(lambda x: to_decimal(x))
df["share_of_indicator"] = df["share_of_indicator"].apply(lambda x: to_decimal(x))
df["GNI Share"] = df["GNI Share"].apply(lambda x: to_decimal(x))

schema = pa.schema([
    ('year', pa.dictionary(pa.int8(), pa.int16())),
    ('Indicator', pa.dictionary(index_type=pa.int8(), value_type=pa.string())),
    ('Donor Name', pa.dictionary(index_type=pa.int8(), value_type=pa.string())),
    ('Recipient Name', pa.dictionary(index_type=pa.int8(), value_type=pa.string())),
    ('Currency', pa.dictionary(index_type=pa.int8(), value_type=pa.string())),
    ('Prices', pa.dictionary(index_type=pa.int8(), value_type=pa.string())),
    ('Sector', pa.dictionary(index_type=pa.int8(), value_type=pa.string())),
    ('Subsector', pa.dictionary(index_type=pa.int16(), value_type=pa.string())),
    ("value", pa.decimal128(7, 2)),
    ("share_of_total", pa.decimal128(5, 2)),
    ("share_of_indicator", pa.decimal128(6, 2)),
    ("GNI Share", pa.decimal128(6, 2))
])

sparkbarTable = pa.Table.from_pandas(df, schema=schema, preserve_index=False)

# Write PyArrow Table to Parquet
buf = pa.BufferOutputStream()
pq.write_table(sparkbarTable, buf, compression="snappy")

# Get the Parquet bytes
buf_bytes = buf.getvalue().to_pybytes()
sys.stdout.buffer.write(buf_bytes)