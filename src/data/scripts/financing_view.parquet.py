import numpy as np
import pandas as pd
from oda_data import OECDClient, DAC1Data
from oda_data.indicators.research.eu import get_eui_plus_bilateral_providers_indicator
from oda_data.tools.groupings import provider_groupings

from src.data.analysis_tools.helper_functions import (
    get_dac_ids,
    set_cache_dir,
    parquet_to_stdout,
    convert_values_to_units,
)
from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_donor_groupings,
    add_donor_names,
    add_financing_indicator_codes,
    add_share_of_gni,
    add_share_of_total_oda,
    widen_currency_price,
)
from src.data.config import (
    FINANCING_INDICATORS,
    FINANCING_TIME,
    IN_DONOR_FINANCING_INDICATORS,
    OTHER_FINANCING_INDICATORS,
    PATHS,
    eui_bi_code,
    logger,
)

donor_ids = get_dac_ids(PATHS.DONORS)
eu_ids = provider_groupings()["eu27_total"]
set_cache_dir(oda_data=True, pydeflate=True)

def get_dac1():
    # in-donor indicators in net flows
    in_donor_raw = OECDClient(
        years=range(FINANCING_TIME["start"], FINANCING_TIME["end"] + 1),
        providers=donor_ids,
        measure="net_disbursement",
        use_bulk_download=True,
    ).get_indicators(list(IN_DONOR_FINANCING_INDICATORS))

    # other indicators in net flows up to 2017
    other_flow_raw = OECDClient(
        years=range(FINANCING_TIME["start"], 2018),
        providers=donor_ids,
        measure="net_disbursement",
        use_bulk_download=True,
    ).get_indicators(list(OTHER_FINANCING_INDICATORS))

    # other indicators in grant equivalents after 2017
    other_ge_raw = OECDClient(
        years=range(2018, FINANCING_TIME["end"] + 1),
        providers=donor_ids,
        measure="grant_equivalent",
        use_bulk_download=True,
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
        use_bulk_download=True,
    )

    in_donor_raw = get_eui_plus_bilateral_providers_indicator(
        in_donor_client, indicator=list(IN_DONOR_FINANCING_INDICATORS)
    )

    # other indicators in net flows up to 2017
    other_flow_client = OECDClient(
        years=range(FINANCING_TIME["start"], 2018),
        providers=list(eu_ids),
        measure="net_disbursement",
        use_bulk_download=True,
    )

    other_flow_raw = get_eui_plus_bilateral_providers_indicator(
        other_flow_client, indicator=list(OTHER_FINANCING_INDICATORS)
    )

    # other indicators in grant equivalents after 2017
    other_ge_client = OECDClient(
        years=range(2018, FINANCING_TIME["end"] + 1),
        providers=list(eu_ids),
        measure="grant_equivalent",
        use_bulk_download=True,
    )

    other_ge_raw = get_eui_plus_bilateral_providers_indicator(
        other_ge_client, indicator=list(OTHER_FINANCING_INDICATORS)
    )

    eui_eu27_dac1_raw = pd.concat([in_donor_raw, other_flow_raw, other_ge_raw])

    eui_eu27_dac1 = (
        eui_eu27_dac1_raw.query("donor_code == 918")
        .assign(donor_code=eui_bi_code)
        .assign(indicator=lambda d: d["one_indicator"].map(FINANCING_INDICATORS))[
            ["year", "donor_code", "indicator", "value"]
        ]
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
        grants_flow_client, indicator="DAC1.10.1010"
    )

    grants_ge_client = OECDClient(
        years=range(2018, FINANCING_TIME["end"]),
        providers=list(eu_ids),
        measure=["net_disbursement_grant", "grant_equivalent"],
        use_bulk_download=True,
    )

    grants_ge_raw = get_eui_plus_bilateral_providers_indicator(
        grants_ge_client, indicator="DAC1.10.1010"
    )

    eui_eu27_grants_raw = pd.concat([grants_flow_raw, grants_ge_raw])

    eui_eu27_grants = (
        eui_eu27_grants_raw.query("donor_code == 918")
        .assign(donor_code=eui_bi_code)
        .assign(indicator=lambda d: d["fund_flows"].map(mapping))
        .pivot(index=["year", "donor_code"], columns="indicator", values="value")
        .reset_index()
        .assign(**{"Non-grants": lambda d: d["Total ODA"] - d["Grants"]})
        .melt(id_vars=["year", "donor_code"], value_vars=["Grants", "Non-grants"])[
            ["year", "donor_code", "indicator", "value"]
        ]
    )

    return eui_eu27_grants


def get_financing_data():
    dac1 = get_dac1()
    grants = get_grants()

    eui_eu27_dac1 = get_eui_eu27_dac1()
    eui_eu27_grants = get_eui_eu27_grants()

    financing = pd.concat([dac1, grants, eui_eu27_dac1, eui_eu27_grants])

    financing = financing.loc[lambda d: d["value"] != 0]

    # Add currencies and prices
    financing = add_currencies_and_prices(financing)

    # Add donor groupings
    financing = add_donor_groupings(financing)

    # Add indicator code
    financing = add_financing_indicator_codes(financing)

    # Add donor name
    financing = add_donor_names(financing)

    # Add type column
    financing["type"] = np.where(financing["year"] < 2018, "Flows", "Grant equivalents")

    # Pivot values to columns
    financing = widen_currency_price(
        df=financing,
        index_cols=(
            "year",
            "donor_code",
            "donor_name",
            "indicator",
            "indicator_name",
            "type",
        ),
    )

    # Add share of total ODA
    financing = add_share_of_total_oda(financing)

    # Add share of GNI column
    financing = add_share_of_gni(financing)

    # Convert values to units (integers) for better compression
    # NOTE: Frontend queries must divide value_* columns by 1e6 to get millions
    financing = convert_values_to_units(financing)

    return financing


if __name__ == "__main__":
    logger.info("Generating financing table...")
    df = get_financing_data()
    parquet_to_stdout(df)
