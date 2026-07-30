import pandas as pd

from oda_data import CRSData
from oda_data.tools import sector_lists
from oda_data.indicators.research.sector_imputations import (
    imputed_multilateral_by_purpose,
)

from src.data.analysis_tools.transformations import (
    add_currencies_and_prices,
    add_share_of_reference_total,
    get_attribute_total,
    get_group_total,
    widen_currency_price,
)
from src.data.config import (
    logger,
    SECTORS_TIME,
    BILATERAL_DONORS,
    EU_INSTITUTIONS,
    EU_COUNTRIES,
    DAC_COUNTRIES,
    G7_COUNTRIES,
    NON_DAC_COUNTRIES,
    CRS_RECIPIENTS,
    SAHEL_RECIPIENTS,
    FRANCE_PRIORITY_RECIPIENTS,
    CRS_INCOME_LABELS,
    CRS_REGION_ROLLUPS,
    SECTORS_UNCLASSIFIED_REGION,
    SECTORS_UNCLASSIFIED_INCOME,
    SECTORS_DONORS_ORDER,
    SECTORS_RECIPIENTS_ORDER,
)
from src.data.analysis_tools.helper_functions import (
    set_cache_dir,
    generate_view_options,
    normalize_unspecified_names,
    slugify,
    write_partitioned_dataset,
    convert_values_to_units,
)

set_cache_dir(oda_data=True, pydeflate=True)

YEARS = range(SECTORS_TIME["start"], SECTORS_TIME["end"] + 1)

# All providers reporting to the CRS in their own right. The CRS has no aggregate
# providers, so every donor group below is summed from these.
SECTORS_PROVIDERS: dict = BILATERAL_DONORS | EU_INSTITUTIONS

REGION_COL = "recipient_region"
INCOME_COL = "incomegroup_name"
CONTINENT_COL = "_continent"

UNALLOCATED_SUB_SECTOR = "Unallocated/unspecified"

CRS_COLUMNS: list[str] = [
    "year",
    "donor_code",
    "donor_name",
    "recipient_code",
    "recipient_name",
    REGION_COL,
    INCOME_COL,
    "purpose_code",
    "usd_disbursement",
]


def _assign_sub_sector(df: pd.DataFrame) -> pd.DataFrame:
    """Label each row with its sub-sector, based on the purpose code."""
    for name, codes in sector_lists.get_sector_groups().items():
        df.loc[df["purpose_code"].isin(codes), "sub_sector"] = name

    # Purpose codes outside every group would otherwise leave a NaN grouping key.
    unmatched = int(df["sub_sector"].isna().sum()) if "sub_sector" in df else len(df)
    if unmatched:
        logger.info(
            "%s rows have a purpose code outside the sector groups, labelled %r",
            f"{unmatched:,}", UNALLOCATED_SUB_SECTOR,
        )
    df["sub_sector"] = df.get("sub_sector", pd.Series(index=df.index, dtype="object"))
    df["sub_sector"] = df["sub_sector"].fillna(UNALLOCATED_SUB_SECTOR)

    return df


