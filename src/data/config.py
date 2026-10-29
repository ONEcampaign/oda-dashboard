"""Constants shared by every data loader, plus the process setup they all depend on.

Section 1 is the exception to the rule: it configures logging, for the pipeline and for the
libraries it calls, because every module needs it and importing config is what every module
already does.
Sections 2 onwards hold values and no logic: paths, time windows, the indicator codes each view
requests, which providers and recipients make up each aggregate, and the labels and orderings
the frontend displays. If something takes a DataFrame and returns one, it belongs in
``analysis_tools.transformations``; if it writes a file, ``analysis_tools.outputs``; if it
decides how an entity is labelled, ``analysis_tools.naming``.

Sections, in order:
    1. Environment (logging, paths)
    2. Units and shared columns
    3. Time windows
    4. Indicators, per view
    5. Donors (memberships and aggregates)
    6. Recipients (memberships and aggregates)
    7. CRS classifications (regions, income groups, sentinels)
    8. Display orderings
"""

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

import oda_data as oda
import pandas as pd

# ---------------------------------------------------------------------------------------
# 1. Environment
# ---------------------------------------------------------------------------------------

_LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(message)s"

# Libraries whose INFO records (what was read, from which release, any fallbacks) belong in
# the pipeline log. They propagate to the root handler.
_LIBRARY_LOGGERS: tuple[str, ...] = ("oda_data", "oda_reader", "pydeflate")


def _configure_logging() -> logging.Logger:
    """Set up the pipeline logger, warning capture and library logging, once per process.

    The pipeline logger and ``py.warnings`` share one handler and do not propagate, so
    each record is emitted once. ``captureWarnings`` turns warnings such as oda_data's
    ``OdaDataWarning`` (partial years, missing lines) into log records instead of bare
    stderr output. The library loggers propagate to a root handler, added only when the
    root has none, so an application or test runner that configured logging first keeps
    its own.

    Returns:
        The pipeline logger.
    """
    pipeline_logger = logging.getLogger(__name__)
    if pipeline_logger.handlers:
        return pipeline_logger

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    pipeline_logger.addHandler(handler)
    pipeline_logger.setLevel(logging.INFO)
    pipeline_logger.propagate = False

    logging.captureWarnings(True)
    warnings_logger = logging.getLogger("py.warnings")
    warnings_logger.addHandler(handler)
    warnings_logger.propagate = False

    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
    for name in _LIBRARY_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)

    return pipeline_logger


logger = _configure_logging()


class PATHS:
    """Filesystem locations the pipeline reads from and writes to."""

    SRC = Path(__file__).resolve().parent.parent

    TOPIC_PAGE = SRC.parent / "topic_page"
    CDN_FILES = SRC.parent / "cdn_files"

    # oda_reader and pydeflate share one cache directory; see outputs.set_cache_dir.
    DATA = SRC / "data" / "cache"


# ---------------------------------------------------------------------------------------
# 2. Units and shared columns
# ---------------------------------------------------------------------------------------

# Values are published as whole currency units rather than millions, because integers compress
# far better in parquet. The frontend divides by this to get back to millions.
#
# Values arrive here with float32 precision (widen_currency_price stores them as float32, at
# about seven significant digits). convert_values_to_units widens them to float64 before
# multiplying, so the scaling adds no further rounding of its own.
UNITS_PER_MILLION: float = 1e6

# Above this, a value column no longer fits in Int32 and has to be stored as Int64.
INT32_MAX: int = 2_147_483_647

CURRENCIES: list[str] = ["USD", "EUR", "GBP", "CAD"]

# Display names several views build or look up, defined once so a rename cannot leave one
# view behind.
ALL_BILATERAL_DONORS: str = "All bilateral donors"
DAC_COUNTRIES_NAME: str = "DAC countries"
EU27_COUNTRIES_NAME: str = "EU27 countries"
EU27_EUI_NAME: str = "EU27 & EU Institutions"
ODA_ELIGIBLE: str = "ODA eligible countries"
TOTAL_ODA: str = "Total ODA"
CORE_ODA: str = "Core ODA (ONE Definition)"
PSI: str = "Private sector instruments"
BILATERAL: str = "Bilateral"
IMPUTED_MULTILATERAL: str = "Imputed multilateral"

