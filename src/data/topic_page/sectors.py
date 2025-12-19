import pandas as pd
from oda_data import CRSData, provider_groupings
from oda_data.clean_data.common import convert_units
from oda_data.indicators.research.sector_imputations import (
    imputed_multilateral_by_purpose,
)
from oda_data.tools import sector_lists

from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
)

DONOR_IDS = list(provider_groupings()["dac_countries"])


def _assign_sub_sector(df: pd.DataFrame, broad: bool = False) -> pd.DataFrame:
    """Assigns sub-sector names based on purpose codes."""
    sub_sectors = sector_lists.get_sector_groups()

    for name, codes in sub_sectors.items():
        df.loc[df.purpose_code.isin(codes), "sub_sector"] = name

    if broad:
        broad_sectors = sector_lists.get_broad_sector_groups()
        df["sub_sector"] = (
            df["sub_sector"].map(broad_sectors).fillna("Unallocated/unspecified")
        )
    return df


def get_bilateral_by_sector(years: list, broad: bool = False) -> pd.DataFrame:
    """Fetches and aggregates bilateral ODA disbursements by sector."""
    raw_bilateral = CRSData(years=years).read(
        using_bulk_download=True,
        additional_filters=[
            ("donor_code", "in", DONOR_IDS),
            ("category", "in", [10, 60]),
        ],
        columns=[
            "year",
            "donor_code",
            "recipient_code",
            "purpose_code",
            "usd_disbursement",
        ],
    )

    df = _assign_sub_sector(raw_bilateral, broad=broad)

    sectors_bi = (
        df.groupby(
            ["year", "donor_code", "recipient_code", "sub_sector"],
            dropna=False,
            observed=True,
        )["usd_disbursement"]
        .sum()
        .reset_index()
        .rename(columns={"usd_disbursement": "value"})
        .assign(indicator="Bilateral")
    )

    return sectors_bi[lambda d: d.value != 0]


def get_imputed_multi_by_sector(years: list, broad: bool = False) -> pd.DataFrame:
    """Fetches and aggregates imputed multilateral disbursements by sector."""
    raw_multi = imputed_multilateral_by_purpose(
        years=years,
        providers=DONOR_IDS,
        measure="gross_disbursement",
        currency="USD",
        base_year=None,
    )

    raw_multi = _assign_sub_sector(raw_multi, broad=broad)
    raw_multi["sub_sector"] = raw_multi["sub_sector"].fillna("Unallocated/unspecificed")

    sectors_multi = (
        raw_multi.groupby(
            ["year", "donor_code", "recipient_code", "sub_sector"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator="Imputed multilateral")
    )

    return sectors_multi[sectors_multi["value"] != 0]


def total_sectors(
    years: list | range,
    as_total: bool = False,
    broad: bool = False,
    base_year: int | None = None,
    currency: str = "USD",
) -> pd.DataFrame:
    """Merges bilateral and multilateral sector data and enriches with metadata."""
    sectors_bi = get_bilateral_by_sector(years=years, broad=broad)
    sectors_multi = get_imputed_multi_by_sector(years=years, broad=broad)
    sectors = pd.concat([sectors_bi, sectors_multi], ignore_index=True)

    if as_total:
        sectors = (
            sectors.assign(indicator="Total (bilateral + imputed multi)")
            .groupby([c for c in sectors if c != "value"], dropna=False, observed=True)[
                ["value"]
            ]
            .sum()
            .reset_index()
        )

    sectors = convert_units(data=sectors, currency=currency, base_year=base_year)

    return sectors


if __name__ == "__main__":
    set_cache_dir(oda_data=True, pydeflate=True)
    sectors_data = total_sectors(years=range(2013, 2025), as_total=True, broad=True)
