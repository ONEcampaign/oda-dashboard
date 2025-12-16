"""Anomaly detection for data validation (warnings, not hard gates)."""

import pandas as pd
from validation.models import Warning
from validation.config import ANOMALY_Z_SCORE_THRESHOLD, ANOMALY_Z_SCORE_HIGH


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

    if "donor_code" not in df.columns or "year" not in df.columns:
        return warnings

    for donor in df["donor_code"].unique():
        donor_data = df[df["donor_code"] == donor].copy()
        donor_name = (
            donor_data["donor_name"].iloc[0]
            if "donor_name" in donor_data.columns
            else str(donor)
        )

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

    # Compute current aggregates
    current_by_donor = df.groupby("donor_code")[value_column].sum()

    # Get donor names for messages
    donor_names = {}
    if "donor_name" in df.columns:
        donor_names = df.groupby("donor_code")["donor_name"].first().to_dict()

    previous_by_donor = previous_release["aggregates"].get("by_donor", {})

    for donor_str, prev_total in previous_by_donor.items():
        donor = int(donor_str)
        curr_total = current_by_donor.get(donor, 0)

        if prev_total == 0:
            continue

        pct_change = (curr_total - prev_total) / prev_total

        # Flag significant changes (>20% for medium, >40% for high)
        if abs(pct_change) > 0.20:
            level = "high" if abs(pct_change) > 0.40 else "medium"
            donor_name = donor_names.get(donor, str(donor))
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
    major_donors: dict[int, str],
    value_column: str,
) -> list[Warning]:
    """
    Flag cases where we expect data but find gaps.

    Args:
        df: DataFrame to check
        major_donors: Dict of donor_code -> donor_name for critical donors
        value_column: Column to check for values

    Returns:
        List of warnings for missing data
    """
    warnings = []

    if "year" not in df.columns:
        return warnings

    latest_year = df["year"].max()

    for donor_code, donor_name in major_donors.items():
        # Check if donor exists in latest year
        donor_latest = df[
            (df["donor_code"] == donor_code) & (df["year"] == latest_year)
        ]

        # Check if had data in previous year
        donor_prev = df[
            (df["donor_code"] == donor_code) & (df["year"] == latest_year - 1)
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


def detect_new_or_removed_codes(
    df: pd.DataFrame,
    previous_release: dict,
) -> list[Warning]:
    """
    Flag new or removed donor/recipient/indicator codes.

    Args:
        df: Current DataFrame
        previous_release: Previous release data from manifest

    Returns:
        List of warnings for code changes
    """
    warnings = []

    if not previous_release:
        return warnings

    # Check donors
    if "donor_code" in df.columns:
        current_donors = set(int(x) for x in df["donor_code"].unique())
        previous_donors = set(previous_release.get("donors_present", []))

        new_donors = current_donors - previous_donors
        removed_donors = previous_donors - current_donors

        if new_donors:
            warnings.append(
                Warning(
                    level="info",
                    dataset="",
                    message=f"New donor codes: {sorted(new_donors)}",
                )
            )

        if removed_donors:
            warnings.append(
                Warning(
                    level="medium",
                    dataset="",
                    message=f"Removed donor codes: {sorted(removed_donors)}",
                )
            )

    # Check indicators
    if "indicator" in df.columns:
        current_indicators = set(df["indicator"].unique())
        previous_indicators = set(previous_release.get("indicators_present", []))

        new_indicators = current_indicators - previous_indicators
        removed_indicators = previous_indicators - current_indicators

        if new_indicators:
            warnings.append(
                Warning(
                    level="info",
                    dataset="",
                    message=f"New indicators: {sorted(new_indicators)}",
                )
            )

        if removed_indicators:
            warnings.append(
                Warning(
                    level="medium",
                    dataset="",
                    message=f"Removed indicators: {sorted(removed_indicators)}",
                )
            )

    # Check purpose codes (for sectors)
    if "purpose_code" in df.columns:
        current_codes = set(int(x) for x in df["purpose_code"].unique())
        previous_codes = set(previous_release.get("purpose_codes_present", []))

        new_codes = current_codes - previous_codes
        removed_codes = previous_codes - current_codes

        if new_codes:
            sample = sorted(new_codes)[:20]
            warnings.append(
                Warning(
                    level="info",
                    dataset="",
                    message=f"New purpose codes: {sample}{'...' if len(new_codes) > 20 else ''}",
                )
            )

        if removed_codes:
            sample = sorted(removed_codes)[:20]
            warnings.append(
                Warning(
                    level="medium",
                    dataset="",
                    message=f"Removed purpose codes: {sample}{'...' if len(removed_codes) > 20 else ''}",
                )
            )

    # Check sub-sector codes (for sectors_view)
    if "sub_sector_code" in df.columns:
        current_codes = set(int(x) for x in df["sub_sector_code"].dropna().unique())
        previous_codes = set(previous_release.get("sub_sector_codes_present", []))

        new_codes = current_codes - previous_codes
        removed_codes = previous_codes - current_codes

        if new_codes:
            warnings.append(
                Warning(
                    level="info",
                    dataset="",
                    message=f"New sub-sector codes: {sorted(new_codes)}",
                )
            )

        if removed_codes:
            warnings.append(
                Warning(
                    level="medium",
                    dataset="",
                    message=f"Removed sub-sector codes: {sorted(removed_codes)}",
                )
            )

    # Check sector names (for sectors_view)
    if "sector_name" in df.columns:
        current_sectors = set(df["sector_name"].dropna().unique())
        previous_sectors = set(previous_release.get("sectors_present", []))

        new_sectors = current_sectors - previous_sectors
        removed_sectors = previous_sectors - current_sectors

        if new_sectors:
            warnings.append(
                Warning(
                    level="info",
                    dataset="",
                    message=f"New sectors: {sorted(new_sectors)}",
                )
            )

        if removed_sectors:
            warnings.append(
                Warning(
                    level="high",
                    dataset="",
                    message=f"Removed sectors: {sorted(removed_sectors)}",
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

    if "indicator" not in df.columns or not previous_release:
        return warnings

    previous_indicators = set(previous_release.get("indicators_present", []))

    for indicator in previous_indicators:
        indicator_data = df[df["indicator"] == indicator]

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


def detect_agency_drift(
    df: pd.DataFrame,
    previous_release: dict,
    value_column: str,
) -> list[Warning]:
    """
    Flag significant changes in multilateral agency allocations.

    Args:
        df: Current DataFrame
        previous_release: Previous release data
        value_column: Column to compare

    Returns:
        List of warnings for agency drift
    """
    warnings = []

    if "agency_code" not in df.columns or not previous_release:
        return warnings

    current_by_agency = df.groupby("agency_code")[value_column].sum()
    previous_by_agency = previous_release.get("aggregates", {}).get("by_agency", {})

    for agency_str, prev_total in previous_by_agency.items():
        agency = int(agency_str)
        curr_total = current_by_agency.get(agency, 0)

        if prev_total == 0:
            continue

        pct_change = (curr_total - prev_total) / prev_total

        if abs(pct_change) > 0.20:
            level = "high" if abs(pct_change) > 0.40 else "medium"
            warnings.append(
                Warning(
                    level=level,
                    dataset="",
                    message=f"Agency {agency}: {pct_change:+.1%} vs previous release",
                )
            )

    return warnings


def detect_sector_drift(
    df: pd.DataFrame,
    previous_release: dict,
    value_column: str,
    donor_names: dict = None,
) -> list[Warning]:
    """
    Flag significant changes in sector allocations (overall and per-donor).

    Args:
        df: Current DataFrame
        previous_release: Previous release data
        value_column: Column to compare
        donor_names: Optional dict mapping donor_code to donor_name

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
    if "donor_code" not in df.columns:
        return warnings

    donor_names = donor_names or {}
    current_by_donor_sector = df.groupby(["donor_code", "sector_name"], observed=True)[
        value_column
    ].sum()
    previous_by_donor_sector = previous_release.get("aggregates", {}).get(
        "by_donor_sector", {}
    )

    for key, prev_total in previous_by_donor_sector.items():
        if "|" not in key:
            continue

        donor_str, sector = key.split("|", 1)
        donor = int(donor_str)
        curr_total = current_by_donor_sector.get((donor, sector), 0)

        if prev_total == 0:
            continue

        pct_change = (curr_total - prev_total) / prev_total

        # Higher threshold for donor-sector (40%/60%) since there's more variance
        if abs(pct_change) > 0.40:
            level = "high" if abs(pct_change) > 0.60 else "medium"
            donor_label = donor_names.get(donor, f"Donor {donor}")
            warnings.append(
                Warning(
                    level=level,
                    dataset="",
                    message=f"{donor_label} - {sector}: {pct_change:+.1%} vs previous release",
                )
            )

    return warnings