# The label columns the views share. Dictionary-encoding them keeps the frames small enough to
# pivot on a CI runner, and keeps the published parquet compact.
LABEL_COLUMNS: tuple[str, ...] = (
    "donor_name",
    "recipient_name",
    "indicator_name",
    "sector_name",
    "sub_sector",
    "sub_sector_name",
    "type",
    "currency",
    "price",
)

# ---------------------------------------------------------------------------------------
# 3. Time windows
#
# "base" is the price base year for constant-price conversions.
# ---------------------------------------------------------------------------------------

FINANCING_TIME: dict[str, int] = {"start": 1990, "end": 2025, "base": 2025}
BASE_TIME: dict[str, int] = {"start": 1990, "end": 2024, "base": 2024}
SECTORS_TIME: dict[str, int] = {"start": 2013, "end": 2024, "base": 2024}

# The DAC switched its headline ODA measure from net flows to grant equivalents in 2018, so
# financing reads flows up to this year and grant equivalents from it onwards.
GRANT_EQUIVALENT_START_YEAR: int = 2018

# Financing type label for each headline measure the financing view reads.
FINANCING_TYPES: dict[str, str] = {
    "net_disbursement": "Flows",
    "grant_equivalent": "Grant equivalents",
}

# ---------------------------------------------------------------------------------------
# 4. Indicators, per view
#
# Financing indicators are grouped by how they are requested: the aggregates switch from net
# flows to grant equivalents at GRANT_EQUIVALENT_START_YEAR (oda-data's headline basis), total
# private sector instruments at PSI_GRANT_EQUIVALENT_START_YEAR, and the in-donor items and
# the PSI split by approach stay in net flows.
# ---------------------------------------------------------------------------------------

# oda-data indicators read on their headline basis, by display name.
HEADLINE_FINANCING_INDICATORS: dict[str, str] = {
    "oecd.dac1.total_oda": TOTAL_ODA,
    "one.dac1.core_oda": CORE_ODA,
    "oecd.dac1.bilateral_oda": "Bilateral ODA",
    "oecd.dac1.multilateral_oda": "Multilateral ODA",
    "oecd.dac1.debt_relief": "Debt relief",
}

# Indicators that are null for every provider in the partial latest year unless oda-data is
# told to sum the parts that have been reported (allow_partial).
PARTIAL_YEAR_FINANCING_INDICATORS: frozenset[str] = frozenset({"one.dac1.core_oda"})

# Total PSI under the provisional methods, read in net flows before
# PSI_GRANT_EQUIVALENT_START_YEAR.
PSI_FLOW_INDICATOR: str = "oecd.dac1.private_sector_instruments"

# Total PSI from PSI_GRANT_EQUIVALENT_START_YEAR, in grant equivalents: DAC1 line 11030 holds
# PSI reported under the provisional methods and 11040 PSI under the revised methods.
PSI_GRANT_EQUIVALENT_LINES: tuple[int, ...] = (11030, 11040)

# The split of PSI under the provisional methods into its two approaches. It only ever covers
# 11030, so it is in net flows throughout.
PSI_APPROACH_LINES: dict[int, str] = {
    11023: "Private sector instruments - institutional approach",
    11024: "Private sector instruments - instrument approach",
}

IN_DONOR_FINANCING_LINES: dict[int, str] = {
    1820: "Refugees in donor countries",
    1500: "Scholarships and student costs in donor countries",
    1510: "Scholarships/training in donor country",
    1520: "Imputed student costs",
}

# Names read in more than one part, which are summed into one figure. Every other financing
# name has one row per donor, year and type. The DAC's revised PSI methods (2023) came with a
# transition of up to two years: a donor can report PSI under both methods in one year (lines
# 11030 and 11040), and total PSI is their sum. Only
# 11030 exists before 2023 and only 11040 from 2025. 11023 and 11024 split 11030 only, so in
# 2023-24 they cover just the provisional-method part.
SUMMED_FINANCING_NAMES: frozenset[str] = frozenset({PSI})

