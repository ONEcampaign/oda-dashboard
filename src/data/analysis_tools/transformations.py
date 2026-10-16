"""Reshaping and aggregating the data: DataFrame in, DataFrame out.

Everything here takes one or more frames and returns a frame — currency conversion, group
totals, the CRS classification join, the long-to-wide pivot, and the share columns. Nothing
here writes an artifact, and nothing decides how an entity is labelled.

The rule for what belongs elsewhere: writing artifacts is ``outputs``, labelling is ``naming``,
constants are ``config``. Two functions here do fetch from the OECD — ``get_member_gni`` and
``get_crs_recipient_classifications`` — because each exists only to feed the transform beside
it, and splitting them out would separate a denominator or a lookup from its single use.

Sections, in order:
    1. Units
    2. GNI, and the share of it
    3. Group totals, by code list and by data attribute
    4. CRS classifications — the table, the join, and the group builders it feeds
    5. Currencies and prices
    6. Long to wide
    7. Shares
"""

import pandas as pd
import resolvekit as rk
from oda_data import OECDClient
from pydeflate import oecd_dac_deflate, oecd_dac_exchange, set_pydeflate_path

from src.data.analysis_tools.naming import normalize_unspecified_names
from src.data.config import (
    BASE_TIME,
    BILATERAL_DONORS,
    CRS_REGION_ROLLUPS,
    CRS_UNCLASSIFIED_INCOME,
    CRS_UNCLASSIFIED_REGION,
    CURRENCIES,
    DONOR_GROUPS,
    FRANCE_PRIORITY_RECIPIENTS,
    INT32_MAX,
    LDC_GROUP,
    LDC_LABEL,
    PATHS,
    SAHEL_RECIPIENTS,
    UNALLOCATED_BY_INCOME,
    UNITS_PER_MILLION,
    WORLD_BANK_INCOME_GROUPS,
    WORLD_BANK_NOT_CLASSIFIED,
    logger,
)

set_pydeflate_path(PATHS.PYDEFLATE)


def convert_values_to_units(df: pd.DataFrame) -> pd.DataFrame:
    """Convert every value column from millions to whole currency units.

    Integers in units compress far better in parquet than floats in millions, which matters for
    a dataset served over HTTP. Percentage columns are left alone.

    Args:
        df: Wide frame whose value_* columns are in millions.

    Returns:
        The frame with value_* columns as Int32, or Int64 where the range demands it.

    Note:
        This is the contract with the frontend: it divides value_* columns by
        UNITS_PER_MILLION to get back to millions.
    """
    df = df.copy()
    promoted_to_int64 = []
    value_cols = [c for c in df.columns if c.startswith("value_")]

    for col in value_cols:
        # UNITS_PER_MILLION is a float on purpose; an int multiplier silently coarsens the
        # result to float32 precision. See the note on the constant before touching this line.
        units = (df[col] * UNITS_PER_MILLION).round()
        largest = units.abs().max()

        # Int32 tops out at ~2.1 billion units, i.e. ~2,147 million.
        if pd.notna(largest) and largest > INT32_MAX:
            df[col] = units.astype("Int64")
            promoted_to_int64.append(col)
        else:
            df[col] = units.astype("Int32")

    logger.info(
        "Converted %s value columns to units%s",
        len(value_cols),
        f"; {', '.join(promoted_to_int64)} needed Int64" if promoted_to_int64 else "",
    )

    return df


def get_member_gni(start_year: int, end_year: int) -> pd.DataFrame:
    """Read each bilateral donor's GNI.

    A fetch rather than a transformation, kept here because add_share_of_gni is its only
    consumer and the two are easier to follow together.

    Args:
        start_year: First year to read.
        end_year: Last year to read.

    Returns:
        One row per donor_code and year, with donor_name and value (GNI, USD millions).

    Raises:
        ValueError: If the OECD returns two different GNI values for one donor and year.
    """
    gni_raw = OECDClient(
        years=range(start_year, end_year + 1),
        providers=list(BILATERAL_DONORS),
        measure="net_disbursement",
        use_bulk_download=True,
    ).get_indicators("DAC1.40.1")[["donor_code", "donor_name", "year", "value"]]

    key = ["donor_code", "year"]
    conflicting = gni_raw.groupby(key, observed=True)["value"].nunique() > 1
    if conflicting.any():
        raise ValueError(
            f"Conflicting GNI values for donor-years: {conflicting[conflicting].index.tolist()}"
        )
    return gni_raw.drop_duplicates(subset=key)


