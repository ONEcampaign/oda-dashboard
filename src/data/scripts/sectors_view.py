"""Builds the sectors view: ODA by sector and sub-sector, bilateral and imputed multilateral.

Shape of the pipeline:
    1. oecd.crs.bilateral_oda gross disbursements by purpose code, mapped to sub-sectors
       and sectors through oda.sectors. From CRS_PSI_START_YEAR it leaves out private
       sector instruments (CRS category 60)
    2. one.crs.imputed_multilateral_oda by purpose and channel, read one year at a time,
       plus a channel-corrected copy used only for the EU27 + institutions aggregate
    3. recipient names, regions and income groups from the shared CRS classification table
    4. recipient groups then donor groups, summed locally because the CRS publishes neither
    5. shares from both perspectives, then values as integer units
    6. a partitioned dataset addressed by donor and recipient slug, plus its options, under
       cdn_files (or --output-dir)

This is the largest view by far, so the frame is kept dictionary-encoded and stripped of spent
columns before the pivot; see _as_categoricals and the drop before widen_currency_price.

Output is keyed by name: year, donor_name, recipient_name, indicator_name, sector_name,
sub_sector_name, with donor_slug and recipient_slug as the partition keys.
"""

import argparse
import os
import sys
from pathlib import Path

import oda_data as oda
import pandas as pd

from src.data.analysis_tools.imputations import iter_imputed_multilateral
from src.data.analysis_tools.naming import slugify
from src.data.analysis_tools.oda import (
    ProvenanceLog,
    open_context,
    run_query,
    scan_table,
    scanned_release,
)
from src.data.analysis_tools.outputs import (
    build_view_options,
    write_partitioned_dataset,
    write_view_options,
)
from src.data.analysis_tools.sectors import (
    BILATERAL_ODA,
    CRS_BASIS,
    assign_sub_sector,
    sector_names,
)
from src.data.analysis_tools.transformations import (
    RECIPIENT_CLASSIFICATION_COLS,
    add_currencies_and_prices,
    add_donor_and_recipient_shares,
    add_recipient_classifications,
    build_donor_group_totals,
    convert_values_to_units,
    drop_empty_series,
    drop_empty_values,
    get_crs_recipient_classifications,
    widen_currency_price,
    with_crs_recipient_group_totals,
)
from src.data.config import (
    BILATERAL,
    CRS_PSI_START_YEAR,
    CRS_RECIPIENTS,
    CRS_RECIPIENTS_ORDER,
    DEFAULT_DONOR,
    DEFAULT_RECIPIENT,
    DONORS_ORDER,
    EU27_EUI_NAME,
    EU_COUNTRIES,
    EU_INSTITUTIONS,
    EU_TOTAL,
    EUI_CHANNEL_CODES,
    IMPUTED_MULTILATERAL,
    LABEL_COLUMNS,
    PATHS,
    PROVIDERS,
    SECTORS_TIME,
    logger,
)

YEARS: range = range(SECTORS_TIME["start"], SECTORS_TIME["end"] + 1)
CRS: str = "crs"

DATASET_DIR: str = "sectors_view"
OPTIONS_FILE: str = "sectors_view_options.json"

VIEW_KEYS: list[str] = [
    "year",
    "donor_name",
    "recipient_name",
    "indicator_name",
    "sector_name",
    "sub_sector_name",
]
# Everything identifying a row except the recipient, and except the donor, respectively.
RECIPIENT_GROUP_COLS: list[str] = [
    "year",
    "donor_code",
    "donor_name",
    "indicator_name",
    "sub_sector",
    "currency",
    "price",
]
DONOR_GROUP_COLS: list[str] = [
    "year",
    "recipient_name",
    "indicator_name",
    "sub_sector",
    "currency",
    "price",
]


def _as_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    """Cast the label columns to category, for whichever of them are present.

    Sectors carries tens of millions of rows through the currency expansion and the pivot, so
    the label columns have to be dictionary-encoded or the frame does not fit in a CI runner.
    """
    for col in (*LABEL_COLUMNS, *RECIPIENT_CLASSIFICATION_COLS):
        if col in df.columns and df[col].dtype.name != "category":
            df[col] = df[col].astype("category")
    return df