# Total PSI is in net flows up to 2022, when all of it was reported under the provisional
# methods, and shown as grant equivalents from 2023. In the transition years it mixes the two,
# which the financing page notes.
PSI_TRANSITION_YEARS: list[int] = [2023, 2024]
PSI_GRANT_EQUIVALENT_START_YEAR: int = PSI_TRANSITION_YEARS[0]

# Total ODA's grants, the DAC1 flow the financing view splits Total ODA by. Read as gross
# disbursements, which for grants equal their net flows and grant equivalents.
GRANTS_FLOW: int = 1121
GRANTS_BASIS: str = "gross_disbursement"

# DAC2A lines the recipients view reads, both in net disbursements: total net ODA (206) and
# imputed multilateral ODA (106).
RECIPIENTS_LINES: dict[int, str] = {
    206: BILATERAL,
    106: IMPUTED_MULTILATERAL,
}

# Gender marker scores, keyed by the value oda_data's bilateral_policy_marker expects.
GENDER_INDICATORS: dict[str, str] = {
    "principal": "Main target",
    "significant": "Secondary target",
    "not_targeted": "Not targeted",
    "not_screened": "Not screened",
}

# The OECD scores the gender marker 0 (screened, not targeted), 1 (significant) or 2
# (principal) and leaves it blank for activities not screened. oda_data's not_screened read
# returns all allocable aid, so the gender view derives it as the total allocable read minus
# the three screened scores, which is exactly the blank rows.
NOT_SCREENED_SCORE: str = "not_screened"
TOTAL_ALLOCABLE_SCORE: str = "total_allocable"

# Differences below this many USD millions are subtraction residue, not unscreened aid.
GENDER_RESIDUAL_TOLERANCE: float = 1e-6

# oda_data's own name for the unallocated purpose codes, also used for any purpose code outside
# the sector groups.
UNALLOCATED_SUB_SECTOR: str = "Unallocated/ Unspecified"

# CRS flow categories read by the sectors view: ODA (10) and private sector instruments (60),
# which the CRS reports from 2023 and which count towards ODA. Other official flows (21) are
# not ODA and stay out. The gender view gets the same scope from oda_data's oda_only filter.
CRS_FLOW_CATEGORIES: list[int] = [10, 60]

# Spending whose sector pattern multilaterals' core funding is imputed by, in oda_data's terms.
# ODA and OOF together, oda_data's default and the former OECD method: OOF-only channels such
# as IBRD otherwise have no pattern, and far more core funding is left unallocated.
IMPUTATION_FLOW_TYPES: tuple[str, ...] = ("ODA", "OOF")

# Aid to developing countries that cannot be attributed to a country or region, including the
# imputed multilateral money oda_data cannot assign to a recipient. DAC2A calls it "Developing
# countries, unspecified" and the CRS "Bilateral, unspecified". Every view uses one name, the
# unspecified part of "ODA eligible countries", following the "<area>, unspecified" convention.
UNSPECIFIED_RECIPIENT_CODE: int = 9998
UNSPECIFIED_RECIPIENT_NAME: str = "ODA eligible countries, unspecified"

# ---------------------------------------------------------------------------------------
# 5. Donors
#
# Every view reads individual providers and sums the memberships below into donor aggregates.
# None requests the OECD's own aggregate providers, so each aggregate is defined once.
# ---------------------------------------------------------------------------------------


def _named_codes(dimension: str, codes: Iterable[int]) -> dict[int, str]:
    """Map provider or recipient codes to the names oda_data's results carry.

    Args:
        dimension: ``"provider"`` or ``"recipient"``.
        codes: The codes to name.

    Returns:
        Each code and its name, in the order given.

    Raises:
        ValueError: If oda_data has no name for a code.
    """
    named = oda.add_names(pd.DataFrame({dimension: list(codes)}))
    name_column = f"{dimension}_name"
    unnamed = named.loc[named[name_column].isna(), dimension].tolist()
    if unnamed:
        raise ValueError(f"oda_data has no {dimension} name for codes {unnamed}.")
    return dict(
        zip(named[dimension].astype(int).tolist(), named[name_column], strict=True)
    )


