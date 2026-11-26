"""ODA to Ukraine from DAC members: bilateral plus imputed multilateral, by year.

Each year comes from one basis. Bilateral ODA is DAC2A net flows (line 206) before
GRANT_EQUIVALENT_START_YEAR and CRS grant equivalents from then on. Imputed multilateral is
DAC2A net flows (line 106) throughout. DAC2A is read as the recipients view reads it (Part I),
so the years before GRANT_EQUIVALENT_START_YEAR match that view's Ukraine figures.
"""

import oda_data as oda
import pandas as pd

from src.data.analysis_tools.oda import ProvenanceLog, open_context, run_query
from src.data.analysis_tools.recipients import read_dac2a_part_i
from src.data.config import (
    DAC_COUNTRIES,
    DAC_COUNTRIES_NAME,
    GRANT_EQUIVALENT_START_YEAR,
    IMPUTED_MULTILATERAL,
    PATHS,
    RECIPIENTS_LINES,
    logger,
)
from src.data.topic_page.common import (
    CONSTANT_YEAR,
    LATEST_YEAR_DETAIL,
    PRE_INVASION_YEAR,
    SHORT_START_YEAR,
    to_usd_constant,
    with_dac_total,
)

UKRAINE_CODE: int = 85
UKRAINE_NAME: str = "Ukraine"
CRS_BILATERAL_ODA: str = "oecd.crs.bilateral_oda"
GRANT_EQUIVALENT: str = "grant_equivalent"
# CRS and DAC2A hold no full year after LATEST_YEAR_DETAIL.
YEARS: range = range(SHORT_START_YEAR, LATEST_YEAR_DETAIL + 1)
DONOR_YEAR: list[str] = ["donor_code", "year"]


def _dac2a_rows(provenance: ProvenanceLog) -> pd.DataFrame:
    """DAC2A imputed multilateral every year, and bilateral before grant equivalents."""
    dac2a = read_dac2a_part_i(
        lines=RECIPIENTS_LINES,
        years=YEARS,
        providers=DAC_COUNTRIES,
        recipients=[UKRAINE_CODE],
        provenance=provenance,
    )
    keep = (dac2a["indicator_name"] == IMPUTED_MULTILATERAL) | (
        dac2a["year"] < GRANT_EQUIVALENT_START_YEAR
    )
    return dac2a.loc[keep, [*DONOR_YEAR, "value"]]


def _crs_grant_equivalents(ctx: oda.Context, provenance: ProvenanceLog) -> pd.DataFrame:
    """CRS bilateral grant equivalents to Ukraine, from GRANT_EQUIVALENT_START_YEAR."""
    return run_query(
        ctx,
        CRS_BILATERAL_ODA,
        provenance=provenance,
        years=range(GRANT_EQUIVALENT_START_YEAR, LATEST_YEAR_DETAIL + 1),
        providers=list(DAC_COUNTRIES),
        recipients=[UKRAINE_CODE],
        basis=GRANT_EQUIVALENT,
        by=["provider", "year"],
    )[[*DONOR_YEAR, "value"]]


def dac_to_ukraine_total(ctx: oda.Context, provenance: ProvenanceLog) -> pd.DataFrame:
    """Read ODA to Ukraine per DAC member and year, plus the DAC countries total.

    Args:
        ctx: From open_context.
        provenance: Log to record every read and the conversion factors in.

    Returns:
        donor_name, year and value, in constant USD millions of CONSTANT_YEAR.
    """
    current = (
        pd.concat(
            [_dac2a_rows(provenance), _crs_grant_equivalents(ctx, provenance)],
            ignore_index=True,
        )
        .groupby(DONOR_YEAR, as_index=False)["value"]
        .sum()
    )
    constant = to_usd_constant(current, base_year=CONSTANT_YEAR, provenance=provenance)
    constant["donor_name"] = constant["donor_code"].map(DAC_COUNTRIES)
    return with_dac_total(constant, ["year"])[["donor_name", "year", "value"]]


def write_ukraine_comparison(ukraine: pd.DataFrame) -> None:
    """Write aid_to_ukraine_comparison.csv: each DAC member's ODA to Ukraine by year.

    From PRE_INVASION_YEAR, latest year first and the largest donor first within a year.

    Args:
        ukraine: From dac_to_ukraine_total, constant USD millions of CONSTANT_YEAR.
    """
    members = ukraine.loc[
        (ukraine["year"] >= PRE_INVASION_YEAR)
        & (ukraine["donor_name"] != DAC_COUNTRIES_NAME)
        & ukraine["value"].notna()
    ]
    data = members.assign(
        recipient_name=UKRAINE_NAME, value=members["value"].round(2)
    ).sort_values(["year", "value"], ascending=False)
    data[["year", "donor_name", "recipient_name", "value"]].to_csv(
        PATHS.TOPIC_PAGE / "aid_to_ukraine_comparison.csv", index=False
    )
    logger.info("Saved chart version of aid_to_ukraine_comparison.csv")


def main() -> None:
    """Log the DAC countries' ODA to Ukraine per year; total_excl_donor publishes it."""
    with open_context() as ctx:
        data = dac_to_ukraine_total(ctx, ProvenanceLog())
    logger.info(
        "DAC countries ODA to Ukraine, constant %s USD million:\n%s",
        CONSTANT_YEAR,
        data.loc[data["donor_name"] == DAC_COUNTRIES_NAME].to_string(index=False),
    )


if __name__ == "__main__":
    main()
