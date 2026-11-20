"""Shared fixtures for the validation tests: in-memory views and on-disk layouts."""

import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.data.validation.io import DATA_FILE, OPTIONS_FILE, LoadedView
from src.data.validation.views import ViewSpec, get_spec

type MakeView = Callable[..., LoadedView]

_NUMPY_DTYPES = {"int16": np.int16, "float64": np.float64, "float32": np.float32}


def _cast_to_spec(df: pd.DataFrame, spec: ViewSpec) -> pd.DataFrame:
    """Cast the columns present to the dtypes load_view returns."""
    dtypes = {
        col: pd.StringDtype("pyarrow") if dtype == "string" else _NUMPY_DTYPES[dtype]
        for col, dtype in spec.dtypes.items()
        if col in df.columns
    }
    return df.astype(dtypes)


def _fill_missing_measures(df: pd.DataFrame, spec: ViewSpec) -> pd.DataFrame:
    """Add absent value columns (copies of value_usd_current, else 0) and shares (0.0)."""
    df = df.copy()
    for col in spec.value_columns:
        if col not in df.columns:
            df[col] = (
                df["value_usd_current"] if "value_usd_current" in df.columns else 0
            )
    for col in spec.share_columns:
        if col not in df.columns:
            df[col] = 0.0
    return df


def _default_options(df: pd.DataFrame, spec: ViewSpec) -> dict:
    """Options consistent with the rows: each label key's sorted values, the spec's years."""
    options: dict = {
        key: sorted(df[key].dropna().unique().tolist())
        for key in spec.keys
        if key not in ("year", "type") and key in df.columns
    }
    options["year"] = dict(spec.time)
    options["defaults"] = {}
    return options


def build_view(
    name: str,
    rows: pd.DataFrame | Iterable[Mapping[str, object]],
    options: dict | None = None,
    *,
    fill: bool = True,
    source: Path = Path("memory"),
) -> LoadedView:
    """Build a LoadedView in memory with load_view's dtypes.

    Args:
        name: A key of VIEWS.
        rows: The rows, as a frame or an iterable of dicts.
        options: The options dict; None derives one from the rows (see _default_options).
        fill: Add any missing value and share columns (value columns copy
            value_usd_current, or 0; shares are 0.0). Pass False to test missing columns.
        source: The LoadedView.source to record.
    """
    spec = get_spec(name)
    df = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    if fill:
        df = _fill_missing_measures(df, spec)
    df = _cast_to_spec(df, spec)
    if options is None:
        options = _default_options(df, spec)
    return LoadedView(spec=spec, data=df, options=options, source=source)


@pytest.fixture
def make_view() -> MakeView:
    """The build_view factory: make_view(name, rows, options=None, *, fill=True)."""
    return build_view


def _to_dictionary_table(df: pd.DataFrame) -> pa.Table:
    """An arrow table as the pipeline writes it: labels dictionary-encoded, values int64."""
    table = pa.Table.from_pandas(df, preserve_index=False)
    fields = []
    for f in table.schema:
        if pa.types.is_string(f.type) or pa.types.is_large_string(f.type):
            f = pa.field(f.name, pa.dictionary(pa.int16(), pa.string()))
        elif f.name.startswith("value_"):
            f = pa.field(f.name, pa.int64())
        fields.append(f)
    return table.cast(pa.schema(fields))


def write_flat(view: LoadedView, directory: Path) -> Path:
    """Write a view as data.parquet + options.json into directory; returns directory."""
    directory.mkdir(parents=True, exist_ok=True)
    pq.write_table(_to_dictionary_table(view.data), directory / DATA_FILE)
    (directory / OPTIONS_FILE).write_text(json.dumps(view.options))
    return directory


def _slug(name: str) -> str:
    """A simple slug for test partitions."""
    return name.lower().replace(" ", "-")


def write_hive(
    view: LoadedView, directory: Path, *, options_beside: bool = False
) -> Path:
    """Write a view as donor_slug=/recipient_slug= partitions; returns the hive directory.

    Args:
        view: The view; needs donor_name and recipient_name.
        directory: The hive directory to create.
        options_beside: Write ``<parent>/<view>_options.json`` (the CDN layout) instead of
            ``options.json`` inside the hive directory (the baseline layout).
    """
    for (donor, recipient), part in view.data.groupby(
        ["donor_name", "recipient_name"], observed=True
    ):
        part_dir = (
            directory
            / f"donor_slug={_slug(donor)}"
            / f"recipient_slug={_slug(recipient)}"
        )
        part_dir.mkdir(parents=True, exist_ok=True)
        pq.write_table(_to_dictionary_table(part), part_dir / "part-0.parquet")
    options_path = (
        directory.parent / f"{view.spec.name}_options.json"
        if options_beside
        else directory / OPTIONS_FILE
    )
    options_path.write_text(json.dumps(view.options))
    return directory


@pytest.fixture
def sector_rows() -> list[dict]:
    """Four sectors_view rows: two donors by two recipients."""
    return [
        {
            "year": 2024,
            "donor_name": donor,
            "recipient_name": recipient,
            "indicator_name": "Bilateral",
            "sector_name": "Health",
            "sub_sector_name": "Basic Health",
            "value_usd_current": value,
        }
        for donor, recipient, value in [
            ("France", "Kenya", 1_000_000),
            ("France", "Mali", 2_000_000),
            ("Germany", "Kenya", 3_000_000),
            ("Germany", "Mali", 4_000_000),
        ]
    ]
