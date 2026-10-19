"""Builds the gender view: bilateral ODA by gender policy marker score.

Shape of the pipeline:
    1. CRS bilateral allocable flows by gender marker score, with "Not screened" derived as
       the allocable total minus the three screened scores
    2. recipient names, regions and income groups from the shared CRS classification table,
       since the marker data carries only recipient codes
    3. recipient groups then donor groups, summed locally because the CRS publishes neither
    4. each score as a share of the entity's bilateral allocable total, which the four scores
       make up together, so they sum to 100%
    5. one zip on stdout for Observable: the data as parquet and its dropdown options

Output is keyed by name: year, donor_name, recipient_name, indicator_name.
"""

import pandas as pd
from oda_data import bilateral_policy_marker

from src.data.analysis_tools.gender import derive_not_screened
from src.data.analysis_tools.outputs import (
    build_view_options,
    set_cache_dir,
    view_archive_to_stdout,
)
from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_recipient_classifications,
    add_share_of_group_total,
    build_donor_group_totals,
    convert_values_to_units,
    drop_empty_values,
    get_crs_recipient_classifications,
    get_group_total,
    widen_currency_price,
    with_crs_recipient_group_totals,
)
from src.data.config import (
    BASE_TIME,
    CRS_RECIPIENTS,
    CRS_RECIPIENTS_ORDER,
    DEFAULT_DONOR,
    DEFAULT_RECIPIENT,
    DONORS_ORDER,
    EU27_EUI_NAME,
    EU_COUNTRIES,
    EU_INSTITUTIONS,
    GENDER_INDICATORS,
    NOT_SCREENED_SCORE,
    PROVIDERS,
    TOTAL_ALLOCABLE_SCORE,
    logger,
)

YEARS = range(BASE_TIME["start"], BASE_TIME["end"] + 1)

# Everything identifying a row except the recipient, and except the donor, respectively.
RECIPIENT_GROUP_COLS = [
    "year",
    "donor_code",
    "donor_name",
    "indicator_name",
    "currency",
    "price",
]
DONOR_GROUP_COLS = ["year", "recipient_name", "indicator_name", "currency", "price"]
# The level each marker score is summed to before "Not screened" is derived.
GENDER_KEY = ["year", "donor_code", "donor_name", "recipient_code"]


def read_marker_score(score: str) -> pd.Series:
    """Read gross disbursements for one gender marker score, summed by donor and recipient.

    Args:
        score: A marker score bilateral_policy_marker accepts, e.g. "principal".

    Returns:
        Values indexed by GENDER_KEY.
    """
    marker = bilateral_policy_marker(
        years=YEARS,
        providers=list(PROVIDERS),
        recipients=list(CRS_RECIPIENTS),
        measure="gross_disbursement",
        marker="gender",
        marker_score=score,
    )
    if marker[GENDER_KEY].isna().any().any():
        raise ValueError(f"Gender marker rows for {score!r} have a missing key column")

    return marker.groupby(GENDER_KEY, observed=True)["value"].sum()


def get_gender_markers() -> pd.DataFrame:
    """Read gross disbursements by gender marker score.

    "Not screened" is the allocable total minus the three screened scores (see
    NOT_SCREENED_SCORE in config). bilateral_policy_marker returns donor_code, donor_name and
    recipient_code only, so the recipient's name, region and income group are attached later
    from the shared CRS classification table.

    Returns:
        One row per year, donor, recipient and indicator name, zero rows dropped.

    Raises:
        ValueError: If screened rows fall outside the allocable total.
    """
    scores = {
        score: read_marker_score(score)
        for score in GENDER_INDICATORS
        if score != NOT_SCREENED_SCORE
    }
    gender = derive_not_screened(scores, read_marker_score(TOTAL_ALLOCABLE_SCORE))
    # Zeros are dropped here, before the currency conversion multiplies the rows by eight.
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
    classified, ldc_members = get_crs_recipient_classifications(
        YEARS, list(CRS_RECIPIENTS)
    )
    gender = add_recipient_classifications(gender, classified, "gender markers")

    logger.info("Adding currencies and prices...")
    gender = add_currencies_and_prices(gender, base_year=BASE_TIME["base"])
    gender = drop_empty_values(gender, "gender")

    # Recipient groups must exist before the donor groups are summed, so that every donor
    # aggregate covers every recipient group as well as every country.
    logger.info("Building recipient and donor group totals...")
    gender = with_crs_recipient_group_totals(gender, RECIPIENT_GROUP_COLS, ldc_members)
    gender = pd.concat(
        [
            gender,
            *build_donor_group_totals(gender, DONOR_GROUP_COLS).values(),
            # A plain sum is safe here: the marker data has no imputed multilateral leg
            # through which member contributions could be counted twice.
            get_group_total(
                gender,
                EU_COUNTRIES | EU_INSTITUTIONS,
                group_cols=DONOR_GROUP_COLS,
                group_name=EU27_EUI_NAME,
            ),
        ],
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
    set_cache_dir(oda_data=True, pydeflate=True)
    logger.info("Generating gender view table...")
    df = combined_gender()
    options = build_view_options(
        df=df,
        columns={
            "donor_name": DONORS_ORDER,
            "recipient_name": CRS_RECIPIENTS_ORDER,
            "indicator_name": list(GENDER_INDICATORS.values()),
            "year": [],
        },
        base_year=BASE_TIME["base"],
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
