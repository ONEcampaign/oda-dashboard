"""Builds the financing view: ODA totals and their components, by donor and year.

Shape of the pipeline:
    1. DAC1 aggregates, private sector instruments and in-donor items, read in net flows up to
       GRANT_EQUIVALENT_START_YEAR and grant equivalents from then on
    2. the grants / non-grants split, derived from one indicator read under two measures
    3. the EU27 + institutions aggregate, which oda_data weights so that member states'
       contributions to the institutions are not counted twice
    4. donor aggregates summed locally, then shares of total ODA and of GNI
    5. one parquet on stdout for Observable, plus the dropdown options beside it

Output is keyed by name: year, donor_name, indicator_name, type.
"""

import numpy as np
import pandas as pd
from oda_data import OECDClient
from oda_data.indicators.research.eu import get_eui_plus_bilateral_providers_indicator

from src.data.analysis_tools.outputs import (
    set_cache_dir,
    parquet_to_stdout,
    generate_view_options,
)
from src.data.analysis_tools.financing import (
    drop_grants_split,
    resolve_indicator_duplicates,
    split_grants,
    years_missing_grants,
)
from src.data.analysis_tools.naming import map_indicator_names
from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    drop_empty_values,
    add_share_of_gni,
    add_share_of_total_oda,
    convert_values_to_units,
    get_member_gni,
    widen_currency_price,
    build_donor_group_totals,
)
from src.data.config import (
    logger,
    FINANCING_TIME,
    GRANT_EQUIVALENT_START_YEAR,
    AGGREGATE_FINANCING_INDICATORS,
    PSI_FINANCING_INDICATORS,
    IN_DONOR_FINANCING_INDICATORS,
    ALL_FINANCING_INDICATORS,
    PROVIDERS,
    DONOR_GROUPS,
    EU27_EUI_LAST_YEAR,
    EU_TOTAL,
    DONORS_ORDER,
    FINANCING_INDICATORS_ORDER,
)

set_cache_dir(oda_data=True, pydeflate=True)


