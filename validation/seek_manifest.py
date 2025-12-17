"""Manifest handling for SEEK-style sector validation."""

from datetime import datetime
from pathlib import Path

import pandas as pd

from validation.config import (
    MANIFESTS_DIR,
    SEEK_HEALTH_PURPOSE_CODES,
    SEEK_AGRICULTURE_PURPOSE_CODES,
)
from validation.manifest import load_manifest, save_manifest
from validation.seek_data import compute_sector_aggregates


def get_seek_manifest_path() -> Path:
    """Get path to SEEK validation manifest file."""
    return MANIFESTS_DIR / "seek_sectors_validation.json"


def update_seek_manifest(
    manifest: dict,
    release: str,
    df: pd.DataFrame,
    health_codes: list[int] | None = None,
    agriculture_codes: list[int] | None = None,
) -> dict:
    """
    Update SEEK manifest with new release data.

    Args:
        manifest: Existing manifest (or empty dict for first run)
        release: Release name (e.g., "april_2025")
        df: DataFrame with purpose-code level data
        health_codes: Health purpose codes (defaults to config)
        agriculture_codes: Agriculture purpose codes (defaults to config)

    Returns:
        Updated manifest dict
    """
    health_codes = health_codes or SEEK_HEALTH_PURPOSE_CODES
    agriculture_codes = agriculture_codes or SEEK_AGRICULTURE_PURPOSE_CODES

    # Initialize if empty
    if not manifest:
        manifest = {
            "dataset": "seek_sectors_validation",
            "releases": {},
        }

    # Compute aggregates for this release
    aggregates = compute_sector_aggregates(
        df=df,
        health_codes=health_codes,
        agriculture_codes=agriculture_codes,
    )

    # Store release data
    manifest["releases"][release] = {
        "computed_at": datetime.now().isoformat(),
        "latest_year": aggregates["latest_year"],
        "by_donor_total": {
            str(k): float(v) for k, v in aggregates["by_donor_total"].items()
        },
        "by_donor_health": {
            str(k): float(v) for k, v in aggregates["by_donor_health"].items()
        },
        "by_donor_agriculture": {
            str(k): float(v) for k, v in aggregates["by_donor_agriculture"].items()
        },
    }

    return manifest


def get_previous_seek_release(manifest: dict) -> dict:
    """
    Get the most recent release data to compare against.

    Always returns the most recent release by timestamp, regardless of name.
    This allows automatic comparison without requiring manual release name management.

    Args:
        manifest: SEEK manifest dict

    Returns:
        Most recent release data dict, or empty dict if none
    """
    releases = manifest.get("releases", {})
    if not releases:
        return {}

    # Sort by computed_at timestamp (most recent first)
    # Fall back to release name if no timestamp
    def sort_key(name):
        release = releases[name]
        return release.get("computed_at", name)

    release_names = sorted(releases.keys(), key=sort_key, reverse=True)
    if release_names:
        return releases[release_names[0]]

    return {}


def generate_release_name() -> str:
    """
    Generate an automatic release name based on current date.

    Format: YYYY-MM (e.g., "2025-04")
    """
    return datetime.now().strftime("%Y-%m")


def load_seek_manifest() -> dict:
    """Load SEEK manifest from disk."""
    return load_manifest(get_seek_manifest_path())


def save_seek_manifest(manifest: dict) -> None:
    """Save SEEK manifest to disk."""
    save_manifest(manifest, get_seek_manifest_path())
