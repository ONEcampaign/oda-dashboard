import pandas as pd

from oda_data import OECDClient

from src.data.config import PATHS, FINANCING_INDICATORS, FINANCING_TIME, logger

from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
    get_dac_ids,
    add_index_column,
    df_to_parquet,
    save_time_range_to_json
)

donor_ids = get_dac_ids(PATHS.DONORS)

def get_dac1():

    dac1_raw = OECDClient(
        years=range(FINANCING_TIME["start"], FINANCING_TIME["end"] + 1),
        providers=donor_ids,
        measure=["net_disbursement", "grant_equivalent"],
        use_bulk_download=True,
    ).get_indicators(list(FINANCING_INDICATORS.keys()))

    # Remove net disbursements after 2018
    dac1_raw = dac1_raw[
        ~((dac1_raw["year"] >= 2018) & (dac1_raw["fund_flows"] == "Disbursements, net"))
    ]

    dac1 = (
        dac1_raw.groupby(
            ["year", "donor_code", "one_indicator"], dropna=False, observed=True
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator=lambda d: d["one_indicator"].map(FINANCING_INDICATORS))
        .drop(columns=["one_indicator"])
    )

    return dac1


def get_grants():

    mapping = {
        "Disbursements, net": "Total ODA",
        "Grant equivalents": "Total ODA",
        "Disbursements, grants": "Grants",
    }

    grants_raw = OECDClient(
        years=range(FINANCING_TIME["start"], FINANCING_TIME["end"] + 1),
        providers=donor_ids,
        measure=["net_disbursement_grant", "net_disbursement", "grant_equivalent"],
        use_bulk_download=True,
    ).get_indicators(["DAC1.10.1010", "DAC1.10.11010"])

    # Remove net disbursements after 2018
    grants_raw = grants_raw[
        ~(
            (grants_raw["year"] >= 2018)
            & (grants_raw["fund_flows"] == "Disbursements, net")
        )
    ]

    grants = (
        grants_raw.assign(indicator=lambda d: d["fund_flows"].map(mapping))
        .groupby(["year", "donor_code", "indicator"], dropna=False, observed=True)[
            "value"
        ]
        .sum()
        .reset_index()
        .pivot(index=["year", "donor_code"], columns="indicator", values="value")
        .reset_index()
        .assign(**{"Non-grants": lambda d: d["Total ODA"] - d["Grants"]})
        .melt(id_vars=["year", "donor_code"], value_vars=["Grants", "Non-grants"])
    )

    return grants


def get_financing_data():

    dac1 = get_dac1()
    grants = get_grants()

    financing = pd.concat([dac1, grants])

    financing = financing[financing["value"] != 0]

    financing = add_index_column(
        df=financing,
        column="indicator",
        json_path=PATHS.TOOLS / "financing_indicators.json",
        ordered_list=list(FINANCING_INDICATORS.values()) + ["Grants", "Non-grants"],
    )

    return financing


def financing_to_parquet():
    df = get_financing_data()
    df_to_parquet(df)


if __name__ == "__main__":
    save_time_range_to_json(FINANCING_TIME, "financing_time.json")
    logger.info("Generating financing table...")
    set_cache_dir(oda_data=True)
    financing_to_parquet()
