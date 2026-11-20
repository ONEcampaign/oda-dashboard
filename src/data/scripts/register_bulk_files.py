"""Register the OECD bulk files in the oda_reader cache without downloading anything.

The OECD file server puts a Cloudflare browser challenge in front of its bulk files
(ONEcampaign/oda_reader#50), which blocks oda_reader's own downloads. This script takes the
four files as downloaded in a browser and registers each with its source URL and a version
string. Registration makes no network call, and later ``oda_reader.scan(..., offline=True)``
calls resolve to the registered copy.

Usage:
    PYTHONPATH=. uv run python src/data/scripts/register_bulk_files.py \
        --dir src/data/raw_data/oecd_bulk [--version VERSION | --versions JSON]

``--dir`` must hold the files named in ``BULK_FILES``. ``--version`` is one token for every
file and defaults to ``local-<today>``. ``--versions`` is a JSON object mapping each file name
to its own token, e.g. ``{"CRS.parquet": "2026-10-15T13:08:35Z", ...}``. CI passes each
release asset's ``updatedAt``, and the script prefixes it with ``oecd-bulk-data-``. Either way
the provenance recorded for each table says which upload it came from.
"""

import argparse
import datetime as dt
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

import oda_reader

from src.data.analysis_tools import oda
from src.data.config import PATHS, logger

RELEASE_TOKEN_PREFIX: str = "oecd-bulk-data-"
DEFAULT_BULK_DIR: Path = PATHS.SRC / "data" / "raw_data" / "oecd_bulk"


class BulkFile(NamedTuple):
    """One bulk file: its oda_reader dataset, local file name and OECD source URL."""

    dataset: str
    file_name: str
    url: str


# The URLs are the ones oda_reader resolves from each dataflow's EXT_RESOURCE annotation on
# sdmx.oecd.org. Registering with url and version skips that lookup and the HEAD request to
# the Cloudflare-protected host. The DAC2A URL is not in oda-reader's source and comes from
# ``_resolve_bulk_file_url(*BULK_DATASETS["dac2a"])``. The local file names are the browser
# download names, except MultiSystem. The OECD serves that one as
# "MultiSystem entire dataset.zip", and GitHub release assets cannot hold spaces.
BULK_FILES: tuple[BulkFile, ...] = (
    BulkFile(
        "crs",
        "CRS.parquet",
        "https://webfs-dcd.oecd.org/files/dotStat/DSD_CRS/CRS.parquet",
    ),
    BulkFile(
        "multisystem",
        "MultiSystem.zip",
        "https://webfs-dcd.oecd.org/files/dotStat/DSD_MULTI/MultiSystem%20entire%20dataset.zip",
    ),
    BulkFile(
        "dac1",
        "Table1_Data.zip",
        "https://webfs-dcd.oecd.org/files/dotStat/DSD_DAC1/Table1_Data.zip",
    ),
    BulkFile(
        "dac2a",
        "Table2a_Data.zip",
        "https://webfs-dcd.oecd.org/files/dotStat/DSD_DAC2/Table2a_Data.zip",
    ),
)


def default_version() -> str:
    """Return the version used when none is given: ``local-<today, ISO>``."""
    return f"local-{dt.date.today().isoformat()}"


def find_bulk_files(directory: Path) -> list[tuple[BulkFile, Path]]:
    """Pair each expected bulk file with its path in ``directory``.

    Args:
        directory: Folder holding the four files.

    Returns:
        ``(spec, path)`` pairs in ``BULK_FILES`` order.

    Raises:
        FileNotFoundError: If any expected file is missing. The message lists every missing name.
    """
    pairs = [(spec, directory / spec.file_name) for spec in BULK_FILES]
    missing = [path.name for _, path in pairs if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing OECD bulk files in {directory}: {missing}")
    return pairs


def parse_versions(raw: str) -> dict[str, str]:
    """Parse the ``--versions`` JSON into file name -> token, adding the release prefix.

    Args:
        raw: JSON object mapping file names to version strings (asset timestamps).

    Returns:
        The map with ``RELEASE_TOKEN_PREFIX`` prepended to every value.

    Raises:
        ValueError: If ``raw`` is not a JSON object of non-empty strings.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--versions is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("--versions must be a JSON object of file name -> version")
    bad = [k for k, v in parsed.items() if not isinstance(v, str) or not v.strip()]
    if bad:
        raise ValueError(f"--versions has empty or non-string values for: {bad}")
    return {name: f"{RELEASE_TOKEN_PREFIX}{token}" for name, token in parsed.items()}


def register_all(directory: Path, *, versions: Mapping[str, str]) -> None:
    """Register every bulk file in ``directory`` with oda_reader, each at its own version.

    oda_reader reuses a derived parquet by token, so a re-upload of a file must carry a new
    token or a restored cache would serve the old data.

    Args:
        directory: Folder holding the four files.
        versions: Version string stored with each registration, by file name.

    Raises:
        FileNotFoundError: If any expected file is missing.
        ValueError: If a present file has no version, or a version is empty.
    """
    pairs = find_bulk_files(directory)
    unversioned = [
        spec.file_name for spec, _ in pairs if spec.file_name not in versions
    ]
    if unversioned:
        raise ValueError(f"No version given for bulk files: {unversioned}")
    empty = [
        spec.file_name for spec, _ in pairs if not versions[spec.file_name].strip()
    ]
    if empty:
        raise ValueError(f"Empty version for bulk files: {empty}")

    oda.use_cache_dir()

    for spec, path in pairs:
        version = versions[spec.file_name]
        registered = oda_reader.register_bulk_file(
            path, dataset=spec.dataset, url=spec.url, version=version
        )
        logger.info(
            "Registered %s from %s (version %s) as %s",
            spec.dataset,
            path.name,
            version,
            registered,
        )


def main(argv: Sequence[str] | None = None) -> None:
    """Parse arguments and register the bulk files."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_BULK_DIR,
        help=f"folder holding the bulk files (default: {DEFAULT_BULK_DIR})",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--version",
        default=default_version(),
        help="one version string for every file (default: local-<today>)",
    )
    group.add_argument(
        "--versions",
        help="JSON object mapping each file name to its own version string",
    )
    args = parser.parse_args(argv)
    if args.versions is not None:
        versions = parse_versions(args.versions)
    else:
        versions = {spec.file_name: args.version for spec in BULK_FILES}
    register_all(args.dir, versions=versions)


if __name__ == "__main__":
    main()
