import pandas as pd
from oda_data import OECDClient
from pydeflate import oecd_dac_deflate, oecd_dac_exchange, set_pydeflate_path

from src.data.config import (
    logger,
    BASE_TIME,
    CURRENCIES,
    ALL_DONORS,
    AGGREGATE_DONORS,
    BILATERAL_DONORS,
    EU_COUNTRIES,
    PATHS,
    CRS_PROVIDERS,
    DAC_COUNTRIES,
    G7_COUNTRIES,
    NON_DAC_COUNTRIES,
    SAHEL_RECIPIENTS,
    FRANCE_PRIORITY_RECIPIENTS,
    CRS_INCOME_LABELS,
    CRS_REGION_ROLLUPS,
    CRS_UNCLASSIFIED_REGION,
    CRS_UNCLASSIFIED_INCOME,
    EU_INSTITUTIONS,
)

from src.data.analysis_tools.helper_functions import (
    apply_name_overrides,
    normalize_unspecified_names,
)

set_pydeflate_path(PATHS.PYDEFLATE)


def get_gni(start_year: int, end_year: int) -> pd.DataFrame:

    gni_raw = OECDClient(
        years=range(start_year, end_year + 1),
        providers=list(ALL_DONORS),
        measure="net_disbursement",
        use_bulk_download=True,
    ).get_indicators("DAC1.40.1")[["donor_code", "donor_name", "year", "value"]]

    # Deduplicate - raw data may have duplicate rows with identical GNI values
    gni_df = gni_raw.drop_duplicates(subset=["donor_code", "year"])

    gni_df = apply_name_overrides(gni_df, AGGREGATE_DONORS, "donor")

    eu27_df = get_group_total(gni_df, EU_COUNTRIES, ["year"], group_name="EU27 countries")
    # Label must match the donor_name used by the views, or the GNI merge silently
    # yields NaN. EU institutions have no GNI of their own, so the denominator for
    # the EU27 + institutions aggregate is the member states' combined GNI.
    eu27_eui_df = get_group_total(
        gni_df, EU_COUNTRIES, ["year"], group_name="EU27 & EU Institutions"
    )
    bilateral_df = get_group_total(
        gni_df,
        BILATERAL_DONORS,
        ["year"],
        group_name="All bilateral donors"
    )

    return (
        pd.concat([gni_df, eu27_df, eu27_eui_df, bilateral_df])
        .rename(columns={"value": "gni"})
        .drop(columns="donor_code")
    )



def _default_coverage_cols(df: pd.DataFrame, column: str) -> list[str]:
    """Pick the combinations to assess group coverage over.

    Completeness is judged per year and per counterpart entity: when aggregating donors
    that means year x recipient, and when aggregating recipients it means year x donor.
    Columns absent from the data are skipped.

    Args:
        df: Frame being aggregated.
        column: Entity being aggregated over, "donor" or "recipient".

    Returns:
        Column names to group by when checking coverage.
    """
    counterpart = "recipient" if column == "donor" else "donor"
    candidates = ["year", f"{counterpart}_code", f"{counterpart}_name"]

    cols = ["year"] if "year" in df.columns else []
    for candidate in candidates[1:]:
        if candidate in df.columns:
            cols.append(candidate)
            break

    return cols


