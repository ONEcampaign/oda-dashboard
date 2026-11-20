"""Resolve the four registered OECD bulk files before the main build.

Run after ``register_bulk_files.py``. The first offline scan of a zip converts it to
parquet (DAC1 under a second, MultiSystem about 3 s, DAC2A about 5 s). Without this step the
loaders, which run in parallel during ``observable build``, would each start that
conversion on the same file. Scanning here runs the conversions one after another, so
every loader afterwards reads a ready parquet file.

Everything is offline. A dataset that is not registered fails here, before any loader runs.

Exits 0 on success. An unregistered dataset raises and exits non-zero.
"""

import time

from src.data.analysis_tools import oda
from src.data.config import logger
from src.data.scripts.register_bulk_files import BULK_FILES


def prewarm_bulk_files() -> None:
    """Scan every registered bulk dataset offline, converting zips to parquet once."""
    for spec in BULK_FILES:
        start = time.perf_counter()
        table = oda.scan_table(spec.dataset)
        logger.info(
            "Resolved %s in %.1fs: %s (release %s)",
            spec.dataset,
            time.perf_counter() - start,
            table.path,
            table.release,
        )


if __name__ == "__main__":
    prewarm_bulk_files()