def _group_members(group: oda.Group) -> dict[int, str]:
    """Map an oda_data built-in group's member codes to their names."""
    if group.dimension is None:
        raise ValueError(f"oda_data group {group.name!r} has no dimension to name.")
    codes = [code for code in group.members if isinstance(code, int)]
    if len(codes) != len(group.members):
        raise ValueError(
            f"oda_data group {group.name!r} has members that are not codes."
        )
    return _named_codes(group.dimension, codes)


BILATERAL_DONORS: dict[int, str] = _group_members(oda.groups.all_bilateral)
DAC_COUNTRIES: dict[int, str] = _group_members(oda.groups.dac_countries)
G7_COUNTRIES: dict[int, str] = _group_members(oda.groups.g7)
NON_DAC_COUNTRIES: dict[int, str] = _group_members(oda.groups.non_dac_countries)

EU_COUNTRIES: dict[int, str] = _group_members(oda.groups.eu27)
# The EU Institutions' provider code, which belongs to no oda_data provider group.
EU_INSTITUTIONS_CODE: int = 918
EU_INSTITUTIONS: dict[int, str] = _named_codes("provider", [EU_INSTITUTIONS_CODE])
EU_TOTAL: dict[int, str] = EU_COUNTRIES | EU_INSTITUTIONS

# Every provider the views read: the bilateral donors, plus EU Institutions, which is shown on
# its own but belongs to no donor group.
PROVIDERS: dict[int, str] = BILATERAL_DONORS | EU_INSTITUTIONS

# Donor aggregates, each the sum of its members, built the same way in every view. "All
# bilateral donors" is exactly DAC countries plus Non-DAC countries. EU Institutions is left
# out of every group, as in the OECD's headline totals: much of its spending is funded by
# donors' contributions, which their own totals already include.
DONOR_GROUPS: dict[str, dict] = {
    ALL_BILATERAL_DONORS: BILATERAL_DONORS,
    DAC_COUNTRIES_NAME: DAC_COUNTRIES,
    "Non-DAC countries": NON_DAC_COUNTRIES,
    "G7 countries": G7_COUNTRIES,
    EU27_COUNTRIES_NAME: EU_COUNTRIES,
}
if DAC_COUNTRIES.keys() & NON_DAC_COUNTRIES.keys() or (
    BILATERAL_DONORS.keys() != DAC_COUNTRIES.keys() | NON_DAC_COUNTRIES.keys()
):
    raise ValueError(
        "oda_data's all_bilateral group no longer splits into dac_countries and "
        "non_dac_countries, so All bilateral donors would not equal DAC + Non-DAC."
    )

# The EU27 + institutions bloc needs EU members' contributions to the institutions to avoid
# counting them twice. Preliminary DAC1 data for the latest year do not yet carry them, so
# the financing view shows the bloc only up to this year.
EU27_EUI_LAST_YEAR: int = 2024

# Channels through which EU member states' core contributions reach the EU institutions.
# Members' imputed multilateral on these channels is excluded from the EU27 + institutions
# bloc, or it would be counted once there and again as the institutions' own spending.
# Source: human-development-dashboard/src/data/scripts/imputations.py
EUI_CHANNEL_CODES: frozenset[int] = frozenset({42000, 42001, 42003, 42004, 42999})

# ---------------------------------------------------------------------------------------
# 6. Recipients
#
# The recipients view reads DAC2A for a pinned list of recipients: every country and
# "<area>, unspecified" code, plus the groups DAC2A publishes (continents, regions, income).
# The CRS publishes no groups, so the sectors and gender views build them from the
# classifications in section 7 instead.
# ---------------------------------------------------------------------------------------

