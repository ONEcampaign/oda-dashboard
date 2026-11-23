"""Everything the pipeline writes out.

This module owns the boundary between a finished DataFrame and the artifacts the frontend
consumes: each loader's archive on stdout (its data as parquet and its dropdown options), and
for sectors the partitioned dataset and its options JSON, published together on the CDN.

The rule for what belongs here: I/O and serialisation. Anything that takes a
DataFrame and returns a DataFrame belongs in ``transformations``; anything that decides how an
entity is labelled belongs in ``naming``.
"""

import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.data.config import LABEL_COLUMNS, PATHS, logger


def build_view_options(
    df: pd.DataFrame,
    columns: dict[str, list[str]],
    year_col: str = "year",
    base_year: int | None = None,
    extra: dict | None = None,
    defaults: dict[str, str | list[str]] | None = None,
    names: dict[str, dict[str, str]] | None = None,
) -> dict:
    """Build the dropdown values a view's frontend reads, from the data it ships with.

    The year column becomes ``{"start", "end", "base"}``; every other column becomes a list of
    its unique values.

    Args:
        columns: Maps each column to include onto the values to pin at the front of its list,
            in order. Pass an empty list for purely alphabetical ordering.
        year_col: Column to treat as a year range rather than a list.
        base_year: Value for the "base" key; defaults to the latest year in the data.
        extra: Additional keys merged into the output, e.g. the name-to-slug maps the frontend
            needs to build partition paths, or a sector-to-sub-sector index.
        defaults: The selection each dropdown opens on, by column; a list for a multi-select.
        names: Option values the frontend refers to by key, grouped by column, e.g.
            {"indicator_name": {"total_oda": "Total ODA"}}. Returned as one flat key map.

    Returns:
        The options, ready to serialise as JSON.

    Raises:
        ValueError: If a default or a name is not among the options, so a rename fails the
            build instead of leaving the frontend pointing at a value that no longer exists.
    """

    def _ordered(values: list[str], order: list[str]) -> list[str]:
        pinned = [v for v in order if v in set(values)]
        rest = sorted(v for v in values if v not in set(order))
        return pinned + rest

    options = {}
    for col, order in columns.items():
        if col == year_col:
            years = df[col].dropna().astype(int)
            options[col] = {
                "start": int(years.min()),
                "end": int(years.max()),
                "base": base_year if base_year is not None else int(years.max()),
            }
        else:
            unique_vals = [str(v) for v in df[col].dropna().unique()]
            options[col] = (
                _ordered(unique_vals, order) if order else sorted(unique_vals)
            )

    for col, value in (defaults or {}).items():
        selected = [value] if isinstance(value, str) else value
        _require_options(selected, options.get(col, []), f"default {col}")
    for col, keyed in (names or {}).items():
        _require_options(list(keyed.values()), options.get(col, []), f"names {col}")
    if defaults:
        options["defaults"] = defaults
    if names:
        keys = [k for keyed in names.values() for k in keyed]
        if dupes := sorted({k for k in keys if keys.count(k) > 1}):
            raise ValueError(f"names keys used in more than one column: {dupes}")
        options["names"] = {k: v for keyed in names.values() for k, v in keyed.items()}

    if extra:
        options |= extra

    return options


def write_view_options(
    options: dict, file_name: str, *, root: Path = PATHS.CDN_FILES
) -> None:
    """Write a view's options, to be published beside its CDN dataset.

    Args:
        options: From build_view_options.
        file_name: Output filename.
        root: Directory to write into; CI publishes PATHS.CDN_FILES.
    """
    path = root / file_name
    logger.info("Saving view options to %s", path)
    with open(path, "w") as f:
        json.dump(options, f, indent=2)


def _require_options(values: list[str], options: list[str], label: str) -> None:
    """Raise if any value is not among the options."""
    missing = [v for v in values if v not in options]
    if missing:
        raise ValueError(f"{label} not among the options: {missing}")


# Members of the archive a view's loader writes; the frontend reads them as
# <view>_view/<member>.
VIEW_DATA_MEMBER: str = "data.parquet"
VIEW_OPTIONS_MEMBER: str = "options.json"