def _warn_missing_group_members(
    df: pd.DataFrame,
    group_dict: dict,
    code_col: str,
    coverage_cols: list[str],
    label: str,
) -> None:
    """Warn about group members missing from the data being aggregated.

    Members that never appear are reported separately from members missing out of
    individual combinations: the former means the total silently omits them, while the
    latter is usually genuine sparsity (a donor simply gave nothing that year).

    Args:
        df: Frame being aggregated, before filtering to the group.
        group_dict: Mapping of {member code: member name} defining the group.
        code_col: Column holding the member codes.
        coverage_cols: Columns whose combinations are checked for completeness.
        label: Name of the total being built, used in the log message.
    """
    members = set(group_dict)
    present = df.loc[df[code_col].isin(members), [code_col, *coverage_cols]].drop_duplicates()
    found = set(present[code_col].dropna().unique())

    never = sorted(members - found)
    if never:
        logger.warning(
            "%s: %d of %d members never appear in the data, so the total excludes them: %s",
            label, len(never), len(members), {code: group_dict[code] for code in never},
        )

    if not coverage_cols:
        return

    per_combination = present.groupby(
        coverage_cols, dropna=False, observed=True
    )[code_col].nunique()
    incomplete = int((per_combination < len(members)).sum())
    if not incomplete:
        return

    total = len(per_combination)
    appearances = present.groupby(code_col, dropna=False, observed=True).size()
    gaps = sorted(
        ((total - int(appearances.get(code, 0)), code) for code in members), reverse=True
    )
    worst = ", ".join(
        f"{group_dict[code]} ({missing:,})" for missing, code in gaps[:5] if missing
    )
    logger.warning(
        "%s: %d of %d %s combinations are missing at least one member. Members absent "
        "from the most combinations: %s. This is expected where a member reported "
        "nothing, but a sharp change here means lost coverage.",
        label, incomplete, total, " x ".join(coverage_cols), worst,
    )


def get_group_total(
        df: pd.DataFrame,
        group_dict: dict,
        group_cols: list,
        column: str = "donor",
        check_all_keys: bool = True,
        group_name: str = None,
        group_code: str = None,
        coverage_cols: list[str] = None,
) -> pd.DataFrame:
    """Sum a group of donors or recipients into a single aggregate row per group_cols.

    Args:
        df: Long-form frame with a "value" column.
        group_dict: Mapping of {member code: member name} defining the group.
        group_cols: Columns to group by when summing.
        column: Entity being aggregated over, "donor" or "recipient".
        check_all_keys: Log a warning naming group members missing from the data. Never
            raises: members legitimately absent from a source must not break the build.
        group_name: Value to assign to the aggregate's name column.
        group_code: Value to assign to the aggregate's code column.
        coverage_cols: Combinations to check coverage over. Defaults to year plus the
            counterpart entity, e.g. year x recipient when aggregating donors.

    Returns:
        The aggregated frame.
    """
    code_col = f"{column}_code"
    name_col = f"{column}_name"

    if check_all_keys:
        _warn_missing_group_members(
            df,
            group_dict,
            code_col,
            coverage_cols if coverage_cols is not None
            else _default_coverage_cols(df, column),
            group_name or f"{column} group total",
        )

    df = (
        df.loc[lambda d: d[code_col].isin(group_dict)]
        .groupby(group_cols, observed=True, dropna=False)["value"]
        .sum()
        .reset_index()
    )

    if group_name:
        df[name_col] = group_name
    if group_code:
        df[code_col] = group_code

    return df




# CRS column names carrying the classifications both CRS-based views group by.
CRS_REGION_COL = "recipient_region"
CRS_INCOME_COL = "incomegroup_name"
_CONTINENT_COL = "_continent"

_CRS_CLASSIFICATION_COLUMNS = [
    "year",
    "recipient_code",
    "recipient_name",
    CRS_REGION_COL,
    CRS_INCOME_COL,
]


def _modal_value(series: pd.Series):
    """Return the most common non-null value, ties broken by sort order for determinism."""
    present = series.dropna()
    if present.empty:
        return pd.NA
    return present.mode().sort_values().iloc[0]