# Display labels for recipients in every view, keyed by code. Regions are renamed to match
# across the DAC2A and CRS views.
RECIPIENT_NAME_OVERRIDES: dict[int, str] = {
    10_100: ODA_ELIGIBLE,
    UNSPECIFIED_RECIPIENT_CODE: UNSPECIFIED_RECIPIENT_NAME,
    10_016: "Least Developed Countries (LDCs)",
    10_045: "Low Income Countries (LICs)",
    10_046: "Lower-Middle Income Countries (LMICs)",
    10_047: "Upper-Middle Income Countries (UMICs)",
    10_048: "High Income Countries (HICs)",
    10_030: "Heavily Indebted Poor Countries (HIPCs)",
    10_203: "Fragile states",
    10_002: "North of Sahara",
    189: "North of Sahara, unspecified",
    10_003: "South of Sahara",
    289: "South of Sahara, unspecified",
    10_009: "South & Central Asia",
    689: "South & Central Asia, unspecified",
    10_005: "Caribbean & Central America",
    389: "Caribbean & Central America, unspecified",
    # DAC2A calls both the sub-region and the country (code 860) "Micronesia"
    10_058: "Micronesia (region)",
}

# DAC2A recipients the recipients view must not read, checked against DAC2A_RECIPIENTS:
# - the DAC-list income groups (Other LICs, LMICs, UMICs, unallocated by income, MADCTs),
#   since the view uses the World Bank classification and both have an "LMICs" and "UMICs";
# - multilateral agencies reported as recipients (IDA, UNDP, ...), and their totals "All
#   multilateral recipients" (10150) and "All recipients" (10200), as the view covers
#   developing countries and regions. Bilateral flows to those totals include donors' core
#   contributions to multilaterals, which the imputed multilateral series counts again.
EXCLUDED_DAC2A_RECIPIENTS: frozenset[int] = frozenset(
    {10_017, 10_018, 10_019, 10_024, 10_025, 10_150, 10_200, 816, *range(900, 990)}
)

# The CRS records aid that cannot be allocated to a country against regional codes
# ("Africa, regional") and code 9998 (see UNSPECIFIED_RECIPIENT_CODE), which together are roughly
# half of all bilateral flows, so the CRS views need the full recipient list. Safe to sum:
# the CRS never reports the same money against both a country and a region, and it contains
# no "X, Total" style aggregates. oda_data's all_recipients leaves out the DAC2A aggregates and
# the multilateral agencies, neither of which the CRS uses as a recipient.
CRS_RECIPIENTS: dict[int, str] = _group_members(oda.groups.all_recipients)

# Country lists that no source publishes as an aggregate, so every view sums them.
FRANCE_PRIORITY_RECIPIENTS: dict[int, str] = _group_members(oda.groups.france_priority)
SAHEL_RECIPIENTS: dict[int, str] = _group_members(oda.groups.sahel)

# DAC2A codes from here up are groups; below it are countries and unspecified codes.
_DAC2A_GROUP_CODE_MIN: int = 10_000
# DAC2A's Least Developed Countries group. The recipients view does not read it and sums
# resolvekit's UN LDC members instead, as the CRS views do.
DAC2A_LDC_CODE: int = 10_016

# The DAC2A groups the recipients view reads, by code, with their display names. The bulk
# file spells most of them "<group>, Total"; the view shows these names.
DAC2A_RECIPIENT_AGGREGATES: dict[int, str] = {
    10_001: "Africa",
    10_004: "America",
    10_006: "South America",
    10_007: "Asia",
    10_008: "Far East Asia",
    10_010: "Europe",
    10_011: "Middle East",
    10_012: "Oceania",
    10_040: "ACP",
    10_049: "Countries not classified by the World Bank",
    10_050: "Eastern Africa",
    10_051: "Middle Africa",
    10_052: "Southern Africa",
    10_053: "Western Africa",
    10_054: "Caribbean",
    10_055: "Central America",
    10_056: "Northern America",
    10_057: "Melanesia",
    10_059: "Polynesia",
    10_201: "Land locked developing countries",
    10_202: "Small island developing states",
    # Groups every view names the same way.
    **{
        code: name
        for code, name in RECIPIENT_NAME_OVERRIDES.items()
        if code >= _DAC2A_GROUP_CODE_MIN and code != DAC2A_LDC_CODE
    },
}

