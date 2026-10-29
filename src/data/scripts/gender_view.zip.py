"""Builds the gender view: bilateral ODA by gender policy marker score.

Shape of the pipeline:
    1. one oecd.crs.gender_marker read, by provider, recipient, score and year, in gross
       disbursements from MARKERS_START_YEAR (oecd.crs.gender_marker starts in 2010 and
       refuses earlier years).
       From CRS_PSI_START_YEAR it leaves out private sector instruments (CRS category 60)
    2. recipient names, regions and income groups from the shared CRS classification table,
       since the marker data carries only recipient codes
    3. recipient groups then donor groups, summed locally because the CRS publishes neither
    4. each score as a share of the entity's bilateral allocable total, which the four scores
       make up together, so they sum to 100%
    5. one zip on stdout for Observable: the data as parquet and its dropdown options, with
       the provenance of every table read

Output is keyed by name: year, donor_name, recipient_name, indicator_name.
"""

import oda_data as oda
import pandas as pd

from src.data.analysis_tools.gender import label_marker_scores
from src.data.analysis_tools.oda import (
    ProvenanceLog,
    open_context,
    run_query,
    scan_table,
    scanned_release,
)
from src.data.analysis_tools.outputs import build_view_options, view_archive_to_stdout
from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_recipient_classifications,
    add_share_of_group_total,
    build_donor_group_totals,
    convert_values_to_units,
    drop_empty_series,
    get_crs_recipient_classifications,
    get_group_total,
    widen_currency_price,
    with_crs_recipient_group_totals,
)
from src.data.config import (
    CRS_PSI_START_YEAR,
    CRS_RECIPIENTS,
    CRS_RECIPIENTS_ORDER,
    DEFAULT_DONOR,
    DEFAULT_RECIPIENT,
    DONORS_ORDER,
    EU27_EUI_NAME,
    EU_COUNTRIES,
    EU_INSTITUTIONS,
    GENDER_INDICATORS,
    GENDER_TIME,
    PROVIDERS,
    logger,
)

YEARS: range = range(GENDER_TIME["start"], GENDER_TIME["end"] + 1)
GENDER_MARKER: str = "oecd.crs.gender_marker"
CRS: str = "crs"

VIEW_KEYS: list[str] = ["year", "donor_name", "recipient_name", "indicator_name"]
# Everything identifying a row except the recipient, and except the donor, respectively.
RECIPIENT_GROUP_COLS: list[str] = [
    "year",
    "donor_code",
    "donor_name",
    "indicator_name",
    "currency",
    "price",
]
DONOR_GROUP_COLS: list[str] = [
    "year",
    "recipient_name",
    "indicator_name",
    "currency",
    "price",
]


def read_gender_markers(ctx: oda.Context, provenance: ProvenanceLog) -> pd.DataFrame:
    """Read gross disbursements by gender marker score, provider and recipient.

    oecd.crs.gender_marker returns all four scores, "Not screened" included, so nothing is
    derived here. Recipient names, regions and income groups are attached later from the
    shared CRS classification table.

    Args:
        ctx: From open_context.
        provenance: Log to record the CRS release in.

    Returns:
        One row per year, donor, recipient and indicator name, zero rows dropped, in current
        USD millions.
    """
    markers = run_query(
        ctx,
        GENDER_MARKER,
        years=YEARS,
        providers=list(PROVIDERS),
        recipients=list(CRS_RECIPIENTS),
        by=["provider", "recipient", "score", "year"],
        provenance=provenance,
    )
    return label_marker_scores(markers)


def combined_gender(ctx: oda.Context, provenance: ProvenanceLog) -> pd.DataFrame:
    """Assemble the gender view from its parts.

    Args:
        ctx: From open_context.
        provenance: Log to record every read and the conversion factors in.

    Returns:
        Wide frame keyed by year, donor_name, recipient_name and indicator_name, with one
        column per currency and price pair plus pct_of_total_oda.
    """
    logger.info("Fetching gender marker data...")
    gender = read_gender_markers(ctx, provenance)

    logger.info("Attaching recipient classifications...")
    classified, ldc_members = get_crs_recipient_classifications(
        YEARS, list(CRS_RECIPIENTS)
    )
    # The classification scans the same CRS file; recording it checks the release matches.
    provenance.record_table(CRS, scanned_release(scan_table(CRS)))
    gender = add_recipient_classifications(gender, classified, "gender markers")

    logger.info("Adding currencies and prices...")
    gender = add_currencies_and_prices(
        gender, base_year=GENDER_TIME["base"], provenance=provenance
    )

    # Recipient groups must exist before the donor groups are summed, so that every donor
    # aggregate covers every recipient group as well as every country.
    logger.info("Building recipient and donor group totals...")
    gender = with_crs_recipient_group_totals(gender, RECIPIENT_GROUP_COLS, ldc_members)
    gender = pd.concat(
        [
            gender,
            *build_donor_group_totals(gender, DONOR_GROUP_COLS).values(),
            # A plain sum is safe here: the marker data has no imputed multilateral leg
            # through which member contributions could be counted twice, and with provider
            # in `by` the CRS returns EU Institutions (918) as any other provider.
            get_group_total(
                gender,
                EU_COUNTRIES | EU_INSTITUTIONS,
                group_cols=DONOR_GROUP_COLS,
                group_name=EU27_EUI_NAME,
            ),
        ],
        ignore_index=True,
    )

    gender = drop_empty_series(
        gender[[*VIEW_KEYS, "currency", "price", "value"]], VIEW_KEYS, "gender"
    )

    logger.info("Pivoting to wide format...")
    gender = widen_currency_price(df=gender, index_cols=tuple(VIEW_KEYS))

    # The four marker scores partition each entity's allocable aid, so the denominator is the
    # entity's own total rather than a reference entity's.
    gender = add_share_of_group_total(
        gender,
        group_cols=["year", "donor_name", "recipient_name"],
        pct_col="pct_of_total_oda",
    )

    # Integers in units compress far better than floats in millions.
    return convert_values_to_units(gender)


def main() -> None:
    """Build the view and write it to stdout as Observable's zip archive."""
    logger.info("Generating gender view table...")
    provenance = ProvenanceLog()
    with open_context() as ctx:
        df = combined_gender(ctx, provenance)
    options = build_view_options(
        df=df,
        columns={
            "donor_name": DONORS_ORDER,
            "recipient_name": CRS_RECIPIENTS_ORDER,
            "indicator_name": list(GENDER_INDICATORS.values()),
            "year": [],
        },
        base_year=GENDER_TIME["base"],
        extra={
            "psi_excluded_from": CRS_PSI_START_YEAR,
            "provenance": provenance.to_dict(),
        },
        defaults={
            "donor_name": DEFAULT_DONOR,
            "recipient_name": DEFAULT_RECIPIENT,
            "indicator_name": [
                GENDER_INDICATORS["principal"],
                GENDER_INDICATORS["significant"],
            ],
        },
    )
    view_archive_to_stdout(df, options)


if __name__ == "__main__":
    main()
