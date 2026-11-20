"""Bilateral plus imputed multilateral ODA by DAC member, year and broad sector.

The definition is the sectors view's: CRS bilateral ODA (oecd.crs.bilateral_oda, gross
disbursements, which leaves out private sector instruments from CRS_PSI_START_YEAR) to every
CRS recipient, plus imputed multilateral spending, labelled through the shared sector lookup
and converted per donor-year with the views' factors.
"""

from collections.abc import Iterable

import oda_data as oda
import pandas as pd

from src.data.analysis_tools.imputations import iter_imputed_multilateral
from src.data.analysis_tools.oda import ProvenanceLog, run_query
from src.data.analysis_tools.sectors import (
    BILATERAL_ODA,
    CRS_BASIS,
    assign_sub_sector,
    sector_names,
)
from src.data.config import CRS_RECIPIENTS, DAC_COUNTRIES
from src.data.topic_page.common import to_usd_constant

SECTOR_KEYS: list[str] = ["year", "donor_code", "sector"]


def _sum_by_sector(df: pd.DataFrame) -> pd.DataFrame:
    """Label rows with their broad sector and sum them per year, donor and sector."""
    df = assign_sub_sector(df)
    df["sector"] = sector_names(df["sub_sector"])
    return df.groupby(SECTOR_KEYS, as_index=False)["value"].sum()


def sector_totals(
    ctx: oda.Context,
    *,
    years: Iterable[int],
    base_year: int,
    provenance: ProvenanceLog,
) -> pd.DataFrame:
    """Read bilateral plus imputed multilateral ODA per DAC member, year and broad sector.

    Args:
        ctx: From open_context.
        years: Years to read.
        base_year: Base year of the constant prices.
        provenance: Log to record every read and the conversion factors in.

    Returns:
        year, donor_code, sector and value, in constant USD millions of base_year.
    """
    years = list(years)
    providers = list(DAC_COUNTRIES)
    bilateral = run_query(
        ctx,
        BILATERAL_ODA,
        provenance=provenance,
        years=years,
        providers=providers,
        recipients=list(CRS_RECIPIENTS),
        by=["provider", "sector", "year"],
        basis=CRS_BASIS,
    )
    parts = [_sum_by_sector(bilateral)]
    parts.extend(
        _sum_by_sector(raw)
        for raw in iter_imputed_multilateral(
            ctx, years=years, providers=providers, provenance=provenance
        )
    )
    current = (
        pd.concat(parts, ignore_index=True)
        .groupby(SECTOR_KEYS, as_index=False)["value"]
        .sum()
    )
    return to_usd_constant(current, base_year=base_year, provenance=provenance)
