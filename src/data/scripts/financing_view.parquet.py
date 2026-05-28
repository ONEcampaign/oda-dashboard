from collections import Counter

import numpy as np
import pandas as pd
from oda_data import OECDClient
from oda_data.indicators.research.eu import get_eui_plus_bilateral_providers_indicator

from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
    parquet_to_stdout,
    convert_values_to_units,
)
from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_share_of_gni,
    add_share_of_total_oda,
    widen_currency_price, get_group_total,
)
from src.data.config import (
    FINANCING_INDICATORS,
    FINANCING_TIME,
    IN_DONOR_FINANCING_INDICATORS,
    OTHER_FINANCING_INDICATORS,
    ALL_DONORS,
    EU_TOTAL,
    logger, EU_COUNTRIES, BILATERAL_DONORS,
)

set_cache_dir(oda_data=True, pydeflate=True)


def resolve_indicator_duplicates(dac1_raw: pd.DataFrame) -> pd.DataFrame:
    multi_code_names = {
        name
        for name, count in Counter(FINANCING_INDICATORS.values()).items()
        if count > 1
    }

    annotated = dac1_raw.assign(_indicator=lambda d: d["one_indicator"].map(FINANCING_INDICATORS))
    shared = annotated[annotated["_indicator"].isin(multi_code_names)]

    conflicts = []
    drop_indices = []

    for (year, donor_code, indicator), group in shared.groupby(
        ["year", "donor_code", "_indicator"], dropna=False, observed=True
    ):
        if len(group) <= 1:
            continue
        if group["value"].dropna().nunique() <= 1:
            drop_indices.extend(group.index[1:].tolist())
        else:
            conflicts.append((year, donor_code, indicator))

    if conflicts:
        lines = [
            f"  year={y}, donor_code={d}, indicator='{ind}'"
            for y, d, ind in conflicts
        ]
        raise ValueError(
            "Conflicting values for year-donor pairs with shared indicator codes:\n"
            + "\n".join(lines)
        )

    return dac1_raw.drop(index=drop_indices)


def get_dac1():
    # in-donor indicators in net flows
    in_donor_raw = OECDClient(
        years=range(FINANCING_TIME["start"], FINANCING_TIME["end"] + 1),
        providers=list(ALL_DONORS),
        measure="net_disbursement",
        use_bulk_download=True,
    ).get_indicators(list(IN_DONOR_FINANCING_INDICATORS))

    # other indicators in net flows up to 2017
    other_flow_raw = OECDClient(
        years=range(FINANCING_TIME["start"], 2018),
        providers=list(ALL_DONORS),
        measure="net_disbursement",
        use_bulk_download=True,
    ).get_indicators(list(OTHER_FINANCING_INDICATORS))

    # other indicators in grant equivalents after 2017
    other_ge_raw = OECDClient(
        years=range(2018, FINANCING_TIME["end"] + 1),
        providers=list(ALL_DONORS),
        measure="grant_equivalent",
        use_bulk_download=True,
    ).get_indicators(list(OTHER_FINANCING_INDICATORS))

    dac1_raw = pd.concat([in_donor_raw, other_flow_raw, other_ge_raw])
    dac1_raw = resolve_indicator_duplicates(dac1_raw)

    dac1 = (
        dac1_raw.groupby(
            ["year", "donor_code", "donor_name", "one_indicator"], dropna=False, observed=True
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator_name=lambda d: d["one_indicator"].map(FINANCING_INDICATORS))
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
        providers=list(ALL_DONORS),
        measure=["net_disbursement_grant", "net_disbursement"],
        use_bulk_download=True,
    ).get_indicators(["DAC1.10.1010"])

    grants_ge_raw = OECDClient(
        years=range(2018, FINANCING_TIME["end"] + 1),
        providers=list(ALL_DONORS),
        measure=["net_disbursement_grant", "grant_equivalent"],
        use_bulk_download=True,
    ).get_indicators(["DAC1.10.1010"])

    grants_raw = pd.concat([grants_flow_raw, grants_ge_raw])

    grants = (
        grants_raw.assign(indicator_name=lambda d: d["fund_flows"].map(mapping))
        .groupby(["year", "donor_code", "donor_name", "indicator_name"], dropna=False, observed=True)[
            "value"
        ]
        .sum()
        .reset_index()
        .pivot(index=["year", "donor_code", "donor_name"], columns="indicator_name", values="value")
        .reset_index()
        .assign(**{"Non-grants": lambda d: d["Total ODA"] - d["Grants"]})
        .melt(id_vars=["year", "donor_code", "donor_name"], value_vars=["Grants", "Non-grants"])
    )

    return grants


