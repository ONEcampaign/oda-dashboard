"""SEEK-style anomaly detection for sector validation.

Implements Z-score based anomaly detection that compares donor-level
spending between releases for total, health, and agriculture sectors.
"""

import pandas as pd

from validation.models import Warning
from validation.config import (
    SEEK_Z_SCORE_THRESHOLD,
    SEEK_Z_SCORE_HIGH,
    SEEK_PCT_CHANGE_THRESHOLD,
    SEEK_PCT_CHANGE_HIGH,
    SEEK_HEALTH_PURPOSE_CODES,
    SEEK_AGRICULTURE_PURPOSE_CODES,
    MAJOR_DONORS,
)
from validation.seek_data import compute_sector_aggregates


def detect_seek_donor_drift(
    current_aggregates: dict[int, float],
    previous_aggregates: dict[int, float],
    sector_name: str,
    donor_names: dict[int, str],
    z_threshold: float = SEEK_Z_SCORE_THRESHOLD,
    z_high: float = SEEK_Z_SCORE_HIGH,
    pct_threshold: float = SEEK_PCT_CHANGE_THRESHOLD,
    pct_high: float = SEEK_PCT_CHANGE_HIGH,
) -> list[Warning]:
    """
    Compare donor totals between releases for a specific sector.

    Replicates SEEK R code comparison pattern:
    - For each donor, compute % change from previous release
    - Calculate Z-scores across donors to identify outliers
    - Flag significant changes using Z-score or percentage thresholds

    Args:
        current_aggregates: {donor_code: value} for current release
        previous_aggregates: {donor_code: value} for previous release
        sector_name: "total", "health", or "agriculture" for messages
        donor_names: {donor_code: donor_name} for readable messages
        z_threshold: Z-score threshold for medium warning (default: 2.0)
        z_high: Z-score threshold for high warning (default: 3.0)
        pct_threshold: Percentage change threshold for medium warning (default: 0.20)
        pct_high: Percentage change threshold for high warning (default: 0.40)

    Returns:
        List of Warning objects for flagged donors
    """
    warnings = []

    if not previous_aggregates:
        return warnings

    # Compute all percentage changes for Z-score calculation
    changes = []
    for donor, curr_val in current_aggregates.items():
        prev_val = previous_aggregates.get(donor, 0)
        if prev_val > 0:
            pct_change = (curr_val - prev_val) / prev_val
            changes.append((donor, curr_val, prev_val, pct_change))

    if len(changes) < 2:
        # Not enough data for Z-score, use simple percentage thresholds
        for donor, curr_val, prev_val, pct_change in changes:
            if abs(pct_change) > pct_threshold:
                level = "high" if abs(pct_change) > pct_high else "medium"
                donor_name = donor_names.get(donor, f"Donor {donor}")
                warnings.append(
                    Warning(
                        level=level,
                        dataset="seek_sectors",
                        message=(
                            f"SEEK {sector_name}: {donor_name} changed {pct_change:+.1%} "
                            f"vs previous release"
                        ),
                    )
                )
        return warnings

    # Compute Z-scores across all donors
    pct_changes = [c[3] for c in changes]
    mean_change = sum(pct_changes) / len(pct_changes)
    variance = sum((x - mean_change) ** 2 for x in pct_changes) / len(pct_changes)
    std_change = variance**0.5

    for donor, curr_val, prev_val, pct_change in changes:
        # Calculate Z-score (handle zero std)
        z_score = (pct_change - mean_change) / std_change if std_change > 0 else 0

        # Flag if Z-score OR percentage exceeds thresholds
        is_z_anomaly = abs(z_score) > z_threshold
        is_pct_anomaly = abs(pct_change) > pct_threshold

        if is_z_anomaly or is_pct_anomaly:
            # Determine level based on both criteria
            is_high = abs(z_score) > z_high or abs(pct_change) > pct_high
            level = "high" if is_high else "medium"
            donor_name = donor_names.get(donor, f"Donor {donor}")

            warnings.append(
                Warning(
                    level=level,
                    dataset="seek_sectors",
                    message=(
                        f"SEEK {sector_name}: {donor_name} changed {pct_change:+.1%} "
                        f"(z={z_score:.1f}, typical: {mean_change:+.1%} ± {std_change:.1%})"
                    ),
                )
            )

    return warnings


