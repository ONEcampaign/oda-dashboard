import pandas as pd
from oda_data import OECDClient
from oda_data.indicators.research.eu import get_eui_plus_bilateral_providers_indicator

from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    get_group_total,
    widen_currency_price,
)
from src.data.config import (
    logger,
    BASE_TIME,
    RECIPIENTS_INDICATORS,
    ALL_DONORS,
    AGGREGATE_DONORS,
    EU_TOTAL,
    EU_COUNTRIES,
    EU_INSTITUTIONS,
    EUI_BILATERAL_NAME,
    BILATERAL_DONORS,
    ALL_RECIPIENTS,
    AGGREGATE_RECIPIENTS,
    SAHEL_RECIPIENTS,
    FRANCE_PRIORITY_RECIPIENTS,
    DONORS_ORDER,
    RECIPIENTS_ORDER
)
from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
    apply_name_overrides,
    parquet_to_stdout,
    convert_values_to_units,
    generate_view_options,
)

set_cache_dir(oda_data=True, pydeflate=True)


def _add_pct_column(
    df: pd.DataFrame,
    filter_col: str,
    filter_val: str,
    merge_cols: list[str],
    pct_col: str,
) -> pd.DataFrame:
    """Compute each row's value_usd_current as a share of a reference total.

    The reference total is the sum of value_usd_current across ALL indicators
    for the entity identified by filter_col == filter_val, grouped by merge_cols.
    Summing across indicators means the two indicator percentages for any
    (year, donor, recipient) pair sum to that entity's combined share, never
    exceeding 100%.
    """
    total = (
        df.loc[lambda d: d[filter_col] == filter_val]
        .groupby(merge_cols, dropna=False, observed=True)["value_usd_current"]
        .sum()
        .reset_index()
        .rename(columns={"value_usd_current": "total_oda"})
    )
    merged = df.merge(total, on=merge_cols, how="left")
    merged[pct_col] = (merged["value_usd_current"] / merged["total_oda"]).round(6)
    return merged.drop(columns=["total_oda"])