def get_crs_recipient_classifications(
    years: range | list | int, recipients: list | None = None
) -> pd.DataFrame:
    """Build the recipient name, region and income-group table the CRS views group by.

    Only the CRS carries these classifications. Imputed multilateral spending is keyed on
    [channel, purpose, recipient, year, currency, prices] and policy marker data on
    [provider, agency, recipient, modality, finance type, purpose, year], so neither knows a
    recipient's region or income group. Building one table here and joining it to every frame
    keeps them consistent: grouping one frame on a column another lacks is what double counts.

    Args:
        years: Years to cover.
        recipients: Recipient codes to restrict to, or None for all.

    Returns:
        One row per (recipient_code, year) with recipient name, region and income group.
    """
    from oda_data import CRSData

    raw = CRSData(years=years, recipients=recipients).read(
        using_bulk_download=True, columns=_CRS_CLASSIFICATION_COLUMNS
    )

    # CRSData.read silently drops requested columns that do not exist, which would quietly
    # empty the classifications, so check rather than trust.
    missing = [c for c in _CRS_CLASSIFICATION_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"CRS did not return required columns: {missing}")

    raw["recipient_name"] = normalize_unspecified_names(raw["recipient_name"])

    attributes = ["recipient_name", CRS_REGION_COL, CRS_INCOME_COL]
    grouped = raw.groupby(["recipient_code", "year"], dropna=False, observed=True)[attributes]

    # Reduce each column to its most common non-null value, rather than deduplicating whole
    # rows. A recipient-year often has some transactions with a blank region or income group,
    # and dropping duplicate rows can pick one of those and lose a value the data does have.
    # Where transactions genuinely disagree, the majority wins, so the result does not depend
    # on row order.
    classified = grouped.agg(_modal_value).reset_index()

    conflicts = grouped.nunique(dropna=True)
    for col in attributes:
        disagreeing = conflicts.index[conflicts[col] > 1]
        if len(disagreeing):
            logger.warning(
                "%s (recipient_code, year) combinations report more than one %s; taking the "
                "most common. Recipient codes: %s",
                len(disagreeing), col,
                sorted({int(code) for code, _ in disagreeing})[:10],
            )

    logger.info("Recipient classification table: %s recipient-years", f"{len(classified):,}")

    return classified


def add_recipient_classifications(
    df: pd.DataFrame, classified: pd.DataFrame, label: str
) -> pd.DataFrame:
    """Attach recipient name, region and income group, keyed on (recipient_code, year).

    Recipient-years the CRS never classifies fall back to the recipient's own classification
    from other years, and anything still unmatched gets an explicit sentinel — never NaN in a
    grouping key, and never silently dropped.

    Args:
        df: Frame with recipient_code, year and a "value" column.
        classified: Table from get_crs_recipient_classifications.
        label: Name of the frame, used in log messages.

    Returns:
        The frame with recipient_name, region and income group attached.
    """
    before_rows, before_value = len(df), df["value"].sum()
    merged = df.drop(columns=["recipient_name"], errors="ignore").merge(
        classified, on=["recipient_code", "year"], how="left", validate="m:1"
    )

    if len(merged) != before_rows:
        raise ValueError(
            f"{label}: classification join changed the row count "
            f"({before_rows:,} -> {len(merged):,})"
        )

    # Fall back to the recipient's classification from any year before giving up.
    per_recipient = (
        classified.sort_values("year")
        .drop_duplicates("recipient_code", keep="last")
        .set_index("recipient_code")
    )
    for col in ("recipient_name", CRS_REGION_COL, CRS_INCOME_COL):
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

    for col, sentinel in (
        (CRS_REGION_COL, CRS_UNCLASSIFIED_REGION),
        (CRS_INCOME_COL, CRS_UNCLASSIFIED_INCOME),
    ):
        still_missing = merged[col].isna()
        if still_missing.any():
            logger.warning(
                "%s: %s rows worth %s have no %s in the CRS at all; labelled %r. "
                "Recipient codes: %s",
                label, f"{int(still_missing.sum()):,}",
                f"{merged.loc[still_missing, 'value'].sum():,.1f}", col, sentinel,
                sorted(merged.loc[still_missing, "recipient_code"].dropna().unique())[:10],
            )
            merged[col] = merged[col].fillna(sentinel)

    if abs(merged["value"].sum() - before_value) > max(1e-6, abs(before_value) * 1e-9):
        raise ValueError(
            f"{label}: classification join changed the total "
            f"({before_value:,.2f} -> {merged['value'].sum():,.2f})"
        )

    return merged