def get_eui_eu27_dac1():

    # in-donor indicators in net flows
    in_donor_client = OECDClient(
        years=range(FINANCING_TIME["start"], FINANCING_TIME["end"] + 1),
        providers=list(EU_TOTAL),
        measure="net_disbursement",
        use_bulk_download=True,
    )

    in_donor_raw = get_eui_plus_bilateral_providers_indicator(
        in_donor_client, indicator=list(IN_DONOR_FINANCING_INDICATORS)
    )

    # other indicators in net flows up to 2017
    other_flow_client = OECDClient(
        years=range(FINANCING_TIME["start"], 2018),
        providers=list(EU_TOTAL),
        measure="net_disbursement",
        use_bulk_download=True,
    )

    other_flow_raw = get_eui_plus_bilateral_providers_indicator(
        other_flow_client, indicator=list(OTHER_FINANCING_INDICATORS)
    )

    # other indicators in grant equivalents after 2017
    other_ge_client = OECDClient(
        years=range(2018, FINANCING_TIME["end"] + 1),
        providers=list(EU_TOTAL),
        measure="grant_equivalent",
        use_bulk_download=True,
    )

    other_ge_raw = get_eui_plus_bilateral_providers_indicator(
        other_ge_client, indicator=list(OTHER_FINANCING_INDICATORS)
    )

    eui_eu27_dac1_raw = pd.concat([in_donor_raw, other_flow_raw, other_ge_raw])

    eui_eu27_dac1_raw = resolve_indicator_duplicates(eui_eu27_dac1_raw)

    eui_eu27_dac1_converted = add_currencies_and_prices(eui_eu27_dac1_raw, base_year=FINANCING_TIME["base"])

    eui_eu27_dac1 = (
        eui_eu27_dac1_converted
        .assign(
            indicator_name=lambda d: d["one_indicator"].map(FINANCING_INDICATORS),
            donor_name="EU27 & EU Institutions",
        ).groupby(["year", "donor_name", "currency", "price", "indicator_name"], dropna=False, observed=True)["value"].sum().reset_index()
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
        providers=list(EU_TOTAL),
        measure=["net_disbursement_grant", "net_disbursement"],
        use_bulk_download=True,
    )

    grants_flow_raw = get_eui_plus_bilateral_providers_indicator(
        grants_flow_client, indicator="DAC1.10.1010"
    )

    grants_ge_client = OECDClient(
        years=range(2018, FINANCING_TIME["end"] + 1),
        providers=list(EU_TOTAL),
        measure=["net_disbursement_grant", "grant_equivalent"],
        use_bulk_download=True,
    )

    grants_ge_raw = get_eui_plus_bilateral_providers_indicator(
        grants_ge_client, indicator="DAC1.10.1010"
    )

    eui_eu27_grants_raw = pd.concat([grants_flow_raw, grants_ge_raw])

    eui_eu27_grants_converted = add_currencies_and_prices(eui_eu27_grants_raw, base_year=FINANCING_TIME["base"])

    eui_eu27_grants = (
        eui_eu27_grants_converted
        .assign(indicator_name=lambda d: d["fund_flows"].map(mapping))
        .pivot(index=["year", "donor_code", "currency", "price"], columns="indicator_name", values="value")
        .reset_index()
        .assign(**{"Non-grants": lambda d: d["Total ODA"] - d["Grants"]})
        .melt(id_vars=["year", "donor_code", "currency", "price"], value_vars=["Grants", "Non-grants"])
        .groupby(["year", "indicator_name", "currency", "price"], dropna=False, observed=True)["value"].sum().reset_index()
        .assign(donor_name= "EU27 & EU Institutions")
    )

    return eui_eu27_grants


def get_financing_data():
    dac1 = get_dac1()
    grants = get_grants()

    non_eu_financing = pd.concat([dac1, grants])

    # Add currencies and prices
    non_eu_financing = add_currencies_and_prices(non_eu_financing, base_year=FINANCING_TIME["base"])

    eu27_financing = get_group_total(
        non_eu_financing,
        EU_COUNTRIES,
        check_all_keys=False,
        group_cols=["year", "indicator_name", "currency", "price"],
        donor_name="EU27 countries"
    )
    all_bilateral_financing = get_group_total(
        non_eu_financing,
        BILATERAL_DONORS,
        check_all_keys=False,
        group_cols=["year", "indicator_name", "currency", "price"],
        donor_name="All bilateral donors"
    )

    eui_eu27_dac1 = get_eui_eu27_dac1()
    eui_eu27_grants = get_eui_eu27_grants()

    financing = pd.concat([
        non_eu_financing,
        eu27_financing,
        all_bilateral_financing,
        eui_eu27_dac1,
        eui_eu27_grants
    ])

    financing = financing.loc[
        lambda d: d["value"].notna() & (d["value"] != 0)
    ]

    # Add type column
    financing["type"] = np.where(financing["year"] < 2018, "Flows", "Grant equivalents")

    # Pivot values to columns
    financing = widen_currency_price(
        df=financing,
        index_cols=(
            "year",
            "donor_name",
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
