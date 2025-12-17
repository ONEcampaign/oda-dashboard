"""Data fetching utilities for SEEK-style validation using purpose-code level data."""

import pandas as pd

from validation.config import (
    SEEK_HEALTH_PURPOSE_CODES,
    SEEK_AGRICULTURE_PURPOSE_CODES,
)


def fetch_seek_sectors_data(
    start_year: int | None = None,
    end_year: int | None = None,
    currency: str = "USD",
    base_year: int | None = None,
) -> pd.DataFrame:
    """
    Fetch purpose-code level sector data from SEEK functions.

    Uses seek/sectors.py pipeline to get raw purpose code data
    for validation comparisons.

    Args:
        start_year: Start year for data (defaults to SEEK module default)
        end_year: End year for data (defaults to SEEK module default)
        currency: Currency for values (default: USD)
        base_year: Base year for constant prices (None = current prices)

    Returns:
        DataFrame with purpose-code level data by donor
    """
    # Import here to avoid circular imports and ensure fresh data
    from src.data.partners.seek.sectors import (
        START_YEAR as SEEK_START_YEAR,
        END_YEAR as SEEK_END_YEAR,
        get_bilateral_disbursements_by_sector,
        get_imputed_multilateral_disbursements_by_sector,
    )

    start_year = start_year or SEEK_START_YEAR
    end_year = end_year or SEEK_END_YEAR

    # Get bilateral data at purpose level
    bilateral = get_bilateral_disbursements_by_sector(
        start_year=start_year,
        end_year=end_year,
        currency=currency,
        base_year=base_year,
        group_by="purpose",
        by_recipient=False,
    ).assign(indicator="Bilateral")

    # Get imputed multilateral data at purpose level
    multilateral = get_imputed_multilateral_disbursements_by_sector(
        start_year=start_year,
        end_year=end_year,
        currency=currency,
        base_year=base_year,
        group_by="purpose",
        by_recipient=False,
    ).assign(indicator="Multilateral")

    # Combine bilateral and multilateral
    df = pd.concat([bilateral, multilateral], ignore_index=True)

    return df


def filter_by_purpose_codes(
    df: pd.DataFrame,
    purpose_codes: list[int],
    purpose_column: str = "purpose_code",
) -> pd.DataFrame:
    """
    Filter dataframe to rows matching given purpose codes.

    Args:
        df: DataFrame with purpose_code column
        purpose_codes: List of purpose codes to include
        purpose_column: Name of column containing purpose codes

    Returns:
        Filtered DataFrame
    """
    return df[df[purpose_column].isin(purpose_codes)]


def aggregate_by_donor(
    df: pd.DataFrame,
    value_column: str = "value",
) -> dict[int, float]:
    """
    Aggregate values by donor.

    Args:
        df: DataFrame with donor_code and value columns
        value_column: Name of column containing values

    Returns:
        Dict mapping donor_code to total value
    """
    return df.groupby("donor_code")[value_column].sum().to_dict()


def get_latest_year_data(
    df: pd.DataFrame,
    year_column: str = "year",
) -> pd.DataFrame:
    """
    Filter to most recent year in data.

    Args:
        df: DataFrame with year column
        year_column: Name of column containing year

    Returns:
        DataFrame filtered to latest year only
    """
    if len(df) == 0:
        return df
    latest = df[year_column].max()
    return df[df[year_column] == latest]


def get_donor_names(df: pd.DataFrame) -> dict[int, str]:
    """
    Extract donor code to name mapping from dataframe.

    Args:
        df: DataFrame with donor_code and donor_name columns

    Returns:
        Dict mapping donor_code to donor_name
    """
    if "donor_name" not in df.columns:
        return {}
    return df.groupby("donor_code")["donor_name"].first().to_dict()


def compute_sector_aggregates(
    df: pd.DataFrame,
    health_codes: list[int] | None = None,
    agriculture_codes: list[int] | None = None,
    value_column: str = "value",
) -> dict:
    """
    Compute SEEK-style aggregates for validation.

    Computes totals by donor for:
    - All sectors combined
    - Health sector (filtered by purpose codes)
    - Agriculture sector (filtered by purpose codes)

    Args:
        df: DataFrame with purpose-code level data
        health_codes: Health purpose codes (defaults to config)
        agriculture_codes: Agriculture purpose codes (defaults to config)
        value_column: Name of value column

    Returns:
        Dict with latest_year, by_donor_total, by_donor_health, by_donor_agriculture
    """
    health_codes = health_codes or SEEK_HEALTH_PURPOSE_CODES
    agriculture_codes = agriculture_codes or SEEK_AGRICULTURE_PURPOSE_CODES

    # Filter to latest year
    latest_df = get_latest_year_data(df)
    latest_year = int(latest_df["year"].iloc[0]) if len(latest_df) > 0 else None

    # Total by donor (all sectors)
    total_by_donor = aggregate_by_donor(latest_df, value_column)

    # Health by donor
    health_df = filter_by_purpose_codes(latest_df, health_codes)
    health_by_donor = aggregate_by_donor(health_df, value_column)

    # Agriculture by donor
    ag_df = filter_by_purpose_codes(latest_df, agriculture_codes)
    ag_by_donor = aggregate_by_donor(ag_df, value_column)

    return {
        "latest_year": latest_year,
        "by_donor_total": total_by_donor,
        "by_donor_health": health_by_donor,
        "by_donor_agriculture": ag_by_donor,
    }
