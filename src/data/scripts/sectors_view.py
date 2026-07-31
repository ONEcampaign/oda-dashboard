"""Builds the sectors view: ODA by sector and sub-sector, bilateral and imputed multilateral.

Shape of the pipeline:
    1. CRS bilateral disbursements by purpose code, mapped to sub-sectors
    2. imputed multilateral spending by purpose, plus a channel-corrected second read used
       only for the EU27 + institutions aggregate
    3. recipient names, regions and income groups from the shared CRS classification table
    4. recipient groups then donor groups, summed locally because the CRS publishes neither
    5. shares from both perspectives, then values as integer units
    6. a partitioned dataset under cdn_files, addressed by donor and recipient slug

This is the largest view by far, so the frame is kept dictionary-encoded and stripped of spent
columns before the pivot; see _as_categoricals and the drop before widen_currency_price.

Output is keyed by name: year, donor_name, recipient_name, indicator_name, sector_name,
sub_sector_name, with donor_slug and recipient_slug as the partition keys.
"""

import os
import sys
from functools import cache

import pandas as pd

from oda_data import CRSData
from oda_data.tools import sector_lists
from oda_data.indicators.research.sector_imputations import (
    imputed_multilateral_by_purpose,
)

from src.data.analysis_tools.transformations import (
    CRS_INCOME_COL,
    CRS_REGION_COL,
    add_currencies_and_prices,
    add_recipient_classifications,
    add_share_of_reference_total,
    build_crs_donor_group_totals,
    build_crs_recipient_group_totals,
    convert_values_to_units,
    get_crs_recipient_classifications,
    widen_currency_price,
)
from src.data.config import (
    logger,
    SECTORS_TIME,
    CRS_PROVIDERS,
    CRS_FLOW_CATEGORIES,
    CRS_RECIPIENTS,
    DONORS_ORDER,
    LABEL_COLUMNS,
    CRS_RECIPIENTS_ORDER,
    EU_COUNTRIES,
    EU_INSTITUTIONS,
    EU_TOTAL,
    EUI_CHANNEL_CODES,
)
from src.data.analysis_tools.outputs import (
    set_cache_dir,
    generate_view_options,
    write_partitioned_dataset,
)
from src.data.analysis_tools.naming import slugify

set_cache_dir(oda_data=True, pydeflate=True)

YEARS = range(SECTORS_TIME["start"], SECTORS_TIME["end"] + 1)

# Everything identifying a row except the recipient, and except the donor, respectively.
RECIPIENT_GROUP_COLS = [
    "year", "donor_code", "donor_name", "indicator_name", "sub_sector", "currency", "price",
]
DONOR_GROUP_COLS = [
    "year", "recipient_name", "indicator_name", "sub_sector", "currency", "price",
]

UNALLOCATED_SUB_SECTOR = "Unallocated/unspecified"

CRS_COLUMNS: list[str] = [
    "year",
    "donor_code",
    "donor_name",
    "recipient_code",
    "purpose_code",
    "usd_disbursement",
]


def _as_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    """Cast the label columns to category, for whichever of them are present.

    Sectors carries tens of millions of rows through the currency expansion and the pivot, so
    the label columns have to be dictionary-encoded or the frame does not fit in a CI runner.
    """
    for col in (*LABEL_COLUMNS, CRS_REGION_COL, CRS_INCOME_COL):
        if col in df.columns and df[col].dtype.name != "category":
            df[col] = df[col].astype("category")
    return df


@cache
def _purpose_to_sub_sector() -> dict[int, str]:
    """Build the purpose code to sub-sector lookup once per run.

    oda_data expresses the mapping the other way round, as 70 groups each listing its purpose
    codes. Inverting it once turns sub-sector assignment into a single map, where scanning the
    frame per group meant 70 passes over millions of rows every time.

    Three purpose codes appear in more than one group. Building the dict in group order means
    the last group wins, which is what the original sequence of overwriting assignments did.

    Returns:
        ``{purpose_code: sub-sector name}``.
    """
    mapping: dict[int, str] = {}
    for name, codes in sector_lists.get_sector_groups().items():
        mapping.update({int(code): name for code in codes})

    return mapping


