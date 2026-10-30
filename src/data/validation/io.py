"""Load dashboard views and topic_page outputs for validation.

A view source is a directory in one of three layouts:

1. Flat: ``<source>/data.parquet`` + ``<source>/options.json``. The Observable cache
   (``src/.observablehq/cache/data/scripts/<view>/``) and the baseline snapshot
   (``validation_data/baseline/<view>/``) both use it.
2. Hive with options inside: ``<source>/donor_slug=*/recipient_slug=*/*.parquet`` +
   ``<source>/options.json``. The baseline snapshot of sectors_view.
3. Hive with options beside it: ``<source>/donor_slug=*/...`` +
   ``<source>/../<view>_options.json``. The CDN build (``cdn_files/sectors_view``).
   Passing the parent (``cdn_files``) also works: ``<source>/<view>`` is tried first.

So a baseline or source root ``R`` maps every view to ``R/<view>``.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from src.data.config import PATHS
from src.data.validation.views import ViewSpec, get_spec

DATA_FILE: str = "data.parquet"
OPTIONS_FILE: str = "options.json"
PARTITION_COLUMNS: tuple[str, ...] = ("donor_slug", "recipient_slug")

OBSERVABLE_CACHE_DIR: Path = PATHS.SRC / ".observablehq" / "cache" / "data" / "scripts"
VALIDATION_DATA_DIR: Path = PATHS.SRC.parent / "validation_data"
BASELINE_DIR: Path = VALIDATION_DATA_DIR / "baseline"

_STRING_DTYPE = pd.StringDtype("pyarrow")
_ARROW_STRING_TYPES = {pa.string(): _STRING_DTYPE, pa.large_string(): _STRING_DTYPE}

# Topic page amounts: an optional "US$", a number, then a unit word.
_AMOUNT_PATTERN = re.compile(
    r"^\s*(?:US\$)?\s*(?P<number>-?[\d,]*\.?\d+)\s*(?P<unit>billion|million)\s*$",
    re.IGNORECASE,
)
_AMOUNT_UNITS_IN_MILLIONS: dict[str, float] = {"billion": 1_000.0, "million": 1.0}
_PERCENT_PATTERN = re.compile(r"^\s*(?P<number>-?[\d,]*\.?\d+)\s*%\s*$")
_PERCENT: float = 100.0


@dataclass
class LoadedView:
    """A view's data and options, as loaded from one source.

    Attributes:
        spec: The view's spec.
        data: The rows. Label columns are ``string[pyarrow]``, value columns float64 (nulls
            as NaN), year and shares keep their parquet dtypes (int16, float32). Partition
            slug columns are dropped.
        options: The parsed options.json (the dropdown lists, year window and defaults).
        source: The directory the view was loaded from.
    """

    spec: ViewSpec
    data: pd.DataFrame
    options: dict
    source: Path


def default_sources() -> dict[str, Path]:
    """The local build location of each view.

    Returns:
        View name -> source directory: the Observable cache for the three archive views,
        ``cdn_files/sectors_view`` for sectors.
    """
    return {
        "financing_view": OBSERVABLE_CACHE_DIR / "financing_view",
        "recipients_view": OBSERVABLE_CACHE_DIR / "recipients_view",
        "gender_view": OBSERVABLE_CACHE_DIR / "gender_view",
        "sectors_view": PATHS.CDN_FILES / "sectors_view",
    }


def _is_hive_dir(path: Path) -> bool:
    """Whether a directory holds hive partitions (``key=value`` subdirectories)."""
    return path.is_dir() and any(p.is_dir() and "=" in p.name for p in path.iterdir())


def _resolve_source(name: str, source: Path) -> tuple[Path, Path]:
    """Find a view's data path and options path under a source directory.

    Returns:
        (data path: a parquet file or a hive directory, options.json path).

    Raises:
        FileNotFoundError: Naming every path tried.
    """
    if (source / name).is_dir():
        source = source / name

    flat = source / DATA_FILE
    if flat.is_file():
        data_path = flat
    elif _is_hive_dir(source):
        data_path = source
    else:
        raise FileNotFoundError(
            f"No {name} data at {source}: tried {flat} and hive partitions in {source}"
        )

    options_candidates = [source / OPTIONS_FILE, source.parent / f"{name}_options.json"]
    for options_path in options_candidates:
        if options_path.is_file():
            return data_path, options_path
    tried = ", ".join(str(p) for p in options_candidates)
    raise FileNotFoundError(f"No {name} options: tried {tried}")


def _table_to_frame(table: pa.Table, spec: ViewSpec) -> pd.DataFrame:
    """Convert an arrow table to pandas with load_view's dtypes.

    Dictionary-encoded labels become ``string[pyarrow]`` rather than categoricals or Python
    objects. Value columns become float64 whether or not they hold nulls (pandas would
    otherwise turn an int64 column into float64 only when it has a null), so the dtype does
    not depend on the data. float64 is exact for every integer below 2**53 (~9e15), above
    MAX_SANE_VALUE.
    """
    fields = []
    for f in table.schema:
        if pa.types.is_dictionary(f.type):
            f = pa.field(f.name, pa.string())
        elif f.name in spec.value_columns and pa.types.is_integer(f.type):
            f = pa.field(f.name, pa.float64())
        fields.append(f)
    table = table.cast(pa.schema(fields))
    return table.to_pandas(types_mapper=_ARROW_STRING_TYPES.get)


def _data_columns(dataset: ds.Dataset) -> list[str]:
    """A dataset's columns without the hive partition columns."""
    return [c for c in dataset.schema.names if c not in PARTITION_COLUMNS]


