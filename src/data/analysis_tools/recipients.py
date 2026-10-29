"""Testable frame logic for the recipients loader, which Python cannot import by name.

The view reads DAC2A Part I (developing countries) straight from the bulk table. The
indicator queries sum Part I and Part II (countries in transition), and Part II is Official
Aid, not ODA. It is absent from the "Developing countries, Total" (10100) figure, so
countries that were Part II would push the sum of countries above it.
"""

from collections.abc import Iterable

import duckdb
import oda_data as oda
import pandas as pd

from src.data.analysis_tools.naming import (
    apply_name_overrides,
    canonical_recipient_names,
    map_config_values,
)
from src.data.analysis_tools.oda import (
    ProvenanceLog,
    scan_table,
    scanned_release,
    to_repo_frame,
)
from src.data.analysis_tools.transformations import get_crs_recipient_classifications
from src.data.config import (
    DAC2A_RECIPIENT_AGGREGATES,
    DAC2A_RECIPIENT_NAMES,
    ODA_ELIGIBLE,
    RECIPIENT_NAME_OVERRIDES,
)

DAC2A: str = "dac2a"
CRS: str = "crs"
# Raw DAC2A codes: Part I of the DAC list (developing countries), and current prices.
DAC2A_PART_I: int = 1
DAC2A_CURRENT_PRICES: str = "A"
_DAC2A_COLUMNS: frozenset[str] = frozenset(
    {
        "donor_code",
        "recipient_code",
        "year",
        "part_code",
        "aidtype_code",
        "data_type_code",
        "value",
    }
)

# The code of "ODA eligible countries" (DAC2A "Developing countries, Total").
ODA_ELIGIBLE_CODE: int = next(
    code for code, name in RECIPIENT_NAME_OVERRIDES.items() if name == ODA_ELIGIBLE
)
# Float noise lets the countries sum above ODA eligible countries by this many USD millions.
RECIPIENT_SUM_TOLERANCE: float = 0.001


def read_dac2a_part_i(
    *,
    lines: dict[int, str],
    years: Iterable[int],
    providers: Iterable[int],
    recipients: Iterable[int],
    provenance: ProvenanceLog | None = None,
) -> pd.DataFrame:
    """Read DAC2A Part I lines in current USD from the bulk table.

    oda.query has no part filter, so this reads the scanned table with DuckDB instead.

    Args:
        lines: DAC2A aid type code -> indicator name, e.g. {206: "Bilateral"}.
        years: Years to read.
        providers: Donor codes to read.
        recipients: Recipient codes to read.
        provenance: Log to record the DAC2A release in.

    Returns:
        One row per donor, recipient, year and indicator_name, in USD millions, with
        oda-data's donor and recipient names and the repo's column names.

    Raises:
        ValueError: If the table lacks a column this read needs, or years has gaps.
    """
    table = scan_table(DAC2A)
    missing = sorted(_DAC2A_COLUMNS - set(table.columns))
    if missing:
        raise ValueError(f"The DAC2A bulk table has no columns {missing}")

    years = sorted(set(years))
    if years != list(range(years[0], years[-1] + 1)):
        raise ValueError(f"DAC2A years must be a contiguous range, got {years}")
    raw = duckdb.execute(
        """
        SELECT donor_code AS provider, recipient_code AS recipient, year,
               aidtype_code AS line, SUM(value) AS value
        FROM read_parquet($path)
        WHERE part_code = $part AND data_type_code = $prices
          AND list_contains($lines, aidtype_code)
          AND year BETWEEN $first AND $last
          AND list_contains($providers, donor_code)
          AND list_contains($recipients, recipient_code)
        GROUP BY ALL
        """,
        {
            "path": str(table.path),
            "part": DAC2A_PART_I,
            "prices": DAC2A_CURRENT_PRICES,
            "lines": sorted(lines),
            "first": years[0],
            "last": years[-1],
            "providers": sorted(set(providers)),
            "recipients": sorted(set(recipients)),
        },
    ).df()

    if provenance is not None:
        provenance.record_table(DAC2A, scanned_release(table))

    named = oda.add_names(raw, table=DAC2A)
    unnamed = named.loc[
        named["provider_name"].isna() | named["recipient_name"].isna(),
        ["provider", "recipient"],
    ].drop_duplicates()
    if not unnamed.empty:
        raise ValueError(
            f"oda_data has no name for DAC2A codes {unnamed.values.tolist()[:10]}"
        )

    named = to_repo_frame(named.drop(columns="line_name", errors="ignore"))
    return named.assign(
        indicator_name=map_config_values(named["line"], lines, what="DAC2A lines")
    ).drop(columns="line")


