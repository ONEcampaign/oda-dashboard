"""Shared constants, reads and formatting for the topic page scripts.

The topic page publishes figures the dashboard views also publish, so it reads them the same
way: DAC1 Total ODA on the headline basis per member, converted per donor with the views'
factor table, and the DAC countries total summed from its members.
"""

import json
from collections.abc import Iterable
from pathlib import Path

import oda_data as oda
import pandas as pd

from src.data.analysis_tools.oda import ProvenanceLog, run_query
from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_group_gni,
    build_gni_matched_group_totals,
    get_group_total,
    get_member_gni,
)
from src.data.config import DAC_COUNTRIES, DAC_COUNTRIES_NAME

LONG_START_YEAR: int = 2000
START_YEAR: int = 2010
# oda-data 3.0's Multisystem, which imputed multilateral spending comes from, starts here.
SECTORS_START_YEAR: int = 2011
SHORT_START_YEAR: int = 2015
LATEST_YEAR_AGG: int = 2025
LATEST_YEAR_DETAIL: int = 2024
CONSTANT_YEAR: int = 2025

BILLION: float = 1e9
# Decimal places of the USD million amounts the chart CSVs publish unformatted.
AMOUNT_DECIMALS: int = 6
UNITS_PER_MILLION: float = 1e6
# The UN target for ODA as a share of GNI.
ODA_GNI_TARGET: float = 0.007

TOTAL_ODA_INDICATOR: str = "oecd.dac1.total_oda"
DONOR_KEYS: list[str] = ["donor_name", "year"]


def _format(series: pd.Series, template: str) -> pd.Series:
    """Format a numeric series as strings with a str.format template.

    Raises:
        ValueError: If the series is not numeric.
    """
    if not pd.api.types.is_numeric_dtype(series):
        raise ValueError(f"Expected a numeric series, got {series.dtype}")
    return series.map(template.format)


def format_percentage(series: pd.Series, decimals: int = 1) -> pd.Series:
    """Format shares where 1 means 100%, e.g. 0.1234 -> "12.3%"."""
    return _format(series, f"{{:,.{decimals}%}}")


def format_billions(series: pd.Series, decimals: int = 1) -> pd.Series:
    """Format absolute values in billions with thousands separators, e.g. 1.5e9 -> "1.5"."""
    return _format(series / BILLION, f"{{:,.{decimals}f}}")


def add_change(
    df: pd.DataFrame, grouper: list | str | None = None, as_formatted_str: bool = False
) -> pd.DataFrame:
    """Add the change in value from the previous row of each group, as pct_change.

    Args:
        df: Frame sorted by year within each group, with a value column.
        grouper: Columns identifying a series. Defaults to donor_code and indicator.
        as_formatted_str: Format the change as "12.3%", empty for the first year.

    Returns:
        The frame with pct_change added.
    """
    if grouper is None:
        grouper = ["donor_code", "indicator"]

    df["pct_change"] = df.groupby(grouper)["value"].pct_change()

    if not as_formatted_str:
        return df

    df["pct_change"] = format_percentage(df["pct_change"], decimals=1).replace(
        "nan%", ""
    )

    return df


def update_key_number(path: Path, new_dict: dict) -> None:
    """Merge new_dict into the key numbers JSON at path, creating the file if needed."""
    data = json.loads(path.read_text()) if path.exists() else {}
    data.update(new_dict)
    path.write_text(json.dumps(data, indent=4))


def df_to_key_number(
    df: pd.DataFrame,
    indicator_name: str,
    id_column: str,
    value_columns: str | list[str],
) -> dict:
    """Turn rows into {indicator_name: {id: {column: value as str}}} for the key numbers."""
    if isinstance(value_columns, str):
        value_columns = [value_columns]

    return {
        indicator_name: df.set_index(id_column)[value_columns]
        .astype(str)
        .to_dict(orient="index")
    }


def sort_dac_first(df: pd.DataFrame) -> pd.DataFrame:
    """Move the DAC countries rows to the top, keeping the order within each part."""
    is_dac = df["name"] == DAC_COUNTRIES_NAME
    return pd.concat([df[is_dac], df[~is_dac]], ignore_index=True)