def get_dac1() -> pd.DataFrame:
    """Read the DAC1 indicators, switching measure at the grant-equivalent boundary.

    In-donor items stay in net flows throughout. Preliminary data for the latest year report
    them only as flows, and for earlier years their grant equivalents equal their flows, since
    they are grants.

    Returns:
        One row per year, donor and indicator name.
    """
    # in-donor indicators in net flows
    in_donor_raw = OECDClient(
        years=range(FINANCING_TIME["start"], FINANCING_TIME["end"] + 1),
        providers=list(PROVIDERS),
        measure="net_disbursement",
        use_bulk_download=True,
    ).get_indicators(list(IN_DONOR_FINANCING_INDICATORS))

    # other indicators in net flows up to 2017
    other_flow_raw = OECDClient(
        years=range(FINANCING_TIME["start"], GRANT_EQUIVALENT_START_YEAR),
        providers=list(PROVIDERS),
        measure="net_disbursement",
        use_bulk_download=True,
    ).get_indicators(list(AGGREGATE_FINANCING_INDICATORS | PSI_FINANCING_INDICATORS))

    # other indicators in grant equivalents after 2017
    other_ge_raw = OECDClient(
        years=range(GRANT_EQUIVALENT_START_YEAR, FINANCING_TIME["end"] + 1),
        providers=list(PROVIDERS),
        measure="grant_equivalent",
        use_bulk_download=True,
    ).get_indicators(list(AGGREGATE_FINANCING_INDICATORS | PSI_FINANCING_INDICATORS))

    dac1_raw = pd.concat(
        [in_donor_raw, other_flow_raw, other_ge_raw], ignore_index=True
    )
    dac1_raw = resolve_indicator_duplicates(dac1_raw)

    dac1 = (
        dac1_raw.groupby(
            ["year", "donor_code", "donor_name", "one_indicator"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
        .assign(
            indicator_name=lambda d: map_indicator_names(
                d["one_indicator"], ALL_FINANCING_INDICATORS
            )
        )
        .drop(columns=["one_indicator"])
    )

    return dac1


def get_grants() -> pd.DataFrame:
    """Split total ODA into grants and non-grants.

    Both come from one indicator read under two measures: the grant-only measure gives grants,
    and the headline measure minus that gives non-grants.

    Returns:
        Long-form rows for the two derived indicator names.
    """
    grants_flow_raw = OECDClient(
        years=range(FINANCING_TIME["start"], GRANT_EQUIVALENT_START_YEAR),
        providers=list(PROVIDERS),
        measure=["net_disbursement_grant", "net_disbursement"],
        use_bulk_download=True,
    ).get_indicators(["DAC1.10.1010"])

    grants_ge_raw = OECDClient(
        years=range(GRANT_EQUIVALENT_START_YEAR, FINANCING_TIME["end"] + 1),
        providers=list(PROVIDERS),
        measure=["net_disbursement_grant", "grant_equivalent"],
        use_bulk_download=True,
    ).get_indicators(["DAC1.10.1010"])

    grants_raw = pd.concat([grants_flow_raw, grants_ge_raw])

    return split_grants(grants_raw, ["year", "donor_code", "donor_name"])


def get_eui_eu27_dac1() -> pd.DataFrame:
    """Read the DAC1 indicators for the EU27 + institutions aggregate.

    oda_data scales the institutions' spending by the share not funded by member state
    contributions, so summing members and institutions does not double count.

    Returns:
        One row per year, indicator, currency and price for the aggregate.
    """

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
        years=range(FINANCING_TIME["start"], GRANT_EQUIVALENT_START_YEAR),
        providers=list(EU_TOTAL),
        measure="net_disbursement",
        use_bulk_download=True,
    )

    other_flow_raw = get_eui_plus_bilateral_providers_indicator(
        other_flow_client,
        indicator=list(AGGREGATE_FINANCING_INDICATORS | PSI_FINANCING_INDICATORS),
    )

    # other indicators in grant equivalents after 2017
    other_ge_client = OECDClient(
        years=range(GRANT_EQUIVALENT_START_YEAR, FINANCING_TIME["end"] + 1),
        providers=list(EU_TOTAL),
        measure="grant_equivalent",
        use_bulk_download=True,
    )

    other_ge_raw = get_eui_plus_bilateral_providers_indicator(
        other_ge_client,
        indicator=list(AGGREGATE_FINANCING_INDICATORS | PSI_FINANCING_INDICATORS),
    )

    eui_eu27_dac1_raw = pd.concat(
        [in_donor_raw, other_flow_raw, other_ge_raw], ignore_index=True
    )

    eui_eu27_dac1_raw = resolve_indicator_duplicates(eui_eu27_dac1_raw)

    eui_eu27_dac1_converted = add_currencies_and_prices(
        eui_eu27_dac1_raw, base_year=FINANCING_TIME["base"]
    )

    eui_eu27_dac1 = (
        eui_eu27_dac1_converted.assign(
            indicator_name=lambda d: map_indicator_names(
                d["one_indicator"], ALL_FINANCING_INDICATORS
            ),
            donor_name="EU27 & EU Institutions",
        )
        .groupby(
            ["year", "donor_name", "currency", "price", "indicator_name"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
    )

    return eui_eu27_dac1


def get_eui_eu27_grants() -> pd.DataFrame:
    """Split the EU27 + institutions aggregate into grants and non-grants.

    Returns:
        Long-form rows for the two derived indicator names, for the aggregate.
    """

    # NOTE: measure order matters. get_eui_plus_bilateral_providers_indicator derives the
    # EU institutions weight from measure[0] only, so the total-ODA measure must come
    # first. With the grants measure first the weight is computed on grants (negative in
    # some years), which understates the EUI share and breaks
    # Grants + Non-grants == Total ODA for this aggregate.
    grants_flow_client = OECDClient(
        years=range(FINANCING_TIME["start"], GRANT_EQUIVALENT_START_YEAR),
        providers=list(EU_TOTAL),
        measure=["net_disbursement", "net_disbursement_grant"],
        use_bulk_download=True,
    )

    grants_flow_raw = get_eui_plus_bilateral_providers_indicator(
        grants_flow_client, indicator="DAC1.10.1010"
    )

    grants_ge_client = OECDClient(
        years=range(GRANT_EQUIVALENT_START_YEAR, FINANCING_TIME["end"] + 1),
        providers=list(EU_TOTAL),
        measure=["grant_equivalent", "net_disbursement_grant"],
        use_bulk_download=True,
    )

    grants_ge_raw = get_eui_plus_bilateral_providers_indicator(
        grants_ge_client, indicator="DAC1.10.1010"
    )

    eui_eu27_grants_raw = pd.concat([grants_flow_raw, grants_ge_raw])

    eui_eu27_grants_converted = add_currencies_and_prices(
        eui_eu27_grants_raw, base_year=FINANCING_TIME["base"]
    )

    eui_eu27_grants = (
        split_grants(eui_eu27_grants_converted, ["year", "donor_code", "currency", "price"])
        .groupby(
            ["year", "indicator_name", "currency", "price"], dropna=False, observed=True
        )["value"]
        .sum()
        .reset_index()
        .assign(donor_name="EU27 & EU Institutions")
    )

    return eui_eu27_grants


def get_financing_data() -> pd.DataFrame:
    """Assemble the financing view from its parts.

    Returns:
        Wide frame keyed by year, donor_name, indicator_name and type, with one column per
        currency and price pair plus the two share columns.
    """
    dac1 = get_dac1()
    grants = get_grants()

    non_eu_financing = pd.concat([dac1, grants])

    # Add currencies and prices
    non_eu_financing = add_currencies_and_prices(
        non_eu_financing, base_year=FINANCING_TIME["base"]
    )

    usd_current = non_eu_financing.loc[
        lambda d: (d["currency"] == "USD") & (d["price"] == "current")
    ]
    group_totals = build_donor_group_totals(
        non_eu_financing, ["year", "indicator_name", "currency", "price"]
    )
    donor_groups = [
        drop_grants_split(total, years_missing_grants(usd_current, DONOR_GROUPS[name]))
        for name, total in group_totals.items()
    ]

    eui_eu27 = pd.concat(
        [
            get_eui_eu27_dac1(),
            drop_grants_split(
                get_eui_eu27_grants(), years_missing_grants(usd_current, EU_TOTAL)
            ),
        ]
    )
    logger.info(
        "EU27 & EU Institutions: leaving out years after %s: %s",
        EU27_EUI_LAST_YEAR,
        sorted(eui_eu27.loc[lambda d: d["year"] > EU27_EUI_LAST_YEAR, "year"].unique()),
    )
    eui_eu27 = eui_eu27.loc[lambda d: d["year"] <= EU27_EUI_LAST_YEAR]

    financing = pd.concat([non_eu_financing, *donor_groups, eui_eu27])

    financing = drop_empty_values(financing, "financing")

    # Label each row by the measure it was read in: in-donor items are always flows.
    in_donor = financing["indicator_name"].isin(IN_DONOR_FINANCING_INDICATORS.values())
    financing["type"] = np.where(
        (financing["year"] < GRANT_EQUIVALENT_START_YEAR) | in_donor,
        "Flows",
        "Grant equivalents",
    )

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
    member_gni = get_member_gni(FINANCING_TIME["start"], FINANCING_TIME["end"])
    financing = add_share_of_gni(financing, member_gni, usd_current)

    # Convert values to units (integers) for better compression
    financing = convert_values_to_units(financing)

    return financing


if __name__ == "__main__":
    logger.info("Generating financing table...")
    df = get_financing_data()
    generate_view_options(
        df=df,
        columns={
            "donor_name": DONORS_ORDER,
            "indicator_name": FINANCING_INDICATORS_ORDER,
            "year": [],
        },
        base_year=FINANCING_TIME["base"],
        file_name="financing_view_options.json",
        extra={"eu27_eui_last_year": EU27_EUI_LAST_YEAR},
    )
    parquet_to_stdout(df)
