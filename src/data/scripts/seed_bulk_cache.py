"""Load local copies of the OECD CRS and MultiSystem bulk files into the oda_data cache.

The OECD file server puts a Cloudflare browser challenge in front of these two files, which
blocks the download oda_data would otherwise make (ONEcampaign/oda_reader#50). This script
takes the files as downloaded in a browser and runs them through the same cleaning oda_data
applies after a download, so every loader afterwards gets a cache hit.

Usage:
    PYTHONPATH=. uv run python src/data/scripts/seed_bulk_cache.py [SOURCE_DIR]

SOURCE_DIR defaults to ``src/data/raw_data/oecd_bulk`` and must hold the files named in
``SOURCE_FILES``.
"""

import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from oda_data import CRSData, MultiSystemData
from oda_data.api.sources import Source
from oda_data.clean_data.common import clean_parquet_file_in_batches
from oda_data.tools.cache import BulkCacheEntry

# Private, but it is the extraction oda_reader runs on a downloaded MultiSystem zip, so the
# seeded data matches a real download. oda-reader is pinned in pyproject.toml.
from oda_reader.download.download_tools import (
    _save_or_return_parquet_files_from_content,
)

from src.data.analysis_tools.outputs import set_cache_dir
from src.data.config import PATHS, logger

DEFAULT_SOURCE_DIR: Path = PATHS.SRC / "data" / "raw_data" / "oecd_bulk"

# Source class, and the file name expected in the source directory. The OECD serves the
# MultiSystem zip as "MultiSystem entire dataset.zip"; GitHub release assets cannot hold
# spaces, so it is renamed.
SOURCE_FILES: dict[type[Source], str] = {
    CRSData: "CRS.parquet",
    MultiSystemData: "MultiSystem.zip",
}

CLEAN_BATCH_SIZE: int = 100_000


def _clean_into(raw_parquet: Path, target: Path) -> None:
    """Apply oda_data's bulk cleaning to a raw OECD parquet file."""
    clean_parquet_file_in_batches(raw_parquet, target, batch_size=CLEAN_BATCH_SIZE)


def make_fetcher(source_file: Path) -> Callable[[Path], None]:
    """Build a cache fetcher that reads a local OECD file in place of downloading it.

    Args:
        source_file: A bare parquet file, or a zip holding one parquet, csv or txt file.

    Returns:
        A function that writes the cleaned parquet to the path oda_data passes it.
    """
    if source_file.suffix == ".parquet":
        return lambda target: _clean_into(source_file, target)

    def fetcher(target: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            _save_or_return_parquet_files_from_content(
                source_file, save_to_path=out_dir
            )
            extracted = list(out_dir.glob("*.parquet"))
            if len(extracted) != 1:
                raise ValueError(
                    f"Expected one parquet file from {source_file.name}, got {extracted}"
                )
            _clean_into(extracted[0], target)

    return fetcher


def seed(source: Source, source_file: Path) -> Path:
    """Write one source's cleaned bulk file into the oda_data cache, replacing any copy.

    Args:
        source: The oda_data source whose cache entry is written.
        source_file: The local OECD file for that source.

    Returns:
        Path of the cached parquet file.
    """
    if not source_file.is_file():
        raise FileNotFoundError(f"Missing OECD bulk file: {source_file}")

    # Same key and version oda_data builds in Source._fetch_from_bulk_cache, so its next
    # read finds this entry fresh.
    entry = BulkCacheEntry(
        key=f"{type(source).__name__}_bulk",
        fetcher=make_fetcher(source_file),
        version=source._get_package_version(),
    )
    return source.bulk_cache.ensure(entry, refresh=True)


def main(source_dir: Path) -> None:
    """Seed every source in ``SOURCE_FILES`` from ``source_dir``."""
    set_cache_dir(oda_data=True)
    for source_cls, file_name in SOURCE_FILES.items():
        path = seed(source_cls(), source_dir / file_name)
        logger.info(f"Seeded {source_cls.__name__} from {file_name} into {path}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE_DIR)
