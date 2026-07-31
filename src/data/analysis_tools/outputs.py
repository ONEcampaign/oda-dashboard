"""Everything the pipeline writes out, and the environment it writes into.

This module owns the boundary between a finished DataFrame and the artifacts the frontend
consumes: the parquet on stdout that Observable picks up, the partitioned dataset on the CDN,
and the JSON of dropdown options beside them. It also points oda_data and pydeflate at the
shared cache.

The rule for what belongs here: I/O, serialisation and environment setup. Anything that takes a
DataFrame and returns a DataFrame belongs in ``transformations``; anything that decides how an
entity is labelled belongs in ``naming``.
"""

import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
from oda_data import set_data_path
from pydeflate import set_pydeflate_path

from src.data.config import LABEL_COLUMNS, PATHS, logger


def generate_view_options(
    df: pd.DataFrame,
    columns: dict[str, list[str]],
    year_col: str = "year",
    base_year: int | None = None,
    file_name: str = "view_options.json",
    extra: dict | None = None,
) -> None:
    """Write the JSON of dropdown values a view's frontend reads.

    The year column becomes ``{"start", "end", "base"}``; every other column becomes a list of
    its unique values.

    Args:
        columns: Maps each column to include onto the values to pin at the front of its list,
            in order. Pass an empty list for purely alphabetical ordering.
        year_col: Column to treat as a year range rather than a list.
        base_year: Value for the "base" key; defaults to the latest year in the data.
        file_name: Output filename, written to PATHS.TOOLS.
        extra: Additional keys merged into the output, e.g. the name-to-slug maps the frontend
            needs to build partition paths, or a sector-to-sub-sector index.
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
            options[col] = _ordered(unique_vals, order) if order else sorted(unique_vals)

    if extra:
        options |= extra

    logger.info(f"Saving view options to {PATHS.TOOLS}/{file_name}")
    with open(PATHS.TOOLS / file_name, "w") as f:
        json.dump(options, f, indent=2)


def set_cache_dir(
    path: Path = PATHS.DATA, oda_data: bool = False, pydeflate: bool = False
) -> None:
    """Point the data libraries at the shared cache directory, creating it if needed.

    Every loader calls this before fetching: without it each library caches somewhere of its
    own, and CI restores one directory.

    Args:
        path: Cache directory.
        oda_data: Whether to point oda_data at it.
        pydeflate: Whether to point pydeflate at it.
    """
    if not path.exists():
        logger.info(f"Creating directory for cached data: {path}")
        path.mkdir(parents=True, exist_ok=True)

    if oda_data:
        set_data_path(path)
    if pydeflate:
        set_pydeflate_path(path)


def parquet_to_stdout(df: pd.DataFrame) -> None:
    """Write the frame to stdout as parquet, which is how Observable loaders return data."""
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

    sys.stdout.buffer.write(buf.getvalue().to_pybytes())


# ============================================================================
# Parquet serialisation
# ============================================================================


def optimize_dataframe_types(df: pd.DataFrame) -> pd.DataFrame:
    """Narrow the dtypes so the published parquet stays small.

    Values arrive from convert_values_to_units already as integers in units; anything still
    floating (the pct_* columns) becomes Float32, year becomes Int16, and the label columns are
    dictionary-encoded. Rows are left in whatever order the caller chose:
    write_partitioned_dataset sorts by its partition columns, which is what actually helps
    compression here.

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


def get_parquet_write_options() -> dict:
    """Compression and encoding settings for the single-file parquet written to stdout.

    write_partitioned_dataset deliberately does not reuse these: the paging and row-group keys
    below are arguments to pq.write_table, while the dataset writer takes its row-group sizing
    from ds.write_dataset instead.
    """
    return {
        "compression": "zstd",
        "compression_level": 15,
        "use_dictionary": True,
        "write_statistics": True,
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
) -> None:
    """Write the frame as a Hive-partitioned parquet dataset, for views too big for one file.

    Args:
        df: Wide frame ready to be written.
        base_dir: Directory name, created under PATHS.CDN_FILES.
        partition_cols: Columns to partition by, e.g. the donor and recipient slugs. The
            frontend addresses partitions by these values, so they have to be URL-safe.
    """
    missing = [col for col in partition_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Partition columns absent from the data: {missing}")

    optimized = optimize_dataframe_types(df)

    # Sort by the partition columns so each fragment written covers only a few partitions.
    # Unsorted input makes every fragment span every partition, and pyarrow then refuses the
    # write for exceeding its per-fragment partition ceiling.
    optimized = optimized.sort_values(partition_cols, kind="stable")

    table = pa.Table.from_pandas(optimized, preserve_index=False)

    output_dir = PATHS.CDN_FILES / base_dir
    if output_dir.exists():
        logger.info("Clearing existing partitioned dataset at %s", output_dir)
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Take each partition column's type from the table, so both string slugs and numeric
    # codes work. Forcing int32 here silently ruled out name-based partitioning.
    partition_fields = []
    for col in partition_cols:
        field = table.schema.field(col)
        # Dictionary-typed partition keys make pyarrow hang in teardown across thousands of
        # partitions, so partition on the underlying values instead.
        if pa.types.is_dictionary(field.type):
            field = field.with_type(field.type.value_type)
            table = table.set_column(
                table.schema.get_field_index(col), field, table[col].cast(field.type)
            )
        partition_fields.append(field)
    partition_schema = pa.schema(partition_fields)

    # The same codec as get_parquet_write_options, but only the keys make_write_options
    # accepts: row-group sizing is set on ds.write_dataset below instead.
    parquet_format = ds.ParquetFileFormat()
    file_options = parquet_format.make_write_options(
        compression="zstd",
        compression_level=15,
        use_dictionary=True,
        write_statistics=True,
    )

    # pyarrow's default ceiling is 1024 partitions per fragment; raise it to what the data
    # actually needs so a legitimate dataset is never silently capped.
    n_partitions = optimized.groupby(partition_cols, observed=True, dropna=False).ngroups
    logger.info("Writing %s partitions to %s", f"{n_partitions:,}", output_dir)

    # Write partitioned dataset
    ds.write_dataset(
        data=table,
        base_dir=str(output_dir),
        format="parquet",
        partitioning=ds.partitioning(partition_schema, flavor="hive"),
        basename_template="part-{i}.parquet",
        file_options=file_options,
        existing_data_behavior="delete_matching",
        max_partitions=max(1_024, n_partitions + 1),
        max_rows_per_file=1_000_000,
        max_rows_per_group=100_000,
        min_rows_per_group=100_000,
    )
