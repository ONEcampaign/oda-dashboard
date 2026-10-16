"""Builds the recipients view: who gives to whom, by year.

Shape of the pipeline:
    1. DAC2A bilateral and imputed multilateral flows, for reported donors and every recipient
       DAC2A reports, countries and its published groups (continents, regions, income) alike
    2. the EU27 + institutions aggregate, weighted by oda_data so member contributions to the
       institutions are not counted twice
    3. recipient groups (Sahel, France priority) summed before the donor groups in
       DONOR_GROUPS, so every donor aggregate covers them
    4. shares from both perspectives: of what a recipient received, and of what a donor gave
    5. one parquet on stdout for Observable, plus the dropdown options beside it

Output is keyed by name: year, donor_name, recipient_name, indicator_name.
"""

import pandas as pd
from oda_data import OECDClient
from oda_data.indicators.research.eu import get_eui_plus_bilateral_providers_indicator

from src.data.analysis_tools.naming import (
    map_indicator_names,
)
from src.data.analysis_tools.outputs import (
    generate_view_options,
    parquet_to_stdout,
    set_cache_dir,
)
from src.data.analysis_tools.recipients import (
    aggregate_recipient_names,
    canonical_recipients,
)
from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_donor_and_recipient_shares,
    build_donor_group_totals,
    convert_values_to_units,
    drop_empty_values,
    get_group_total,
    widen_currency_price,
)
from src.data.config import (
    BASE_TIME,
    DONORS_ORDER,
    EU27_EUI_NAME,
    EU_TOTAL,
    FRANCE_PRIORITY_RECIPIENTS,
    PROVIDERS,
    RECIPIENTS_INDICATORS,
    RECIPIENTS_ORDER,
    SAHEL_RECIPIENTS,
    logger,
)


