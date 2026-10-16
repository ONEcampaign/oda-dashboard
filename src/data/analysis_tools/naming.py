"""Turning source values into the strings the views display.

Every view is keyed by name rather than by numeric code, so the names have to be consistent:
the same entity must not appear as "Caribbean unspecified" in one view and
"Caribbean, regional" in another, and a name used as a URL path segment has to be ASCII-safe.
This module owns those rules.

Add here anything that decides how an entity is *labelled*. Aggregation and reshaping belong in
``transformations``; writing files belongs in ``outputs``.
"""

import re
import unicodedata

import pandas as pd

from src.data.config import RECIPIENT_NAME_OVERRIDES


def apply_name_overrides(df: pd.DataFrame, mapping: dict, column: str) -> pd.DataFrame:
    """Replace the name of any row whose code appears in a config mapping.

    The OECD API returns aggregate providers and recipients under spellings that vary between
    datasets ("non-DAC countries" against "Non-DAC countries"). Since the views merge and filter
    on names, one canonical spelling per code has to win, and config decides which.

    Args:
        df: Frame with ``{column}_code`` and ``{column}_name`` columns.
        mapping: ``{code: canonical name}``, e.g. ``RECIPIENT_NAME_OVERRIDES``.
        column: Either "donor" or "recipient".

    Returns:
        The frame with the mapped rows renamed.
    """
    code_col = f"{column}_code"
    name_col = f"{column}_name"

    df = df.copy()
    mask = df[code_col].isin(mapping)
    df.loc[mask, name_col] = df.loc[mask, code_col].map(mapping)

    return df


def map_indicator_names(codes: pd.Series, mapping: dict) -> pd.Series:
    """Name each indicator code from a config mapping, failing on any code it does not know.

    A plain .map would turn an unknown code into a missing name, and the rows would then be
    grouped under that missing name without warning.

    Args:
        codes: Indicator codes, e.g. the one_indicator column.
        mapping: ``{code: display name}`` from config.

    Returns:
        The display names, aligned with codes.

    Raises:
        ValueError: If a non-missing code has no entry in mapping.
    """
    names = codes.map(mapping)
    unknown = sorted(set(codes[names.isna() & codes.notna()]))
    if unknown:
        raise ValueError(f"Indicator codes with no display name in config: {unknown}")
    return names


def normalize_unspecified_names(names: pd.Series) -> pd.Series:
    """Standardise the labels for aid that is not allocated to a specific country.

    "<area>, unspecified" is aid to more than one country in an area that cannot be split
    between them, and "<area>" is the area's full total including it. The sources spell it
    "Africa, regional" (CRS) or "Caribbean unspecified" (DAC2A); all become "<area>,
    unspecified", so the views agree and "regional" never reaches a reader.

    Matching is deliberately case sensitive and anchored to the end of the label, which leaves
    the CRS region value "Regional and Unspecified" alone.

    Args:
        names: Recipient names.

    Returns:
        The names with trailing "regional"/"unspecified" variants normalised.
    """
    return (
        names.astype("string")
        .str.replace(r",?\s+regional$", ", unspecified", regex=True)
        .str.replace(r"(?<!,)\s+unspecified$", ", unspecified", regex=True)
    )


def canonical_recipient_names(df: pd.DataFrame) -> pd.DataFrame:
    """Apply RECIPIENT_NAME_OVERRIDES, then normalise the unspecified labels.

    Every view names recipients through this, so a code-keyed rename reaches them all.

    Args:
        df: Frame with recipient_code and recipient_name.

    Returns:
        The frame with canonical recipient names.
    """
    df = apply_name_overrides(df, RECIPIENT_NAME_OVERRIDES, "recipient")
    df["recipient_name"] = normalize_unspecified_names(df["recipient_name"])
    return df


def normalize_crs_regions(regions: pd.Series) -> pd.Series:
    """Fold "<continent>, regional" CRS region values into "<continent>".

    The CRS sometimes records a continent's own unspecified aid against "Africa, regional"
    rather than "Africa". Both mean the same, and only the plain value rolls into the
    continent total.

    Args:
        regions: CRS recipient_region values.

    Returns:
        The regions with the ", regional" suffix removed.
    """
    return regions.astype("string").str.removesuffix(", regional")


def slugify(value: str) -> str:
    """Reduce a name to a lowercase ASCII slug safe for use in a URL path segment.

    The sectors dataset is partitioned by slug and addressed over HTTP, so the path needs no
    percent encoding and no numeric codes. Deterministic; callers must check the results are
    unique, since two names could in principle reduce to the same slug.

    Args:
        value: Name to convert, e.g. "Côte d'Ivoire".

    Returns:
        Slug, e.g. "cote-d-ivoire".
    """
    decomposed = unicodedata.normalize("NFKD", str(value))
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")

    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_only.lower())).strip("-")
