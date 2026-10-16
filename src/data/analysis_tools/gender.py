"""Testable frame logic for the gender loader, which Python cannot import by name."""

import pandas as pd

from src.data.config import (
    GENDER_INDICATORS,
    GENDER_RESIDUAL_TOLERANCE,
    NOT_SCREENED_SCORE,
)


def derive_not_screened(
    scores: dict[str, pd.Series], allocable: pd.Series
) -> pd.DataFrame:
    """Add "Not screened" as the allocable total minus the screened marker scores.

    The OECD leaves the gender marker blank for activities not screened, and the CRS holds
    only 0, 1, 2 or blank, so the difference is exactly the blank rows. It can be negative,
    since unscreened rows include negative disbursements (corrections). Differences within
    GENDER_RESIDUAL_TOLERANCE are subtraction residue and become zero.

    Args:
        scores: Values by score name (principal, significant, not_targeted), each indexed
            by the same key columns.
        allocable: The allocable total, indexed by the same key columns.

    Returns:
        Long rows for all four scores, with the key columns, value and indicator_name.

    Raises:
        ValueError: If screened rows fall outside the allocable total.
    """
    screened = pd.concat(scores.values(), axis=1).sum(axis=1)
    if not screened.index.difference(allocable.index).empty:
        raise ValueError("Screened gender marker rows fall outside the allocable total")

    not_screened = allocable.sub(screened, fill_value=0)
    all_scores = {
        **scores,
        NOT_SCREENED_SCORE: not_screened.where(
            not_screened.abs() > GENDER_RESIDUAL_TOLERANCE, 0
        ),
    }
    return pd.concat(
        [
            values.rename("value")
            .reset_index()
            .assign(indicator_name=GENDER_INDICATORS[score])
            for score, values in all_scores.items()
        ],
        ignore_index=True,
    )
