"""Constants shared by every data loader, plus the process setup they all depend on.

Section 1 is the exception to the rule: it configures the logger and applies the compatibility
patch, because every module needs both and importing config is what every module already does.
Sections 2 onwards hold values, not logic — paths, time windows, the indicator codes each view
requests, which providers and recipients make up each aggregate, and the labels and orderings
the frontend displays. If something takes a DataFrame and returns one, it belongs in
``analysis_tools.transformations``; if it writes a file, ``analysis_tools.outputs``; if it
decides how an entity is labelled, ``analysis_tools.naming``.

Sections, in order:
    1. Environment — the compatibility patch, the logger, paths
    2. Units and shared columns
    3. Time windows
    4. Indicators, per view
    5. Donors — memberships and aggregates
    6. Recipients — memberships and aggregates
    7. CRS classifications — regions, income groups, sentinels
    8. Display orderings
"""

import logging
from pathlib import Path

from oda_data import provider_groupings, recipient_groupings

# Patches a requests-cache incompatibility that would otherwise fail the first time anything
# reads or writes the OECD HTTP cache. What matters is that it runs before that first request,
# not before the oda_data import; it sits here, above them, because importing config is the one
# thing every module in the pipeline already does. See src/data/_compat.py.
import src.data._compat  # noqa: F401

# ---------------------------------------------------------------------------------------
# 1. Environment
# ---------------------------------------------------------------------------------------

logger = logging.getLogger(__name__)
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
# Without this every record is emitted twice: once by the handler above and again by the root
# handler that oda_data installs, in a different format. oda_data does the same for its logger.
logger.propagate = False


class PATHS:
    """Filesystem locations the pipeline reads from and writes to."""

    SRC = Path(__file__).resolve().parent.parent

    TOPIC_PAGE = SRC.parent / "topic_page"
    CDN_FILES = SRC.parent / "cdn_files"

    # View options and other small artifacts the frontend loads as FileAttachments.
    TOOLS = SRC / "data" / "analysis_tools"

    # oda_data and pydeflate share one cache directory; see outputs.set_cache_dir.
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
EU27_COUNTRIES_NAME: str = "EU27 countries"
EU27_EUI_NAME: str = "EU27 & EU Institutions"
ODA_ELIGIBLE: str = "ODA eligible countries"
TOTAL_ODA: str = "Total ODA"
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

# ---------------------------------------------------------------------------------------
# 4. Indicators, per view
#
# Financing indicators are grouped by how they are requested: the aggregates and the private
# sector instruments switch measure at GRANT_EQUIVALENT_START_YEAR, the in-donor items do not.
# Several codes map to one display name because the DAC renumbered them for grant equivalents.
# ---------------------------------------------------------------------------------------

AGGREGATE_FINANCING_INDICATORS: dict[str, str] = {
    "ONE.10.1010_11010": TOTAL_ODA,
    "ONE.10.1010C": "Core ODA (ONE Definition)",
    "DAC1.10.1015": "Bilateral ODA",
    "DAC1.10.11015": "Bilateral ODA",
    "DAC1.10.2000": "Multilateral ODA",
    "DAC1.10.12000": "Multilateral ODA",
    "DAC1.10.1600": "Debt relief",
    "DAC1.10.11026": "Debt relief",
}

PSI_FINANCING_INDICATORS: dict[str, str] = {
    "DAC1.60.11030": "Private sector instruments",
    "DAC1.60.11040": "Private sector instruments",
    "DAC1.60.11023": "Private sector instruments - institutional approach",
    "DAC1.60.11024": "Private sector instruments - instrument approach",
}

# Code kept when aliases of one name disagree for a donor and year. 11030 and 11040 should
# report the same PSI figure, but the October 2026 DAC1 has them differ for 2023-24 (reported
# to the OECD). Until that is resolved the grant-equivalent figure is used.
PREFERRED_FINANCING_CODES: dict[str, str] = {
    "Private sector instruments": "DAC1.60.11040",
}

IN_DONOR_FINANCING_INDICATORS: dict[str, str] = {
    "DAC1.10.1820": "Refugees in donor countries",
    "DAC1.10.1500": "Scholarships and student costs in donor countries",
    "DAC1.10.1510": "Scholarships/training in donor country",
    "DAC1.10.1520": "Imputed student costs",
}

