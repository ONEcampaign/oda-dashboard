import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import sys

from pathlib import Path

from src.data.settings.utils import get_schema, to_decimal

file_path = Path.cwd() / "scripts" / "output" / "financing.csv"

df = pd.read_csv(file_path)

df.drop(columns=["Donor Code", "share", "description"], inplace=True)

df['year'] = df['year'].astype('category')
df['Indicator'] = df['Indicator'].astype('category')
# df['Donor Code'] = df['Donor Code'].astype('category')
df['Donor Name'] = df['Donor Name'].astype('category')
df['Share of'] = df['Share of'].astype('category')
df['Currency'] = df['Currency'].astype('category')
df['Prices'] = df['Prices'].astype('category')
df['Indicator Type'] = df['Indicator Type'].astype('category')
df["value"] = df["value"].apply(lambda x: to_decimal(x))
# df["share"] = df["share"].apply(lambda x: to_decimal(x)
df["GNI Share"] = df["GNI Share"].apply(lambda x: to_decimal(x))
# df['description'] = df['description'].astype('category')

schema = pa.schema([
    ("year", pa.dictionary(pa.int8(), pa.int16())),
    ("Indicator", pa.dictionary(pa.int8(), pa.string())),
    # ("Donor Code", pa.int32()),
    ("Donor Name", pa.dictionary(pa.int8(), pa.string())),
    ("Share of", pa.dictionary(pa.int8(), pa.string())),
    ("Currency", pa.dictionary(pa.int8(), pa.string())),
    ("Prices", pa.dictionary(pa.int8(), pa.string())),
    ("value", pa.decimal128(9, 2)),
    # ("share", pa.decimal128(6, 2)),
    ("GNI Share", pa.decimal128(6, 2)),
    ("Indicator Type", pa.dictionary(pa.int8(), pa.string())),
    # ("description", pa.dictionary(pa.int8(), pa.string()))
])

sparkbarTable = pa.Table.from_pandas(df, schema=schema, preserve_index=False)

# Write PyArrow Table to Parquet
buf = pa.BufferOutputStream()
pq.write_table(sparkbarTable, buf, compression="snappy")

# Get the Parquet bytes
buf_bytes = buf.getvalue().to_pybytes()
sys.stdout.buffer.write(buf_bytes)