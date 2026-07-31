"""Builds the gender view: bilateral ODA by gender policy marker score.

Shape of the pipeline:
    1. CRS bilateral flows for each of the four marker scores
    2. recipient names, regions and income groups from the shared CRS classification table,
       since the marker data carries only recipient codes
    3. recipient groups then donor groups, summed locally because the CRS publishes neither
    4. each score as a share of the entity's own screened total, so the four sum to 100%
    5. one parquet on stdout for Observable, plus the dropdown options beside it

Output is keyed by name: year, donor_name, recipient_name, indicator_name.
"""

import pandas as pd

from oda_data import bilateral_policy_marker

from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_recipient_classifications,
    add_share_of_group_total,
    build_crs_donor_group_totals,
    build_crs_recipient_group_totals,
    convert_values_to_units,
    get_crs_recipient_classifications,
    widen_currency_price,
)
from src.data.config import (
    logger,
    BASE_TIME,
    GENDER_INDICATORS,
    CRS_PROVIDERS,
    CRS_RECIPIENTS,
    DONORS_ORDER,
    CRS_RECIPIENTS_ORDER,
)
from src.data.analysis_tools.outputs import (
    set_cache_dir,
    generate_view_options,
    parquet_to_stdout,
)

set_cache_dir(oda_data=True, pydeflate=True)

YEARS = range(BASE_TIME["start"], BASE_TIME["end"] + 1)

# Everything identifying a row except the recipient, and except the donor, respectively.
RECIPIENT_GROUP_COLS = [
    "year", "donor_code", "donor_name", "indicator_name", "currency", "price",
]
DONOR_GROUP_COLS = ["year", "recipient_name", "indicator_name", "currency", "price"]


def get_gender_markers() -> pd.DataFrame:
    """Read gross disbursements by gender marker score.

    bilateral_policy_marker returns donor_code, donor_name and recipient_code only, so the
    recipient's name, region and income group are attached later from the shared CRS
    classification table.
    """
    scores = [
        bilateral_policy_marker(
            years=YEARS,
            providers=list(CRS_PROVIDERS),
            recipients=list(CRS_RECIPIENTS),
            measure="gross_disbursement",
            marker="gender",
            marker_score=score,
        )
        for score in GENDER_INDICATORS
    ]

    gender_raw = pd.concat(scores, ignore_index=True)

    unmapped = sorted(set(gender_raw["gender"].dropna().unique()) - set(GENDER_INDICATORS))
    if unmapped:
        raise ValueError(f"Unmapped gender marker scores: {unmapped}")

    gender = (
        gender_raw.assign(indicator_name=lambda d: d["gender"].map(GENDER_INDICATORS))
        .groupby(
            ["year", "donor_code", "donor_name", "recipient_code", "indicator_name"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
    )

    return gender[gender["value"] != 0]


def combined_gender() -> pd.DataFrame:
    """Assemble the gender view from its parts.

    Returns:
        Wide frame keyed by year, donor_name, recipient_name and indicator_name, with one
        column per currency and price pair plus pct_of_total_oda.
    """
    logger.info("Fetching gender marker data...")
    gender = get_gender_markers()

    logger.info("Attaching recipient classifications...")
    classified = get_crs_recipient_classifications(YEARS, list(CRS_RECIPIENTS))
    gender = add_recipient_classifications(gender, classified, "gender markers")

    logger.info("Adding currencies and prices...")
    gender = add_currencies_and_prices(gender, base_year=BASE_TIME["base"])
    gender = gender[gender["value"].notna() & (gender["value"] != 0)]

    # Recipient groups must exist before the donor groups are summed, so that every donor
    # aggregate covers every recipient group as well as every country.
    logger.info("Building recipient and donor group totals...")
    gender = pd.concat(
        [gender, *build_crs_recipient_group_totals(gender, RECIPIENT_GROUP_COLS)],
        ignore_index=True,
    )
    gender = pd.concat(
        [gender, *build_crs_donor_group_totals(gender, DONOR_GROUP_COLS)],
        ignore_index=True,
    )

    logger.info("Pivoting to wide format...")
    gender = widen_currency_price(
        df=gender,
        index_cols=("year", "donor_name", "recipient_name", "indicator_name"),
    )

    # The four marker scores partition each entity's screened aid, so the denominator is the
    # entity's own total rather than a reference entity's.
    gender = add_share_of_group_total(
        gender,
        group_cols=["year", "donor_name", "recipient_name"],
        pct_col="pct_of_total_oda",
    )

    return convert_values_to_units(gender)


if __name__ == "__main__":
    logger.info("Generating gender view table...")
    df = combined_gender()
    generate_view_options(
        df=df,
        columns={
            "donor_name": DONORS_ORDER,
            "recipient_name": CRS_RECIPIENTS_ORDER,
            "indicator_name": list(GENDER_INDICATORS.values()),
            "year": [],
        },
        base_year=BASE_TIME["base"],
        file_name="gender_view_options.json",
    )
    logger.info("Writing parquet to stdout...")
    parquet_to_stdout(df)
