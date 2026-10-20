"""Builds the financing view: ODA totals and their components, by donor and year.

Shape of the pipeline:
    1. DAC1 aggregates, private sector instruments and in-donor items, read in net flows up to
       GRANT_EQUIVALENT_START_YEAR and grant equivalents from then on
    2. the grants / non-grants split, derived from one indicator read under two measures
    3. the EU27 + institutions aggregate, which oda_data weights so that member states'
       contributions to the institutions are not counted twice
    4. donor aggregates summed locally, then shares of total ODA and of GNI
    5. one zip on stdout for Observable: the data as parquet and its dropdown options

Output is keyed by name: year, donor_name, indicator_name, type.
"""

from collections.abc import Callable

import pandas as pd
from oda_data import OECDClient
from oda_data.indicators.research.eu import get_eui_plus_bilateral_providers_indicator

from src.data.analysis_tools.financing import (
    drop_grants_split,
    resolve_indicator_duplicates,
    split_grants,
    years_missing_grants,
)
from src.data.analysis_tools.naming import map_config_values
from src.data.analysis_tools.outputs import (
    build_view_options,
    set_cache_dir,
    view_archive_to_stdout,
)
from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_share_of_gni,
    add_share_of_total_oda,
    build_donor_group_totals,
    convert_values_to_units,
    drop_empty_values,
    get_member_gni,
    widen_currency_price,
)
from src.data.config import (
    AGGREGATE_FINANCING_INDICATORS,
    ALL_FINANCING_INDICATORS,
    CORE_ODA,
    DEFAULT_DONOR,
    DONOR_GROUPS,
    DONORS_ORDER,
    EU27_EUI_LAST_YEAR,
    EU27_EUI_NAME,
    EU_TOTAL,
    FINANCING_INDICATORS_ORDER,
    FINANCING_TIME,
    FINANCING_TYPES,
    GRANT_EQUIVALENT_START_YEAR,
    IN_DONOR_FINANCING_INDICATORS,
    PROVIDERS,
    PSI,
    PSI_APPROACH_INDICATORS,
    PSI_GRANT_EQUIVALENT_START_YEAR,
    PSI_TOTAL_INDICATORS,
    PSI_TRANSITION_YEARS,
    TOTAL_ODA,
    logger,
)

FLOW_YEARS: range = range(FINANCING_TIME["start"], GRANT_EQUIVALENT_START_YEAR)
GE_YEARS: range = range(GRANT_EQUIVALENT_START_YEAR, FINANCING_TIME["end"] + 1)
ALL_YEARS: range = range(FINANCING_TIME["start"], FINANCING_TIME["end"] + 1)
PSI_FLOW_YEARS: range = range(FINANCING_TIME["start"], PSI_GRANT_EQUIVALENT_START_YEAR)
PSI_GE_YEARS: range = range(PSI_GRANT_EQUIVALENT_START_YEAR, FINANCING_TIME["end"] + 1)
# Read as net flows in every year.
NET_FLOW_INDICATORS: list[str] = list(
    IN_DONOR_FINANCING_INDICATORS | PSI_APPROACH_INDICATORS
)
GRANTS_INDICATOR: list[str] = ["DAC1.10.1010"]

# Turns a configured client and indicator codes into raw rows.
Reader = Callable[[OECDClient, list[str]], pd.DataFrame]


def read_indicators(client: OECDClient, indicators: list[str]) -> pd.DataFrame:
    """Read indicators for each provider on its own."""
    return client.get_indicators(indicators)


def read_eui_eu27(client: OECDClient, indicators: list[str]) -> pd.DataFrame:
    """Read indicators for the EU27 + institutions aggregate.

    oda_data scales the institutions' spending by the share not funded by member state
    contributions, so summing members and institutions does not double count.
    """
    return get_eui_plus_bilateral_providers_indicator(client, indicator=indicators)


def _read(
    read: Reader,
    providers: dict[int, str],
    years: range,
    measure: str | list[str],
    indicators: list[str],
) -> pd.DataFrame:
    """Build a bulk-download client, read indicators through it and label their type.

    The type follows the headline measure, the first when several are read together.
    """
    client = OECDClient(
        years=years, providers=list(providers), measure=measure, use_bulk_download=True
    )
    headline = measure if isinstance(measure, str) else measure[0]
    return read(client, indicators).assign(type=FINANCING_TYPES[headline])


def read_dac1(read: Reader, providers: dict[int, str]) -> pd.DataFrame:
    """Read each DAC1 indicator in the measure it is reported in, which sets its type.

    The aggregates switch to grant equivalents at GRANT_EQUIVALENT_START_YEAR. In-donor items
    stay in net flows throughout: preliminary data for the latest year report them only as
    flows, and for earlier years their grant equivalents equal their flows, since they are
    grants. Total PSI was reported under the provisional methods, as net flows, until the
    revised methods began in PSI_GRANT_EQUIVALENT_START_YEAR, and its split by approach only
    ever covers those provisional-method amounts.

    Args:
        read: How to read each client.
        providers: Donor codes to read.

    Returns:
        Raw rows, with duplicates from renumbered indicator codes removed.
    """
    aggregates = list(AGGREGATE_FINANCING_INDICATORS)
    psi_total = list(PSI_TOTAL_INDICATORS)
    parts = [
        _read(read, providers, ALL_YEARS, "net_disbursement", NET_FLOW_INDICATORS),
        _read(read, providers, FLOW_YEARS, "net_disbursement", aggregates),
        _read(read, providers, GE_YEARS, "grant_equivalent", aggregates),
        _read(read, providers, PSI_FLOW_YEARS, "net_disbursement", psi_total),
        _read(read, providers, PSI_GE_YEARS, "grant_equivalent", psi_total),
    ]
    return resolve_indicator_duplicates(pd.concat(parts, ignore_index=True))


