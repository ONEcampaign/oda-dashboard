"""Manifest loading, saving, and computation."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from validation.config import MANIFESTS_DIR


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
    """
    Compute aggregate statistics for the dataset.

    Args:
        df: DataFrame to analyze
        value_column: Column to aggregate

    Returns:
        Dict with aggregates by various dimensions
    """
    aggregates = {}

    # By donor
    if "donor_code" in df.columns:
        by_donor = df.groupby("donor_code")[value_column].sum()
        aggregates["by_donor"] = {str(k): float(v) for k, v in by_donor.items()}

    # By year
    if "year" in df.columns:
        by_year = df.groupby("year")[value_column].sum()
        aggregates["by_year"] = {str(k): float(v) for k, v in by_year.items()}

    # By indicator
    if "indicator" in df.columns:
        by_indicator = df.groupby("indicator")[value_column].sum()
        aggregates["by_indicator"] = {str(k): float(v) for k, v in by_indicator.items()}

    # By recipient region (if recipient_code exists, group by first digit for region)
    if "recipient_code" in df.columns:
        by_recipient = df.groupby("recipient_code")[value_column].sum()
        aggregates["by_recipient"] = {str(k): float(v) for k, v in by_recipient.items()}

    # By agency (if present, for multilateral data)
    if "agency_code" in df.columns:
        by_agency = df.groupby("agency_code")[value_column].sum()
        aggregates["by_agency"] = {str(k): float(v) for k, v in by_agency.items()}

    # By sector (if present, for sectors_view)
    if "sector_name" in df.columns:
        by_sector = df.groupby("sector_name", observed=True)[value_column].sum()
        aggregates["by_sector"] = {str(k): float(v) for k, v in by_sector.items()}

    # By sub-sector (if present, for sectors_view)
    if "sub_sector_code" in df.columns:
        by_sub_sector = df.groupby("sub_sector_code", observed=True)[value_column].sum()
        aggregates["by_sub_sector"] = {str(k): float(v) for k, v in by_sub_sector.items()}

    # By donor-sector combination (if both present, for sectors_view)
    if "donor_code" in df.columns and "sector_name" in df.columns:
        by_donor_sector = df.groupby(["donor_code", "sector_name"], observed=True)[value_column].sum()
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
    if "year" not in df.columns or "donor_code" not in df.columns:
        return {"overall": {"mean": 0, "std": 0}, "by_donor": {}}

    # Compute YoY changes per donor
    yoy_changes = []
    by_donor = {}

    for donor in df["donor_code"].unique():
        donor_data = df[df["donor_code"] == donor].sort_values("year")

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
        overall_std = (sum((x - overall_mean) ** 2 for x in valid_yoy) / len(valid_yoy)) ** 0.5
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
    """
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
        "year_range": [int(df["year"].min()), int(df["year"].max())] if "year" in df.columns else None,
        "donors_present": sorted([int(x) for x in df["donor_code"].unique()]) if "donor_code" in df.columns else [],
        "recipients_present": sorted([int(x) for x in df["recipient_code"].unique()])[:100] if "recipient_code" in df.columns else [],
        "indicators_present": list(df["indicator"].unique()) if "indicator" in df.columns else [],
        "aggregates": compute_aggregates(df, value_column),
        "distribution": compute_distribution(df, value_column),
        "historical_variation": compute_historical_variation(df, value_column),
    }

    # Add purpose codes if present
    if "purpose_code" in df.columns:
        release_data["purpose_codes_present"] = sorted([int(x) for x in df["purpose_code"].unique()])

    # Add sub-sector codes if present (for sectors_view)
    if "sub_sector_code" in df.columns:
        release_data["sub_sector_codes_present"] = sorted([int(x) for x in df["sub_sector_code"].dropna().unique()])

    # Add sector names if present
    if "sector_name" in df.columns:
        release_data["sectors_present"] = sorted(df["sector_name"].dropna().unique().tolist())

    manifest["releases"][release] = release_data

    return manifest


def get_manifest_path(dataset_name: str) -> Path:
    """Get the path to a dataset's manifest file."""
    return MANIFESTS_DIR / f"{dataset_name}.json"
