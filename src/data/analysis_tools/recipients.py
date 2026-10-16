"""Testable frame logic for the recipients loader, which Python cannot import by name."""

import pandas as pd

from src.data.analysis_tools.naming import (
    apply_name_overrides,
    normalize_unspecified_names,
)
from src.data.config import (
    DAC2A_AGGREGATE_CODE_MIN,
    DAC2A_MISSING_RECIPIENT_CODES,
    EXCLUDED_DAC2A_RECIPIENTS,
    RECIPIENT_NAME_OVERRIDES,
    logger,
)


def canonical_recipients(df: pd.DataFrame) -> pd.DataFrame:
    """Drop the DAC2A recipients the view leaves out and give the rest their display names.

    Args:
        df: DAC2A rows with recipient_code and recipient_name.

    Returns:
        The kept rows, with canonical recipient names.

    Raises:
        ValueError: If two recipient codes end up with one name, which the pivot on
            recipient_name would otherwise merge silently.
    """
    df = df.assign(
        recipient_code=df["recipient_code"].fillna(
            df["recipient_name"].astype("string").map(DAC2A_MISSING_RECIPIENT_CODES)
        )
    )
    uncoded = sorted(
        df.loc[df["recipient_code"].isna(), "recipient_name"].astype(str).unique()
    )
    if uncoded:
        logger.warning(
            "DAC2A recipients without a code, kept by name but not checked against "
            "EXCLUDED_DAC2A_RECIPIENTS: %s",
            uncoded,
        )

    df = df.loc[~df["recipient_code"].isin(EXCLUDED_DAC2A_RECIPIENTS)]
    df = apply_name_overrides(df, RECIPIENT_NAME_OVERRIDES, "recipient")
    df["recipient_name"] = normalize_unspecified_names(df["recipient_name"])

    codes_per_name = df.groupby("recipient_name", observed=True)[
        "recipient_code"
    ].nunique()
    clashes = codes_per_name[codes_per_name > 1].index.tolist()
    if clashes:
        raise ValueError(f"Recipient names shared by more than one code: {clashes}")

    return df


def aggregate_recipient_names(df: pd.DataFrame) -> list[str]:
    """List the DAC2A recipient groups in the data, e.g. "Africa", alphabetically.

    Args:
        df: Canonical DAC2A rows with recipient_code and recipient_name.

    Returns:
        Group names, leaving out the "<area>, unspecified" codes in the aggregate range.
    """
    names = df.loc[df["recipient_code"] >= DAC2A_AGGREGATE_CODE_MIN, "recipient_name"]
    return sorted(n for n in names.unique() if not n.endswith(", unspecified"))
