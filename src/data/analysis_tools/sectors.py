"""The purpose code to sub-sector to sector lookup, shared by the sectors view and topic page.

Both read CRS and imputed multilateral spending by purpose code and label it through this one
lookup, so a sector means the same codes wherever it is published.
"""

from functools import cache

import oda_data as oda
import pandas as pd

from src.data.config import BROAD_ONLY_SUB_SECTORS, UNALLOCATED_SUB_SECTOR, logger

BILATERAL_ODA: str = "oecd.crs.bilateral_oda"
# The CRS headline measure, which oecd.crs.bilateral_oda also defaults to.
CRS_BASIS: str = "gross_disbursement"


def _member_code(member: int | oda.ReportedAt) -> int:
    """A sector group member's purpose code; a heading-level member carries its heading."""
    return member if isinstance(member, int) else member.code


@cache
def sector_lookup() -> tuple[dict[int, str], dict[str, str]]:
    """Build the purpose code to sub-sector, and sub-sector to sector, lookups once per run.

    oda.sectors holds the broad sectors and their sub-sectors as one flat set of nested
    groups: a purpose code belongs to its sub-sector's group (the smallest that holds it)
    and its sector's group (the largest). Where the two are one group, the sector has a
    single sub-sector of the same name. Codes in a broad sector's group but in none of its
    sub-sectors' are named by BROAD_ONLY_SUB_SECTORS where the dashboard names them apart.

    Returns:
        ``({purpose_code: sub-sector}, {sub-sector: sector})``.

    Raises:
        ValueError: If a code's groups do not nest, or two groups of one size hold it, so
            its sub-sector or sector would be ambiguous.
    """
    groups = {
        group.label: {_member_code(m) for m in group.members}
        for group in oda.sectors.values()
    }
    holding: dict[int, list[str]] = {}
    for label, codes in groups.items():
        for code in codes:
            holding.setdefault(code, []).append(label)

    sub_sectors: dict[int, str] = {}
    sectors: dict[str, str] = {}
    for code, labels in holding.items():
        labels.sort(key=lambda label: len(groups[label]))
        narrowest, widest = labels[0], labels[-1]
        sizes = [len(groups[label]) for label in labels]
        if len(set(sizes)) != len(sizes) or any(
            not groups[label] <= groups[widest] for label in labels
        ):
            raise ValueError(
                f"oda.sectors groups holding purpose code {code} do not nest: {labels}"
            )
        sub_sector = (
            BROAD_ONLY_SUB_SECTORS.get(narrowest, narrowest)
            if narrowest == widest
            else narrowest
        )
        if sectors.setdefault(sub_sector, widest) != widest:
            raise ValueError(
                f"Sub-sector {sub_sector!r} falls in two sectors: "
                f"{sectors[sub_sector]!r} and {widest!r}"
            )
        sub_sectors[code] = sub_sector

    return sub_sectors, sectors


def assign_sub_sector(df: pd.DataFrame) -> pd.DataFrame:
    """Label each row with its sub-sector, from its purpose code.

    Args:
        df: Frame with purpose_code and value columns.

    Returns:
        The frame with a sub_sector column, never null: null purpose codes (unallocated
        core funding) and codes outside every group are labelled explicitly, since a null
        here would become a null grouping key downstream.
    """
    purpose_to_sub_sector, _ = sector_lookup()
    sub_sector = df["purpose_code"].map(purpose_to_sub_sector)

    unmatched = sub_sector.isna()
    if unmatched.any():
        logger.info(
            "%s rows (%s USD million) have no purpose code or one outside the sector "
            "groups, labelled %r",
            f"{int(unmatched.sum()):,}",
            f"{df.loc[unmatched, 'value'].sum():,.1f}",
            UNALLOCATED_SUB_SECTOR,
        )

    df["sub_sector"] = sub_sector.fillna(UNALLOCATED_SUB_SECTOR)

    return df


def sector_names(sub_sectors: pd.Series) -> pd.Series:
    """Name each sub-sector's broad sector; unallocated rows stay unallocated.

    Args:
        sub_sectors: Sub-sector names, as assign_sub_sector labels them.

    Returns:
        The broad sector of each, never null.
    """
    _, sub_sector_to_sector = sector_lookup()
    return (
        sub_sectors.astype("object")
        .map(sub_sector_to_sector)
        .fillna(UNALLOCATED_SUB_SECTOR)
    )
