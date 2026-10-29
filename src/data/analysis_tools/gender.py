"""Testable frame logic for the gender loader, which Python cannot import by name."""

import pandas as pd

from src.data.config import GENDER_INDICATORS

# The level gender marker rows are keyed at, as run_query names the columns.
MARKER_KEYS: list[str] = ["year", "donor_code", "donor_name", "recipient_code", "score"]
# The columns label_marker_scores returns: the keys without score, then the label and value.
LABELLED_COLUMNS: list[str] = [*MARKER_KEYS[:-1], "indicator_name", "value"]


def label_marker_scores(markers: pd.DataFrame) -> pd.DataFrame:
    """Name each gender marker score by its indicator label and drop zero rows.

    Args:
        markers: oecd.crs.gender_marker rows through run_query, with MARKER_KEYS and value.

    Returns:
        year, donor_code, donor_name, recipient_code, indicator_name and value, one row per
        key with a non-zero value.

    Raises:
        ValueError: If a column is missing, a key is null, a key repeats, or a score is not
            in GENDER_INDICATORS.
    """
    missing = [c for c in [*MARKER_KEYS, "value"] if c not in markers.columns]
    if missing:
        raise ValueError(f"Gender marker rows lack columns {missing}")
    if markers[MARKER_KEYS].isna().any().any():
        raise ValueError("Gender marker rows have a missing key column")
    if markers.duplicated(MARKER_KEYS).any():
        raise ValueError("Gender marker rows repeat a key")
    unknown = sorted(set(markers["score"]) - GENDER_INDICATORS.keys())
    if unknown:
        raise ValueError(f"Gender marker scores without a label: {unknown}")

    # Zeros are dropped here, before the currency conversion multiplies the rows by eight.
    return (
        markers.loc[markers["value"] != 0]
        .assign(indicator_name=lambda d: d["score"].map(GENDER_INDICATORS))
        .loc[:, LABELLED_COLUMNS]
        .reset_index(drop=True)
    )