ALL_FINANCING_INDICATORS: dict[str, str] = (
    AGGREGATE_FINANCING_INDICATORS
    | PSI_FINANCING_INDICATORS
    | IN_DONOR_FINANCING_INDICATORS
)

RECIPIENTS_INDICATORS: dict[str, str] = {
    "DAC2A.10.206": BILATERAL,
    "DAC2A.10.106": IMPUTED_MULTILATERAL,
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
# countries, unspecified" and the CRS "Bilateral, unspecified"; every view uses one name, the
# unspecified part of "ODA eligible countries", following the "<area>, unspecified" convention.
UNSPECIFIED_RECIPIENT_CODE: int = 9998
UNSPECIFIED_RECIPIENT_NAME: str = "ODA eligible countries, unspecified"

# ---------------------------------------------------------------------------------------
# 5. Donors
#
# Every view reads individual providers and sums the memberships below into donor aggregates,
# rather than requesting the OECD's own aggregate providers, so each aggregate is defined once.
# ---------------------------------------------------------------------------------------

# Read once: each oda_data groupings call parses its JSON file again.
_PROVIDER_GROUPINGS: dict[str, dict] = provider_groupings()
BILATERAL_DONORS: dict[int, str] = _PROVIDER_GROUPINGS["all_bilateral"]
DAC_COUNTRIES: dict[int, str] = _PROVIDER_GROUPINGS["dac_countries"]
G7_COUNTRIES: dict[int, str] = _PROVIDER_GROUPINGS["g7"]
NON_DAC_COUNTRIES: dict[int, str] = _PROVIDER_GROUPINGS["non_dac_countries"]

EU_TOTAL: dict[int, str] = _PROVIDER_GROUPINGS["eu27_total"]
EU_COUNTRIES: dict[int, str] = _PROVIDER_GROUPINGS["eu27_countries"]
# Whatever eu27_total holds beyond the member states, i.e. {918: "EU Institutions"}
EU_INSTITUTIONS: dict[int, str] = {
    k: v for k, v in EU_TOTAL.items() if k not in EU_COUNTRIES
}

# Every provider the views read: the bilateral donors, plus EU Institutions, which is shown on
# its own but belongs to no donor group.
PROVIDERS: dict[int, str] = BILATERAL_DONORS | EU_INSTITUTIONS

# Donor aggregates, each the sum of its members, built the same way in every view. "All
# bilateral donors" is exactly DAC countries plus Non-DAC countries. EU Institutions is left
# out of every group, as in the OECD's headline totals: much of its spending is funded by
# donors' contributions, which their own totals already include.
DONOR_GROUPS: dict[str, dict] = {
    ALL_BILATERAL_DONORS: BILATERAL_DONORS,
    "DAC countries": DAC_COUNTRIES,
    "Non-DAC countries": NON_DAC_COUNTRIES,
    "G7 countries": G7_COUNTRIES,
    EU27_COUNTRIES_NAME: EU_COUNTRIES,
}
if DAC_COUNTRIES.keys() & NON_DAC_COUNTRIES.keys() or (
    BILATERAL_DONORS.keys() != DAC_COUNTRIES.keys() | NON_DAC_COUNTRIES.keys()
):
    raise ValueError(
        "oda_data's all_bilateral grouping no longer splits into dac_countries and "
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
# The recipients view takes every recipient DAC2A reports, countries and published groups
# alike. The CRS publishes no groups, so the sectors and gender views build them from the
# classifications in section 7 instead.
# ---------------------------------------------------------------------------------------

# DAC2A recipient codes from here up are groups (continents, regions, income groups), except
# a few "<area> unspecified" codes, which are recognised by name instead.
DAC2A_AGGREGATE_CODE_MIN: int = 10_000

# Display labels for DAC2A recipients, keyed by code. Labels only: what the view contains is
# whatever DAC2A returns. Regions are renamed to match the sectors and gender views.
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

# DAC2A recipients that come back without a code. The cause is upstream in oda_reader's area
# code mapping: a correction overwrites EDF's code, and the other two are missing from it.
# Remove once that is fixed. Codes as in recipient_groupings()["all_recipients"].
DAC2A_MISSING_RECIPIENT_CODES: dict[str, int] = {
    "East African Community": 237,
    "Indus Basin": 650,
    "European Development Fund [EDF]": 918,
}

# DAC2A recipients the recipients view drops:
# - the DAC-list income groups (Other LICs, LMICs, UMICs, unallocated by income, MADCTs),
#   since the view uses the World Bank classification and both have an "LMICs" and "UMICs";
# - multilateral agencies reported as recipients (IDA, UNDP, ...), and their totals "All
#   multilateral recipients" (10150) and "All recipients" (10200), as the view covers
#   developing countries and regions. Bilateral flows to those totals include donors' core
#   contributions to multilaterals, which the imputed multilateral series counts again.
EXCLUDED_DAC2A_RECIPIENTS: frozenset[int] = frozenset(
    {10_017, 10_018, 10_019, 10_024, 10_025, 10_150, 10_200, 816, *range(900, 990)}
)

# Read once: each oda_data groupings call parses its JSON file again.
_RECIPIENT_GROUPINGS: dict[str, dict] = recipient_groupings()

# The CRS records aid that cannot be allocated to a country against regional codes
# ("Africa, regional") and code 9998 (see UNSPECIFIED_RECIPIENT_CODE), which together are roughly
# half of all bilateral flows, so the CRS views need the full recipient list. Safe to sum:
# the CRS never reports the same money against both a country and a region, and it contains
# no "X, Total" style aggregates.
CRS_RECIPIENTS: dict[int, str] = _RECIPIENT_GROUPINGS["all_recipients"]

# Country lists that no source publishes as an aggregate, so every view sums them.
FRANCE_PRIORITY_RECIPIENTS: dict[int, str] = _RECIPIENT_GROUPINGS["france_priority"]
SAHEL_RECIPIENTS: dict[int, str] = _RECIPIENT_GROUPINGS["sahel"]

# ---------------------------------------------------------------------------------------
# 7. CRS classifications
#
# The CRS carries a region on every transaction, which is how the sectors and gender views
# build region groups: membership is read from the data, never maintained here. Income groups
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

# Continent totals, rolled up from CRS regions. The regions themselves are read from the
# data; this only records which regions make up each continent. Each list includes the
# continent-level region value the CRS uses for aid it records against a whole continent
# ("Africa, regional", read as "Africa"), so a continent total covers its sub-regions plus that.
CRS_REGION_ROLLUPS: dict[str, list[str]] = {
    "Africa": ["North of Sahara", "South of Sahara", "Africa"],
    "Asia": ["South & Central Asia", "Far East Asia", "Middle East", "Asia"],
    "America": ["Caribbean & Central America", "South America", "America"],
}

# CRS region values that are not regions. "Regional and Unspecified" holds only code 9998, so a
# region group for it would repeat that recipient value for value.
CRS_NON_REGIONS: frozenset[str] = frozenset({"Regional and Unspecified"})

# Sentinels for recipients the classification table never covers. Distinct from
# UNALLOCATED_BY_INCOME, which is a real category for regional and unspecified recipients.
CRS_UNCLASSIFIED_REGION: str = "Region not reported"
CRS_UNCLASSIFIED_INCOME: str = "Income group not reported"

# ---------------------------------------------------------------------------------------
# 8. Display orderings
#
# generate_view_options pins these first in the dropdowns, in this order; everything else
# follows alphabetically. Names absent from the data are skipped, so one donor ordering serves
# all four views even though they do not all publish every aggregate.
# ---------------------------------------------------------------------------------------

DONORS_ORDER: list[str] = [
    "DAC countries",
    "Non-DAC countries",
    ALL_BILATERAL_DONORS,
    "G7 countries",
    EU27_COUNTRIES_NAME,
    "EU Institutions",
    EU27_EUI_NAME,
]

FINANCING_INDICATORS_ORDER: list[str] = (
    list(dict.fromkeys(AGGREGATE_FINANCING_INDICATORS.values()))
    + ["Grants", "Non-grants"]
    + list(dict.fromkeys(IN_DONOR_FINANCING_INDICATORS.values()))
    + list(dict.fromkeys(PSI_FINANCING_INDICATORS.values()))
)

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
    *CRS_REGION_ROLLUPS,
    "North of Sahara",
    "South of Sahara",
    "Caribbean & Central America",
    "South America",
    "South & Central Asia",
    "Far East Asia",
    "Middle East",
    "Europe",
    "Oceania",
    "Sahel countries",
    "France priority countries",
]
