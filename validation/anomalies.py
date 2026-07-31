"""Anomaly detection for data validation (warnings, not hard gates)."""

import pandas as pd
from validation.models import Warning
from validation.config import ANOMALY_Z_SCORE_THRESHOLD, ANOMALY_Z_SCORE_HIGH

# Dimensions whose membership is compared release to release: the manifest key holding the
# previous values, the column holding the current ones, a label for the message, and how
# seriously to treat a value disappearing. A sector vanishing is worse than a donor doing so,
# because it means a whole slice of spending stopped being classified.
ENTITY_DIMENSIONS: tuple[tuple[str, str, str, str], ...] = (
    ("donors_present", "donor_name", "donors", "medium"),
    ("indicators_present", "indicator_name", "indicators", "medium"),
    ("sectors_present", "sector_name", "sectors", "high"),
    ("sub_sectors_present", "sub_sector_name", "sub-sectors", "medium"),
)

# How many values to name before summarising, so a long list stays readable but never looks
# like the whole story when it is not.
_SAMPLE_LIMIT = 20


def _sample(values: set[str]) -> str:
    """Render a set of names for a warning message, saying how many were left out."""
    shown = sorted(values)[:_SAMPLE_LIMIT]
    remainder = len(values) - len(shown)

    return f"{shown}" + (f" (+{remainder} more)" if remainder else "")


def detect_yoy_anomalies(
    df: pd.DataFrame,
    current_year: int,
    value_column: str,
) -> list[Warning]:
    """
    Flag donors/indicators where latest year deviates significantly
    from their historical year-over-year pattern.

    Args:
        df: DataFrame with historical data
        current_year: The latest year to check
        value_column: Column containing values

    Returns:
        List of warnings for anomalous changes
    """
    warnings = []

    if "donor_name" not in df.columns or "year" not in df.columns:
        return warnings

    for donor_name in df["donor_name"].dropna().unique():
        donor_data = df[df["donor_name"] == donor_name]

        # Get yearly totals
        yearly = donor_data.groupby("year")[value_column].sum().sort_index()

        if len(yearly) < 4:
            continue  # Not enough history

        # Compute historical YoY changes (excluding current year)
        historical = yearly[yearly.index < current_year]
        if len(historical) < 3:
            continue

        yoy_changes = historical.pct_change().dropna()
        if len(yoy_changes) < 2:
            continue

        mean_change = yoy_changes.mean()
        std_change = yoy_changes.std()

        # Skip if std is NA or zero (no variation to compare against)
        if pd.isna(std_change) or std_change == 0:
            continue

        # Current year's change
        if current_year not in yearly.index or (current_year - 1) not in yearly.index:
            continue

        prev_val = yearly[current_year - 1]
        curr_val = yearly[current_year]

        # Skip if previous value is NA or zero
        if pd.isna(prev_val) or prev_val == 0:
            continue

        current_change = (curr_val - prev_val) / prev_val
        z_score = (current_change - mean_change) / std_change

        if abs(z_score) > ANOMALY_Z_SCORE_THRESHOLD:
            level = "high" if abs(z_score) > ANOMALY_Z_SCORE_HIGH else "medium"
            warnings.append(
                Warning(
                    level=level,
                    dataset="",  # Will be set by caller
                    message=(
                        f"{donor_name}: {current_year} change is {current_change:+.1%} "
                        f"(typical: {mean_change:+.1%} ± {std_change:.1%}, z={z_score:.1f})"
                    ),
                )
            )

    return warnings


def detect_release_drift(
    df: pd.DataFrame,
    previous_release: dict,
    release_name: str,
    value_column: str,
) -> list[Warning]:
    """
    Compare aggregates between releases, flag significant differences.

    Args:
        df: Current DataFrame
        previous_release: Previous release data from manifest
        release_name: Name of previous release for message
        value_column: Column to compare

    Returns:
        List of warnings for significant drift
    """
    warnings = []

    if not previous_release or "aggregates" not in previous_release:
        return warnings

    current_by_donor = df.groupby("donor_name", observed=True)[value_column].sum()
    previous_by_donor = previous_release["aggregates"].get("by_donor", {})

    for donor_name, prev_total in previous_by_donor.items():
        curr_total = current_by_donor.get(donor_name, 0)

        if prev_total == 0:
            continue

        pct_change = (curr_total - prev_total) / prev_total

        # Flag significant changes (>20% for medium, >40% for high)
        if abs(pct_change) > 0.20:
            level = "high" if abs(pct_change) > 0.40 else "medium"
            warnings.append(
                Warning(
                    level=level,
                    dataset="",
                    message=f"{donor_name}: {pct_change:+.1%} vs {release_name}",
                )
            )

    return warnings


def detect_missing_expected_data(
    df: pd.DataFrame,
    major_donors: list[str],
    value_column: str,
) -> list[Warning]:
    """
    Flag cases where we expect data but find gaps.

    Args:
        df: DataFrame to check
        major_donors: Donor names that must have data
        value_column: Column to check for values

    Returns:
        List of warnings for missing data
    """
    warnings = []

    if "year" not in df.columns:
        return warnings

    latest_year = df["year"].max()

    for donor_name in major_donors:
        # Check if donor exists in latest year
        donor_latest = df[
            (df["donor_name"] == donor_name) & (df["year"] == latest_year)
        ]

        # Check if had data in previous year
        donor_prev = df[
            (df["donor_name"] == donor_name) & (df["year"] == latest_year - 1)
        ]

        # Had data last year but not this year
        if len(donor_prev) > 0 and len(donor_latest) == 0:
            warnings.append(
                Warning(
                    level="high",
                    dataset="",
                    message=f"{donor_name}: No data for {latest_year} (had data in {latest_year - 1})",
                )
            )
            continue

        # Has rows but all zeros
        if len(donor_latest) > 0:
            total = donor_latest[value_column].sum()
            if total == 0:
                warnings.append(
                    Warning(
                        level="high",
                        dataset="",
                        message=f"{donor_name}: All zeros for {latest_year}",
                    )
                )

    return warnings


