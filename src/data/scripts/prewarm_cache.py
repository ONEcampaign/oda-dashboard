"""Pre-warm the pydeflate exchange rate cache before the main build.

This script runs before observable build to ensure exchange rate and deflator
data is downloaded and cached. Without it, the first data loader that calls
add_currencies_and_prices() downloads from the OECD API inline, and transient
API failures (common with the OECD SDMX endpoint) crash the entire build.

Exits 0 on success, 1 if all retries fail.
"""
import sys
import time

import pandas as pd
from pydeflate import oecd_dac_deflate, oecd_dac_exchange

from src.data.analysis_tools.helper_functions import set_cache_dir
from src.data.config import BASE_TIME, logger

MAX_RETRIES = 3
RETRY_DELAY = 30  # seconds between retries


def prewarm_exchange_rates() -> None:
    """Trigger pydeflate to download and cache exchange rate + deflator data."""
    set_cache_dir(oda_data=False, pydeflate=True)

    # Minimal DataFrame: a single USA row is enough to trigger the full download.
    # pydeflate fetches all-country tables regardless of which donor is requested.
    test_df = pd.DataFrame(
        {"donor_code": [302], "year": [BASE_TIME["base"]], "value": [1.0]}
    )

    logger.info("Downloading exchange rate data (USD → EUR)...")
    oecd_dac_exchange(
        data=test_df.copy(),
        source_currency="USA",
        target_currency="EUR",
        id_column="donor_code",
        use_source_codes=True,
    )

    logger.info("Downloading deflator data (USD constant prices)...")
    oecd_dac_deflate(
        data=test_df.copy(),
        base_year=BASE_TIME["base"],
        source_currency="USA",
        target_currency="USD",
        id_column="donor_code",
        use_source_codes=True,
    )


if __name__ == "__main__":
    logger.info("Pre-warming pydeflate cache...")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            prewarm_exchange_rates()
            logger.info("Pydeflate cache pre-warm successful")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                logger.info(f"Waiting {RETRY_DELAY}s before retry...")
                time.sleep(RETRY_DELAY)

    logger.error("Failed to pre-warm pydeflate cache after all retries")
    sys.exit(1)