def get_bilateral_by_sector() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read bilateral CRS disbursements by sub-sector, carrying the CRS classifications.

    Returns:
        (bilateral totals by sub-sector, the transaction-level rows the classification
        table is built from).
    """
    raw_bilateral = CRSData(years=YEARS).read(
        using_bulk_download=True,
        additional_filters=[
            ("donor_code", "in", list(SECTORS_PROVIDERS)),
            ("recipient_code", "in", list(CRS_RECIPIENTS)),
            ("category", "in", [10, 60]),
        ],
        columns=CRS_COLUMNS,
    )

    # CRSData.read silently drops requested columns that do not exist, which would quietly
    # empty the classifications, so check rather than trust.
    missing = [col for col in CRS_COLUMNS if col not in raw_bilateral.columns]
    if missing:
        raise ValueError(f"CRS did not return required columns: {missing}")

    raw_bilateral["recipient_name"] = normalize_unspecified_names(
        raw_bilateral["recipient_name"]
    )
    raw_bilateral = _assign_sub_sector(raw_bilateral)

    sectors_bi = (
        raw_bilateral.groupby(
            ["year", "donor_code", "donor_name", "recipient_code", "recipient_name",
             "sub_sector"],
            dropna=False,
            observed=True,
        )["usd_disbursement"]
        .sum()
        .reset_index()
        .rename(columns={"usd_disbursement": "value"})
        .assign(indicator_name="Bilateral")
    )

    return sectors_bi[sectors_bi["value"] != 0], raw_bilateral


def get_recipient_classifications(raw_bilateral: pd.DataFrame) -> pd.DataFrame:
    """Build the recipient region and income-group table the whole view is grouped by.

    Only the CRS carries these classifications: imputed multilateral spending is keyed on
    [channel, purpose, recipient, year, currency, prices] alone. Building one table here and
    joining it to both halves keeps the two consistent — grouping one half on a column the
    other lacks is what double counts.

    Args:
        raw_bilateral: Transaction-level CRS rows including region and income columns.

    Returns:
        One row per (recipient_code, year) with region and income group.
    """
    classified = raw_bilateral.loc[
        raw_bilateral[REGION_COL].notna() | raw_bilateral[INCOME_COL].notna(),
        ["recipient_code", "year", REGION_COL, INCOME_COL],
    ].drop_duplicates()

    conflicting = classified[classified.duplicated(["recipient_code", "year"], keep=False)]
    if len(conflicting):
        logger.warning(
            "%s (recipient_code, year) combinations carry more than one CRS "
            "classification; keeping the first: %s",
            conflicting.groupby(["recipient_code", "year"]).ngroups,
            conflicting["recipient_code"].unique().tolist()[:10],
        )
        classified = classified.drop_duplicates(["recipient_code", "year"])

    logger.info("Recipient classification table: %s recipient-years", f"{len(classified):,}")

    return classified


def add_recipient_classifications(
    df: pd.DataFrame, classified: pd.DataFrame, label: str
) -> pd.DataFrame:
    """Attach region and income group to a frame, keyed on (recipient_code, year).

    Recipient-years the CRS never classifies fall back to the recipient's own
    classification from other years, and anything still unmatched gets an explicit
    sentinel — never NaN in a grouping key, and never silently dropped.
    """
    before = df["value"].sum()
    merged = df.merge(
        classified, on=["recipient_code", "year"], how="left", validate="m:1"
    )

    if len(merged) != len(df):
        raise ValueError(
            f"{label}: classification join changed the row count "
            f"({len(df):,} -> {len(merged):,})"
        )

    # Fall back to the recipient's classification from any year before giving up.
    per_recipient = (
        classified.sort_values("year")
        .drop_duplicates("recipient_code", keep="last")
        .set_index("recipient_code")
    )
    for col in (REGION_COL, INCOME_COL):
        gaps = merged[col].isna()
        if gaps.any():
            merged.loc[gaps, col] = merged.loc[gaps, "recipient_code"].map(
                per_recipient[col]
            )
            logger.info(
                "%s: %s rows had no %s for their year; filled from the recipient's other "
                "years where possible",
                label, f"{int(gaps.sum()):,}", col,
            )

    for col, sentinel in ((REGION_COL, SECTORS_UNCLASSIFIED_REGION),
                          (INCOME_COL, SECTORS_UNCLASSIFIED_INCOME)):
        still_missing = merged[col].isna()
        if still_missing.any():
            logger.warning(
                "%s: %s rows worth %s USD million have no %s in the CRS at all; labelled "
                "%r. Recipients: %s",
                label, f"{int(still_missing.sum()):,}",
                f"{merged.loc[still_missing, 'value'].sum():,.1f}", col, sentinel,
                sorted(merged.loc[still_missing, "recipient_name"].dropna().unique())[:10],
            )
            merged[col] = merged[col].fillna(sentinel)

    if abs(merged["value"].sum() - before) > max(1e-6, abs(before) * 1e-9):
        raise ValueError(
            f"{label}: classification join changed the total "
            f"({before:,.2f} -> {merged['value'].sum():,.2f})"
        )

    return merged


def get_imputed_multi_by_sector() -> pd.DataFrame:
    """Read imputed multilateral spending by sub-sector."""
    raw_multi = imputed_multilateral_by_purpose(
        years=YEARS,
        providers=list(SECTORS_PROVIDERS),
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


def combined_sectors() -> pd.DataFrame:
    logger.info("Fetching bilateral data...")
    sectors_bi, raw_bilateral = get_bilateral_by_sector()

    classified = get_recipient_classifications(raw_bilateral)
    del raw_bilateral

    logger.info("Fetching imputed multilateral data...")
    sectors_multi = get_imputed_multi_by_sector()

    # The imputed frame has no donor_name of its own; take it from the CRS side so both
    # halves are identified the same way.
    donor_names = (
        sectors_bi[["donor_code", "donor_name"]].drop_duplicates("donor_code")
        .set_index("donor_code")["donor_name"]
    )
    sectors_multi = sectors_multi.assign(
        donor_name=lambda d: d["donor_code"].map(donor_names)
    )
    unnamed = sorted(sectors_multi.loc[sectors_multi["donor_name"].isna(), "donor_code"].unique())
    if unnamed:
        logger.warning(
            "Imputed multilateral rows for providers absent from the CRS side, so unnamed: "
            "%s. They are dropped from the view.", unnamed,
        )
        sectors_multi = sectors_multi[sectors_multi["donor_name"].notna()]

    # Recipient names only exist on the CRS side; reuse them for the imputed rows before
    # classifying, so both halves are identified the same way throughout.
    recipient_names = (
        sectors_bi[["recipient_code", "recipient_name"]].drop_duplicates("recipient_code")
        .set_index("recipient_code")["recipient_name"]
    )
    sectors_multi["recipient_name"] = sectors_multi["recipient_code"].map(recipient_names)

    logger.info("Attaching recipient classifications...")
    sectors_bi = add_recipient_classifications(sectors_bi, classified, "bilateral")
    sectors_multi = add_recipient_classifications(
        sectors_multi, classified, "imputed multilateral"
    )

    sectors = pd.concat([sectors_bi, sectors_multi], ignore_index=True)
    sectors = sectors[sectors["value"] != 0]

    logger.info("Adding currencies and prices...")
    sectors = add_currencies_and_prices(sectors, base_year=SECTORS_TIME["base"])
    sectors = sectors[sectors["value"].notna() & (sectors["value"] != 0)]

    logger.info("Building donor and recipient group totals...")
    sectors = pd.concat(
        [sectors, *_recipient_group_totals(sectors)], ignore_index=True
    )
    sectors = pd.concat(
        [sectors, *_donor_group_totals(sectors)], ignore_index=True
    )

    logger.info("Adding sector names...")
    sectors = sectors.rename(columns={"sub_sector": "sub_sector_name"})
    sectors["sector_name"] = (
        sectors["sub_sector_name"]
        .map(sector_lists.get_broad_sector_groups())
        .fillna("Unallocated/ Unspecified")
    )

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

    # NOTE: Frontend queries must divide value_* columns by 1e6 to get millions
    return convert_values_to_units(sectors)


def _recipient_group_totals(sectors: pd.DataFrame) -> list[pd.DataFrame]:
    """Build every recipient aggregate: the overall total, income groups, regions, lists."""
    group_cols = [
        "year", "donor_code", "donor_name", "indicator_name", "sub_sector",
        "currency", "price",
    ]

    overall = (
        sectors.groupby(group_cols, dropna=False, observed=True)["value"]
        .sum()
        .reset_index()
        .assign(recipient_name="ODA eligible countries")
    )

    income = get_attribute_total(
        sectors, INCOME_COL, group_cols, label_map=CRS_INCOME_LABELS
    )

    # The CRS uses continent names as region values too, for aid recorded against a whole
    # continent. Those rows belong to the continent rollup below, so they are excluded here:
    # emitting them as regions as well would produce two rows per continent, which the pivot
    # would silently merge.
    regions = get_attribute_total(
        sectors.loc[~sectors[REGION_COL].isin(CRS_REGION_ROLLUPS)], REGION_COL, group_cols
    )

    # Continents are rollups of the CRS regions, so they are summed from the same column.
    region_to_continent = {
        region: continent
        for continent, regions_in in CRS_REGION_ROLLUPS.items()
        for region in regions_in
    }
    continents = get_attribute_total(
        sectors.assign(**{CONTINENT_COL: lambda d: d[REGION_COL].map(region_to_continent)}),
        CONTINENT_COL,
        group_cols,
    ).dropna(subset=["recipient_name"])

    lists = [
        get_group_total(
            sectors,
            members,
            column="recipient",
            group_cols=group_cols,
            group_name=name,
        )
        for name, members in (
            ("Sahel countries", SAHEL_RECIPIENTS),
            ("France priority countries", FRANCE_PRIORITY_RECIPIENTS),
        )
    ]

    return [overall, income, regions, continents, *lists]


def _donor_group_totals(sectors: pd.DataFrame) -> list[pd.DataFrame]:
    """Build every donor aggregate by summing the providers that report to the CRS.

    "All bilateral donors" includes EU Institutions in full. The CRS offers no equivalent of
    the DAC1 weighting the other views use to strip out EU member contributions, so this
    total does double count them; it is the denominator for pct_total_recipient.
    """
    group_cols = [
        "year", "recipient_name", "indicator_name", "sub_sector", "currency", "price",
    ]

    return [
        get_group_total(
            sectors, members, group_cols=group_cols, group_name=name
        )
        for name, members in (
            ("All bilateral donors", SECTORS_PROVIDERS),
            ("DAC countries", DAC_COUNTRIES),
            ("Non-DAC countries", NON_DAC_COUNTRIES),
            ("G7 countries", G7_COUNTRIES),
            ("EU27 countries", EU_COUNTRIES),
        )
    ]


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

        sectors[f"{column}_slug"] = sectors[f"{column}_name"].map(mapping)

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
            "donor_name": SECTORS_DONORS_ORDER,
            "recipient_name": SECTORS_RECIPIENTS_ORDER,
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
