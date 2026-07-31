"""Manifest loading, saving, and computation."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from validation.config import MANIFESTS_DIR

# The dimensions a manifest can be keyed by, and the column carrying each one.
#
# All names, no codes. The views publish no code columns at all, so a manifest keyed by codes
# cannot be compared against them — and because every producer below was guarded on
# "code column in df.columns", the aggregates silently came out empty rather than failing. Adding
# a dimension here is the only place it needs declaring; the guard stays only for dimensions a
# given view genuinely does not have (financing has no recipient, only sectors has sub-sectors).
AGGREGATE_DIMENSIONS: dict[str, str] = {
    "by_donor": "donor_name",
    "by_year": "year",
    "by_indicator": "indicator_name",
    "by_recipient": "recipient_name",
    "by_sector": "sector_name",
    "by_sub_sector": "sub_sector_name",
}

# The same dimensions, recorded as the set of values present rather than as totals.
PRESENCE_DIMENSIONS: dict[str, str] = {
    "donors_present": "donor_name",
    "recipients_present": "recipient_name",
    "indicators_present": "indicator_name",
    "sectors_present": "sector_name",
    "sub_sectors_present": "sub_sector_name",
}


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types, NaN, and infinite values."""

    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if pd.isna(obj):
            return None
        # Handle Python float inf/nan
        if isinstance(obj, float):
            if np.isnan(obj) or np.isinf(obj):
                return None
        return super().default(obj)


def load_manifest(path: Path) -> dict:
    """
    Load a manifest from disk.

    Args:
        path: Path to manifest JSON file

    Returns:
        Manifest dict, or empty dict if file doesn't exist
    """
    if not path.exists():
        return {}

    with open(path, "r") as f:
        return json.load(f)


def _sanitize_for_json(obj):
    """Recursively sanitize a dict/list for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.floating,)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if pd.isna(obj):
        return None
    return obj


def save_manifest(manifest: dict, path: Path) -> None:
    """
    Save a manifest to disk.

    Args:
        manifest: Manifest dict to save
        path: Path to save to
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = _sanitize_for_json(manifest)
    with open(path, "w") as f:
        json.dump(sanitized, f, indent=2)


def compute_aggregates(df: pd.DataFrame, value_column: str) -> dict:
    """Total the value column by each dimension the frame carries.

    Args:
        df: Frame to analyse.
        value_column: Column to total.

    Returns:
        ``{"by_<dimension>": {name: total}}``, for whichever of AGGREGATE_DIMENSIONS are present,
        plus ``by_donor_sector`` keyed ``"<donor>|<sector>"``.
    """
    aggregates = {}

    for key, column in AGGREGATE_DIMENSIONS.items():
        if column not in df.columns:
            continue
        totals = df.groupby(column, observed=True)[value_column].sum()
        aggregates[key] = {str(k): float(v) for k, v in totals.items()}

    # Donor crossed with sector, which catches one donor's allocation collapsing while the
    # sector total stays flat.
    if "donor_name" in df.columns and "sector_name" in df.columns:
        by_donor_sector = df.groupby(["donor_name", "sector_name"], observed=True)[
            value_column
        ].sum()
        aggregates["by_donor_sector"] = {
            f"{donor}|{sector}": float(v)
            for (donor, sector), v in by_donor_sector.items()
        }

    return aggregates


def compute_distribution(df: pd.DataFrame, value_column: str) -> dict:
    """
    Compute distribution statistics for value column.

    Args:
        df: DataFrame to analyze
        value_column: Column to compute stats for

    Returns:
        Dict with min, max, median, percentiles
    """
    values = df[value_column].dropna()

    if len(values) == 0:
        return {"min": None, "max": None, "median": None, "p25": None, "p75": None}

    return {
        "min": float(values.min()),
        "max": float(values.max()),
        "median": float(values.median()),
        "p25": float(values.quantile(0.25)),
        "p75": float(values.quantile(0.75)),
    }


