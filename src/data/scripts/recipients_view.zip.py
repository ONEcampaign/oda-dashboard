"""Builds the recipients view: who gives to whom, by year.

Shape of the pipeline:
    1. DAC2A bilateral (line 206) and imputed multilateral (line 106) flows in net
       disbursements, Part I only, for every provider and the pinned recipient list:
       countries and the groups DAC2A publishes (continents, regions, income) alike
    2. the EU27 + institutions bloc, whose institutions are weighted so member
       contributions to them are not counted twice (analysis_tools.eu)
    3. recipient groups summed before the donor groups in DONOR_GROUPS, so every donor
       aggregate covers them: the Least Developed Countries (resolvekit's UN list, as in the
       CRS views), Sahel and France priority
    4. shares from both perspectives: of what a recipient received, and of what a donor gave
    5. one zip on stdout for Observable: the data as parquet and its dropdown options, with
       the provenance of every table read

Output is keyed by name: year, donor_name, recipient_name, indicator_name.
"""

import oda_data as oda
import pandas as pd

from src.data.analysis_tools.eu import eui_weights, weight_eu_institutions
from src.data.analysis_tools.oda import ProvenanceLog, open_context
from src.data.analysis_tools.outputs import build_view_options, view_archive_to_stdout
from src.data.analysis_tools.recipients import (
    aggregate_recipient_names,
    canonical_recipients,
    check_recipient_sums,
    read_dac2a_part_i,
    read_ldc_members,
)
from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_donor_and_recipient_shares,
    build_donor_group_totals,
    convert_values_to_units,
    drop_empty_series,
    drop_empty_values,
    get_group_total,
    widen_currency_price,
)
from src.data.config import (
    BASE_TIME,
    BILATERAL,
    DAC2A_RECIPIENT_AGGREGATES,
    DAC2A_RECIPIENTS,
    DEFAULT_DONOR,
    DEFAULT_RECIPIENT,
    DONORS_ORDER,
    EU27_EUI_NAME,
    EU_TOTAL,
    FRANCE_PRIORITY_RECIPIENTS,
    IMPUTED_MULTILATERAL,
    LDC_LABEL,
    PROVIDERS,
    RECIPIENTS_LINES,
    RECIPIENTS_ORDER,
    SAHEL_RECIPIENTS,
    logger,
)

YEARS: range = range(BASE_TIME["start"], BASE_TIME["end"] + 1)
# DAC2A lines 206 and 106 are net disbursements; the EU weight must use the same basis.
NET: str = "net_disbursement"

VIEW_KEYS: list[str] = ["year", "donor_name", "recipient_name", "indicator_name"]
# Columns identifying a row apart from the donor, with currency and price. recipient_code
# is kept so recipient group totals (Sahel, France priority) select their members by code.
RECIPIENT_COLS: list[str] = [
    "year",
    "recipient_code",
    "recipient_name",
    "indicator_name",
    "currency",
    "price",
]


def read_dac2a(provenance: ProvenanceLog) -> pd.DataFrame:
    """Read DAC2A flows for every provider and pinned recipient, with display names.

    Args:
        provenance: Log to record the DAC2A release in.

    Returns:
        One row per year, donor, recipient and indicator name, in current USD millions.

    Raises:
        ValueError: If a donor's countries sum above its ODA eligible countries total.
    """
    dac2a = canonical_recipients(
        read_dac2a_part_i(
            lines=RECIPIENTS_LINES,
            years=YEARS,
            providers=PROVIDERS,
            recipients=DAC2A_RECIPIENTS,
            provenance=provenance,
        )
    )
    check_recipient_sums(dac2a)
    # Zero rows carry nothing, and some fall in donor-years DAC1 has no conversion factor
    # for (Liechtenstein's early years), which the conversion would refuse.
    dac2a = drop_empty_values(dac2a, "DAC2A")
    return dac2a[
        [
            "year",
            "donor_code",
            "donor_name",
            "recipient_code",
            "recipient_name",
            "indicator_name",
            "value",
        ]
    ]