# Countries and unspecified codes whose DAC2A bulk name differs from the name the recipients
# view shows. Recipients view only: the CRS views keep their own spellings.
DAC2A_RECIPIENT_NAMES: dict[int, str] = {
    88: "States ex-Yugoslavia, unspecified",
    247: "C\u00f4te d\u2019Ivoire",
    361: "Sint Maarten",
    550: "Palestinian Authority or West Bank and Gaza Strip",
    679: "Southern Asia, unspecified",
    730: "China (People\u2019s Republic of)",
    740: "Democratic People\u2019s Republic of Korea",
    745: "Lao People\u2019s Democratic Republic",
}

# Unspecified codes the OECD API used and the DAC2A bulk file does not: the bulk file holds
# the same money under the code each maps to, which the view shows under the API's name.
DAC2A_API_ONLY_RECIPIENTS: dict[int, int] = {
    10_280: 1028,  # Middle Africa, unspecified
    10_330: 1033,  # Melanesia, unspecified
    10_350: 1035,  # Polynesia, unspecified
    8600: 1034,  # Micronesia, unspecified
    6790: 679,  # Southern Asia, unspecified
}

# Every recipient the recipients view reads from DAC2A.
DAC2A_RECIPIENTS: frozenset[int] = frozenset(
    (CRS_RECIPIENTS.keys() - DAC2A_API_ONLY_RECIPIENTS.keys())
    | DAC2A_RECIPIENT_AGGREGATES.keys()
)
if DAC2A_RECIPIENTS & EXCLUDED_DAC2A_RECIPIENTS:
    raise ValueError(
        "DAC2A_RECIPIENTS includes recipients the view excludes: "
        f"{sorted(DAC2A_RECIPIENTS & EXCLUDED_DAC2A_RECIPIENTS)}"
    )
if not set(DAC2A_API_ONLY_RECIPIENTS.values()) <= DAC2A_RECIPIENTS:
    raise ValueError("oda_data's all_recipients lacks a DAC2A bulk unspecified code.")

# ---------------------------------------------------------------------------------------
# 7. CRS classifications
#
# The CRS carries a region on every transaction, which is how the sectors and gender views
# build region groups: membership is read from the data. Income groups
# follow the World Bank classification instead, as in the recipients view, using resolvekit's
# data (pinned in pyproject.toml, so the classification changes only when resolvekit does).
# ---------------------------------------------------------------------------------------

# resolvekit World Bank income group -> display label, matching the recipients view. Like the
# recipients view's DAC2A groups, one current classification applies to every year.
WORLD_BANK_INCOME_GROUPS: dict[str, str] = {
    "World Bank Low-Income Countries": RECIPIENT_NAME_OVERRIDES[10_045],
    "World Bank Lower-Middle-Income Countries": RECIPIENT_NAME_OVERRIDES[10_046],
    "World Bank Upper-Middle-Income Countries": RECIPIENT_NAME_OVERRIDES[10_047],
    "World Bank High-Income Countries": RECIPIENT_NAME_OVERRIDES[10_048],
}
# Countries the World Bank does not classify, mostly small territories.
WORLD_BANK_NOT_CLASSIFIED: str = "Countries not classified by the World Bank"
# Regional and unspecified recipients, which belong to no income group.
UNALLOCATED_BY_INCOME: str = "Unallocated by income"

# The UN list of Least Developed Countries, an overlapping group like the recipients view's.
LDC_GROUP: str = "Least Developed Countries"
LDC_LABEL: str = RECIPIENT_NAME_OVERRIDES[10_016]


class CrsRegion(NamedTuple):
    """A CRS region's continent rollup and whether it gets a region group."""

    continent: str | None
    is_region: bool


