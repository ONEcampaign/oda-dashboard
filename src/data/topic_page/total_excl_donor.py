import pandas as pd
from oda_data import OECDClient, provider_groupings

from src.data.analysis_tools.helper_functions import set_cache_dir
from src.data.config import PATHS, logger
from src.data.topic_page.common import (
    LATEST_YEAR_AGG,
    CONSTANT_YEAR,
    SHORT_START_YEAR,
)
from src.data.topic_page.covid import covid_bi_multi_dac
from src.data.topic_page.ukraine import dac_to_ukraine_total


def total_oda_excluding_covid_ukraine_idrc() -> None:
    """Create an overview chart which contains the latest total ODA value and
    the change in constant terms."""
    client = OECDClient(
        years=range(SHORT_START_YEAR, LATEST_YEAR_AGG + 1),
        providers=list(provider_groupings()["dac_countries"]) + [20001],
        base_year=CONSTANT_YEAR,
        measure=["net_disbursement", "grant_equivalent"],
        use_bulk_download=True,
    )

    refugees_indicator = "DAC1.10.1820"
    oda_indicator = "ONE.10.1010_11010"

    data = (
        client.get_indicators(indicators=[oda_indicator, refugees_indicator])
        .drop_duplicates(["donor_code", "year", "one_indicator"])
        .filter(["donor_name", "one_indicator", "year", "value"])
        .pivot(index=["donor_name", "year"], columns="one_indicator", values="value")
        .fillna(0)
        .reset_index(drop=False)
    )

    ukraine_data = (
        dac_to_ukraine_total()
        .filter(["donor_name", "year", "value"])
        .rename(columns={"value": "ukraine"})
    )

    covid_data = (
        covid_bi_multi_dac()
        .filter(["donor_name", "year", "value"])
        .rename(columns={"value": "covid"})
    )

    full_data = (
        data.merge(
            ukraine_data,
            how="left",
            on=["donor_name", "year"],
        )
        .merge(
            covid_data,
            how="left",
            on=["donor_name", "year"],
        )
        .fillna({"covid": 0})
    )

    full_data = full_data.rename(
        columns={
            oda_indicator: "Total ODA",
            refugees_indicator: "IDRC",
            "ukraine": "ODA to Ukraine",
            "covid": "COVID ODA",
            "donor_name": "Donor",
            "year": "Year",
        }
    )

    dac_idrc_24 = (
        full_data.loc[lambda d: d.Year == 2024]
        .loc[lambda d: d.Donor != "DAC countries"]
        .assign(Donor="DAC countries")
        .groupby(["Year", "Donor"], as_index=False)[["IDRC"]]
        .sum()
    )

    full_data.loc[lambda d: (d.Year == 2024) & (d.Donor == "DAC countries"), "IDRC"] = (
        dac_idrc_24.IDRC.item()
    )

    full_data["Other ODA"] = round(
        full_data["Total ODA"].fillna(0)
        - full_data["COVID ODA"].fillna(0)
        - full_data["IDRC"].fillna(0)
        - full_data["ODA to Ukraine"].fillna(0),
        1,
    )

    full_data = full_data.filter(
        [
            "Year",
            "Donor",
            "COVID ODA",
            "IDRC",
            "ODA to Ukraine",
            "Other ODA",
            "Total ODA",
        ]
    )

    # full_data["Preliminary"] = full_data.loc[lambda d: d.Year == 2024, "Other ODA"]
    # full_data.loc[lambda d: d.Year == 2024, "Other ODA"] = None

    dac = full_data.loc[lambda d: d.Donor == "DAC countries"]
    full_data = full_data.loc[lambda d: d.Donor != "DAC countries"]

    full_data = pd.concat([dac, full_data], ignore_index=True)

    # live version
    full_data.to_csv(f"{PATHS.TOPIC_PAGE}/oda_covid.csv", index=False)
    logger.info("Saved chart oda_covid.csv")


if __name__ == "__main__":
    set_cache_dir(oda_data=True, pydeflate=True)
    total_oda_excluding_covid_ukraine_idrc()