def get_dac2a() -> pd.DataFrame:
    """Read DAC2A flows for every reported donor and recipient.

    Returns:
        One row per year, donor, recipient and indicator name, with names made canonical.
    """
    dac2a_raw = OECDClient(
        years=range(BASE_TIME["start"], BASE_TIME["end"] + 1),
        # Individual providers only: donor aggregates are summed from them below.
        providers=list(PROVIDERS),
        recipients=None,  # every DAC2A recipient, groups included
        use_bulk_download=False,
    ).get_indicators(list(RECIPIENTS_INDICATORS.keys()))

    dac2a = (
        dac2a_raw.groupby(
            [
                "year",
                "donor_code",
                "donor_name",
                "recipient_code",
                "recipient_name",
                "one_indicator",
            ],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
        .assign(
            indicator_name=lambda d: map_indicator_names(
                d["one_indicator"], RECIPIENTS_INDICATORS
            )
        )
        .drop(columns=["one_indicator"])
    )

    return canonical_recipients(dac2a)


def get_dac2a_eui_eu27() -> pd.DataFrame:
    """Build the EU27 + institutions aggregate.

    get_eui_plus_bilateral_providers_indicator scales EU institutions' values by the share
    of their spending that is not funded by EU27 member contributions, so its rows can be
    summed without double counting those contributions.

    Returns:
        The EU27 & EU Institutions aggregate, with recipient_code kept.
    """
    dac2a_client = OECDClient(
        years=range(BASE_TIME["start"], BASE_TIME["end"] + 1),
        providers=list(EU_TOTAL),
        recipients=None,  # every DAC2A recipient, groups included
        use_bulk_download=False,
    )

    eui_eu27_dac2a_raw = get_eui_plus_bilateral_providers_indicator(
        dac2a_client, indicator=list(RECIPIENTS_INDICATORS.keys())
    )

    eui_eu27_dac2a_raw = canonical_recipients(eui_eu27_dac2a_raw)

    eui_eu27_dac2a_converted = add_currencies_and_prices(
        eui_eu27_dac2a_raw, base_year=BASE_TIME["base"]
    ).assign(
        indicator_name=lambda d: map_indicator_names(
            d["one_indicator"], RECIPIENTS_INDICATORS
        )
    )

    # recipient_code is kept so that recipient group totals (Sahel, France priority) can
    # be derived for these series too; it is dropped before the pivot.
    group_cols = [
        "year",
        "donor_name",
        "recipient_code",
        "recipient_name",
        "indicator_name",
        "currency",
        "price",
    ]

    eui_eu27_dac2a = (
        eui_eu27_dac2a_converted.assign(donor_name=EU27_EUI_NAME)
        .groupby(group_cols, dropna=False, observed=True)["value"]
        .sum()
        .reset_index()
    )

    return eui_eu27_dac2a


def combined_recipients() -> tuple[pd.DataFrame, list[str]]:
    """Assemble the recipients view from its parts.

    Returns:
        (wide frame keyed by year, donor_name, recipient_name and indicator_name, with one
        column per currency and price pair plus the two share columns; the names of the
        DAC2A recipient groups it contains, for the dropdown ordering).
    """
    dac2a = get_dac2a()
    group_names = aggregate_recipient_names(dac2a)

    dac2a_converted = add_currencies_and_prices(dac2a, base_year=BASE_TIME["base"])

    eui_eu27_dac2a = get_dac2a_eui_eu27()

    # Reported donors (carrying donor_code) and the EU27 + institutions aggregate
    # (identified by name only). Both must be in place before recipient groups are
    # aggregated, so that every donor gets Sahel and France priority rows.
    donors_long = pd.concat([dac2a_converted, eui_eu27_dac2a], ignore_index=True)

    # Recipient group totals must keep donor_code: the donor group totals below select
    # their members by code, and rows without one are silently excluded from them.
    recipient_group_cols = [
        "year",
        "donor_code",
        "donor_name",
        "indicator_name",
        "currency",
        "price",
    ]
    sahel_recipients = get_group_total(
        donors_long,
        SAHEL_RECIPIENTS,
        column="recipient",
        group_cols=recipient_group_cols,
        group_name="Sahel countries",
    )
    france_priority_recipients = get_group_total(
        donors_long,
        FRANCE_PRIORITY_RECIPIENTS,
        column="recipient",
        group_cols=recipient_group_cols,
        group_name="France priority countries",
    )

    with_recipient_groups = pd.concat(
        [
            donors_long,
            sahel_recipients,
            france_priority_recipients,
        ],
        ignore_index=True,
    )

    # Donor group totals are computed from the extended dataset so that every group has
    # rows for every recipient, Sahel and France priority included. "All bilateral donors"
    # is also the pct_total_recipient denominator.
    donor_group_cols = ["year", "recipient_name", "indicator_name", "currency", "price"]
    recipients = pd.concat(
        [
            with_recipient_groups,
            *build_donor_group_totals(with_recipient_groups, donor_group_cols).values(),
        ],
        ignore_index=True,
    )

    recipients = drop_empty_values(recipients, "recipients")

    recipients = recipients.drop(
        columns=["donor_code", "recipient_code"], errors="ignore"
    )

    recipients = widen_currency_price(
        df=recipients,
        index_cols=("year", "donor_name", "recipient_name", "indicator_name"),
    )

    recipients = add_donor_and_recipient_shares(recipients)

    recipients = convert_values_to_units(recipients)

    return recipients, group_names


if __name__ == "__main__":
    set_cache_dir(oda_data=True, pydeflate=True)
    logger.info("Generating recipients table...")
    df, group_names = combined_recipients()
    recipients_order = [
        *RECIPIENTS_ORDER,
        *(n for n in group_names if n not in RECIPIENTS_ORDER),
        "France priority countries",
        "Sahel countries",
    ]
    generate_view_options(
        df=df,
        columns={
            "donor_name": DONORS_ORDER,
            "recipient_name": recipients_order,
            "indicator_name": [],
            "year": [],
        },
        base_year=BASE_TIME["base"],
        file_name="recipients_view_options.json",
    )
    parquet_to_stdout(df)