# Every CRS region the pipeline accepts, by name. Membership is read from the data; this only
# says what each region means. A value missing here fails the build, so a new OECD region is
# classified on purpose instead of silently becoming a group of its own.
#
# The CRS records aid against a whole continent under the continent's name. That aid rolls into
# the continent total, which covers its sub-regions plus that, and is not a region itself.
# "Regional and Unspecified" holds only code 9998, so a region group for it would repeat that
# recipient value for value. Europe and Oceania have no continent total.
#
# The order of first appearance sets the order of continents and regions in
# CRS_RECIPIENTS_ORDER.
CRS_REGIONS: dict[str, CrsRegion] = {
    "Africa": CrsRegion("Africa", is_region=False),
    "Asia": CrsRegion("Asia", is_region=False),
    "America": CrsRegion("America", is_region=False),
    "North of Sahara": CrsRegion("Africa", is_region=True),
    "South of Sahara": CrsRegion("Africa", is_region=True),
    "Caribbean & Central America": CrsRegion("America", is_region=True),
    "South America": CrsRegion("America", is_region=True),
    "South & Central Asia": CrsRegion("Asia", is_region=True),
    "Far East Asia": CrsRegion("Asia", is_region=True),
    "Middle East": CrsRegion("Asia", is_region=True),
    "Europe": CrsRegion(None, is_region=True),
    "Oceania": CrsRegion(None, is_region=True),
    "Regional and Unspecified": CrsRegion(None, is_region=False),
}

# Raw CRS spellings of a region in CRS_REGIONS: the CRS sometimes records a continent's own aid
# against "Africa, regional" rather than "Africa".
CRS_REGION_ALIASES: dict[str, str] = {
    "Africa, regional": "Africa",
    "Asia, regional": "Asia",
    "America, regional": "America",
}

# Raw CRS region value -> region name.
CRS_REGION_NAMES: dict[str, str] = {
    name: name for name in CRS_REGIONS
} | CRS_REGION_ALIASES

CRS_CONTINENTS: list[str] = list(
    dict.fromkeys(r.continent for r in CRS_REGIONS.values() if r.continent)
)
CRS_REGION_GROUPS: list[str] = [name for name, r in CRS_REGIONS.items() if r.is_region]

# Sentinels for recipients the classification table never covers. Distinct from
# UNALLOCATED_BY_INCOME, which is a real category for regional and unspecified recipients.
CRS_UNCLASSIFIED_REGION: str = "Region not reported"
CRS_UNCLASSIFIED_INCOME: str = "Income group not reported"

# ---------------------------------------------------------------------------------------
# 8. Display orderings
#
# build_view_options pins these first in the dropdowns, in this order; everything else
# follows alphabetically. Names absent from the data are skipped, so one donor ordering serves
# all four views even though they do not all publish every aggregate.
# ---------------------------------------------------------------------------------------

DONORS_ORDER: list[str] = [
    DAC_COUNTRIES_NAME,
    "Non-DAC countries",
    ALL_BILATERAL_DONORS,
    "G7 countries",
    EU27_COUNTRIES_NAME,
    "EU Institutions",
    EU27_EUI_NAME,
]

# The donor and recipient every page opens on.
DEFAULT_DONOR: str = DAC_COUNTRIES_NAME
DEFAULT_RECIPIENT: str = ODA_ELIGIBLE

FINANCING_INDICATORS_ORDER: list[str] = [
    *HEADLINE_FINANCING_INDICATORS.values(),
    "Grants",
    "Non-grants",
    *IN_DONOR_FINANCING_LINES.values(),
    PSI,
    *PSI_APPROACH_LINES.values(),
]

# Recipients view: the income and status groups. The script appends the remaining DAC2A groups
# and the two summed country lists, read from the data.
RECIPIENTS_ORDER: list[str] = [
    ODA_ELIGIBLE,
    "Least Developed Countries (LDCs)",
    "Low Income Countries (LICs)",
    "Lower-Middle Income Countries (LMICs)",
    "Upper-Middle Income Countries (UMICs)",
    "High Income Countries (HICs)",
    "Heavily Indebted Poor Countries (HIPCs)",
    "Fragile states",
]

# CRS views: the overall total, then income groups, continents, CRS regions, country lists.
CRS_RECIPIENTS_ORDER: list[str] = [
    ODA_ELIGIBLE,
    LDC_LABEL,
    *WORLD_BANK_INCOME_GROUPS.values(),
    WORLD_BANK_NOT_CLASSIFIED,
    UNALLOCATED_BY_INCOME,
    *CRS_CONTINENTS,
    *CRS_REGION_GROUPS,
    "Sahel countries",
    "France priority countries",
]
