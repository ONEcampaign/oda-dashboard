import pyarrow as pa
import pyarrow.parquet as pq
import sys

from oda_data import CrsData, set_data_path
from src.data.config import PATHS, logger

from src.data.settings.utils import get_schema, to_decimal

set_data_path(PATHS.ODA_DATA)

def get_crs():
    df = (
        CrsData(years=range(2000, 2024))
        .read(using_bulk_download=True)
    )

    return df

def get_transform_gender():

    crs = get_crs()

    # Format gender df including all flows (flow_name)
    gender = (
        crs.dropna(subset=["gender"])

        .groupby(
            [
                'year',
                'donor_code',
                'recipient_code',
                'gender',
            ],
            dropna=False, observed=True
        )['usd_disbursement']
        .sum()
        .reset_index()
        .rename(
            columns={
                'gender': 'gender_code',
                'usd_disbursement': 'value'
            }
        )
    )

    gender = gender[gender["value"] != 0]

    gender['gender_code'] = (
        gender["gender_code"]
        .astype(float)
        .astype("int16[pyarrow]")
    )

    return gender

def convert_types(df):

    df['year'] = df['year'].astype('category')
    df['donor_code'] = df['donor_code'].astype('category')
    df['recipient_code'] = df['recipient_code'].astype('category')
    df['gender_code'] = df['gender_code'].astype('category')
    df["value"] = df["value"].apply(lambda x: to_decimal(x))

    return df

def return_pa_table(df):

    schema = get_schema(df)

    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)

    # Write PyArrow Table to Parquet
    buf = pa.BufferOutputStream()
    pq.write_table(table, buf, compression="snappy")

    # Get the Parquet bytes
    buf_bytes = buf.getvalue().to_pybytes()
    sys.stdout.buffer.write(buf_bytes)


def create_parquet():
    df = get_transform_gender()
    converted_df = convert_types(df)
    return_pa_table(converted_df)


if __name__ == "__main__":
    logger.info("Retrieving gender data")
    create_parquet()