def build_crs_recipient_group_totals(
    df: pd.DataFrame, group_cols: list[str]
) -> list[pd.DataFrame]:
    """Build every recipient aggregate: overall total, income groups, regions, continents, lists.

    Args:
        df: Frame carrying the CRS classification columns and a "value" column.
        group_cols: Columns identifying everything except the recipient, e.g.
            year, donor_code, donor_name, indicator_name, currency, price.

    Returns:
        One frame per aggregate, each naming its group in recipient_name.
    """
    overall = (
        df.groupby(group_cols, dropna=False, observed=True)["value"]
        .sum()
        .reset_index()
        .assign(recipient_name="ODA eligible countries")
    )

    income = get_attribute_total(
        df, CRS_INCOME_COL, group_cols, label_map=CRS_INCOME_LABELS
    )

    # The CRS uses continent names as region values too, for aid recorded against a whole
    # continent. Those rows belong to the continent rollup below, so they are excluded here:
    # emitting them as regions as well would produce two rows per continent, which the pivot
    # would silently merge.
    regions = get_attribute_total(
        df.loc[~df[CRS_REGION_COL].isin(CRS_REGION_ROLLUPS)], CRS_REGION_COL, group_cols
    )

    # Continents are rollups of the CRS regions, so they are summed from the same column.
    region_to_continent = {
        region: continent
        for continent, regions_in in CRS_REGION_ROLLUPS.items()
        for region in regions_in
    }
    continents = get_attribute_total(
        df.assign(**{_CONTINENT_COL: lambda d: d[CRS_REGION_COL].map(region_to_continent)}),
        _CONTINENT_COL,
        group_cols,
    ).dropna(subset=["recipient_name"])

    lists = [
        get_group_total(
            df, members, column="recipient", group_cols=group_cols, group_name=name
        )
        for name, members in (
            ("Sahel countries", SAHEL_RECIPIENTS),
            ("France priority countries", FRANCE_PRIORITY_RECIPIENTS),
        )
    ]

    return [overall, income, regions, continents, *lists]


def build_crs_donor_group_totals(
    df: pd.DataFrame, group_cols: list[str], include_eu27_eui: bool = True
) -> list[pd.DataFrame]:
    """Build every donor aggregate by summing the providers that report to the CRS.

    "All bilateral donors" includes EU Institutions in full. The CRS offers no equivalent of
    the DAC1 weighting the other views use to strip out EU member contributions, so this
    total does double count them; it is also the denominator for recipient-perspective shares.

    "EU27 & EU Institutions" is a plain sum of the member states and the institutions, which is
    correct only where the data has no imputed multilateral component — there is then no channel
    through which members' core contributions could be counted twice. Views that do carry
    imputed multilateral spending must pass include_eu27_eui=False and build the bloc
    themselves, excluding members' contributions routed through EU institution channels.

    Args:
        df: Frame with donor_code and a "value" column.
        group_cols: Columns identifying everything except the donor.
        include_eu27_eui: Whether to add the EU27 + institutions bloc as a plain sum.

    Returns:
        One frame per aggregate, each naming its group in donor_name.
    """
    groups = [
        ("All bilateral donors", CRS_PROVIDERS),
        ("DAC countries", DAC_COUNTRIES),
        ("Non-DAC countries", NON_DAC_COUNTRIES),
        ("G7 countries", G7_COUNTRIES),
        ("EU27 countries", EU_COUNTRIES),
    ]
    if include_eu27_eui:
        groups.append(("EU27 & EU Institutions", EU_COUNTRIES | EU_INSTITUTIONS))

    return [
        get_group_total(df, members, group_cols=group_cols, group_name=name)
        for name, members in groups
    ]


