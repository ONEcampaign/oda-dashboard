import logging
from pathlib import Path

from oda_data import provider_groupings, recipient_groupings

logger = logging.getLogger(__name__)

# Create terminal (stream) handler
shell_handler = logging.StreamHandler()
shell_handler.setLevel(logging.INFO)  # Set logging level for handler
# Define log format (optional but recommended)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
shell_handler.setFormatter(formatter)
# Add the handler to the logger
logger.addHandler(shell_handler)
# Set logger level
logger.setLevel(logging.INFO)

FINANCING_TIME: dict = {"start": 1990, "end": 2025, "base": 2025}
BASE_TIME: dict = {"start": 1990, "end": 2024, "base": 2024}  # for currency conversions
SECTORS_TIME: dict = {"start": 2013, "end": 2024, "base": 2024}
CURRENCIES: list = ["USD", "EUR", "GBP", "CAD"]

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

ALL_FINANCING_INDICATORS: dict = AGGREGATE_FINANCING_INDICATORS | PSI_FINANCING_INDICATORS | IN_DONOR_FINANCING_INDICATORS

FINANCING_INDICATORS_ORDER: list[str] = (
    list(dict.fromkeys(AGGREGATE_FINANCING_INDICATORS.values()))
    + ["Grants", "Non-grants"]
    + list(dict.fromkeys(IN_DONOR_FINANCING_INDICATORS.values()))
    + list(dict.fromkeys(PSI_FINANCING_INDICATORS.values()))
)

RECIPIENTS_INDICATORS: dict = {
    "DAC2A.10.206": "Bilateral",
    "DAC2A.10.106": "Imputed multilateral",
}

GENDER_INDICATORS: dict = {
    "principal": "Main target",
    "significant": "Secondary target",
    "not_targeted": "Not targeted",
    "not_screened": "Not screened",
}


AGGREGATE_DONORS: dict = {
    20_001: "DAC countries",
    20_006: "Non-DAC countries",
    20_003: "G7 countries"
}

BILATERAL_DONORS: dict = provider_groupings()["all_bilateral"]
ALL_DONORS: dict = BILATERAL_DONORS | AGGREGATE_DONORS

EU_TOTAL: dict = provider_groupings()["eu27_total"]
EU_COUNTRIES: dict = provider_groupings()["eu27_countries"]
# Whatever eu27_total holds beyond the member states, i.e. {918: "EU Institutions"}
EU_INSTITUTIONS: dict = {k: v for k, v in EU_TOTAL.items() if k not in EU_COUNTRIES}

# EU institutions spend both their own resources and money contributed by EU member states.
# Only the former can be added to bilateral providers without double counting members'
# contributions, and that portion is what this series holds. It feeds the "All bilateral
# donors" total and is then dropped, so it never reaches the view.
EUI_BILATERAL_NAME: str = "EU Institutions, bilateral"

DONORS_ORDER: list[str] = [
    "DAC countries",
    "Non-DAC countries",
    "All bilateral donors",
    "G7 countries",
    "EU27 countries",
    "EU Institutions",
    "EU27 & EU Institutions",
]

# ---------------------------------------------------------------------------------------
# Sectors groupings
#
# The CRS is transaction level: unlike DAC1 and DAC2A it reports no aggregate providers or
# recipients, so every sectors aggregate is summed locally from these memberships. Donor
# memberships come from oda_data; recipient groupings come from the CRS's own
# recipient_region and incomegroup_name columns.
# ---------------------------------------------------------------------------------------

DAC_COUNTRIES: dict = provider_groupings()["dac_countries"]
G7_COUNTRIES: dict = provider_groupings()["g7"]
NON_DAC_COUNTRIES: dict = provider_groupings()["non_dac_countries"]

# The CRS records aid that cannot be allocated to a country against regional codes
# ("Africa, regional") and "Developing countries, unspecified", which together are roughly
# half of all bilateral flows. COUNTRIES_REGIONS_RECIPIENTS omits them, so the sectors view
# needs the full recipient list. Safe to sum: the CRS never reports the same money against
# both a country and a region, and it contains no "X, Total" style aggregates.
CRS_RECIPIENTS: dict = recipient_groupings()["all_recipients"]

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

# Channels through which EU member states' core contributions reach the EU institutions.
# Members' imputed multilateral on these channels is excluded from the EU27 + institutions
# bloc, or it would be counted once there and again as the institutions' own spending.
# Source: human-development-dashboard/src/data/scripts/imputations.py
EUI_CHANNEL_CODES: frozenset[int] = frozenset({42000, 42001, 42003, 42004, 42999})

# Sentinels for recipients the CRS never classifies. Distinct from the CRS's own
# "Part I unallocated by income" class, which is a real reported category.
CRS_UNCLASSIFIED_REGION: str = "Region not reported"
CRS_UNCLASSIFIED_INCOME: str = "Income group not reported"

# Every provider that reports to the CRS in its own right. The CRS has no aggregate
# providers, so the donor groups of both CRS views are summed from these.
CRS_PROVIDERS: dict = BILATERAL_DONORS | EU_INSTITUTIONS

# "EU27 & EU Institutions" is deliberately absent: it cannot be computed from the CRS, which
# offers no equivalent of the DAC1 EU-institutions weighting used by the other views.
CRS_DONORS_ORDER: list[str] = [
    "DAC countries",
    "Non-DAC countries",
    "All bilateral donors",
    "G7 countries",
    "EU27 countries",
    "EU Institutions",
]

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

AGGREGATE_RECIPIENTS: dict = {
    10_100: "ODA eligible countries",
    998: "ODA eligible countries, unspecified",
    10_016: "Least Developed Countries (LDCs)",
    10_045: "Low Income Countries (LICs)",
    10_046: "Lower-Middle Income Countries (LMICs)",
    10_047: "Upper-Middle Income Countries (UMICs)",
    10_048: "High Income Countries (HICs)",
    10_030: "Heavily Indebted Poor Countries (HIPCs)",
    10_203: "Fragile states"
}

FRANCE_PRIORITY_RECIPIENTS: dict = recipient_groupings()["france_priority"]
SAHEL_RECIPIENTS: dict = recipient_groupings()["sahel"]

COUNTRIES_REGIONS_RECIPIENTS: dict = recipient_groupings()["all_developing_countries_regions"]
ALL_RECIPIENTS: dict = AGGREGATE_RECIPIENTS | COUNTRIES_REGIONS_RECIPIENTS

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



class PATHS:
    """Class to store the paths to the data."""

    SRC = Path(__file__).resolve().parent.parent

    TOPIC_PAGE = SRC.parent / "topic_page"
    CDN_FILES = SRC.parent / "cdn_files"

    TOOLS = SRC / "data" / "analysis_tools"
    INDICATORS = TOOLS / "indicators.json"

    DATA = SRC / "data" / "cache"
    PYDEFLATE = DATA
    ODA_DATA = DATA

    COMPONENTS = SRC / "components"