def read_grants(read: Reader, providers: dict[int, str]) -> pd.DataFrame:
    """Read Total ODA under its headline measure and the grant-only measure.

    Args:
        read: How to read each client.
        providers: Donor codes to read.

    Returns:
        Raw DAC1.10.1010 rows for split_grants.
    """
    # The headline measure comes first: get_eui_plus_bilateral_providers_indicator derives
    # the EU institutions weight from measure[0] only. With the grants measure first the
    # weight is computed on grants (negative in some years), which understates the EUI share
    # and breaks Grants + Non-grants == Total ODA for that aggregate.
    parts = [
        _read(
            read,
            providers,
            FLOW_YEARS,
            ["net_disbursement", "net_disbursement_grant"],
            GRANTS_INDICATOR,
        ),
        _read(
            read,
            providers,
            GE_YEARS,
            ["grant_equivalent", "net_disbursement_grant"],
            GRANTS_INDICATOR,
        ),
    ]
    return pd.concat(parts, ignore_index=True)


def get_dac1() -> pd.DataFrame:
    """Read the DAC1 indicators for each provider.

    Summing by name adds up the codes that are parts of one figure (SUMMED_FINANCING_NAMES);
    every other name has one code per donor and year once duplicates are resolved.

    Returns:
        One row per year, donor and indicator name.
    """
    return (
        read_dac1(read_indicators, PROVIDERS)
        .assign(
            indicator_name=lambda d: map_config_values(
                d["one_indicator"], ALL_FINANCING_INDICATORS, what="Indicator codes"
            )
        )
        .groupby(
            ["year", "donor_code", "donor_name", "type", "indicator_name"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
    )


def get_grants() -> pd.DataFrame:
    """Split each provider's total ODA into grants and non-grants.

    Returns:
        Long-form rows for the two derived indicator names.
    """
    return split_grants(
        read_grants(read_indicators, PROVIDERS),
        ["year", "donor_code", "donor_name", "type"],
    )


def get_eui_eu27_dac1() -> pd.DataFrame:
    """Read the DAC1 indicators for the EU27 + institutions aggregate.

    Returns:
        One row per year, indicator, currency and price for the aggregate.
    """
    converted = add_currencies_and_prices(
        read_dac1(read_eui_eu27, EU_TOTAL), base_year=FINANCING_TIME["base"]
    )
    return (
        converted.assign(
            indicator_name=lambda d: map_config_values(
                d["one_indicator"], ALL_FINANCING_INDICATORS, what="Indicator codes"
            ),
            donor_name=EU27_EUI_NAME,
        )
        .groupby(
            ["year", "donor_name", "type", "currency", "price", "indicator_name"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
    )


def get_eui_eu27_grants() -> pd.DataFrame:
    """Split the EU27 + institutions aggregate into grants and non-grants.

    Returns:
        Long-form rows for the two derived indicator names, for the aggregate.
    """
    converted = add_currencies_and_prices(
        read_grants(read_eui_eu27, EU_TOTAL), base_year=FINANCING_TIME["base"]
    )
    return (
        split_grants(converted, ["year", "donor_code", "type", "currency", "price"])
        .groupby(
            ["year", "indicator_name", "type", "currency", "price"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
        .assign(donor_name=EU27_EUI_NAME)
    )


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
        non_eu_financing, ["year", "indicator_name", "type", "currency", "price"]
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

    # Every row needs the type it was read in, and one per year: two would split a series.
    if financing["type"].isna().any():
        raise ValueError("Financing rows without a type: a part skipped _read's label")
    types_per_series = financing.groupby(
        ["year", "donor_name", "indicator_name"], observed=True
    )["type"].nunique()
    if not (clashes := types_per_series[types_per_series > 1]).empty:
        raise ValueError(
            f"Financing series read in more than one measure: {clashes.index.tolist()[:10]}"
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
    set_cache_dir(oda_data=True, pydeflate=True)
    logger.info("Generating financing table...")
    df = get_financing_data()
    options = build_view_options(
        df=df,
        columns={
            "donor_name": DONORS_ORDER,
            "indicator_name": FINANCING_INDICATORS_ORDER,
            "year": [],
        },
        base_year=FINANCING_TIME["base"],
        extra={
            "eu27_eui_last_year": EU27_EUI_LAST_YEAR,
            "psi_transition_years": PSI_TRANSITION_YEARS,
        },
        defaults={"donor_name": DEFAULT_DONOR, "indicator_name": TOTAL_ODA},
        names={
            "indicator_name": {
                "total_oda": TOTAL_ODA,
                "core_oda": CORE_ODA,
                "psi": PSI,
            },
            "donor_name": {"eu27_eui": EU27_EUI_NAME},
        },
    )
    view_archive_to_stdout(df, options)