def _assign_sub_sector(df: pd.DataFrame) -> pd.DataFrame:
    """Label each row with its sub-sector, from its purpose code.

    Args:
        df: Frame with a purpose_code column.

    Returns:
        The frame with a sub_sector column, never null: purpose codes outside every group are
        labelled explicitly, since a null here would become a null grouping key downstream.
    """
    sub_sector = df["purpose_code"].map(_purpose_to_sub_sector())

    unmatched = int(sub_sector.isna().sum())
    if unmatched:
        logger.info(
            "%s rows have a purpose code outside the sector groups, labelled %r",
            f"{unmatched:,}", UNALLOCATED_SUB_SECTOR,
        )

    df["sub_sector"] = sub_sector.fillna(UNALLOCATED_SUB_SECTOR)

    return df


def get_bilateral_by_sector() -> pd.DataFrame:
    """Read bilateral CRS disbursements by sub-sector."""
    raw_bilateral = CRSData(years=YEARS).read(
        using_bulk_download=True,
        additional_filters=[
            ("donor_code", "in", list(CRS_PROVIDERS)),
            ("recipient_code", "in", list(CRS_RECIPIENTS)),
            ("category", "in", CRS_FLOW_CATEGORIES),
        ],
        columns=CRS_COLUMNS,
    )

    # CRSData.read silently drops requested columns that do not exist, which would quietly
    # empty the classifications, so check rather than trust.
    missing = [col for col in CRS_COLUMNS if col not in raw_bilateral.columns]
    if missing:
        raise ValueError(f"CRS did not return required columns: {missing}")

    raw_bilateral = _assign_sub_sector(raw_bilateral)

    sectors_bi = (
        raw_bilateral.groupby(
            ["year", "donor_code", "donor_name", "recipient_code", "sub_sector"],
            dropna=False,
            observed=True,
        )["usd_disbursement"]
        .sum()
        .reset_index()
        .rename(columns={"usd_disbursement": "value"})
        .assign(indicator_name="Bilateral")
    )

    return sectors_bi[sectors_bi["value"] != 0]