def get_dac2a():
    dac2a_raw = OECDClient(
        years=range(BASE_TIME["start"], BASE_TIME["end"] + 1),
        # EU Institutions is reported separately from the bilateral providers, and is
        # selectable in its own right. It is deliberately absent from BILATERAL_DONORS
        # and EU_COUNTRIES, so it never affects those group totals.
        providers=list(ALL_DONORS | EU_INSTITUTIONS),
        recipients=list(ALL_RECIPIENTS),
        use_bulk_download=False,
    ).get_indicators(list(RECIPIENTS_INDICATORS.keys()))

    dac2a = (
        dac2a_raw.groupby(
            ["year", "donor_code", "donor_name", "recipient_code", "recipient_name", "one_indicator"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator_name=lambda d: d["one_indicator"].map(RECIPIENTS_INDICATORS))
        .drop(columns=["one_indicator"])
    )

    dac2a = apply_name_overrides(dac2a, AGGREGATE_DONORS, "donor")
    dac2a = apply_name_overrides(dac2a, AGGREGATE_RECIPIENTS, "recipient")

    return dac2a


def get_dac2a_eui_eu27() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the EU27 + institutions aggregate and the EU institutions bilateral series.

    get_eui_plus_bilateral_providers_indicator scales EU institutions' values by the share
    of their spending that is not funded by EU27 member contributions, so its rows can be
    summed without double counting those contributions. Summed over all providers this
    gives the EU27 + institutions aggregate; the scaled EU institutions rows on their own
    are the only part of EU institutions' spending that can be added to bilateral
    providers without double counting.

    Returns:
        (EU27 & EU Institutions aggregate, EU institutions bilateral-equivalent series).
    """
    dac2a_client = OECDClient(
        years=range(BASE_TIME["start"], BASE_TIME["end"] + 1),
        providers=list(EU_TOTAL),
        recipients=list(ALL_RECIPIENTS),
        use_bulk_download=False,
    )

    eui_eu27_dac2a_raw = get_eui_plus_bilateral_providers_indicator(
        dac2a_client, indicator=list(RECIPIENTS_INDICATORS.keys())
    )

    eui_eu27_dac2a_raw = apply_name_overrides(eui_eu27_dac2a_raw, AGGREGATE_RECIPIENTS, "recipient")

    eui_eu27_dac2a_converted = add_currencies_and_prices(
        eui_eu27_dac2a_raw, base_year=BASE_TIME["base"]
    ).assign(indicator_name=lambda d: d["one_indicator"].map(RECIPIENTS_INDICATORS))

    # recipient_code is kept so that recipient group totals (Sahel, France priority) can
    # be derived for these series too; it is dropped before the pivot.
    group_cols = [
        "year", "donor_name", "recipient_code", "recipient_name", "indicator_name",
        "currency", "price",
    ]

    eui_eu27_dac2a = (
        eui_eu27_dac2a_converted
        .assign(donor_name="EU27 & EU Institutions")
        .groupby(group_cols, dropna=False, observed=True)["value"].sum().reset_index()
    )

    eui_bilateral = (
        eui_eu27_dac2a_converted
        .loc[lambda d: d["donor_code"].isin(EU_INSTITUTIONS)]
        .assign(donor_name=EUI_BILATERAL_NAME)
        .groupby(group_cols, dropna=False, observed=True)["value"].sum().reset_index()
    )

    return eui_eu27_dac2a, eui_bilateral


def combined_recipients():
    dac2a = get_dac2a()

    dac2a_converted = add_currencies_and_prices(dac2a, base_year=BASE_TIME["base"])

    eui_eu27_dac2a, eui_bilateral = get_dac2a_eui_eu27()

    # Reported donors (carrying donor_code) and the EU-institution aggregates (identified
    # by name only). All must be in place before recipient groups are aggregated, so that
    # every donor gets Sahel and France priority rows.
    donors_long = pd.concat(
        [dac2a_converted, eui_eu27_dac2a, eui_bilateral], ignore_index=True
    )

    # Recipient group totals must keep donor_code: the donor group totals below select
    # their members by code, and rows without one are silently excluded from them.
    recipient_group_cols = [
        "year", "donor_code", "donor_name", "indicator_name", "currency", "price",
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

    with_recipient_groups = pd.concat([
        donors_long,
        sahel_recipients,
        france_priority_recipients,
    ], ignore_index=True)

    # Donor group totals are computed from the extended dataset so that
    # All bilateral / EU27 rows exist for every recipient including Sahel
    # and France priority — required for pct_total_recipient denominators.
    donor_group_cols = ["year", "recipient_name", "indicator_name", "currency", "price"]
    eu27_recipients = get_group_total(
        with_recipient_groups,
        EU_COUNTRIES,
        group_cols=donor_group_cols,
        group_name="EU27 countries",
    )
    # "All bilateral donors" covers the reported bilateral providers plus EU institutions'
    # bilateral-equivalent spending. EU institutions are not in BILATERAL_DONORS, so they
    # are added explicitly here; using the scaled series rather than the full EU
    # Institutions total keeps EU member contributions from being counted twice. This is
    # also the pct_total_recipient denominator, so it must stay double-count free.
    all_bilateral_rows = pd.concat([
        with_recipient_groups.loc[lambda d: d["donor_code"].isin(BILATERAL_DONORS)],
        with_recipient_groups.loc[lambda d: d["donor_name"] == EUI_BILATERAL_NAME],
    ])
    all_bilateral_recipients = (
        all_bilateral_rows
        .groupby(donor_group_cols, dropna=False, observed=True)["value"]
        .sum()
        .reset_index()
        .assign(donor_name="All bilateral donors")
    )

    recipients = pd.concat([
        with_recipient_groups,
        eu27_recipients,
        all_bilateral_recipients,
    ], ignore_index=True)

    recipients = recipients.loc[
        lambda d: d["value"].notna() & (d["value"] != 0)
    ]

    # The EU institutions bilateral series exists only to keep "All bilateral donors" (and
    # therefore the pct_total_recipient denominator) free of double counting. That total is
    # already aggregated above, so dropping the series here removes it from the view
    # without changing any published value.
    recipients = recipients.loc[lambda d: d["donor_name"] != EUI_BILATERAL_NAME]

    recipients = recipients.drop(columns=["donor_code", "recipient_code"], errors="ignore")

    recipients = widen_currency_price(
        df=recipients,
        index_cols=("year", "donor_name", "recipient_name", "indicator_name"),
    )

    recipients = _add_pct_column(
        recipients,
        filter_col="donor_name",
        filter_val="All bilateral donors",
        merge_cols=["year", "recipient_name"],
        pct_col="pct_total_recipient",
    )
    recipients = _add_pct_column(
        recipients,
        filter_col="recipient_name",
        filter_val="ODA eligible countries",
        merge_cols=["year", "donor_name"],
        pct_col="pct_total_donor",
    )

    recipients = convert_values_to_units(recipients)

    return recipients


if __name__ == "__main__":
    logger.info("Generating recipients table...")
    df = combined_recipients()
    generate_view_options(
        df=df,
        columns={
            "donor_name": DONORS_ORDER,
            "recipient_name": RECIPIENTS_ORDER,
            "indicator_name": [],
            "year": [],
        },
        base_year=BASE_TIME["base"],
        file_name="recipients_view_options.json",
    )
    parquet_to_stdout(df)
