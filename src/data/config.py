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

# Patches a requests-cache incompatibility that would otherwise fail the first time anything
# reads or writes the OECD HTTP cache. What matters is that it runs before that first request,
# not before the oda_data import; it sits here, above them, because importing config is the one
# thing every module in the pipeline already does. See src/data/_compat.py.
import src.data._compat  # noqa: F401
from oda_data import provider_groupings, recipient_groupings

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
    PYDEFLATE = DATA


# ---------------------------------------------------------------------------------------
# 2. Units and shared columns
# ---------------------------------------------------------------------------------------

# Values are published as whole currency units rather than millions, because integers compress
# far better in parquet. The frontend divides by this to get back to millions.
#
# A float, deliberately, and do not "tidy" it to 1_000_000. The sectors value columns are
# float32 when they are scaled, and with the float literal the product comes out float64, so
# the rounding sees every digit the source had. Written as an int the product stayed float32,
# which by the hundreds of millions can only land on multiples of 16: that change moved 176,089
# cells and shifted the sectors total by ~33,000 units. Measured in the pipeline, not in
# isolation — a float32 Series times 1e6 is float32 on its own, so the promotion depends on
# state the OECD libraries set up. Hence the warning rather than an explanation.
UNITS_PER_MILLION: float = 1e6

# Above this, a value column no longer fits in Int32 and has to be stored as Int64.
INT32_MAX: int = 2_147_483_647

CURRENCIES: list = ["USD", "EUR", "GBP", "CAD"]

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

FINANCING_TIME: dict = {"start": 1990, "end": 2025, "base": 2025}
BASE_TIME: dict = {"start": 1990, "end": 2024, "base": 2024}
SECTORS_TIME: dict = {"start": 2013, "end": 2024, "base": 2024}

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

AGGREGATE_FINANCING_INDICATORS: dict = {
    "ONE.10.1010_11010": "Total ODA",
    "ONE.10.1010C": "Core ODA (ONE Definition)",
    "DAC1.10.1015": "Bilateral ODA",
    "DAC1.10.11015": "Bilateral ODA",
    "DAC1.10.2000": "Multilateral ODA",
    "DAC1.10.12000": "Multilateral ODA",
    "DAC1.10.1600": "Debt relief",
    "DAC1.10.11026": "Debt relief",
}

PSI_FINANCING_INDICATORS: dict = {
    "DAC1.60.11030": "Private sector instruments",
    "DAC1.60.11040": "Private sector instruments",
    "DAC1.60.11023": "Private sector instruments - institutional approach",
    "DAC1.60.11024": "Private sector instruments - instrument approach",
}

IN_DONOR_FINANCING_INDICATORS: dict = {
    "DAC1.10.1820": "Refugees in donor countries",
    "DAC1.10.1500": "Scholarships and student costs in donor countries",
    "DAC1.10.1510": "Scholarships/training in donor country",
    "DAC1.10.1520": "Imputed student costs",
}

ALL_FINANCING_INDICATORS: dict = (
    AGGREGATE_FINANCING_INDICATORS | PSI_FINANCING_INDICATORS | IN_DONOR_FINANCING_INDICATORS
)

RECIPIENTS_INDICATORS: dict = {
    "DAC2A.10.206": "Bilateral",
    "DAC2A.10.106": "Imputed multilateral",
}

# Gender marker scores, keyed by the value oda_data's bilateral_policy_marker expects.
GENDER_INDICATORS: dict = {
    "principal": "Main target",
    "significant": "Secondary target",
    "not_targeted": "Not targeted",
    "not_screened": "Not screened",
}

# CRS flow categories read by the sectors and gender views: ODA (10) and other official
# flows (60). Anything else is out of scope for those views.
CRS_FLOW_CATEGORIES: list[int] = [10, 60]

# ---------------------------------------------------------------------------------------
# 5. Donors
#
# DAC1 and DAC2A publish aggregate providers, so financing and recipients request them by code.
# The CRS does not, so the sectors and gender views sum the memberships below instead.
# ---------------------------------------------------------------------------------------

# ONE's own aggregate provider codes, accepted by OECDClient as providers.
AGGREGATE_DONORS: dict = {
    20_001: "DAC countries",
    20_006: "Non-DAC countries",
    20_003: "G7 countries",
}

BILATERAL_DONORS: dict = provider_groupings()["all_bilateral"]
ALL_DONORS: dict = BILATERAL_DONORS | AGGREGATE_DONORS

DAC_COUNTRIES: dict = provider_groupings()["dac_countries"]
G7_COUNTRIES: dict = provider_groupings()["g7"]
NON_DAC_COUNTRIES: dict = provider_groupings()["non_dac_countries"]

EU_TOTAL: dict = provider_groupings()["eu27_total"]
EU_COUNTRIES: dict = provider_groupings()["eu27_countries"]
# Whatever eu27_total holds beyond the member states, i.e. {918: "EU Institutions"}
EU_INSTITUTIONS: dict = {k: v for k, v in EU_TOTAL.items() if k not in EU_COUNTRIES}

# Every provider that reports to the CRS in its own right, and so the basis of "All bilateral
# donors" in the sectors and gender views.
CRS_PROVIDERS: dict = BILATERAL_DONORS | EU_INSTITUTIONS