def add_share_of_group_total(
    df: pd.DataFrame, group_cols: list[str], pct_col: str
) -> pd.DataFrame:
    """Add each row's value_usd_current as a share of its own group's total.

    Unlike add_share_of_reference_total, the denominator is not a reference entity but the
    group the row already belongs to — used where the indicators partition a whole, as the
    gender marker scores do.

    Args:
        df: Wide-form frame containing value_usd_current.
        group_cols: Columns defining the group whose total is the denominator.
        pct_col: Name of the share column to add.

    Returns:
        The frame with pct_col added.
    """
    total = (
        df.groupby(group_cols, dropna=False, observed=True)["value_usd_current"]
        .sum()
        .reset_index()
        .rename(columns={"value_usd_current": "total_oda"})
    )
    merged = df.merge(total, on=group_cols, how="left", validate="m:1")
    merged[pct_col] = (merged["value_usd_current"] / merged["total_oda"]).round(6)
    return merged.drop(columns=["total_oda"])


def get_attribute_total(
    df: pd.DataFrame,
    attribute_col: str,
    group_cols: list,
    column: str = "recipient",
    label_map: dict | None = None,
) -> pd.DataFrame:
    """Sum rows by a classification the data itself carries, e.g. CRS region or income group.

    The counterpart to get_group_total: that one aggregates a group defined by a list of
    member codes, this one aggregates a group defined by an attribute column, so the
    membership never has to be maintained anywhere.

    Args:
        df: Long-form frame with a "value" column and the attribute column.
        attribute_col: Column holding the classification, e.g. "incomegroup_name".
        group_cols: Columns to group by alongside the attribute.
        column: Entity the groups stand in for, "donor" or "recipient".
        label_map: Optional display labels keyed by attribute value. Values missing from
            the map keep their original label and are logged.

    Returns:
        One row per attribute value per group_cols combination, named as the entity.
    """
    name_col = f"{column}_name"

    totals = (
        df.groupby(group_cols + [attribute_col], dropna=False, observed=True)["value"]
        .sum()
        .reset_index()
    )

    # The attribute may arrive dictionary-encoded, in which case mapping it to new labels and
    # filling gaps would fail on values outside its categories. Work in plain objects.
    attribute = totals[attribute_col].astype("object")

    if label_map:
        unmapped = sorted(set(attribute.dropna().unique()) - set(label_map))
        if unmapped:
            logger.warning(
                "%s: no display label configured for %s, keeping the raw value(s): %s",
                attribute_col, len(unmapped), unmapped,
            )
        totals[name_col] = attribute.map(label_map).fillna(attribute)
    else:
        totals[name_col] = attribute

    return totals.drop(columns=[attribute_col])


def add_share_of_reference_total(
    df: pd.DataFrame,
    filter_col: str,
    filter_val: str,
    merge_cols: list[str],
    pct_col: str,
) -> pd.DataFrame:
    """Add each row's value_usd_current as a share of a reference entity's total.

    The reference total sums value_usd_current across ALL indicators for the entity
    identified by filter_col == filter_val, grouped by merge_cols. Summing across
    indicators means the indicator percentages for any (year, donor, recipient) pair sum to
    that entity's combined share, never exceeding 100%.

    Args:
        df: Wide-form frame containing value_usd_current.
        filter_col: Column identifying the reference entity, e.g. "donor_name".
        filter_val: Value identifying the reference entity, e.g. "All bilateral donors".
        merge_cols: Columns the reference total is grouped by and merged on.
        pct_col: Name of the share column to add.

    Returns:
        The frame with pct_col added.
    """
    total = (
        df.loc[lambda d: d[filter_col] == filter_val]
        .groupby(merge_cols, dropna=False, observed=True)["value_usd_current"]
        .sum()
        .reset_index()
        .rename(columns={"value_usd_current": "total_oda"})
    )
    merged = df.merge(total, on=merge_cols, how="left", validate="m:1")
    merged[pct_col] = (merged["value_usd_current"] / merged["total_oda"]).round(6)
    return merged.drop(columns=["total_oda"])