def detect_seek_missing_donors(
    current_aggregates: dict[int, float],
    previous_aggregates: dict[int, float],
    sector_name: str,
    donor_names: dict[int, str],
    critical_donors: list[int] | None = None,
) -> list[Warning]:
    """
    Flag critical donors that had data in previous release but are missing now.

    Args:
        current_aggregates: {donor_code: value} for current release
        previous_aggregates: {donor_code: value} for previous release
        sector_name: "total", "health", or "agriculture" for messages
        donor_names: {donor_code: donor_name} for readable messages
        critical_donors: List of donor codes to check (defaults to MAJOR_DONORS)

    Returns:
        List of Warning objects for missing donors
    """
    warnings = []
    critical_donors = critical_donors or MAJOR_DONORS

    for donor in critical_donors:
        prev_val = previous_aggregates.get(donor, 0)
        curr_val = current_aggregates.get(donor, 0)

        # Had significant data before but now zero/missing
        if prev_val > 0 and curr_val == 0:
            donor_name = donor_names.get(donor, f"Donor {donor}")
            warnings.append(
                Warning(
                    level="high",
                    dataset="seek_sectors",
                    message=(
                        f"SEEK {sector_name}: {donor_name} has no data "
                        f"(had {prev_val:,.0f} in previous release)"
                    ),
                )
            )

    return warnings


def detect_seek_new_donors(
    current_aggregates: dict[int, float],
    previous_aggregates: dict[int, float],
    sector_name: str,
    donor_names: dict[int, str],
) -> list[Warning]:
    """
    Flag donors that are new in this release (not present in previous).

    Args:
        current_aggregates: {donor_code: value} for current release
        previous_aggregates: {donor_code: value} for previous release
        sector_name: "total", "health", or "agriculture" for messages
        donor_names: {donor_code: donor_name} for readable messages

    Returns:
        List of Warning objects for new donors (info level)
    """
    warnings = []

    current_donors = set(current_aggregates.keys())
    previous_donors = set(previous_aggregates.keys())
    new_donors = current_donors - previous_donors

    if new_donors:
        # Summarize rather than list each one
        new_names = [donor_names.get(d, str(d)) for d in sorted(new_donors)]
        if len(new_names) <= 5:
            names_str = ", ".join(new_names)
        else:
            names_str = f"{', '.join(new_names[:5])} and {len(new_names) - 5} others"

        warnings.append(
            Warning(
                level="info",
                dataset="seek_sectors",
                message=f"SEEK {sector_name}: New donors in this release: {names_str}",
            )
        )

    return warnings


def run_seek_validation(
    df: pd.DataFrame,
    previous_release: dict,
    donor_names: dict[int, str],
    health_codes: list[int] | None = None,
    agriculture_codes: list[int] | None = None,
    critical_donors: list[int] | None = None,
) -> list[Warning]:
    """
    Run all SEEK-style validation checks.

    This is the main entry point for SEEK anomaly detection.
    Compares current data against previous release for:
    - Total spending by donor
    - Health spending by donor
    - Agriculture spending by donor

    Args:
        df: DataFrame with purpose-code level data for current release
        previous_release: Previous release data from manifest
        donor_names: {donor_code: donor_name} mapping
        health_codes: Health purpose codes (defaults to config)
        agriculture_codes: Agriculture purpose codes (defaults to config)
        critical_donors: Donors to check for missing data (defaults to MAJOR_DONORS)

    Returns:
        List of Warning objects from all checks
    """
    warnings = []
    health_codes = health_codes or SEEK_HEALTH_PURPOSE_CODES
    agriculture_codes = agriculture_codes or SEEK_AGRICULTURE_PURPOSE_CODES
    critical_donors = critical_donors or MAJOR_DONORS

    # Compute current aggregates
    current_aggs = compute_sector_aggregates(
        df=df,
        health_codes=health_codes,
        agriculture_codes=agriculture_codes,
    )

    # Get previous aggregates (convert string keys back to int from JSON)
    prev_total = {
        int(k): v for k, v in previous_release.get("by_donor_total", {}).items()
    }
    prev_health = {
        int(k): v for k, v in previous_release.get("by_donor_health", {}).items()
    }
    prev_ag = {
        int(k): v for k, v in previous_release.get("by_donor_agriculture", {}).items()
    }

    # Run drift detection for each sector
    warnings.extend(
        detect_seek_donor_drift(
            current_aggs["by_donor_total"],
            prev_total,
            "total",
            donor_names,
        )
    )
    warnings.extend(
        detect_seek_donor_drift(
            current_aggs["by_donor_health"],
            prev_health,
            "health",
            donor_names,
        )
    )
    warnings.extend(
        detect_seek_donor_drift(
            current_aggs["by_donor_agriculture"],
            prev_ag,
            "agriculture",
            donor_names,
        )
    )

    # Check for missing critical donors
    warnings.extend(
        detect_seek_missing_donors(
            current_aggs["by_donor_total"],
            prev_total,
            "total",
            donor_names,
            critical_donors,
        )
    )
    warnings.extend(
        detect_seek_missing_donors(
            current_aggs["by_donor_health"],
            prev_health,
            "health",
            donor_names,
            critical_donors,
        )
    )
    warnings.extend(
        detect_seek_missing_donors(
            current_aggs["by_donor_agriculture"],
            prev_ag,
            "agriculture",
            donor_names,
            critical_donors,
        )
    )

    # Check for new donors (info level)
    warnings.extend(
        detect_seek_new_donors(
            current_aggs["by_donor_total"],
            prev_total,
            "total",
            donor_names,
        )
    )

    return warnings