# EU institutions spend both their own resources and money contributed by EU member states.
# Only the former can be added to bilateral providers without double counting members'
# contributions, and that portion is what this series holds. It feeds the "All bilateral
# donors" total in the recipients view and is then dropped, so it never reaches the view.
EUI_BILATERAL_NAME: str = "EU Institutions, bilateral"

# Channels through which EU member states' core contributions reach the EU institutions.
# Members' imputed multilateral on these channels is excluded from the EU27 + institutions
# bloc, or it would be counted once there and again as the institutions' own spending.
# Source: human-development-dashboard/src/data/scripts/imputations.py
EUI_CHANNEL_CODES: frozenset[int] = frozenset({42000, 42001, 42003, 42004, 42999})

# ---------------------------------------------------------------------------------------
# 6. Recipients
#
# DAC2A publishes aggregate recipients, requested by code below. The CRS does not, so the
# sectors and gender views group by the classifications in section 7 instead.
# ---------------------------------------------------------------------------------------

# DAC2A aggregate recipient codes, with the labels the views display.
AGGREGATE_RECIPIENTS: dict = {
    10_100: "ODA eligible countries",
    998: "ODA eligible countries, unspecified",
    10_016: "Least Developed Countries (LDCs)",
    10_045: "Low Income Countries (LICs)",
    10_046: "Lower-Middle Income Countries (LMICs)",
    10_047: "Upper-Middle Income Countries (UMICs)",
    10_048: "High Income Countries (HICs)",
    10_030: "Heavily Indebted Poor Countries (HIPCs)",
    10_203: "Fragile states",
}

COUNTRIES_REGIONS_RECIPIENTS: dict = recipient_groupings()["all_developing_countries_regions"]
ALL_RECIPIENTS: dict = AGGREGATE_RECIPIENTS | COUNTRIES_REGIONS_RECIPIENTS

# The CRS records aid that cannot be allocated to a country against regional codes
# ("Africa, regional") and "Developing countries, unspecified", which together are roughly
# half of all bilateral flows. COUNTRIES_REGIONS_RECIPIENTS omits them, so the CRS views
# need the full recipient list. Safe to sum: the CRS never reports the same money against
# both a country and a region, and it contains no "X, Total" style aggregates.
CRS_RECIPIENTS: dict = recipient_groupings()["all_recipients"]

# Country lists that no source publishes as an aggregate, so every view sums them.
FRANCE_PRIORITY_RECIPIENTS: dict = recipient_groupings()["france_priority"]
SAHEL_RECIPIENTS: dict = recipient_groupings()["sahel"]

# ---------------------------------------------------------------------------------------
# 7. CRS classifications
#
# The CRS carries a region and an income group on every transaction, which is how the sectors
# and gender views build those groups: membership is read from the data, never maintained here.
# ---------------------------------------------------------------------------------------

# CRS income class -> display label. Membership is entirely the CRS incomegroup_name column;
# only the wording is mapped, to match the recipients view.
CRS_INCOME_LABELS: dict = {
    "LDCs": "Least Developed Countries (LDCs)",
    "Other LICs": "Other Low Income Countries",
    "LMICs": "Lower-Middle Income Countries (LMICs)",
    "UMICs": "Upper-Middle Income Countries (UMICs)",
    "MADCTs": "More Advanced Developing Countries",
    "Part I unallocated by income": "Unallocated by income",
}

# Continent totals, rolled up from CRS regions. The regions themselves are read from the
# data; this only records which regions make up each continent. Each list includes the
# continent-level region value the CRS uses for aid it records against a whole continent
# (e.g. "Africa, regional"), so a continent total covers its sub-regions plus that.
CRS_REGION_ROLLUPS: dict = {
    "Africa": ["North of Sahara", "South of Sahara", "Africa"],
    "Asia": ["South & Central Asia", "Far East Asia", "Middle East", "Asia"],
    "America": ["Caribbean & Central America", "South America", "America"],
}

# Sentinels for recipients the CRS never classifies. Distinct from the CRS's own
# "Part I unallocated by income" class, which is a real reported category.
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
    "All bilateral donors",
    "G7 countries",
    "EU27 countries",
    "EU Institutions",
    "EU27 & EU Institutions",
]

FINANCING_INDICATORS_ORDER: list[str] = (
    list(dict.fromkeys(AGGREGATE_FINANCING_INDICATORS.values()))
    + ["Grants", "Non-grants"]
    + list(dict.fromkeys(IN_DONOR_FINANCING_INDICATORS.values()))
    + list(dict.fromkeys(PSI_FINANCING_INDICATORS.values()))
)

# Recipients view: the DAC2A aggregates, then the two summed country lists.
RECIPIENTS_ORDER: list[str] = [
    "ODA eligible countries",
    "Least Developed Countries (LDCs)",
    "Low Income Countries (LICs)",
    "Lower-Middle Income Countries (LMICs)",
    "Upper-Middle Income Countries (UMICs)",
    "High Income Countries (HICs)",
    "Heavily Indebted Poor Countries (HIPCs)",
    "Fragile states",
    "France priority countries",
    "Sahel countries",
]

# CRS views: the overall total, then income groups, continents, CRS regions, country lists.
CRS_RECIPIENTS_ORDER: list[str] = [
    "ODA eligible countries",
    *CRS_INCOME_LABELS.values(),
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