def get_imputed_multi_by_sector() -> pd.DataFrame:
    """Read imputed multilateral spending by sub-sector."""
    raw_multi = imputed_multilateral_by_purpose(
        years=YEARS,
        providers=list(CRS_PROVIDERS),
        measure="gross_disbursement",
        currency="USD",
        base_year=None,
    )

    raw_multi = raw_multi[raw_multi["recipient_code"].isin(CRS_RECIPIENTS)]
    raw_multi = _assign_sub_sector(raw_multi)

    sectors_multi = (
        raw_multi.groupby(
            ["year", "donor_code", "recipient_code", "sub_sector"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator_name="Imputed multilateral")
    )

    return sectors_multi[sectors_multi["value"] != 0]


def get_eu27_eui_imputed() -> pd.DataFrame:
    """Imputed multilateral for the EU27 + institutions bloc, free of double counting.

    EU member states' core contributions reach the EU institutions through the channels in
    EUI_CHANNEL_CODES. Left in, those rows would be counted once as each member's imputed
    multilateral and again as the institutions' own spending, so they are dropped. The
    institutions' own imputed multilateral is kept in full: their contributions to non-EU
    multilaterals do not overlap with their bilateral spending.

    Read separately rather than by keeping channel_code in the main frame — channel adds a
    dimension to every row, which the eight-fold currency expansion would then multiply.
    """
    raw = imputed_multilateral_by_purpose(
        years=YEARS,
        providers=list(EU_TOTAL),
        measure="gross_disbursement",
        currency="USD",
        base_year=None,
    )
    raw = raw[raw["recipient_code"].isin(CRS_RECIPIENTS)]

    routed_via_eui = raw["donor_code"].isin(EU_COUNTRIES) & raw["channel_code"].isin(
        EUI_CHANNEL_CODES
    )
    logger.info(
        "EU27 & EU Institutions: excluding %s USD million of member contributions routed "
        "through EU institution channels, to avoid double counting",
        f"{raw.loc[routed_via_eui, 'value'].sum():,.1f}",
    )
    raw = raw[~routed_via_eui]
    raw = _assign_sub_sector(raw)

    imputed = (
        raw.groupby(
            ["year", "donor_code", "recipient_code", "sub_sector"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator_name="Imputed multilateral")
    )

    return imputed[imputed["value"] != 0]


def build_eu27_eui_total(
    sectors: pd.DataFrame, eu_imputed: pd.DataFrame, group_cols: list[str]
) -> pd.DataFrame:
    """Combine the bloc's bilateral spending with its corrected imputed multilateral.

    Args:
        sectors: The converted frame, used for the bilateral half.
        eu_imputed: The channel-corrected imputed multilateral from get_eu27_eui_imputed,
            already carrying its own recipient groups.
        group_cols: Columns identifying everything except the donor.

    Returns:
        One frame of rows named "EU27 & EU Institutions".
    """
    bilateral = sectors.loc[
        sectors["donor_code"].isin(EU_COUNTRIES | EU_INSTITUTIONS)
        & sectors["indicator_name"].astype("object").eq("Bilateral")
    ]

    return (
        pd.concat([bilateral, eu_imputed], ignore_index=True)
        .groupby(group_cols, dropna=False, observed=True)["value"]
        .sum()
        .reset_index()
        .assign(donor_name="EU27 & EU Institutions")
    )


def combined_sectors() -> pd.DataFrame:
    """Assemble the sectors view from its parts.

    Returns:
        Wide frame keyed by year, donor_name, recipient_name, indicator_name, sector_name and
        sub_sector_name, with the partition slugs and the two share columns.
    """
    logger.info("Fetching bilateral data...")
    sectors_bi = get_bilateral_by_sector()

    classified = get_crs_recipient_classifications(YEARS, list(CRS_RECIPIENTS))

    logger.info("Fetching imputed multilateral data...")
    sectors_multi = get_imputed_multi_by_sector()
    eu_imputed = get_eu27_eui_imputed()

    # The imputed frame has no donor_name of its own; take it from the CRS side so both
    # halves are identified the same way.
    donor_names = (
        sectors_bi[["donor_code", "donor_name"]].drop_duplicates("donor_code")
        .set_index("donor_code")["donor_name"]
    )
    sectors_multi = sectors_multi.assign(
        donor_name=lambda d: d["donor_code"].map(donor_names)
    )
    eu_imputed = eu_imputed.assign(donor_name=lambda d: d["donor_code"].map(donor_names))
    unnamed = sorted(sectors_multi.loc[sectors_multi["donor_name"].isna(), "donor_code"].unique())
    if unnamed:
        logger.warning(
            "Imputed multilateral rows for providers absent from the CRS side, so unnamed: "
            "%s. They are dropped from the view.", unnamed,
        )
        sectors_multi = sectors_multi[sectors_multi["donor_name"].notna()]

    # recipient_name comes from the shared classification table, so both halves are
    # identified the same way without either needing to carry it.
    logger.info("Attaching recipient classifications...")
    sectors_bi = add_recipient_classifications(sectors_bi, classified, "bilateral")
    sectors_multi = add_recipient_classifications(
        sectors_multi, classified, "imputed multilateral"
    )
    eu_imputed = add_recipient_classifications(
        eu_imputed, classified, "EU27 & EU Institutions imputed"
    )

    sectors = pd.concat([sectors_bi, sectors_multi], ignore_index=True)
    sectors = sectors[sectors["value"] != 0]

    # Categories before the eight-fold currency expansion: as objects these label columns cost
    # ~8 bytes per row in pointers alone and make the pivot's MultiIndex far more expensive.
    sectors = _as_categoricals(sectors)

    logger.info("Adding currencies and prices...")
    sectors = add_currencies_and_prices(sectors, base_year=SECTORS_TIME["base"])
    sectors = sectors[sectors["value"].notna() & (sectors["value"] != 0)]
    # Converted separately, since it is a differently corrected view of the same spending.
    eu_imputed = _as_categoricals(
        add_currencies_and_prices(eu_imputed, base_year=SECTORS_TIME["base"])
    )
    eu_imputed = eu_imputed[eu_imputed["value"].notna() & (eu_imputed["value"] != 0)]

    logger.info("Building donor and recipient group totals...")
    sectors = pd.concat(
        [sectors, *build_crs_recipient_group_totals(sectors, RECIPIENT_GROUP_COLS)], ignore_index=True
    )
    sectors = pd.concat(
        [
            sectors,
            # include_eu27_eui=False: a plain sum would double count member contributions
            # routed through the institutions, so the bloc is built from the corrected frame.
            *build_crs_donor_group_totals(sectors, DONOR_GROUP_COLS, include_eu27_eui=False),
            # The corrected frame needs the same recipient groups as everything else, or the
            # bloc would carry imputed multilateral for countries but not for regions,
            # income groups or the overall total.
            build_eu27_eui_total(
                sectors,
                pd.concat(
                    [
                        eu_imputed,
                        *build_crs_recipient_group_totals(eu_imputed, RECIPIENT_GROUP_COLS),
                    ],
                    ignore_index=True,
                ),
                DONOR_GROUP_COLS,
            ),
        ],
        ignore_index=True,
    )
    del eu_imputed

    logger.info("Adding sector names...")
    sectors = sectors.rename(columns={"sub_sector": "sub_sector_name"})
    sectors["sector_name"] = (
        sectors["sub_sector_name"]
        .astype("object")
        .map(sector_lists.get_broad_sector_groups())
        .fillna("Unallocated/ Unspecified")
    )

    # Codes and classifications have done their work in the group totals above, and the
    # aggregates introduced new group names, which turns the concatenated label columns back
    # into objects. Drop what is spent and re-apply the categories before the pivot.
    sectors = sectors.drop(
        columns=["donor_code", "recipient_code", CRS_REGION_COL, CRS_INCOME_COL],
        errors="ignore",
    )
    sectors = _as_categoricals(sectors)

    logger.info("Pivoting to wide format...")
    index_cols = (
        "year",
        "donor_name",
        "recipient_name",
        "indicator_name",
        "sector_name",
        "sub_sector_name",
    )
    sectors = widen_currency_price(df=sectors, index_cols=index_cols)

    logger.info("Adding shares...")
    sectors = add_share_of_reference_total(
        sectors,
        filter_col="recipient_name",
        filter_val="ODA eligible countries",
        merge_cols=["year", "donor_name"],
        pct_col="pct_total_donor",
    )
    sectors = add_share_of_reference_total(
        sectors,
        filter_col="donor_name",
        filter_val="All bilateral donors",
        merge_cols=["year", "recipient_name"],
        pct_col="pct_total_recipient",
    )

    sectors = _add_partition_slugs(sectors)

    return convert_values_to_units(sectors)


def _add_partition_slugs(sectors: pd.DataFrame) -> pd.DataFrame:
    """Add the URL-safe slug columns the CDN dataset is partitioned by."""
    for column in ("donor", "recipient"):
        names = sectors[f"{column}_name"].dropna().unique()
        mapping = {name: slugify(name) for name in names}

        collisions = {}
        for name, slug in mapping.items():
            collisions.setdefault(slug, []).append(name)
        clashing = {slug: names_ for slug, names_ in collisions.items() if len(names_) > 1}
        if clashing:
            raise ValueError(
                f"{column} slugs are not unique, which would merge distinct entities into "
                f"one partition: {clashing}"
            )

        # Plain strings, not categories: a dictionary-typed partition key makes pyarrow hang
        # in teardown when writing thousands of hive partitions.
        sectors[f"{column}_slug"] = (
            sectors[f"{column}_name"].astype("object").map(mapping).astype("object")
        )

    return sectors


def _slug_map(sectors: pd.DataFrame, column: str) -> dict:
    """Name to slug map for the frontend to build partition paths from."""
    return (
        sectors[[f"{column}_name", f"{column}_slug"]]
        .drop_duplicates()
        .set_index(f"{column}_name")[f"{column}_slug"]
        .sort_index()
        .to_dict()
    )


if __name__ == "__main__":
    logger.info("Generating sectors table...")
    df = combined_sectors()

    sub_sectors_by_sector = (
        df[["sector_name", "sub_sector_name"]]
        .drop_duplicates()
        .groupby("sector_name")["sub_sector_name"]
        .apply(lambda s: sorted(s))
        .to_dict()
    )

    generate_view_options(
        df=df,
        columns={
            "donor_name": DONORS_ORDER,
            "recipient_name": CRS_RECIPIENTS_ORDER,
            "indicator_name": [],
            "sector_name": [],
            "year": [],
        },
        base_year=SECTORS_TIME["base"],
        file_name="sectors_view_options.json",
        extra={
            "donor_slugs": _slug_map(df, "donor"),
            "recipient_slugs": _slug_map(df, "recipient"),
            "sub_sectors_by_sector": sub_sectors_by_sector,
        },
    )

    logger.info("Writing partitioned dataset...")
    write_partitioned_dataset(
        df, "sectors_view", partition_cols=["donor_slug", "recipient_slug"]
    )
    logger.info("Sectors view completed")

    # pyarrow's global thread pool intermittently deadlocks in its static destructor after a
    # large partitioned write, leaving the process hung with all the work already done:
    #   exit -> __cxa_finalize_ranges -> arrow::internal::ThreadPool::~ThreadPool
    #        -> Shutdown -> condition_variable::wait
    # Nothing is buffered by this point — the dataset is on disk and logs go to stderr — so
    # skip interpreter teardown rather than let CI hang until its timeout.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