def read_total_oda(
    ctx: oda.Context,
    *,
    years: Iterable[int],
    providers: Iterable[int],
    provenance: ProvenanceLog,
) -> pd.DataFrame:
    """Read each provider's Total ODA on the headline basis, as the financing view does.

    Net flows before 2018, grant equivalents from then on.

    Args:
        ctx: From open_context.
        years: Years to read.
        providers: Donor codes to read.
        provenance: Log to record the DAC1 release in.

    Returns:
        donor_code, donor_name, year and value, in current USD millions.
    """
    return run_query(
        ctx,
        TOTAL_ODA_INDICATOR,
        provenance=provenance,
        years=list(years),
        providers=list(providers),
    )[["donor_code", "donor_name", "year", "value"]]


def to_usd_constant(
    df: pd.DataFrame, *, base_year: int, provenance: ProvenanceLog
) -> pd.DataFrame:
    """Convert individual donors' current USD values to constant USD of base_year.

    Uses the views' per donor-year factors, so the topic page and the views agree.

    Args:
        df: Long frame in current USD millions, with donor_code, year and value.
        base_year: Base year of the constant prices.
        provenance: Log to record the DAC1 release of the factors in.

    Returns:
        The same rows, with value in constant USD millions.
    """
    converted = add_currencies_and_prices(
        df, base_year=base_year, provenance=provenance
    )
    constant = converted.loc[
        (converted["currency"] == "USD") & (converted["price"] == "constant")
    ]
    if len(constant) != len(df):
        raise ValueError("The constant USD conversion changed the number of rows")
    return constant.drop(columns=["currency", "price"]).reset_index(drop=True)


def with_dac_total(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Append the DAC countries total, the sum of its members, as the views build it.

    Args:
        df: Long frame of individual donors with donor_code and value.
        group_cols: Columns identifying everything except the donor.

    Returns:
        df with the DAC countries rows appended; those have no donor_code.
    """
    total = get_group_total(
        df, DAC_COUNTRIES, group_cols=group_cols, group_name=DAC_COUNTRIES_NAME
    )
    return pd.concat([df, total], ignore_index=True)


def oda_gni_table(
    ctx: oda.Context,
    *,
    years: range,
    providers: Iterable[int],
    base_year: int,
    provenance: ProvenanceLog,
) -> pd.DataFrame:
    """Total ODA and its share of GNI per donor and year, plus the DAC countries total.

    ODA/GNI follows the financing view: a member's ODA over its GNI in current USD, and for
    DAC countries the ODA of the members reporting GNI that year over their summed GNI.
    Donors with no GNI of their own (EU Institutions) get no ratio.

    Args:
        ctx: From open_context.
        years: Contiguous years to read.
        providers: Donor codes to read.
        base_year: Base year of oda_constant.
        provenance: Log to record every read in.

    Returns:
        donor_name, year, oda_current, oda_constant (USD millions), oda_gni (a fraction)
        and gap_current, how far the ODA in that ratio falls short of ODA_GNI_TARGET of GNI
        (current USD millions, negative when above it).
    """
    current = read_total_oda(
        ctx, years=years, providers=providers, provenance=provenance
    )
    constant = to_usd_constant(current, base_year=base_year, provenance=provenance)
    table = (
        with_dac_total(current, ["year"])
        .rename(columns={"value": "oda_current"})[[*DONOR_KEYS, "oda_current"]]
        .merge(
            with_dac_total(constant, ["year"]).rename(
                columns={"value": "oda_constant"}
            )[[*DONOR_KEYS, "oda_constant"]],
            on=DONOR_KEYS,
            how="left",
            validate="1:1",
        )
    )

    member_gni = get_member_gni(ctx, years[0], years[-1], provenance=provenance)
    table = table.merge(
        add_group_gni(member_gni), on=DONOR_KEYS, how="left", validate="1:1"
    ).merge(
        build_gni_matched_group_totals(current, member_gni, ["year"]),
        on=DONOR_KEYS,
        how="left",
        validate="1:1",
    )
    numerator = table["gni_matched_value"].fillna(table["oda_current"])
    # Unrounded, unlike safe_share: oda_gni_single_year_ts publishes 5 dp of a percent.
    table["oda_gni"] = numerator / table["gni"].where(table["gni"] != 0)
    table["gap_current"] = table["gni"] * ODA_GNI_TARGET - numerator
    return table.drop(columns=["gni", "gni_matched_value"])
