"""Builds the financing view: ODA totals and their components, by donor and year.

Shape of the pipeline:
    1. DAC1 aggregates on oda-data's headline basis (net flows before
       GRANT_EQUIVALENT_START_YEAR, grant equivalents from then on), total private sector
       instruments in net flows then grant equivalents, and the in-donor items and the PSI
       split by approach in net flows; each row's type is the basis it was read on
    2. the grants / non-grants split of Total ODA, from the grants flow
    3. donor aggregates summed locally, including the EU27 + institutions bloc, whose
       institutions are weighted so member contributions to them are not counted twice
       (analysis_tools.eu)
    4. shares of total ODA and of GNI
    5. one zip on stdout for Observable: the data as parquet and its dropdown options, with
       the provenance of every table read

Output is keyed by name: year, donor_name, indicator_name, type.
"""

import oda_data as oda
import pandas as pd

from src.data.analysis_tools.eu import eui_weights, weight_eu_institutions
from src.data.analysis_tools.financing import (
    check_one_type_per_series,
    drop_grants_split,
    split_grants,
    sum_by_name,
    to_financing_rows,
    years_missing_grants,
)
from src.data.analysis_tools.naming import map_config_values
from src.data.analysis_tools.oda import ProvenanceLog, open_context, run_query
from src.data.analysis_tools.outputs import build_view_options, view_archive_to_stdout
from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_share_of_gni,
    add_share_of_total_oda,
    build_donor_group_totals,
    convert_values_to_units,
    drop_empty_series,
    get_group_total,
    get_member_gni,
    widen_currency_price,
)
from src.data.config import (
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
    GRANTS_BASIS,
    GRANTS_FLOW,
    HEADLINE_FINANCING_INDICATORS,
    IN_DONOR_FINANCING_LINES,
    PARTIAL_YEAR_FINANCING_INDICATORS,
    PROVIDERS,
    PSI,
    PSI_APPROACH_LINES,
    PSI_FLOW_INDICATOR,
    PSI_GRANT_EQUIVALENT_LINES,
    PSI_GRANT_EQUIVALENT_START_YEAR,
    PSI_TRANSITION_YEARS,
    TOTAL_ODA,
    logger,
)

NET: str = "net_disbursement"
GRANT_EQUIVALENT: str = "grant_equivalent"

ALL_YEARS: range = range(FINANCING_TIME["start"], FINANCING_TIME["end"] + 1)
PSI_FLOW_YEARS: range = range(FINANCING_TIME["start"], PSI_GRANT_EQUIVALENT_START_YEAR)
PSI_GE_YEARS: range = range(PSI_GRANT_EQUIVALENT_START_YEAR, FINANCING_TIME["end"] + 1)
# The years the EU27 + institutions bloc is published for, on each basis it is read on.
EU27_EUI_YEARS: dict[str, range] = {
    NET: range(FINANCING_TIME["start"], EU27_EUI_LAST_YEAR + 1),
    GRANT_EQUIVALENT: range(GRANT_EQUIVALENT_START_YEAR, EU27_EUI_LAST_YEAR + 1),
}
VIEW_KEYS: tuple[str, ...] = ("year", "donor_name", "indicator_name", "type")
NET_FLOW_LINES: dict[int, str] = IN_DONOR_FINANCING_LINES | PSI_APPROACH_LINES

# Every row of the view is labelled by basis, and the EU weight must use the same one.
if set(EU27_EUI_YEARS) != set(FINANCING_TYPES):
    raise ValueError("EU27_EUI_YEARS must cover every basis in FINANCING_TYPES")


def read_dac1(ctx: oda.Context, provenance: ProvenanceLog) -> pd.DataFrame:
    """Read each DAC1 indicator for each provider, on the basis it is reported on.

    The aggregates follow oda-data's headline basis. In-donor items stay in net flows
    throughout: preliminary data for the latest year report them only as flows, and for
    earlier years their grant equivalents equal their flows, since they are grants. Total
    PSI was reported under the provisional methods, as net flows, until the revised methods
    began in PSI_GRANT_EQUIVALENT_START_YEAR; from then it is the sum of lines 11030 and
    11040 in grant equivalents. Its split by approach only ever covers the
    provisional-method amounts, in net flows.

    Args:
        ctx: From open_context.
        provenance: Log to record every query in.

    Returns:
        One financing row per year, donor, indicator name and type, in current USD.
    """
    providers = list(PROVIDERS)
    headline = [
        to_financing_rows(
            run_query(
                ctx,
                indicator,
                provenance=provenance,
                years=ALL_YEARS,
                providers=providers,
                allow_partial=indicator in PARTIAL_YEAR_FINANCING_INDICATORS,
            ),
            name,
        )
        for indicator, name in HEADLINE_FINANCING_INDICATORS.items()
    ]
    psi_flows = run_query(
        ctx,
        PSI_FLOW_INDICATOR,
        provenance=provenance,
        years=PSI_FLOW_YEARS,
        providers=providers,
        basis=NET,
    )
    psi_grant_equivalents = run_query(
        ctx,
        "oecd.dac1.lines",
        provenance=provenance,
        lines=list(PSI_GRANT_EQUIVALENT_LINES),
        years=PSI_GE_YEARS,
        providers=providers,
        basis=GRANT_EQUIVALENT,
        by=["provider", "year", "line"],
    )
    net_lines = run_query(
        ctx,
        "oecd.dac1.lines",
        provenance=provenance,
        lines=list(NET_FLOW_LINES),
        years=ALL_YEARS,
        providers=providers,
        basis=NET,
        by=["provider", "year", "line"],
    )
    rows = pd.concat(
        [
            *headline,
            to_financing_rows(psi_flows, PSI),
            to_financing_rows(psi_grant_equivalents, PSI),
            to_financing_rows(
                net_lines,
                map_config_values(net_lines["line"], NET_FLOW_LINES, what="DAC1 lines"),
            ),
        ],
        ignore_index=True,
    )
    return sum_by_name(rows)