def add_group_gni(member_gni: pd.DataFrame) -> pd.DataFrame:
    """Add the donor-group GNI the financing view needs to each donor's GNI.

    EU institutions have no GNI of their own, so the EU27 + institutions denominator is the
    member states' combined GNI, under the donor_name the views use.

    Args:
        member_gni: Output of get_member_gni.

    Returns:
        One row per year and donor_name, with a gni column.
    """
    group_totals = build_donor_group_totals(member_gni, ["year"])
    eu27_eui_df = group_totals["EU27 countries"].assign(
        donor_name="EU27 & EU Institutions"
    )

    return (
        pd.concat([member_gni, *group_totals.values(), eu27_eui_df])
        .rename(columns={"value": "gni"})
        .drop(columns="donor_code")
    )


def build_gni_matched_group_totals(
    df: pd.DataFrame, member_gni: pd.DataFrame, group_cols: list[str]
) -> pd.DataFrame:
    """Sum each donor group over only the members that report GNI in that year.

    A group's share of GNI must divide the ODA of the same members whose GNI is in the
    denominator. Donors without GNI (Saudi Arabia and Kuwait in some years, for example)
    would otherwise add ODA to the numerator only.

    Args:
        df: Long frame of individual donors in current USD, with donor_code and value.
        member_gni: Output of get_member_gni.
        group_cols: Columns identifying everything except the donor, e.g. year, indicator.

    Returns:
        One row per group and group_cols, with the matched total in gni_matched_value.
    """
    reporting = df.merge(
        member_gni[["donor_code", "year"]], on=["donor_code", "year"], how="inner"
    )
    return pd.concat(build_donor_group_totals(reporting, group_cols).values()).rename(
        columns={"value": "gni_matched_value"}
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
    present = df.loc[
        df[code_col].isin(members), [code_col, *coverage_cols]
    ].drop_duplicates()
    found = set(present[code_col].dropna().unique())

    never = sorted(members - found)
    if never:
        logger.warning(
            "%s: %d of %d members never appear in the data, so the total excludes them: %s",
            label,
            len(never),
            len(members),
            {code: group_dict[code] for code in never},
        )

    if not coverage_cols:
        return

    per_combination = present.groupby(coverage_cols, dropna=False, observed=True)[
        code_col
    ].nunique()
    incomplete = int((per_combination < len(members)).sum())
    if not incomplete:
        return

    total = len(per_combination)
    appearances = present.groupby(code_col, dropna=False, observed=True).size()
    gaps = sorted(
        ((total - int(appearances.get(code, 0)), code) for code in members),
        reverse=True,
    )
    worst = ", ".join(
        f"{group_dict[code]} ({missing:,})" for missing, code in gaps[:5] if missing
    )
    logger.warning(
        "%s: %d of %d %s combinations are missing at least one member. Members absent "
        "from the most combinations: %s. This is expected where a member reported "
        "nothing, but a sharp change here means lost coverage.",
        label,
        incomplete,
        total,
        " x ".join(coverage_cols),
        worst,
    )


def get_group_total(
    df: pd.DataFrame,
    group_dict: dict,
    group_cols: list,
    column: str = "donor",
    check_all_keys: bool = True,
    group_name: str | None = None,
    group_code: int | None = None,
    coverage_cols: list[str] | None = None,
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
            coverage_cols
            if coverage_cols is not None
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


# Columns carrying the classifications both CRS-based views group by: the CRS region, and the
# World Bank income group classify_income derives.
CRS_REGION_COL = "recipient_region"
INCOME_GROUP_COL = "income_group"
RECIPIENT_CLASSIFICATION_COLS: tuple[str, ...] = (CRS_REGION_COL, INCOME_GROUP_COL)
_CRS_ISO3_COL = "de_recipientcode"
_CONTINENT_COL = "_continent"

_CRS_CLASSIFICATION_COLUMNS = [
    "year",
    "recipient_code",
    "recipient_name",
    _CRS_ISO3_COL,
    CRS_REGION_COL,
]


def _resolve_iso3(codes: pd.Series, known: set[str]) -> dict[str, str | None]:
    """Resolve CRS recipient codes to ISO3 with resolvekit, one call per unique code.

    Codes already in known are taken as they are: resolvekit's fuzzy matching finds some valid
    codes ambiguous (UGA, UKR). Its bulk resolver is not used because it loses Kosovo, which the
    CRS spells XKV and the scalar resolver maps to XKX.

    Args:
        codes: CRS de_recipientcode values.
        known: ISO3 codes that need no resolving.

    Returns:
        ISO3 code, or None for codes that are not a country, by three-letter code.
    """
    resolver = rk.default()
    resolved = {}
    for code in codes.dropna().unique():
        if not (isinstance(code, str) and len(code) == 3 and code.isalpha()):
            continue
        if code in known:
            resolved[code] = code
            continue
        try:
            resolved[code] = resolver.resolve(code, to="iso3")
        except rk.AmbiguousResolutionError:
            logger.warning("Recipient code %s matches more than one country", code)
            resolved[code] = None
    return resolved


def classify_income(iso_codes: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Assign World Bank income groups and LDC status to recipient codes, using resolvekit.

    Codes that resolve to no country are regional or unspecified recipients, so they are
    unallocated by income; countries in no World Bank group are not classified.

    Args:
        iso_codes: The CRS de_recipientcode of each recipient.

    Returns:
        (income group label, whether the recipient is an LDC), both aligned with iso_codes.
    """
    resolver = rk.default()
    group_of = {
        iso3: label
        for group, label in WORLD_BANK_INCOME_GROUPS.items()
        for iso3 in resolver.members_of(group, as_codes="iso3")
    }
    ldcs = set(resolver.members_of(LDC_GROUP, as_codes="iso3"))

    resolved = _resolve_iso3(iso_codes, set(group_of) | ldcs)
    iso3 = iso_codes.map(resolved)

    is_country = iso3.notna()
    income = iso3.map(group_of)
    not_classified = is_country & income.isna()
    if not_classified.any():
        logger.info(
            "Countries the World Bank does not classify: %s",
            sorted(iso_codes[not_classified].unique()),
        )
    income = income.mask(not_classified, WORLD_BANK_NOT_CLASSIFIED)
    income = income.mask(~is_country, UNALLOCATED_BY_INCOME)

    return income, iso3.isin(ldcs)


def _modal_value(series: pd.Series) -> object:
    """Return the most common non-null value, ties broken by sort order for determinism."""
    present = series.dropna()
    if present.empty:
        return pd.NA
    return present.mode().sort_values().iloc[0]


def get_crs_recipient_classifications(
    years: range | list | int, recipients: list | None = None
) -> tuple[pd.DataFrame, dict]:
    """Build the recipient name, region and income-group table the CRS views group by.

    Names and regions come from the CRS, the only source that carries regions; income groups
    and LDC status from classify_income. Imputed multilateral spending is keyed on
    [channel, purpose, recipient, year, currency, prices] and policy marker data on
    [provider, agency, recipient, modality, finance type, purpose, year], so neither knows a
    recipient's region or income group. Building one table here and joining it to every frame
    keeps them consistent: grouping one frame on a column another lacks is what double counts.

    Args:
        years: Years to cover.
        recipients: Recipient codes to restrict to, or None for all.

    Returns:
        (one row per recipient_code and year with recipient name, region and income group;
        the Least Developed Countries among the recipients, as {recipient_code: name}).
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

    attributes = ["recipient_name", _CRS_ISO3_COL, CRS_REGION_COL]
    grouped = raw.groupby(["recipient_code", "year"], dropna=False, observed=True)[
        attributes
    ]

    # Reduce each column to its most common non-null value, rather than deduplicating whole
    # rows. A recipient-year often has some transactions with a blank region,
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
                len(disagreeing),
                col,
                sorted({int(code) for code, _ in disagreeing})[:10],
            )

    income, is_ldc = classify_income(classified[_CRS_ISO3_COL])
    ldc_members = (
        classified.loc[is_ldc]
        .drop_duplicates("recipient_code")
        .set_index("recipient_code")["recipient_name"]
        .to_dict()
    )
    classified = classified.assign(**{INCOME_GROUP_COL: income}).drop(
        columns=[_CRS_ISO3_COL]
    )

    logger.info(
        "Recipient classification table: %s recipient-years", f"{len(classified):,}"
    )

    return classified, ldc_members


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
    for col in ("recipient_name", *RECIPIENT_CLASSIFICATION_COLS):
        gaps = merged[col].isna()
        if gaps.any():
            merged.loc[gaps, col] = merged.loc[gaps, "recipient_code"].map(
                per_recipient[col]
            )
            logger.info(
                "%s: %s rows had no %s for their year; filled from the recipient's other "
                "years where possible",
                label,
                f"{int(gaps.sum()):,}",
                col,
            )

    for col, sentinel in (
        (CRS_REGION_COL, CRS_UNCLASSIFIED_REGION),
        (INCOME_GROUP_COL, CRS_UNCLASSIFIED_INCOME),
    ):
        still_missing = merged[col].isna()
        if still_missing.any():
            logger.warning(
                "%s: %s rows worth %s have no %s in the CRS at all; labelled %r. "
                "Recipient codes: %s",
                label,
                f"{int(still_missing.sum()):,}",
                f"{merged.loc[still_missing, 'value'].sum():,.1f}",
                col,
                sentinel,
                sorted(merged.loc[still_missing, "recipient_code"].dropna().unique())[
                    :10
                ],
            )
            merged[col] = merged[col].fillna(sentinel)

    if abs(merged["value"].sum() - before_value) > max(1e-6, abs(before_value) * 1e-9):
        raise ValueError(
            f"{label}: classification join changed the total "
            f"({before_value:,.2f} -> {merged['value'].sum():,.2f})"
        )

    return merged


def build_crs_recipient_group_totals(
    df: pd.DataFrame, group_cols: list[str], ldc_members: dict
) -> list[pd.DataFrame]:
    """Build every recipient aggregate: overall total, income groups, regions, continents, lists.

    Args:
        df: Frame carrying the CRS classification columns and a "value" column.
        group_cols: Columns identifying everything except the recipient, e.g.
            year, donor_code, donor_name, indicator_name, currency, price.
        ldc_members: The Least Developed Countries, from get_crs_recipient_classifications.

    Returns:
        One frame per aggregate, each naming its group in recipient_name.
    """
    overall = (
        df.groupby(group_cols, dropna=False, observed=True)["value"]
        .sum()
        .reset_index()
        .assign(recipient_name="ODA eligible countries")
    )

    income = get_attribute_total(df, INCOME_GROUP_COL, group_cols)

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
        df.assign(
            **{_CONTINENT_COL: lambda d: d[CRS_REGION_COL].map(region_to_continent)}
        ),
        _CONTINENT_COL,
        group_cols,
    ).dropna(subset=["recipient_name"])

    lists = [
        get_group_total(
            df, members, column="recipient", group_cols=group_cols, group_name=name
        )
        for name, members in (
            # LDCs overlap the income groups, like the two country lists.
            (LDC_LABEL, ldc_members),
            ("Sahel countries", SAHEL_RECIPIENTS),
            ("France priority countries", FRANCE_PRIORITY_RECIPIENTS),
        )
    ]

    return [overall, income, regions, continents, *lists]


def build_donor_group_totals(
    df: pd.DataFrame, group_cols: list[str]
) -> dict[str, pd.DataFrame]:
    """Build every donor aggregate in DONOR_GROUPS by summing its members.

    Every view builds its aggregates here, so "All bilateral donors" is DAC countries plus
    Non-DAC countries everywhere, and EU Institutions sits in no group. Each view builds the
    EU27 + institutions bloc itself, since how to avoid counting member contributions twice
    depends on the data it reads.

    Args:
        df: Frame with donor_code and a "value" column.
        group_cols: Columns identifying everything except the donor.

    Returns:
        One frame per group name, each naming its group in donor_name.
    """
    return {
        name: get_group_total(df, members, group_cols=group_cols, group_name=name)
        for name, members in DONOR_GROUPS.items()
    }


# Decimal places kept on share columns; ratios need more than the 4 kept on values.
SHARE_DECIMALS: int = 6


def safe_share(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide, returning NaN where the denominator is zero rather than an infinite share.

    Args:
        numerator: Values to express as a share.
        denominator: Totals they are a share of.

    Returns:
        The ratio, rounded to SHARE_DECIMALS.
    """
    return (numerator / denominator.where(denominator != 0)).round(SHARE_DECIMALS)


def check_share_column(df: pd.DataFrame, pct_col: str) -> None:
    """Log how many shares are missing, negative or above one.

    Missing shares come from zero or absent denominators, and shares outside [0, 1] from net
    flows with negative values, so neither is an error on its own.

    Args:
        df: Frame holding the share column.
        pct_col: The share column.
    """
    share = df[pct_col]
    logger.info(
        "%s: %s missing, %s negative, %s above 1, of %s rows",
        pct_col,
        f"{share.isna().sum():,}",
        f"{(share < 0).sum():,}",
        f"{(share > 1).sum():,}",
        f"{len(share):,}",
    )


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
    merged[pct_col] = safe_share(merged["value_usd_current"], merged["total_oda"])
    check_share_column(merged, pct_col)
    return merged.drop(columns=["total_oda"])


def get_attribute_total(
    df: pd.DataFrame,
    attribute_col: str,
    group_cols: list,
    column: str = "recipient",
) -> pd.DataFrame:
    """Sum rows by a classification the data itself carries, e.g. CRS region or income group.

    The counterpart to get_group_total: that one aggregates a group defined by a list of
    member codes, this one aggregates a group defined by an attribute column, so the
    membership never has to be maintained anywhere.

    Args:
        df: Long-form frame with a "value" column and the attribute column.
        attribute_col: Column holding the classification, e.g. "recipient_region".
        group_cols: Columns to group by alongside the attribute.
        column: Entity the groups stand in for, "donor" or "recipient".

    Returns:
        One row per attribute value per group_cols combination, named as the entity.
    """
    totals = (
        df.groupby(group_cols + [attribute_col], dropna=False, observed=True)["value"]
        .sum()
        .reset_index()
    )
    # The attribute may arrive dictionary-encoded; as plain objects the totals concatenate
    # with the other group frames without category mismatches.
    totals[f"{column}_name"] = totals[attribute_col].astype("object")
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
    merged[pct_col] = safe_share(merged["value_usd_current"], merged["total_oda"])
    check_share_column(merged, pct_col)
    return merged.drop(columns=["total_oda"])


def add_currencies_and_prices(
    df: pd.DataFrame, base_year: int = BASE_TIME["base"]
) -> pd.DataFrame:
    """Copy the data into every currency in CURRENCIES, at current and constant prices.

    Args:
        df: Long frame in current USD, with donor_code, year and value.
        base_year: Base year for constant prices.

    Returns:
        One copy per currency and price, labelled in currency and price columns.

    Raises:
        ValueError: If the conversions do not return one row per input row.
    """
    df = df.assign(currency="USD", price="current")
    converted = []

    for currency in CURRENCIES:
        logger.info("Converting to %s", currency)
        current = (
            df
            if currency == "USD"
            else oecd_dac_exchange(
                data=df.copy(),
                source_currency="USA",
                target_currency=currency,
                id_column="donor_code",
                use_source_codes=True,
            )
        )
        constant = oecd_dac_deflate(
            data=df.copy(),
            base_year=base_year,
            source_currency="USA",
            target_currency=currency,
            id_column="donor_code",
            use_source_codes=True,
        )
        converted += [
            current.assign(currency=currency, price="current"),
            constant.assign(currency=currency, price="constant"),
        ]

    if any(len(frame) != len(df) for frame in converted):
        raise ValueError("A currency or price conversion changed the number of rows")

    # Values present in USD but lost in conversion mean a missing exchange rate or deflator.
    had_value = df["value"].notna().to_numpy()
    for frame in converted:
        lost = had_value & frame["value"].isna().to_numpy()
        if lost.any():
            logger.warning(
                "No %s %s conversion for %s rows, so they and any group totals that "
                "include them are short in that currency (donor codes %s)",
                frame["currency"].iat[0],
                frame["price"].iat[0],
                f"{lost.sum():,}",
                sorted(frame.loc[lost, "donor_code"].dropna().unique().tolist())[:10],
            )

    return pd.concat(converted, ignore_index=True)


def drop_empty_values(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Drop rows whose value is missing or zero, logging how many of each go.

    Zero rows carry no information. Missing values after a currency conversion are the
    rows add_currencies_and_prices already warned about.

    Args:
        df: Long frame with a value column.
        label: Name of the frame, for the log.

    Returns:
        The rows with a non-zero value.
    """
    missing = df["value"].isna()
    zero = df["value"] == 0
    logger.info(
        "%s: dropping %s rows with no value and %s with a zero value",
        label,
        f"{missing.sum():,}",
        f"{zero.sum():,}",
    )
    return df.loc[~missing & ~zero]


def widen_currency_price(
    df: pd.DataFrame,
    index_cols: tuple[str, ...] = ("year", "donor_code", "indicator"),
) -> pd.DataFrame:
    """Pivot currency/price pairs into wide value columns.

    Args:
        df: Long-form DataFrame with columns: year, donor_code, indicator, currency, price,
            value. Its value column is rounded in place.
        index_cols: Columns to keep as the row index in the wide table.

    Returns:
        Wide DataFrame with value columns like value_usd_current, value_eur_constant.

    Raises:
        ValueError: If two rows share the same index, currency and price.
    """
    # Pre-process values in long format (much faster than on wide data). This rounds the
    # caller's frame in place: a copy would double the memory of the sectors frame, and
    # every caller replaces its frame with the result.
    df["value"] = df["value"].round(4).astype("float32")

    # A duplicate key would mean two rows merged into one cell, double counting or silently
    # combining two entities. The pivot itself refuses duplicates, so the full duplicate
    # scan only runs to describe the failure, not on every call at the memory peak.
    pivot_cols = list(index_cols) + ["currency", "price"]
    try:
        wide = df.pivot(
            index=list(index_cols),
            columns=["currency", "price"],
            values="value",
        )
    except ValueError as error:
        duplicates = df.duplicated(subset=pivot_cols, keep=False)
        raise ValueError(
            f"{duplicates.sum():,} rows share a key before the pivot, e.g. "
            f"{df.loc[duplicates, pivot_cols].head(3).to_dict('records')}"
        ) from error

    # Flatten MultiIndex columns -> "value_usd_current"
    wide.columns = [
        f"value_{cur.lower()}_{price}" for cur, price in wide.columns.to_list()
    ]
    wide = wide.reset_index()

    # Reorder columns: index cols first, then sorted value cols
    value_cols = sorted([c for c in wide.columns if c not in index_cols])
    return wide[list(index_cols) + value_cols]


def add_share_of_total_oda(df: pd.DataFrame) -> pd.DataFrame:
    """Add each row's value_usd_current as a share of the same donor's Total ODA.

    Args:
        df: Wide financing frame keyed by year, donor_name and indicator_name.

    Returns:
        The frame with pct_of_total_oda added.
    """
    return add_share_of_reference_total(
        df, "indicator_name", "Total ODA", ["year", "donor_name"], "pct_of_total_oda"
    )


def add_share_of_gni(
    df: pd.DataFrame, member_gni: pd.DataFrame, members_usd_current: pd.DataFrame
) -> pd.DataFrame:
    """Add each row's value_usd_current as a share of the donor's GNI.

    Donor groups divide the ODA of only their members that report GNI, so the numerator and
    denominator cover the same countries.

    Args:
        df: Wide financing frame keyed by year, donor_name and indicator_name.
        member_gni: Output of get_member_gni.
        members_usd_current: Long frame of individual donors in current USD, with
            donor_code, year, indicator_name and value.

    Returns:
        The frame with pct_of_gni added.
    """
    gni_matched = build_gni_matched_group_totals(
        members_usd_current, member_gni, ["year", "indicator_name"]
    )
    merged = df.merge(
        add_group_gni(member_gni), on=["year", "donor_name"], how="left", validate="m:1"
    ).merge(
        gni_matched,
        on=["year", "donor_name", "indicator_name"],
        how="left",
        validate="m:1",
    )
    numerator = merged["gni_matched_value"].fillna(merged["value_usd_current"])
    merged["pct_of_gni"] = safe_share(numerator, merged["gni"])
    check_share_column(merged, "pct_of_gni")
    return merged.drop(columns=["gni", "gni_matched_value"])