def _parquet_files(path: Path) -> list[Path]:
    """The parquet files under a hive directory, sorted.

    Listed explicitly because the baseline layout keeps options.json inside the directory.

    Raises:
        FileNotFoundError: No parquet files under path.
    """
    files = sorted(path.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files under {path}")
    return files


def _hive_dataset(path: Path, files: list[Path] | None = None) -> ds.Dataset:
    """Open hive-partitioned parquet files under path (all of them by default)."""
    files = _parquet_files(path) if files is None else files
    return ds.dataset(
        [str(f) for f in files],
        format="parquet",
        partitioning="hive",
        partition_base_dir=str(path),
    )


def read_hive_files(path: Path, files: list[Path], spec: ViewSpec) -> pd.DataFrame:
    """Read some parquet files of a hive directory with load_view's dtypes.

    Args:
        path: The hive directory (the partition base).
        files: Parquet files under path to read.
        spec: The view's spec, for the value column dtypes.

    Returns:
        The rows, without the partition slug columns.
    """
    dataset = _hive_dataset(path, files)
    return _table_to_frame(dataset.to_table(columns=_data_columns(dataset)), spec)


def _read_options(path: Path) -> dict:
    """Parse an options.json file, which must hold a JSON object."""
    options = json.loads(path.read_text())
    if not isinstance(options, dict):
        raise ValueError(
            f"{path} must hold a JSON object, got {type(options).__name__}"
        )
    return options


def load_view(name: str, source: Path) -> LoadedView:
    """Load a whole view from a source directory (see the module docstring for layouts).

    Args:
        name: A key of VIEWS.
        source: The view's directory.

    Returns:
        The view with labels as ``string[pyarrow]`` and slug columns dropped.

    Raises:
        KeyError: Unknown view name.
        FileNotFoundError: No data or options under ``source``.
    """
    spec = get_spec(name)
    data_path, options_path = _resolve_source(name, source)
    if data_path.is_file():
        table = pq.read_table(data_path)
        table = table.drop_columns(
            [c for c in PARTITION_COLUMNS if c in table.schema.names]
        )
    else:
        dataset = _hive_dataset(data_path)
        table = dataset.to_table(columns=_data_columns(dataset))
    return LoadedView(
        spec=spec,
        data=_table_to_frame(table, spec),
        options=_read_options(options_path),
        source=source,
    )


def iter_partitions(
    name: str,
    source: Path,
    by: Literal["donor_slug", "recipient_slug"] = "recipient_slug",
) -> Iterator[tuple[str, LoadedView]]:
    """Load a hive view one partition value at a time, to bound memory.

    ``by="recipient_slug"`` yields every donor for one recipient, which is what donor-group
    sums need; ``by="donor_slug"`` yields every recipient for one donor. Each yielded view
    shares the same options dict. A flat (single-file) source yields the whole view once,
    keyed "all", so callers can treat every view alike.

    Args:
        name: A key of VIEWS.
        source: The view's directory.
        by: The partition column to split on.

    Yields:
        (partition value, e.g. "oda-eligible-countries"; the partition's rows as a view),
        in sorted partition order.

    Raises:
        ValueError: ``by`` is not a partition column.
        FileNotFoundError: No data or options under ``source``.
    """
    if by not in PARTITION_COLUMNS:
        raise ValueError(f"by must be one of {PARTITION_COLUMNS}, got {by!r}")
    spec = get_spec(name)
    data_path, options_path = _resolve_source(name, source)
    options = _read_options(options_path)

    if data_path.is_file():
        yield "all", load_view(name, source)
        return

    files_by_value: dict[str, list[Path]] = {}
    prefix = f"{by}="
    for file in _parquet_files(data_path):
        part = next(
            (p for p in file.relative_to(data_path).parts if p.startswith(prefix)), None
        )
        if part is None:
            raise ValueError(f"{file} is not under a {by}= partition")
        files_by_value.setdefault(part.removeprefix(prefix), []).append(file)

    # One small dataset per partition value, built from its own files: filtering one
    # dataset over every file held ~1 GB of scan buffers for the real sectors view.
    for value in sorted(files_by_value):
        yield (
            value,
            LoadedView(
                spec=spec,
                data=read_hive_files(data_path, files_by_value[value], spec),
                options=options,
                source=source,
            ),
        )


def load_topic_page(name: str) -> pd.DataFrame:
    """Read a topic_page CSV with every cell as a raw string.

    Formatted cells ("US$27.0 billion", "26.8%") are left for the caller to parse with
    parse_amount and parse_percent, since bare numbers carry file-specific units. Empty cells
    are empty strings.

    Args:
        name: The file name, with or without ".csv", e.g. "oda_gni_ts".

    Raises:
        FileNotFoundError: No such file in PATHS.TOPIC_PAGE.
    """
    filename = name if name.endswith(".csv") else f"{name}.csv"
    path = PATHS.TOPIC_PAGE / filename
    if not path.is_file():
        raise FileNotFoundError(f"No topic_page file at {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def parse_amount(text: str) -> float:
    """Parse a formatted topic_page amount into USD millions.

    Accepts "59.0 billion", "US$27.0 billion", "694.2 million", "1,234.5 million".

    Raises:
        ValueError: No number or no unit word (a bare number's unit is file-specific).
    """
    match = _AMOUNT_PATTERN.match(text)
    if match is None:
        raise ValueError(f"Not an amount with a billion/million unit: {text!r}")
    number = float(match["number"].replace(",", ""))
    return number * _AMOUNT_UNITS_IN_MILLIONS[match["unit"].lower()]


def parse_percent(text: str) -> float:
    """Parse a formatted percentage ("26.8%", "-23.1 %") into a fraction (0.268).

    Raises:
        ValueError: Not a number followed by "%".
    """
    match = _PERCENT_PATTERN.match(text)
    if match is None:
        raise ValueError(f"Not a percentage: {text!r}")
    return float(match["number"].replace(",", "")) / _PERCENT