def get_bilateral_by_sector(
    ctx: oda.Context, provenance: ProvenanceLog
) -> pd.DataFrame:
    """Read bilateral CRS gross disbursements by donor, recipient and sub-sector.

    Args:
        ctx: From open_context.
        provenance: Log to record the CRS release in.

    Returns:
        One row per year, donor, recipient and sub-sector, zero rows dropped, in current USD
        millions.
    """
    raw = run_query(
        ctx,
        BILATERAL_ODA,
        years=YEARS,
        providers=list(PROVIDERS),
        recipients=list(CRS_RECIPIENTS),
        by=["provider", "recipient", "sector", "year"],
        basis=CRS_BASIS,
        provenance=provenance,
    )
    sectors_bi = (
        assign_sub_sector(raw)
        .groupby(
            ["year", "donor_code", "donor_name", "recipient_code", "sub_sector"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator_name=BILATERAL)
    )

    return sectors_bi[sectors_bi["value"] != 0]


def _sum_imputed_by_sector(raw: pd.DataFrame) -> pd.DataFrame:
    """Sum imputed multilateral rows to donor, recipient and sub-sector."""
    imputed = (
        raw.groupby(
            ["year", "donor_code", "recipient_code", "sub_sector"],
            dropna=False,
            observed=True,
        )["value"]
        .sum()
        .reset_index()
        .assign(indicator_name=IMPUTED_MULTILATERAL)
    )
    return imputed[imputed["value"] != 0]


def get_eu27_eui_imputed(raw: pd.DataFrame) -> pd.DataFrame:
    """Imputed multilateral for the EU27 + institutions bloc, free of double counting.

    EU member states' core contributions reach the EU institutions through the channels in
    EUI_CHANNEL_CODES. Left in, those rows would be counted once as each member's imputed
    multilateral and again as the institutions' own spending, so they are dropped. The
    institutions' own imputed multilateral is kept in full: their contributions to non-EU
    multilaterals do not overlap with their bilateral spending.

    Derived from the raw read, before channel_code is summed away. Channel adds a dimension
    to every row, which the eight-fold currency expansion would then multiply.

    Args:
        raw: Imputed multilateral rows for every provider, with channel_code and sub_sector.

    Returns:
        The bloc's members and institutions, summed like the main imputed frame.
    """
    routed_via_eui = raw["donor_code"].isin(EU_COUNTRIES) & raw["channel_code"].isin(
        EUI_CHANNEL_CODES
    )
    logger.info(
        "EU27 & EU Institutions: excluding %s USD million of member contributions routed "
        "through EU institution channels, to avoid double counting",
        f"{raw.loc[routed_via_eui, 'value'].sum():,.1f}",
    )
    return _sum_imputed_by_sector(
        raw[raw["donor_code"].isin(EU_TOTAL) & ~routed_via_eui]
    )


def get_imputed_by_sector(
    ctx: oda.Context, provenance: ProvenanceLog
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read imputed multilateral by sub-sector, and the bloc's channel-corrected copy.

    Each year is summed as soon as it is read, so only one year of the raw read, with its
    channel dimension, is ever held.

    Args:
        ctx: From open_context.
        provenance: Log to record the MultiSystem and CRS releases in.

    Returns:
        (imputed multilateral by year, donor, recipient and sub-sector; the EU27 +
        institutions copy from get_eu27_eui_imputed), both in current USD millions.
    """
    imputed, eu_imputed = [], []
    for raw in iter_imputed_multilateral(
        ctx, years=YEARS, providers=PROVIDERS, provenance=provenance
    ):
        raw = assign_sub_sector(raw)
        imputed.append(_sum_imputed_by_sector(raw))
        eu_imputed.append(get_eu27_eui_imputed(raw))

    return (
        pd.concat(imputed, ignore_index=True),
        pd.concat(eu_imputed, ignore_index=True),
    )


def _name_donors(df: pd.DataFrame, donor_names: pd.Series, label: str) -> pd.DataFrame:
    """Name imputed donors from the CRS side, dropping any the CRS does not have.

    The imputed frame has no donor_name of its own, so both halves are identified the same
    way.
    """
    df = df.assign(donor_name=df["donor_code"].map(donor_names))
    unnamed = df["donor_name"].isna()
    if unnamed.any():
        logger.warning(
            "%s for providers absent from the CRS side, so unnamed, is dropped from the "
            "view: %s USD million, donor codes %s",
            label,
            f"{df.loc[unnamed, 'value'].sum():,.1f}",
            sorted(df.loc[unnamed, "donor_code"].unique()),
        )
    return df[~unnamed]


def _convert(df: pd.DataFrame, label: str, provenance: ProvenanceLog) -> pd.DataFrame:
    """Add currencies and prices, then drop the rows left empty."""
    # Categories before the eight-fold currency expansion: as objects these label columns cost
    # ~8 bytes per row in pointers alone and make the pivot's MultiIndex far more expensive.
    converted = add_currencies_and_prices(
        _as_categoricals(df), base_year=SECTORS_TIME["base"], provenance=provenance
    )
    return drop_empty_values(converted, label)


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
        & sectors["indicator_name"].astype("object").eq(BILATERAL)
    ]

    return (
        pd.concat([bilateral, eu_imputed], ignore_index=True)
        .groupby(group_cols, dropna=False, observed=True)["value"]
        .sum()
        .reset_index()
        .assign(donor_name=EU27_EUI_NAME)
    )


def _add_sector_names(sectors: pd.DataFrame) -> pd.DataFrame:
    """Name each sub-sector's broad sector, and drop the codes the totals no longer need."""
    sectors = sectors.rename(columns={"sub_sector": "sub_sector_name"})
    sectors["sector_name"] = sector_names(sectors["sub_sector_name"])

    # The aggregates introduced new group names, which turns the concatenated label columns
    # back into objects, so the categories are re-applied before the pivot.
    sectors = sectors.drop(
        columns=["donor_code", "recipient_code", *RECIPIENT_CLASSIFICATION_COLS],
        errors="ignore",
    )
    return _as_categoricals(sectors)


def combined_sectors(ctx: oda.Context, provenance: ProvenanceLog) -> pd.DataFrame:
    """Assemble the sectors view from its parts.

    Args:
        ctx: From open_context.
        provenance: Log to record every read and the conversion factors in.

    Returns:
        Wide frame keyed by year, donor_name, recipient_name, indicator_name, sector_name and
        sub_sector_name, with the partition slugs and the two share columns.
    """
    logger.info("Fetching bilateral data...")
    sectors_bi = get_bilateral_by_sector(ctx, provenance)
    classified, ldc_members = get_crs_recipient_classifications(
        YEARS, list(CRS_RECIPIENTS)
    )
    # The classification scans the same CRS file; recording it checks the release matches.
    provenance.record_table(CRS, scanned_release(scan_table(CRS)))

    logger.info("Fetching imputed multilateral data...")
    sectors_multi, eu_imputed = get_imputed_by_sector(ctx, provenance)
    donor_names = (
        sectors_bi[["donor_code", "donor_name"]]
        .drop_duplicates("donor_code")
        .set_index("donor_code")["donor_name"]
    )
    sectors_multi = _name_donors(sectors_multi, donor_names, "Imputed multilateral")
    eu_imputed = _name_donors(eu_imputed, donor_names, "EU27 & EU Institutions imputed")

    # recipient_name comes from the shared classification table, so both halves are
    # identified the same way without either needing to carry it.
    logger.info("Attaching recipient classifications...")
    sectors = pd.concat(
        [
            add_recipient_classifications(sectors_bi, classified, "bilateral"),
            add_recipient_classifications(
                sectors_multi, classified, "imputed multilateral"
            ),
        ],
        ignore_index=True,
    )
    eu_imputed = add_recipient_classifications(
        eu_imputed, classified, "EU27 & EU Institutions imputed"
    )
    del sectors_bi, sectors_multi, classified

    logger.info("Adding currencies and prices...")
    sectors = _convert(sectors, "sectors", provenance)
    # Converted separately, since it is a differently corrected view of the same spending.
    eu_imputed = _convert(eu_imputed, "EU27 & EU Institutions imputed", provenance)

    logger.info("Building donor and recipient group totals...")
    sectors = with_crs_recipient_group_totals(
        sectors, RECIPIENT_GROUP_COLS, ldc_members
    )
    sectors = pd.concat(
        [
            sectors,
            # No EU27 + institutions plain sum: it would double count member contributions
            # routed through the institutions, so the bloc is built from the corrected frame.
            *build_donor_group_totals(sectors, DONOR_GROUP_COLS).values(),
            # The corrected frame needs the same recipient groups as everything else, or the
            # bloc would carry imputed multilateral for countries but not for regions,
            # income groups or the overall total.
            build_eu27_eui_total(
                sectors,
                with_crs_recipient_group_totals(
                    eu_imputed, RECIPIENT_GROUP_COLS, ldc_members
                ),
                DONOR_GROUP_COLS,
            ),
        ],
        ignore_index=True,
    )
    del eu_imputed

    logger.info("Adding sector names...")
    sectors = _add_sector_names(sectors)
    # A group sum that cancels to zero in USD current can leave float residue in the
    # converted copies; drop such series in every currency, not row by row.
    sectors = drop_empty_series(
        sectors[[*VIEW_KEYS, "currency", "price", "value"]], VIEW_KEYS, "sectors"
    )

    logger.info("Pivoting to wide format...")
    sectors = widen_currency_price(df=sectors, index_cols=tuple(VIEW_KEYS))

    logger.info("Adding shares...")
    sectors = add_donor_and_recipient_shares(sectors)

    return convert_values_to_units(_add_partition_slugs(sectors))


def _add_partition_slugs(sectors: pd.DataFrame) -> pd.DataFrame:
    """Add the URL-safe slug columns the CDN dataset is partitioned by."""
    for column in ("donor", "recipient"):
        names = sectors[f"{column}_name"].dropna().unique()
        mapping = {name: slugify(name) for name in names}

        collisions = {}
        for name, slug in mapping.items():
            collisions.setdefault(slug, []).append(name)
        clashing = {
            slug: names_ for slug, names_ in collisions.items() if len(names_) > 1
        }
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


def main(output_dir: Path) -> None:
    """Build the sectors view, its dropdown options and the partitioned dataset.

    Args:
        output_dir: Directory to write the dataset and its options into. CI publishes
            PATHS.CDN_FILES; a scratch directory keeps a trial build away from it.
    """
    logger.info("Generating sectors table...")
    provenance = ProvenanceLog()
    with open_context() as ctx:
        df = combined_sectors(ctx, provenance)

    sub_sectors_by_sector = (
        df[["sector_name", "sub_sector_name"]]
        .drop_duplicates()
        .groupby("sector_name", observed=True)["sub_sector_name"]
        .apply(lambda s: sorted(s))
        .to_dict()
    )

    options = build_view_options(
        df=df,
        columns={
            "donor_name": DONORS_ORDER,
            "recipient_name": CRS_RECIPIENTS_ORDER,
            "indicator_name": [],
            "sector_name": [],
            "year": [],
        },
        base_year=SECTORS_TIME["base"],
        defaults={
            "donor_name": DEFAULT_DONOR,
            "recipient_name": DEFAULT_RECIPIENT,
            "indicator_name": [BILATERAL, IMPUTED_MULTILATERAL],
        },
        extra={
            "donor_slugs": _slug_map(df, "donor"),
            "recipient_slugs": _slug_map(df, "recipient"),
            "sub_sectors_by_sector": sub_sectors_by_sector,
            "psi_excluded_from": CRS_PSI_START_YEAR,
            "provenance": provenance.to_dict(),
        },
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Writing partitioned dataset...")
    write_partitioned_dataset(
        df,
        DATASET_DIR,
        partition_cols=["donor_slug", "recipient_slug"],
        root=output_dir,
    )
    # Written after the dataset, so the options only exist alongside the data they describe;
    # CI publishes both to the CDN, where the page reads them.
    write_view_options(options, OPTIONS_FILE, root=output_dir)
    logger.info("Sectors view completed")


def _parse_args() -> argparse.Namespace:
    """Read the command line: only the output directory, which defaults to the CDN files."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PATHS.CDN_FILES,
        help=f"Where to write {DATASET_DIR}/ and {OPTIONS_FILE} (default: cdn_files).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        main(args.output_dir)
        exit_code = 0
    except Exception:
        logger.exception("Sectors view failed")
        exit_code = 1

    # pyarrow's global thread pool intermittently deadlocks in its static destructor after a
    # large partitioned write, leaving the process hung with all the work already done:
    #   exit -> __cxa_finalize_ranges -> arrow::internal::ThreadPool::~ThreadPool
    #        -> Shutdown -> condition_variable::wait
    # Nothing is buffered by this point — the dataset is on disk and logs go to stderr — so
    # skip interpreter teardown rather than let CI hang until its timeout.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