def compute_historical_variation(df: pd.DataFrame, value_column: str) -> dict:
    """
    Analyze year-over-year variation in the data to establish normal ranges.

    Args:
        df: DataFrame with historical data
        value_column: Column to analyze

    Returns:
        Dict with variation statistics by donor and overall
    """
    if "year" not in df.columns or "donor_name" not in df.columns:
        return {"overall": {"mean": 0, "std": 0}, "by_donor": {}}

    # Compute YoY changes per donor
    yoy_changes = []
    by_donor = {}

    for donor in df["donor_name"].unique():
        donor_data = df[df["donor_name"] == donor].sort_values("year")

        if len(donor_data) < 2:
            continue

        # Compute year-over-year percentage changes
        donor_yearly = donor_data.groupby("year")[value_column].sum()
        pct_changes = donor_yearly.pct_change().dropna()

        if len(pct_changes) > 0:
            # Filter out NA and infinite values before computing stats
            valid_changes = pct_changes.replace([np.inf, -np.inf], np.nan).dropna()
            if len(valid_changes) > 0:
                yoy_changes.extend(valid_changes.tolist())
                mean_val = valid_changes.mean()
                std_val = valid_changes.std() if len(valid_changes) > 1 else 0
                by_donor[str(donor)] = {
                    "mean": float(mean_val) if not pd.isna(mean_val) else 0,
                    "std": float(std_val) if not pd.isna(std_val) else 0,
                }

    # Overall statistics - filter any remaining inf/nan
    valid_yoy = [x for x in yoy_changes if np.isfinite(x)]
    if valid_yoy:
        overall_mean = sum(valid_yoy) / len(valid_yoy)
        overall_std = (
            sum((x - overall_mean) ** 2 for x in valid_yoy) / len(valid_yoy)
        ) ** 0.5
    else:
        overall_mean = 0
        overall_std = 0

    return {
        "overall": {"mean": overall_mean, "std": overall_std},
        "by_donor": by_donor,
    }


def update_manifest(
    manifest: dict,
    release: str,
    df: pd.DataFrame,
    value_column: str,
    key_columns: list[str],
) -> dict:
    """
    Update manifest with data from a new release.

    Args:
        manifest: Existing manifest (or empty dict)
        release: Release name (e.g., "dec_2024")
        df: DataFrame for this release
        value_column: Primary value column
        key_columns: Columns that form the unique key

    Returns:
        Updated manifest dict

    Raises:
        ValueError: If a declared key column is absent. Writing a manifest from a frame that is
            missing one would record an empty dimension, and every later release would then
            compare against nothing and pass.
    """
    missing = [col for col in key_columns if col not in df.columns]
    if missing:
        raise ValueError(
            f"Cannot build a manifest: declared key columns absent from the data: {missing}"
        )

    # Initialize if empty
    if not manifest:
        manifest = {
            "dataset": "",
            "schema": {"columns": [], "dtypes": {}},
            "releases": {},
        }

    # Update schema
    manifest["schema"]["columns"] = list(df.columns)
    manifest["schema"]["dtypes"] = {col: str(df[col].dtype) for col in df.columns}

    # Compute release data
    release_data = {
        "row_count": len(df),
        "year_range": [int(df["year"].min()), int(df["year"].max())]
        if "year" in df.columns
        else None,
        "aggregates": compute_aggregates(df, value_column),
        "distribution": compute_distribution(df, value_column),
        "historical_variation": compute_historical_variation(df, value_column),
    }

    # Which values each dimension holds. Recorded in full: the previous version capped
    # recipients at 100, which made every recipient past the hundredth look newly removed.
    for key, column in PRESENCE_DIMENSIONS.items():
        if column not in df.columns:
            continue
        release_data[key] = sorted(str(x) for x in df[column].dropna().unique())

    manifest["releases"][release] = release_data

    return manifest


def get_manifest_path(dataset_name: str) -> Path:
    """Get the path to a dataset's manifest file."""
    return MANIFESTS_DIR / f"{dataset_name}.json"