def view_archive_to_stdout(df: pd.DataFrame, options: dict) -> None:
    """Write a view's data and its options to stdout as one zip, Observable's archive loader.

    Built in one run, the dropdowns cannot drift from the data they describe.

    Args:
        df: The view's wide frame.
        options: From build_view_options.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr(VIEW_DATA_MEMBER, dataframe_to_parquet_bytes(df))
        archive.writestr(VIEW_OPTIONS_MEMBER, json.dumps(options, indent=2))
    sys.stdout.buffer.write(buf.getvalue())


def dataframe_to_parquet_bytes(df: pd.DataFrame) -> bytes:
    """Serialise the frame as compressed parquet."""
    table, value_cols = dataframe_to_arrow_table(df)

    # Byte-stream-split reorders the bytes of each value so the compressor sees runs of similar
    # exponents; it is worth applying to the numeric columns only.
    bss_cols = {c: True for c in value_cols}

    buf = pa.BufferOutputStream()
    pq.write_table(
        table,
        buf,
        use_byte_stream_split=bss_cols,
        **get_parquet_write_options(),
    )
    return buf.getvalue().to_pybytes()


# ============================================================================
# Parquet serialisation
# ============================================================================


def optimize_dataframe_types(df: pd.DataFrame) -> pd.DataFrame:
    """Narrow the dtypes so the published parquet stays small.

    Values arrive from convert_values_to_units already as integers in units; anything still
    floating (the pct_* columns) becomes Float32, year becomes Int16, and the label columns are
    dictionary-encoded. Rows are left in whatever order the caller chose.

    Args:
        df: Wide frame ready to be written.

    Returns:
        The frame with narrowed dtypes.
    """
    df = df.copy()

    for col in [c for c in df.columns if c.startswith(("value_", "pct"))]:
        # Integer value columns come from convert_values_to_units and must stay integers.
        if not pd.api.types.is_integer_dtype(df[col]):
            df[col] = df[col].astype("Float32")

    if "year" in df.columns:
        df["year"] = df["year"].astype("Int16")

    for col in LABEL_COLUMNS:
        if col in df.columns and df[col].dtype.name != "category":
            df[col] = df[col].astype("category")

    return df


# The one file per partition; src/js/sectorsQueries.js fetches exactly this name.
PARTITION_FILE: str = "part-0.parquet"
PARTITION_ROW_GROUP_SIZE: int = 100_000

# Codec shared by the single-file and partitioned writers.
PARQUET_CODEC: dict[str, str | int | bool] = {
    "compression": "zstd",
    "compression_level": 15,
    "use_dictionary": True,
    "write_statistics": True,
}


def get_parquet_write_options() -> dict:
    """Compression and encoding settings for the single-file parquet in a view's archive."""
    return {
        **PARQUET_CODEC,
        "data_page_size": 1_048_576,
        "row_group_size": 100_000,
    }


def dataframe_to_arrow_table(df: pd.DataFrame) -> tuple[pa.Table, list[str]]:
    """Narrow the dtypes and convert to an Arrow table.

    Args:
        df: Wide frame ready to be written.

    Returns:
        The Arrow table, and the names of the value columns, which the writers pass to
        pyarrow as byte-stream-split candidates.
    """
    df = optimize_dataframe_types(df)
    value_cols = [c for c in df.columns if c.startswith(("value_", "pct"))]

    return pa.Table.from_pandas(df, preserve_index=False), value_cols


def write_partitioned_dataset(
    df: pd.DataFrame,
    base_dir: str,
    partition_cols: list[str],
    *,
    root: Path = PATHS.CDN_FILES,
) -> None:
    """Write the frame as a Hive-partitioned parquet dataset, for views too big for one file.

    Each partition is written as exactly one file, part-0.parquet, which is the only file the
    frontend fetches. pyarrow's ds.write_dataset split about 90 sectors partitions across
    part-0 and part-1, so those charts silently lost every row in part-1.

    Args:
        df: Wide frame ready to be written.
        base_dir: Directory name, created under root.
        partition_cols: Columns to partition by, e.g. the donor and recipient slugs. The
            frontend addresses partitions by these values, so they have to be URL-safe.
        root: Directory to write into; CI publishes PATHS.CDN_FILES.

    Raises:
        ValueError: If a partition column is absent or has missing values.
    """
    missing = [col for col in partition_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Partition columns absent from the data: {missing}")
    null_keys = [col for col in partition_cols if df[col].isna().any()]
    if null_keys:
        raise ValueError(f"Partition columns with missing values: {null_keys}")

    # Sorting keeps each partition's rows in a stable order within its file.
    optimized = optimize_dataframe_types(df).sort_values(partition_cols, kind="stable")

    output_dir = root / base_dir
    if output_dir.exists():
        logger.info("Clearing existing partitioned dataset at %s", output_dir)
        shutil.rmtree(output_dir)

    groups = optimized.groupby(partition_cols, observed=True, sort=False)
    logger.info("Writing %s partitions to %s", f"{groups.ngroups:,}", output_dir)
    for keys, part in groups:
        part_dir = output_dir.joinpath(
            *(f"{col}={key}" for col, key in zip(partition_cols, keys, strict=True))
        )
        part_dir.mkdir(parents=True)
        pq.write_table(
            pa.Table.from_pandas(
                part.drop(columns=partition_cols), preserve_index=False
            ),
            part_dir / PARTITION_FILE,
            row_group_size=PARTITION_ROW_GROUP_SIZE,
            **PARQUET_CODEC,
        )
