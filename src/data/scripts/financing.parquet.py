import pandas as pd

from oda_data import OECDClient
from oda_data.tools.groupings import provider_groupings
from oda_data.indicators.research.eu import get_eui_plus_bilateral_providers_indicator

from src.data.config import (
    PATHS,
    IN_DONOR_FINANCING_INDICATORS,
    OTHER_FINANCING_INDICATORS,
    FINANCING_INDICATORS,
    FINANCING_TIME,
    eui_bi_code,
    logger
)

from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
    get_dac_ids,
    add_index_column,
    df_to_parquet,
    save_time_range_to_json,
)

donor_ids = get_dac_ids(PATHS.DONORS)
eu_ids = provider_groupings()["eu27_total"]


def get_dac1():

    # in-donor indicators in net flows
    in_donor_raw = OECDClient(
        years=range(FINANCING_TIME["start"], FINANCING_TIME["end"] + 1),
        providers=donor_ids,
        measure="net_disbursement",
        use_bulk_download=True
    ).get_indicators(list(IN_DONOR_FINANCING_INDICATORS))

    # other indicators in net flows up to 2017
    other_flow_raw = OECDClient(
        years=range(FINANCING_TIME['start'], 2018),
        providers=donor_ids,
        measure="net_disbursement",
        use_bulk_download=True
    ).get_indicators(list(OTHER_FINANCING_INDICATORS))

    # other indicators in grant equivalents after 2017
    other_ge_raw = OECDClient(
        years=range(2018, FINANCING_TIME["end"] + 1),
        providers=donor_ids,
        measure="grant_equivalent",
        use_bulk_download=True
    ).get_indicators(list(OTHER_FINANCING_INDICATORS))

    dac1_raw = pd.concat([in_donor_raw, other_flow_raw, other_ge_raw])

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

    grants_flow_raw = OECDClient(
        years=range(FINANCING_TIME["start"], 2018),
        providers=donor_ids,
        measure=["net_disbursement_grant", "net_disbursement"],
        use_bulk_download=True,
    ).get_indicators(["DAC1.10.1010"])

    grants_ge_raw = OECDClient(
        years=range(2018, FINANCING_TIME["end"]),
        providers=donor_ids,
        measure=["net_disbursement_grant", "grant_equivalent"],
        use_bulk_download=True,
    ).get_indicators(["DAC1.10.1010"])

    grants_raw = pd.concat([grants_flow_raw, grants_ge_raw])

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

def get_eui_eu27_dac1():

    # in-donor indicators in net flows
    in_donor_client = OECDClient(
        years=range(FINANCING_TIME["start"], FINANCING_TIME["end"] + 1),
        providers=list(eu_ids),
        measure="net_disbursement",
        use_bulk_download=True
    )

    in_donor_raw = get_eui_plus_bilateral_providers_indicator(
        in_donor_client,
        indicator=list(IN_DONOR_FINANCING_INDICATORS)
    )

    # other indicators in net flows up to 2017
    other_flow_client = OECDClient(
        years=range(FINANCING_TIME['start'], 2018),
        providers=list(eu_ids),
        measure="net_disbursement",
        use_bulk_download=True
    )

    other_flow_raw = get_eui_plus_bilateral_providers_indicator(
        other_flow_client,
        indicator=list(OTHER_FINANCING_INDICATORS)
    )

    # other indicators in grant equivalents after 2017
    other_ge_client = OECDClient(
        years=range(2018, FINANCING_TIME["end"] + 1),
        providers=list(eu_ids),
        measure="grant_equivalent",
        use_bulk_download=True
    )

    other_ge_raw = get_eui_plus_bilateral_providers_indicator(
        other_ge_client,
        indicator=list(OTHER_FINANCING_INDICATORS)
    )

    eui_eu27_dac1_raw = pd.concat([in_donor_raw, other_flow_raw, other_ge_raw])

    eui_eu27_dac1 = (
        eui_eu27_dac1_raw.query("donor_code == 918")
        .assign(donor_code=eui_bi_code)
        .assign(indicator=lambda d: d["one_indicator"].map(FINANCING_INDICATORS))
        [["year", "donor_code", "indicator", "value"]]
    )

    return eui_eu27_dac1

def get_eui_eu27_grants():

    mapping = {
        "Disbursements, net": "Total ODA",
        "Grant equivalents": "Total ODA",
        "Disbursements, grants": "Grants",
    }

    grants_flow_client = OECDClient(
        years=range(FINANCING_TIME["start"], 2018),
        providers=list(eu_ids),
        measure=["net_disbursement_grant", "net_disbursement"],
        use_bulk_download=True,
    )

    grants_flow_raw = get_eui_plus_bilateral_providers_indicator(
        grants_flow_client,
        indicator="DAC1.10.1010"
    )

    grants_ge_client = OECDClient(
        years=range(2018, FINANCING_TIME["end"]),
        providers=list(eu_ids),
        measure=["net_disbursement_grant", "grant_equivalent"],
        use_bulk_download=True,
    )

    grants_ge_raw = get_eui_plus_bilateral_providers_indicator(
        grants_ge_client,
        indicator="DAC1.10.1010"
    )

    eui_eu27_grants_raw = pd.concat([grants_flow_raw, grants_ge_raw])

    eui_eu27_grants = (
        eui_eu27_grants_raw.query("donor_code == 918")
        .assign(donor_code=eui_bi_code)
        .assign(indicator=lambda d: d["fund_flows"].map(mapping))
        .pivot(index=["year", "donor_code"], columns="indicator", values="value")
        .reset_index()
        .assign(**{"Non-grants": lambda d: d["Total ODA"] - d["Grants"]})
        .melt(id_vars=["year", "donor_code"], value_vars=["Grants", "Non-grants"])
        [["year", "donor_code", "indicator", "value"]]
    )

    return eui_eu27_grants


def get_financing_data():

    dac1 = get_dac1()
    grants = get_grants()

    eui_eu27_dac1 = get_eui_eu27_dac1()
    eui_eu27_grants = get_eui_eu27_grants()

    financing = pd.concat([dac1, grants, eui_eu27_dac1, eui_eu27_grants])

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
    # Write parquet with a low compression level to favour fast reads in DuckDB
    df_to_parquet(df, compression="zstd", compression_level=1)


if __name__ == "__main__":
    save_time_range_to_json(FINANCING_TIME, "financing_time.json")
    logger.info("Generating financing table...")
    set_cache_dir(oda_data=True)
    financing_to_parquet()
