"""Imputed multilateral spending, read the same way by every script that needs it."""

import pandas as pd
from oda_data.indicators.research.sector_imputations import (
    imputed_multilateral_by_purpose,
)

from src.data.config import (
    CRS_RECIPIENTS,
    IMPUTATION_FLOW_TYPES,
    UNSPECIFIED_RECIPIENT_CODE,
    logger,
)


def read_imputed_multilateral(years: range, providers: list[int]) -> pd.DataFrame:
    """Read imputed multilateral spending by purpose, keeping money with no recipient.

    oda_data leaves core funding it cannot allocate, and fixed-purpose proxies, without a
    recipient. Dropping those rows would understate imputed multilateral by $3-5bn a year,
    so they are recorded under UNSPECIFIED_RECIPIENT_CODE, as DAC2A records them.

    Args:
        years: Years to impute.
        providers: Donor codes to impute for.

    Returns:
        oda_data's imputation rows in current USD, every one with a recipient in
        CRS_RECIPIENTS.

    Raises:
        ValueError: If a row has a recipient outside CRS_RECIPIENTS.
    """
    raw = imputed_multilateral_by_purpose(
        years=years,
        providers=providers,
        measure="gross_disbursement",
        currency="USD",
        base_year=None,
        flow_types=IMPUTATION_FLOW_TYPES,
    )

    no_recipient = raw["recipient_code"].isna()
    logger.info(
        "Imputed multilateral with no recipient, recorded as %s: %s USD million",
        UNSPECIFIED_RECIPIENT_CODE,
        f"{raw.loc[no_recipient, 'value'].sum():,.1f}",
    )
    raw["recipient_code"] = raw["recipient_code"].fillna(UNSPECIFIED_RECIPIENT_CODE)

    outside = ~raw["recipient_code"].isin(CRS_RECIPIENTS)
    if outside.any():
        raise ValueError(
            "Imputed multilateral recipients outside CRS_RECIPIENTS: "
            f"{sorted(raw.loc[outside, 'recipient_code'].unique())}"
        )
    return raw