def canonical_recipients(df: pd.DataFrame) -> pd.DataFrame:
    """Give DAC2A recipients the recipients view's display names.

    Args:
        df: DAC2A rows with recipient_code and recipient_name.

    Returns:
        The rows, with canonical names, then the view's names for its groups and for the
        countries the bulk file spells differently.

    Raises:
        ValueError: If a recipient has no code, or two recipient codes end up with one name,
            which the pivot on recipient_name would otherwise merge silently.
    """
    if df["recipient_code"].isna().any():
        raise ValueError("DAC2A rows without a recipient code")

    df = canonical_recipient_names(df)
    df = apply_name_overrides(
        df, DAC2A_RECIPIENT_AGGREGATES | DAC2A_RECIPIENT_NAMES, "recipient"
    )

    codes_per_name = df.groupby("recipient_name", observed=True)[
        "recipient_code"
    ].nunique()
    clashes = codes_per_name[codes_per_name > 1].index.tolist()
    if clashes:
        raise ValueError(f"Recipient names shared by more than one code: {clashes}")

    return df


def aggregate_recipient_names(df: pd.DataFrame) -> list[str]:
    """List the DAC2A recipient groups in the data, e.g. "Africa", alphabetically.

    Args:
        df: Canonical DAC2A rows with recipient_code and recipient_name.

    Returns:
        The names of the rows whose code is in DAC2A_RECIPIENT_AGGREGATES.
    """
    names = df.loc[
        df["recipient_code"].isin(DAC2A_RECIPIENT_AGGREGATES), "recipient_name"
    ]
    return sorted(names.unique())


def check_recipient_sums(df: pd.DataFrame) -> None:
    """Check that no donor's countries sum to more than its ODA eligible countries total.

    The total may exceed the countries: some donors report part of their ODA against the
    total only (Saudi Arabia, per oda-data's DAC2A notes).

    Args:
        df: DAC2A rows in USD millions with donor_code, recipient_code, year,
            indicator_name and value.

    Raises:
        ValueError: If a donor, year and indicator's countries exceed the total by more than
            RECIPIENT_SUM_TOLERANCE.
    """
    keys = ["donor_code", "year", "indicator_name"]
    countries = (
        df.loc[~df["recipient_code"].isin(DAC2A_RECIPIENT_AGGREGATES)]
        .groupby(keys, observed=True)["value"]
        .sum()
    )
    total = (
        df.loc[df["recipient_code"] == ODA_ELIGIBLE_CODE]
        .groupby(keys, observed=True)["value"]
        .sum()
        .reindex(countries.index, fill_value=0.0)
    )
    overshoot = countries - total
    bad = overshoot[overshoot > RECIPIENT_SUM_TOLERANCE]
    if not bad.empty:
        worst = bad.sort_values(ascending=False).head(5).round(3).to_dict()
        raise ValueError(
            f"{len(bad):,} donor-years where countries sum above {ODA_ELIGIBLE} "
            f"(USD millions), e.g. {worst}"
        )


def read_ldc_members(
    *,
    years: Iterable[int],
    recipients: Iterable[int],
    provenance: ProvenanceLog | None = None,
) -> dict[int, str]:
    """Find the Least Developed Countries among the recipients, as the CRS views do.

    Membership is resolvekit's UN LDC list, a snapshot of the current members applied to
    every year, matched to DAC recipient codes through the CRS's ISO3 codes.

    Args:
        years: Years of the CRS to match codes in.
        recipients: Recipient codes to look among.
        provenance: Log to record the CRS release in.

    Returns:
        {recipient_code: name} for the LDCs.

    Raises:
        ValueError: If no recipient is an LDC.
    """
    _, members = get_crs_recipient_classifications(
        sorted(set(years)), recipients=sorted(set(recipients))
    )
    if not members:
        raise ValueError("No recipient matched resolvekit's LDC list")
    if provenance is not None:
        provenance.record_table(CRS, scanned_release(scan_table(CRS)))
    return members