def add_currencies_and_prices(
    df: pd.DataFrame, base_year: int = BASE_TIME["base"]
) -> pd.DataFrame:
    """
    Adds copies of the data in different currencies and prices
    """
    # do the currency conversions first
    current_dfs = []

    df = df.assign(currency="USD", price="current")

    for currency in CURRENCIES:
        logger.info(f"Converting to {currency}")
        if currency == "USD":
            current_dfs.append(df.assign(currency=currency, price="current"))
        else:
            converted = oecd_dac_exchange(
                data=df.copy(),
                source_currency="USA",
                target_currency=currency,
                id_column="donor_code",
                use_source_codes=True,
            )
            current_dfs.append(converted.assign(currency=currency, price="current"))

    constant_dfs = []
    for currency in CURRENCIES:
        converted = oecd_dac_deflate(
            data=df.copy(),
            base_year=base_year,
            source_currency="USA",
            target_currency=currency,
            id_column="donor_code",
            use_source_codes=True,
        )
        constant_dfs.append(converted.assign(currency=currency, price="constant"))

    # Don't include df in concat since USD/current is already in current_dfs[0]
    return pd.concat(current_dfs + constant_dfs, ignore_index=True)


def widen_currency_price(
    df: pd.DataFrame,
    index_cols: tuple[str, ...] = ("year", "donor_code", "indicator"),
) -> pd.DataFrame:
    """Pivot currency/price pairs into wide value columns.

    Args:
        df: Long-form DataFrame with columns: year, donor_code, indicator, currency, price, value.
        index_cols: Columns to keep as the row index in the wide table.

    Returns:
        Wide DataFrame where columns are like 'USD_current_value', 'USD_constant_value', etc.
    """
    # Pre-process values in long format (much faster than on wide data)
    df["value"] = df["value"].round(4).astype("float32")

    # Check for duplicates before pivoting and aggregate if found. Use subset= rather than
    # df[pivot_cols].duplicated(): the latter materialises a second copy of every index
    # column, which on the sectors frame means tens of millions of rows twice over.
    pivot_cols = list(index_cols) + ["currency", "price"]
    logger.info("Checking for duplicates before pivot...")
    duplicates = df.duplicated(subset=pivot_cols)

    if duplicates.any():
        logger.warning(f"Found {duplicates.sum():,} duplicate rows before pivoting")
        logger.info("Aggregating duplicates by summing values...")
        # Aggregate duplicates by grouping and summing
        df = (
            df.groupby(pivot_cols, dropna=False, observed=True)["value"]
            .sum()
            .reset_index()
        )
        logger.info(f"After aggregation: {len(df):,} rows")
    else:
        logger.info("No duplicates detected - proceeding with pivot")

    wide = df.pivot(
        index=list(index_cols),
        columns=["currency", "price"],
        values="value",
    )

    # Flatten MultiIndex columns -> "value_usd_current"
    wide.columns = [
        f"value_{cur.lower()}_{price}" for cur, price in wide.columns.to_list()
    ]
    wide = wide.reset_index()

    # Reorder columns: index cols first, then sorted value cols
    value_cols = sorted([c for c in wide.columns if c not in index_cols])
    return wide[list(index_cols) + value_cols]


def add_share_of_total_oda(df: pd.DataFrame) -> pd.DataFrame:
    """Add column for share of total ODA"""

    total = (
        df.loc[lambda d: d["indicator_name"] == "Total ODA"]
        .copy()
        .filter(["year", "donor_name", "value_usd_current"])
        .rename(columns={"value_usd_current": "total_oda"})
    )

    merged = df.merge(total, on=["year", "donor_name"], how="left")

    merged["pct_of_total_oda"] = (
        merged["value_usd_current"] / merged["total_oda"]
    ).round(6)

    merged = merged.drop(columns=["total_oda"])

    return merged


def add_share_of_gni(df: pd.DataFrame) -> pd.DataFrame:
    """Add column for share of GNI"""

    gni = get_gni(start_year=df["year"].min(), end_year=df["year"].max())

    merged = df.merge(gni, on=["year", "donor_name"], how="left")

    merged["pct_of_gni"] = (merged["value_usd_current"] / merged["gni"]).round(5)

    merged = merged.drop(columns=["gni"])

    return merged


