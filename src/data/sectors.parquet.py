import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import sys

from pathlib import Path

file_path = Path.cwd() / "scripts" / "output" / "sectors.csv"

df = pd.read_csv(file_path)
df['Indicator'] = df['Indicator'].astype('category')
df['Donor Name'] = df['Donor Name'].astype('category')
df['Recipient Name'] = df['Recipient Name'].astype('category')
df['Currency'] = df['Currency'].astype('category')
df['Prices'] = df['Prices'].astype('category')
df['Sector'] = df['Sector'].astype('category')
df['Subsector'] = df['Subsector'].astype('category')

schema = pa.schema([
    ('year', pa.int32()),
    ('Indicator', pa.dictionary(index_type=pa.int32(), value_type=pa.string())),
    ('Donor Name', pa.dictionary(index_type=pa.int32(), value_type=pa.string())),
    ('Recipient Name', pa.dictionary(index_type=pa.int32(), value_type=pa.string())),
    ('Currency', pa.dictionary(index_type=pa.int32(), value_type=pa.string())),
    ('Prices', pa.dictionary(index_type=pa.int32(), value_type=pa.string())),
    ('Sector', pa.dictionary(index_type=pa.int32(), value_type=pa.string())),
    ('Subsector', pa.dictionary(index_type=pa.int32(), value_type=pa.string())),
    ('value', pa.float32()),
    ('share_of_total', pa.float32()),
    ('GNI Share', pa.float32()),
    ('share_of_indicator', pa.float32())
])

table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)

# Write PyArrow Table to Parquet
buf = pa.BufferOutputStream()
pq.write_table(table, buf, compression="snappy")

# Get the Parquet bytes
buf_bytes = buf.getvalue().to_pybytes()
sys.stdout.buffer.write(buf_bytes)