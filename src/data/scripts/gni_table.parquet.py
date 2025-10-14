from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
    parquet_to_stdout,
)
from src.data.analysis_tools.transformations import get_gni
from src.data.config import FINANCING_TIME, logger

set_cache_dir(oda_data=True)


def gni_to_parquet():
    df = get_gni(FINANCING_TIME["start"], FINANCING_TIME["end"])
    return df


if __name__ == "__main__":
    logger.info("Generating GNI table...")
    set_cache_dir(oda_data=True)
    df = gni_to_parquet()
    logger.info("Writing parquet to stdout...")
    parquet_to_stdout(df)
