"""Total ODA and ODA/GNI per DAC member and year (oda_gni_ts.csv, oda_gni_single_year_ts.csv).

Both use the financing view's definitions: Total ODA on the DAC1 headline basis, converted
per member, and ODA/GNI with the DAC total over the members reporting GNI (common.oda_gni_table).
"""

import numpy as np
import pandas as pd

from src.data.analysis_tools.oda import ProvenanceLog, open_context
from src.data.config import (
    DAC_COUNTRIES,
    EU_INSTITUTIONS,
    EU_INSTITUTIONS_CODE,
    PATHS,
    logger,
)
from src.data.topic_page.common import (
    AMOUNT_DECIMALS,
    CONSTANT_YEAR,
    LATEST_YEAR_AGG,
    LONG_START_YEAR,
    oda_gni_table,
    sort_dac_first,
)

YEARS: range = range(LONG_START_YEAR, LATEST_YEAR_AGG + 1)
PERCENT: float = 100.0
MILLIONS_PER_BILLION: float = 1e3
EU_INSTITUTIONS_NAME: str = EU_INSTITUTIONS[EU_INSTITUTIONS_CODE]
# Row order of oda_gni_ts within a year: DAC members by code, EU Institutions last.
DONOR_ORDER: dict[str, int] = {
    name: code for code, name in (DAC_COUNTRIES | EU_INSTITUTIONS).items()
}


def _billions_or_millions(value: float) -> str:
    """Format USD millions as "5.67 billion" from a billion up, else "694.2 million"."""
    if value > MILLIONS_PER_BILLION:
        return f"{value / MILLIONS_PER_BILLION:.2f} billion"
    return f"{value:.1f} million"


def oda_gni_ts(table: pd.DataFrame) -> None:
    """Write oda_gni_ts.csv: ODA (constant USD millions) and ODA/GNI (%, 2 dp).

    Args:
        table: From oda_gni_table, for DAC members, EU Institutions and DAC countries.
    """
    data = (
        table.assign(_order=lambda d: d["donor_name"].map(DONOR_ORDER))
        .sort_values(["year", "_order"])
        .assign(
            **{
                "ODA (left-axis)": lambda d: d["oda_constant"].round(AMOUNT_DECIMALS),
                "ODA/GNI (right-axis)": lambda d: (d["oda_gni"] * PERCENT).round(2),
            }
        )
        .rename(columns={"donor_name": "name"})[
            ["name", "year", "ODA (left-axis)", "ODA/GNI (right-axis)"]
        ]
        .pipe(sort_dac_first)
    )

    # EU Institutions have no GNI of their own.
    data["ODA/GNI (right-axis)"] = np.where(
        data["name"] == EU_INSTITUTIONS_NAME, np.nan, data["ODA/GNI (right-axis)"]
    )

    data.to_csv(PATHS.TOPIC_PAGE / "oda_gni_ts.csv", index=False)
    logger.info("Saved chart oda_gni_ts.csv")


def oda_gni_year_columns(table: pd.DataFrame) -> None:
    """Write oda_gni_single_year_ts.csv: ODA, the gap to 0.7% and ODA/GNI, latest year first.

    Amounts are constant USD of CONSTANT_YEAR. The gap is converted with the donor's own
    constant/current ratio of Total ODA (for DAC countries, the total's).

    Args:
        table: From oda_gni_table, for DAC members and DAC countries.
    """
    deflator = table["oda_constant"] / table["oda_current"]
    data = (
        table.assign(
            oda_gni=lambda d: (PERCENT * d["oda_gni"]).round(5),
            missing=(table["gap_current"] * deflator).round(1).clip(lower=0),
        )
        .assign(
            value=lambda d: d["oda_constant"].map(_billions_or_millions),
            missing=lambda d: d["missing"].fillna(0).map(_billions_or_millions),
        )
        .sort_values(["year", "oda_gni", "donor_name"], ascending=[False, False, True])
        .rename(
            columns={
                "value": "Total ODA",
                "oda_gni": "ODA/GNI",
                "donor_name": "Donor",
                "year": "Year",
                "missing": "ODA short of 0.7% commitment",
            }
        )[
            [
                "Donor",
                "Year",
                "Total ODA",
                "ODA short of 0.7% commitment",
                "ODA/GNI",
            ]
        ]
    )

    data.to_csv(PATHS.TOPIC_PAGE / "oda_gni_single_year_ts.csv", index=False)
    logger.info("Saved chart oda_gni_single_year_ts.csv")


def main() -> None:
    """Write oda_gni_ts.csv and oda_gni_single_year_ts.csv."""
    with open_context() as ctx:
        table = oda_gni_table(
            ctx,
            years=YEARS,
            providers=[*DAC_COUNTRIES, EU_INSTITUTIONS_CODE],
            base_year=CONSTANT_YEAR,
            provenance=ProvenanceLog(),
        )
    oda_gni_ts(table)
    oda_gni_year_columns(table.loc[table["donor_name"] != EU_INSTITUTIONS_NAME])


if __name__ == "__main__":
    main()