def read_grants(ctx: oda.Context, provenance: ProvenanceLog) -> pd.DataFrame:
    """Read the grants flow of each provider's Total ODA.

    Args:
        ctx: From open_context.
        provenance: Log to record the query in.

    Returns:
        The query result: one row per donor and year that reports grants.
    """
    return run_query(
        ctx,
        "oecd.dac1.total_oda",
        provenance=provenance,
        years=ALL_YEARS,
        providers=list(PROVIDERS),
        basis=GRANTS_BASIS,
        flows=GRANTS_FLOW,
    )


def read_eu_weights(
    ctx: oda.Context, provenance: ProvenanceLog
) -> dict[str, dict[int, float]]:
    """Read the EU Institutions weight per year, keyed by the financing type it applies to.

    Args:
        ctx: From open_context.
        provenance: Log to record the queries in.

    Returns:
        ``{type: {year: weight}}``.
    """
    return {
        FINANCING_TYPES[basis]: eui_weights(
            ctx, years, basis=basis, provenance=provenance
        )
        for basis, years in EU27_EUI_YEARS.items()
    }


def build_eu27_eui_total(
    converted: pd.DataFrame, weights: dict[str, dict[int, float]]
) -> pd.DataFrame:
    """Sum the EU27 + institutions bloc, with the institutions weighted.

    Args:
        converted: Individual donors' rows in every currency and price.
        weights: From read_eu_weights.

    Returns:
        The bloc's rows up to EU27_EUI_LAST_YEAR, named EU27_EUI_NAME.
    """
    logger.info("EU27 & EU Institutions: published up to %s", EU27_EUI_LAST_YEAR)
    members = converted.loc[
        lambda d: d["donor_code"].isin(EU_TOTAL) & (d["year"] <= EU27_EUI_LAST_YEAR)
    ]
    weighted = pd.concat(
        [
            weight_eu_institutions(rows, weights[str(financing_type)])
            for financing_type, rows in members.groupby("type", observed=True)
        ],
        ignore_index=True,
    )
    return get_group_total(
        weighted,
        EU_TOTAL,
        group_cols=["year", "indicator_name", "type", "currency", "price"],
        group_name=EU27_EUI_NAME,
    )


def get_financing_data(ctx: oda.Context, provenance: ProvenanceLog) -> pd.DataFrame:
    """Assemble the financing view from its parts.

    Args:
        ctx: From open_context.
        provenance: Log to record every query and the conversion factors in.

    Returns:
        Wide frame keyed by year, donor_name, indicator_name and type, with one column per
        currency and price pair plus the two share columns.
    """
    dac1 = read_dac1(ctx, provenance)
    grants = read_grants(ctx, provenance)
    total_oda = dac1.loc[lambda d: d["indicator_name"] == TOTAL_ODA]
    donors = pd.concat([dac1, split_grants(total_oda, grants)], ignore_index=True)

    converted = add_currencies_and_prices(
        donors, base_year=FINANCING_TIME["base"], provenance=provenance
    )
    usd_current = converted.loc[
        lambda d: (d["currency"] == "USD") & (d["price"] == "current")
    ]

    group_totals = build_donor_group_totals(
        converted, ["year", "indicator_name", "type", "currency", "price"]
    )
    donor_groups = [
        drop_grants_split(
            total, years_missing_grants(total_oda, grants, DONOR_GROUPS[name])
        )
        for name, total in group_totals.items()
    ]
    eu27_eui = drop_grants_split(
        build_eu27_eui_total(converted, read_eu_weights(ctx, provenance)),
        years_missing_grants(total_oda, grants, EU_TOTAL),
    )

    financing = drop_empty_series(
        pd.concat([converted, *donor_groups, eu27_eui]), list(VIEW_KEYS), "financing"
    )
    check_one_type_per_series(financing)

    financing = widen_currency_price(df=financing, index_cols=VIEW_KEYS)
    financing = add_share_of_total_oda(financing)

    member_gni = get_member_gni(
        ctx, FINANCING_TIME["start"], FINANCING_TIME["end"], provenance=provenance
    )
    financing = add_share_of_gni(financing, member_gni, usd_current)

    # Integers in units compress far better than floats in millions.
    return convert_values_to_units(financing)


def main() -> None:
    """Build the view and write it to stdout as Observable's zip archive."""
    logger.info("Generating financing table...")
    provenance = ProvenanceLog()
    with open_context() as ctx:
        df = get_financing_data(ctx, provenance)
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
            "provenance": provenance.to_dict(),
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


if __name__ == "__main__":
    main()
