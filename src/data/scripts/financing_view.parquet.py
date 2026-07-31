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

from collections import Counter

import numpy as np
import pandas as pd
from oda_data import OECDClient
from oda_data.indicators.research.eu import get_eui_plus_bilateral_providers_indicator

from src.data.analysis_tools.outputs import (
    set_cache_dir,
    parquet_to_stdout,
    generate_view_options,
)
from src.data.analysis_tools.naming import apply_name_overrides
from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_share_of_gni,
    add_share_of_total_oda,
    convert_values_to_units,
    widen_currency_price, get_group_total,
)
from src.data.config import (
    logger,
    FINANCING_TIME,
    GRANT_EQUIVALENT_START_YEAR,
    AGGREGATE_FINANCING_INDICATORS,
    PSI_FINANCING_INDICATORS,
    IN_DONOR_FINANCING_INDICATORS,
    ALL_FINANCING_INDICATORS,
    ALL_DONORS,
    AGGREGATE_DONORS,
    EU_INSTITUTIONS,
    EU_TOTAL,
    EU_COUNTRIES,
    BILATERAL_DONORS,
    DONORS_ORDER,
    FINANCING_INDICATORS_ORDER,
)

set_cache_dir(oda_data=True, pydeflate=True)


def resolve_indicator_duplicates(
    dac1_raw: pd.DataFrame, raise_error: bool = True
) -> pd.DataFrame:
    """Drop the duplicate rows created by indicators that share a display name.

    The DAC renumbered several indicators when it moved to grant equivalents, so two codes can
    map to one name (1015 and 11015 are both "Bilateral ODA"). Where both are present for the
    same donor and year they report the same figure, and keeping both would double it.

    Args:
        dac1_raw: Raw DAC1 rows, with a one_indicator column.
        raise_error: Whether disagreeing values are fatal. They should be, since it would mean
            the two codes are not interchangeable after all; pass False to log and continue.

    Returns:
        The rows with duplicates removed, keeping the first of each set.

    Raises:
        ValueError: If two codes for one name disagree and raise_error is True.
    """
    multi_code_names = {
        name
        for name, count in Counter(ALL_FINANCING_INDICATORS.values()).items()
        if count > 1
    }

    annotated = dac1_raw.assign(_indicator=lambda d: d["one_indicator"].map(ALL_FINANCING_INDICATORS))
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
            drop_indices.extend(group.index[1:].tolist())

    if conflicts:
        lines = [
            f"  year={y}, donor_code={d}, indicator='{ind}'"
            for y, d, ind in conflicts
        ]
        message = (
            "Conflicting values for year-donor pairs with shared indicator codes:\n"
            + "\n".join(lines)
        )
        if raise_error:
            raise ValueError(message)
        else:
            logger.warning(message)

    return dac1_raw.drop(index=drop_indices)


def get_dac1() -> pd.DataFrame:
    """Read the DAC1 indicators, switching measure at the grant-equivalent boundary.

    In-donor items stay in net flows throughout, because the DAC never restated them as grant
    equivalents.

    Returns:
        One row per year, donor and indicator name.
    """
    # in-donor indicators in net flows
    in_donor_raw = OECDClient(
        years=range(FINANCING_TIME["start"], FINANCING_TIME["end"] + 1),
        providers=list(ALL_DONORS | EU_INSTITUTIONS),
        measure="net_disbursement",
        use_bulk_download=True,
    ).get_indicators(list(IN_DONOR_FINANCING_INDICATORS))

    # other indicators in net flows up to 2017
    other_flow_raw = OECDClient(
        years=range(FINANCING_TIME["start"], GRANT_EQUIVALENT_START_YEAR),
        providers=list(ALL_DONORS | EU_INSTITUTIONS),
        measure="net_disbursement",
        use_bulk_download=True,
    ).get_indicators(list(AGGREGATE_FINANCING_INDICATORS | PSI_FINANCING_INDICATORS))

    # other indicators in grant equivalents after 2017
    other_ge_raw = OECDClient(
        years=range(GRANT_EQUIVALENT_START_YEAR, FINANCING_TIME["end"] + 1),
        providers=list(ALL_DONORS | EU_INSTITUTIONS),
        measure="grant_equivalent",
        use_bulk_download=True,
    ).get_indicators(list(AGGREGATE_FINANCING_INDICATORS | PSI_FINANCING_INDICATORS))

    dac1_raw = pd.concat([in_donor_raw, other_flow_raw, other_ge_raw], ignore_index=True)
    dac1_raw = resolve_indicator_duplicates(dac1_raw)

    dac1 = (
        dac1_raw.groupby(
            ["year", "donor_code", "donor_name", "one_indicator"], dropna=False, observed=True
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator_name=lambda d: d["one_indicator"].map(ALL_FINANCING_INDICATORS))
        .drop(columns=["one_indicator"])
    )

    dac1 = apply_name_overrides(dac1, AGGREGATE_DONORS, "donor")

    return dac1


