"""The EU27 + EU Institutions bloc: weighting the institutions so members are not counted twice.

EU member states fund much of the EU Institutions' (918) spending through their core
contributions, which DAC1 records on line 2102 of each member. Summing members and the
institutions as they stand would count that money twice, once as the members' contributions
and again as the institutions' spending. The institutions' figures are therefore scaled by
the share of their total ODA that member contributions do not fund:

    weight = 1 - sum(EU27 line 2102) / 918 total ODA

per year and basis. This is the calculation of oda-data 2.x's
``get_eui_plus_bilateral_providers_indicator``, which oda-data 3.0 does not provide.
"""

from collections.abc import Iterable

import oda_data as oda
import pandas as pd

from src.data.analysis_tools.oda import ProvenanceLog, run_query
from src.data.config import EU_COUNTRIES, EU_INSTITUTIONS_CODE

# DAC1 line for members' core contributions to the EU institutions.
EU_INSTITUTIONS_CONTRIBUTIONS_LINE: int = 2102


def eu_institutions_weight(
    contributions: pd.DataFrame, institutions_total: pd.DataFrame
) -> dict[int, float]:
    """Compute the share of the institutions' ODA not funded by member contributions.

    Args:
        contributions: Members' line 2102 rows, with year and value.
        institutions_total: 918's total ODA rows, with year and value.

    Returns:
        The weight for every year in institutions_total.

    Raises:
        ValueError: If a year has a total but no contributions (or the reverse), or a
            weight falls outside [0, 1].
    """
    member_sum = contributions.groupby("year")["value"].sum()
    total = institutions_total.groupby("year")["value"].sum()

    unmatched = sorted(set(member_sum.index) ^ set(total.index))
    if unmatched:
        raise ValueError(
            "EU Institutions weight: member contributions and the institutions' total "
            f"cover different years: {unmatched}"
        )

    weight = 1 - member_sum / total
    out_of_range = weight[(weight < 0) | (weight > 1) | weight.isna()]
    if not out_of_range.empty:
        raise ValueError(
            f"EU Institutions weight outside [0, 1]: {out_of_range.round(4).to_dict()}"
        )
    return {int(year): float(w) for year, w in weight.items()}


def eui_weights(
    ctx: oda.Context,
    years: Iterable[int],
    *,
    basis: str,
    provenance: ProvenanceLog | None = None,
) -> dict[int, float]:
    """Read the EU Institutions weight for each year on one basis.

    Args:
        ctx: From oda.open_context.
        years: Years to compute the weight for.
        basis: oda-data basis, e.g. "net_disbursement" or "grant_equivalent". It must match
            the basis of the figures the weight is applied to.
        provenance: Log to record the queries' tables and versions in.

    Returns:
        The weight per year.

    Raises:
        ValueError: If a requested year is missing from either read, or see
            eu_institutions_weight.
    """
    years = sorted(set(years))
    contributions = run_query(
        ctx,
        "oecd.dac1.lines",
        provenance=provenance,
        lines=[EU_INSTITUTIONS_CONTRIBUTIONS_LINE],
        years=years,
        providers=list(EU_COUNTRIES),
        basis=basis,
        by=["provider", "year", "line"],
    )
    institutions_total = run_query(
        ctx,
        "oecd.dac1.total_oda",
        provenance=provenance,
        years=years,
        providers=[EU_INSTITUTIONS_CODE],
        basis=basis,
    )
    weights = eu_institutions_weight(contributions, institutions_total)

    missing = sorted(set(years) - set(weights))
    if missing:
        raise ValueError(f"EU Institutions weight ({basis}): no data for {missing}")
    return weights


def weight_eu_institutions(df: pd.DataFrame, weights: dict[int, float]) -> pd.DataFrame:
    """Scale the EU Institutions' rows by their weight for the year.

    Args:
        df: Long frame with donor_code, year and value, all on the basis of the weights.
        weights: From eui_weights.

    Returns:
        A copy of df with 918's values weighted; other donors are unchanged.

    Raises:
        ValueError: If an EU Institutions row falls in a year with no weight.
    """
    is_eui = df["donor_code"] == EU_INSTITUTIONS_CODE
    unweighted = sorted(set(df.loc[is_eui, "year"]) - set(weights))
    if unweighted:
        raise ValueError(f"No EU Institutions weight for years {unweighted}")

    df = df.copy()
    df.loc[is_eui, "value"] = df.loc[is_eui, "value"] * df.loc[is_eui, "year"].map(
        weights
    )
    return df
