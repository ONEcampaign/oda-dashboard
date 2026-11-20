"""Total ODA split into COVID-19, in-donor refugee costs, Ukraine and the rest (oda_covid.csv).

Total ODA is the financing view's (DAC1 headline basis) and in-donor refugee costs its
"Refugees in donor countries" (DAC1 line 1820, net flows), both converted per member and
summed for DAC countries. The COVID-19 series is the static input covid.py reads.
"""

import oda_data as oda
import pandas as pd

from src.data.analysis_tools.oda import ProvenanceLog, open_context, run_query
from src.data.config import DAC_COUNTRIES, DAC_COUNTRIES_NAME, PATHS, logger
from src.data.topic_page.common import (
    AMOUNT_DECIMALS,
    CONSTANT_YEAR,
    LATEST_YEAR_AGG,
    SHORT_START_YEAR,
    read_total_oda,
    to_usd_constant,
    with_dac_total,
)
from src.data.topic_page.covid import covid_bi_multi_dac
from src.data.topic_page.ukraine import dac_to_ukraine_total

# DAC1 line for in-donor refugee costs, read in net flows as the financing view reads it.
IDRC_LINE: int = 1820
NET: str = "net_disbursement"
YEARS: range = range(SHORT_START_YEAR, LATEST_YEAR_AGG + 1)

TOTAL_ODA: str = "Total ODA"
IDRC: str = "IDRC"
OUTPUT_COLUMNS: list[str] = [
    "Year",
    "Donor",
    "COVID ODA",
    IDRC,
    "ODA to Ukraine",
    "Other ODA",
    TOTAL_ODA,
]


def read_total_and_idrc(ctx: oda.Context, provenance: ProvenanceLog) -> pd.DataFrame:
    """Read Total ODA and in-donor refugee costs per DAC member, plus the DAC total.

    Args:
        ctx: From open_context.
        provenance: Log to record every read and the conversion factors in.

    Returns:
        One row per donor_name and year, with TOTAL_ODA and IDRC columns in constant USD
        millions of CONSTANT_YEAR, 0 where a donor reports nothing.
    """
    providers = list(DAC_COUNTRIES)
    total = read_total_oda(ctx, years=YEARS, providers=providers, provenance=provenance)
    idrc = run_query(
        ctx,
        "oecd.dac1.lines",
        provenance=provenance,
        lines=[IDRC_LINE],
        years=YEARS,
        providers=providers,
        basis=NET,
        by=["provider", "year", "line"],
    )
    current = pd.concat(
        [
            total.assign(indicator=TOTAL_ODA),
            idrc.assign(indicator=IDRC),
        ],
        ignore_index=True,
    )[["donor_code", "year", "indicator", "value"]]
    constant = to_usd_constant(current, base_year=CONSTANT_YEAR, provenance=provenance)
    constant["donor_name"] = constant["donor_code"].map(DAC_COUNTRIES)
    return (
        with_dac_total(constant, ["year", "indicator"])
        .pivot(index=["donor_name", "year"], columns="indicator", values="value")
        .fillna(0)
        .reset_index()
        .rename_axis(None, axis=1)
    )


def total_oda_excluding_covid_ukraine_idrc(
    ctx: oda.Context, provenance: ProvenanceLog
) -> None:
    """Write oda_covid.csv: Total ODA and its parts per DAC member and year, DAC first.

    The latest year is preliminary, so its "Other ODA" moves to the Preliminary column.

    Args:
        ctx: From open_context.
        provenance: Log to record every read and the conversion factors in.
    """
    ukraine = dac_to_ukraine_total(ctx, provenance).rename(
        columns={"value": "ODA to Ukraine"}
    )
    covid = covid_bi_multi_dac()[["donor_name", "year", "value"]].rename(
        columns={"value": "COVID ODA"}
    )

    full_data = (
        read_total_and_idrc(ctx, provenance)
        .merge(ukraine, how="left", on=["donor_name", "year"], validate="1:1")
        .merge(covid, how="left", on=["donor_name", "year"], validate="1:1")
        .fillna({"COVID ODA": 0})
        .rename(columns={"donor_name": "Donor", "year": "Year"})
    )

    full_data["Other ODA"] = round(
        full_data[TOTAL_ODA]
        - full_data["COVID ODA"]
        - full_data[IDRC]
        - full_data["ODA to Ukraine"].fillna(0),
        1,
    )
    full_data = full_data[OUTPUT_COLUMNS].round(
        {
            TOTAL_ODA: AMOUNT_DECIMALS,
            IDRC: AMOUNT_DECIMALS,
            "ODA to Ukraine": AMOUNT_DECIMALS,
        }
    )

    is_preliminary = full_data["Year"] == LATEST_YEAR_AGG
    full_data["Preliminary"] = full_data["Other ODA"].where(is_preliminary)
    full_data.loc[is_preliminary, "Other ODA"] = None

    is_dac = full_data["Donor"] == DAC_COUNTRIES_NAME
    full_data = pd.concat([full_data[is_dac], full_data[~is_dac]], ignore_index=True)

    full_data.to_csv(PATHS.TOPIC_PAGE / "oda_covid.csv", index=False)
    logger.info("Saved chart oda_covid.csv")


def main() -> None:
    """Write oda_covid.csv."""
    with open_context() as ctx:
        total_oda_excluding_covid_ukraine_idrc(ctx, ProvenanceLog())


if __name__ == "__main__":
    main()