def get_grants() -> pd.DataFrame:
    """Split total ODA into grants and non-grants.

    Both come from one indicator read under two measures: the grant-only measure gives grants,
    and the headline measure minus that gives non-grants.

    Returns:
        Long-form rows for the two derived indicator names.
    """
    mapping = {
        "Disbursements, net": "Total ODA",
        "Grant equivalents": "Total ODA",
        "Disbursements, grants": "Grants",
    }

    grants_flow_raw = OECDClient(
        years=range(FINANCING_TIME["start"], GRANT_EQUIVALENT_START_YEAR),
        providers=list(ALL_DONORS | EU_INSTITUTIONS),
        measure=["net_disbursement_grant", "net_disbursement"],
        use_bulk_download=True,
    ).get_indicators(["DAC1.10.1010"])

    grants_ge_raw = OECDClient(
        years=range(GRANT_EQUIVALENT_START_YEAR, FINANCING_TIME["end"] + 1),
        providers=list(ALL_DONORS | EU_INSTITUTIONS),
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

    grants = apply_name_overrides(grants, AGGREGATE_DONORS, "donor")

    return grants


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
        other_flow_client, indicator=list(AGGREGATE_FINANCING_INDICATORS | PSI_FINANCING_INDICATORS)
    )

    # other indicators in grant equivalents after 2017
    other_ge_client = OECDClient(
        years=range(GRANT_EQUIVALENT_START_YEAR, FINANCING_TIME["end"] + 1),
        providers=list(EU_TOTAL),
        measure="grant_equivalent",
        use_bulk_download=True,
    )

    other_ge_raw = get_eui_plus_bilateral_providers_indicator(
        other_ge_client, indicator=list(AGGREGATE_FINANCING_INDICATORS | PSI_FINANCING_INDICATORS)
    )

    eui_eu27_dac1_raw = pd.concat([in_donor_raw, other_flow_raw, other_ge_raw], ignore_index=True)

    eui_eu27_dac1_raw = resolve_indicator_duplicates(eui_eu27_dac1_raw)

    eui_eu27_dac1_converted = add_currencies_and_prices(eui_eu27_dac1_raw, base_year=FINANCING_TIME["base"])

    eui_eu27_dac1 = (
        eui_eu27_dac1_converted
        .assign(
            indicator_name=lambda d: d["one_indicator"].map(ALL_FINANCING_INDICATORS),
            donor_name="EU27 & EU Institutions",
        ).groupby(["year", "donor_name", "currency", "price", "indicator_name"], dropna=False, observed=True)["value"].sum().reset_index()
    )

    return eui_eu27_dac1


def get_eui_eu27_grants() -> pd.DataFrame:
    """Split the EU27 + institutions aggregate into grants and non-grants.

    Returns:
        Long-form rows for the two derived indicator names, for the aggregate.
    """

    mapping = {
        "Disbursements, net": "Total ODA",
        "Grant equivalents": "Total ODA",
        "Disbursements, grants": "Grants",
    }

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
    non_eu_financing = add_currencies_and_prices(non_eu_financing, base_year=FINANCING_TIME["base"])

    eu27_financing = get_group_total(
        non_eu_financing,
        EU_COUNTRIES,
        group_cols=["year", "indicator_name", "currency", "price"],
        group_name="EU27 countries"
    )
    all_bilateral_financing = get_group_total(
        non_eu_financing,
        BILATERAL_DONORS,
        group_cols=["year", "indicator_name", "currency", "price"],
        group_name="All bilateral donors"
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
    financing["type"] = np.where(
        financing["year"] < GRANT_EQUIVALENT_START_YEAR, "Flows", "Grant equivalents"
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
    financing = add_share_of_gni(financing)

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
    )
    parquet_to_stdout(df)