def detect_new_or_removed_entities(
    df: pd.DataFrame,
    previous_release: dict,
) -> list[Warning]:
    """
    Flag donors, indicators, sectors or sub-sectors that appeared or disappeared.

    Args:
        df: Current DataFrame
        previous_release: Previous release data from manifest

    Returns:
        List of warnings, one per dimension that gained or lost values
    """
    warnings = []

    if not previous_release:
        return warnings

    for presence_key, column, label, removed_level in ENTITY_DIMENSIONS:
        if column not in df.columns:
            continue

        current = set(str(x) for x in df[column].dropna().unique())
        previous = set(str(x) for x in previous_release.get(presence_key, []))

        if new := current - previous:
            warnings.append(
                Warning(
                    level="info",
                    dataset="",
                    message=f"New {label}: {_sample(new)}",
                )
            )

        # A disappearance is the serious direction: it means a slice of the data silently
        # stopped being published.
        if removed := previous - current:
            warnings.append(
                Warning(
                    level=removed_level,
                    dataset="",
                    message=f"Removed {label}: {_sample(removed)}",
                )
            )

    return warnings


def detect_row_count_change(
    current_count: int,
    previous_count: int,
    dataset: str,
    threshold: float = 0.15,
) -> list[Warning]:
    """
    Flag significant changes in row count.

    Args:
        current_count: Current number of rows
        previous_count: Previous number of rows
        dataset: Dataset name for message
        threshold: Percentage change threshold (default 15%)

    Returns:
        List of warnings if change exceeds threshold
    """
    warnings = []

    if previous_count == 0:
        return warnings

    pct_change = (current_count - previous_count) / previous_count

    if abs(pct_change) > threshold:
        level = "high" if abs(pct_change) > 0.30 else "medium"
        warnings.append(
            Warning(
                level=level,
                dataset=dataset,
                message=f"Row count: {previous_count:,} -> {current_count:,} ({pct_change:+.1%})",
            )
        )

    return warnings


def detect_indicator_coverage_gaps(
    df: pd.DataFrame,
    previous_release: dict,
    value_column: str,
) -> list[Warning]:
    """
    Flag indicators that had data before but are now empty.

    Args:
        df: Current DataFrame
        previous_release: Previous release data
        value_column: Column to check for values

    Returns:
        List of warnings for coverage gaps
    """
    warnings = []

    if "indicator_name" not in df.columns or not previous_release:
        return warnings

    previous_indicators = set(previous_release.get("indicators_present", []))

    for indicator in previous_indicators:
        indicator_data = df[df["indicator_name"] == indicator]

        if len(indicator_data) == 0:
            warnings.append(
                Warning(
                    level="high",
                    dataset="",
                    message=f"Indicator '{indicator}' has no data (was present in previous release)",
                )
            )
        elif indicator_data[value_column].sum() == 0:
            warnings.append(
                Warning(
                    level="medium",
                    dataset="",
                    message=f"Indicator '{indicator}' is all zeros",
                )
            )

    return warnings


def detect_sector_drift(
    df: pd.DataFrame,
    previous_release: dict,
    value_column: str,
) -> list[Warning]:
    """
    Flag significant changes in sector allocations (overall and per-donor).

    Args:
        df: Current DataFrame
        previous_release: Previous release data
        value_column: Column to compare

    Returns:
        List of warnings for sector drift
    """
    warnings = []

    if "sector_name" not in df.columns or not previous_release:
        return warnings

    # Overall sector drift
    current_by_sector = df.groupby("sector_name", observed=True)[value_column].sum()
    previous_by_sector = previous_release.get("aggregates", {}).get("by_sector", {})

    for sector, prev_total in previous_by_sector.items():
        curr_total = current_by_sector.get(sector, 0)

        if prev_total == 0:
            continue

        pct_change = (curr_total - prev_total) / prev_total

        if abs(pct_change) > 0.20:
            level = "high" if abs(pct_change) > 0.40 else "medium"
            warnings.append(
                Warning(
                    level=level,
                    dataset="",
                    message=f"Sector '{sector}': {pct_change:+.1%} vs previous release",
                )
            )

    # Donor-sector drift (catches individual donor problems masked by totals)
    if "donor_name" not in df.columns:
        return warnings

    current_by_donor_sector = df.groupby(["donor_name", "sector_name"], observed=True)[
        value_column
    ].sum()
    previous_by_donor_sector = previous_release.get("aggregates", {}).get(
        "by_donor_sector", {}
    )

    for key, prev_total in previous_by_donor_sector.items():
        if "|" not in key:
            continue

        donor_name, sector = key.split("|", 1)
        curr_total = current_by_donor_sector.get((donor_name, sector), 0)

        if prev_total == 0:
            continue

        pct_change = (curr_total - prev_total) / prev_total

        # Higher threshold for donor-sector (40%/60%) since there's more variance
        if abs(pct_change) > 0.40:
            level = "high" if abs(pct_change) > 0.60 else "medium"
            warnings.append(
                Warning(
                    level=level,
                    dataset="",
                    message=f"{donor_name} - {sector}: {pct_change:+.1%} vs previous release",
                )
            )

    return warnings