def build_eu27_eui_total(
    converted: pd.DataFrame, weights: dict[int, float]
) -> pd.DataFrame:
    """Sum the EU27 + institutions bloc, with the institutions weighted.

    Args:
        converted: Individual donors' rows in every currency and price.
        weights: From eui_weights, on the net disbursement basis.

    Returns:
        The bloc's rows, named EU27_EUI_NAME, with recipient_code kept.
    """
    members = converted.loc[lambda d: d["donor_code"].isin(EU_TOTAL)]
    return get_group_total(
        weight_eu_institutions(members, weights),
        EU_TOTAL,
        group_cols=RECIPIENT_COLS,
        group_name=EU27_EUI_NAME,
    )


def combined_recipients(
    ctx: oda.Context, provenance: ProvenanceLog
) -> tuple[pd.DataFrame, list[str]]:
    """Assemble the recipients view from its parts.

    Args:
        ctx: From open_context.
        provenance: Log to record every read and the conversion factors in.

    Returns:
        (wide frame keyed by year, donor_name, recipient_name and indicator_name, with one
        column per currency and price pair plus the two share columns; the names of the
        DAC2A recipient groups it contains, for the dropdown ordering).
    """
    dac2a = read_dac2a(provenance)
    group_names = aggregate_recipient_names(dac2a)

    converted = add_currencies_and_prices(
        dac2a, base_year=BASE_TIME["base"], provenance=provenance
    )
    eu27_eui = build_eu27_eui_total(
        converted, eui_weights(ctx, YEARS, basis=NET, provenance=provenance)
    )

    # Reported donors (carrying donor_code) and the EU27 + institutions bloc (identified by
    # name only). Both must be in place before recipient groups are aggregated, so that
    # every donor gets LDC, Sahel and France priority rows.
    donors_long = pd.concat([converted, eu27_eui], ignore_index=True)

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
    ldc_members = read_ldc_members(
        years=YEARS,
        recipients=dac2a.loc[
            ~dac2a["recipient_code"].isin(DAC2A_RECIPIENT_AGGREGATES), "recipient_code"
        ],
        provenance=provenance,
    )
    recipient_groups = [
        get_group_total(
            donors_long,
            members,
            column="recipient",
            group_cols=recipient_group_cols,
            group_name=name,
        )
        for name, members in (
            (LDC_LABEL, ldc_members),
            ("Sahel countries", SAHEL_RECIPIENTS),
            ("France priority countries", FRANCE_PRIORITY_RECIPIENTS),
        )
    ]
    with_recipient_groups = pd.concat(
        [donors_long, *recipient_groups], ignore_index=True
    )

    # Donor group totals are computed from the extended dataset so that every group has
    # rows for every recipient, the recipient groups included. "All bilateral donors"
    # is also the pct_total_recipient denominator.
    donor_group_cols = ["year", "recipient_name", "indicator_name", "currency", "price"]
    recipients = pd.concat(
        [
            with_recipient_groups,
            *build_donor_group_totals(with_recipient_groups, donor_group_cols).values(),
        ],
        ignore_index=True,
    )

    recipients = drop_empty_series(
        recipients.drop(columns=["donor_code", "recipient_code"]),
        VIEW_KEYS,
        "recipients",
    )
    recipients = widen_currency_price(
        df=recipients,
        index_cols=tuple(VIEW_KEYS),
    )
    recipients = add_donor_and_recipient_shares(recipients)

    # Integers in units compress far better than floats in millions.
    return convert_values_to_units(recipients), group_names


def main() -> None:
    """Build the view and write it to stdout as Observable's zip archive."""
    logger.info("Generating recipients table...")
    provenance = ProvenanceLog()
    with open_context() as ctx:
        df, group_names = combined_recipients(ctx, provenance)
    recipients_order = [
        *RECIPIENTS_ORDER,
        *(n for n in group_names if n not in RECIPIENTS_ORDER),
        "France priority countries",
        "Sahel countries",
    ]
    options = build_view_options(
        df=df,
        columns={
            "donor_name": DONORS_ORDER,
            "recipient_name": recipients_order,
            "indicator_name": [],
            "year": [],
        },
        base_year=BASE_TIME["base"],
        extra={"provenance": provenance.to_dict()},
        defaults={
            "donor_name": DEFAULT_DONOR,
            "recipient_name": DEFAULT_RECIPIENT,
            "indicator_name": [BILATERAL, IMPUTED_MULTILATERAL],
        },
    )
    view_archive_to_stdout(df, options)


if __name__ == "__main__":
    main()
