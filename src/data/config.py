import logging
from pathlib import Path

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

eui_bi_code: int = 919

BASE_TIME: dict = {"start": 1990, "end": 2023, "base": 2023}  # for currency conversions
CURRENCIES: list = ["USD", "EUR", "GBP", "CAD"]

FINANCING_TIME: dict = {"start": 1990, "end": 2024, "base": 2024}

SECTORS_TIME: dict = {"start": 2013, "end": 2023, "base": 2023}

IN_DONOR_FINANCING_INDICATORS: dict = {
    "DAC1.10.1820": "Refugees in donor countries",
    "DAC1.10.1500": "Scholarships and student costs in donor countries",
    "DAC1.10.1510": "Scholarships/training in donor country",
    "DAC1.10.1520": "Imputed student costs",
}

OTHER_FINANCING_INDICATORS: dict = {
    "ONE.10.1010_11010": "Total ODA",
    "ONE.10.1010C": "Core ODA (ONE Definition)",
    "DAC1.10.1015": "Bilateral ODA",
    "DAC1.10.2000": "Multilateral ODA",
    "DAC1.10.1600": "Debt relief",
    "DAC1.60.11030": "Private sector instruments",
    "DAC1.60.11023": "Private sector instruments - institutional approach",
    "DAC1.60.11024": "Private sector instruments - instrument approach",
}

FINANCING_INDICATORS: dict = OTHER_FINANCING_INDICATORS | IN_DONOR_FINANCING_INDICATORS

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

DONOR_GROUPS: dict = {
    "All bilateral donors": 20_000,
    "DAC countries": 20_001,
    "EU27 countries": 20_002,
    "EU27 + EU Institutions": 20_003,
    "G7 countries": 20_004,
    "non-DAC countries": 20_005,
}

RECIPIENT_GROUPS: dict = {
    "Developing countries": 100_000,
    "Africa": 100_001,
    "America": 100_002,
    "Asia": 100_003,
    "Caribbean": 100_004,
    "Central America": 100_006,
    "Central America and the Caribbean": 10_005,
    "Eastern Africa": 100_007,
    "Europe": 100_008,
    "Far East Asia": 100_009,
    "Fragile and conflict-affected countries": 100_010,
    "France priority countries": 100_011,
    "Least developed countries": 100_012,
    "Low income countries": 100_013,
    "Lower-middle income countries": 100_014,
    "Melanesia": 100_015,
    "Micronesia": 100_016,
    "Middle Africa": 100_017,
    "Middle East": 100_018,
    "North America": 100_019,
    "Northern Africa": 100_02,
    "Oceania": 100_021,
    "Polynesia": 100_022,
    "Sahel countries": 100_023,
    "South America": 100_024,
    "Southern Africa": 100_025,
    "Southern and Central Asia": 100_026,
    "Sub-Saharan Africa": 10_003,
    "Upper-middle income countries": 100_028,
    "Western Africa": 100_029,
    "Middle income countries": 100_030,
}


class PATHS:
    """Class to store the paths to the data."""

    SRC = Path(__file__).resolve().parent.parent

    TOPIC_PAGE = SRC.parent / "topic_page"
    CDN_FILES = SRC.parent / "cdn_files"

    TOOLS = SRC / "data" / "analysis_tools"
    INDICATORS = TOOLS / "indicators.json"
    DONORS = TOOLS / "donors.json"
    RECIPIENTS = TOOLS / "recipients.json"

    FINANCING_INDICATORS_CODES = TOOLS / "financing_indicators.json"
    RECIPIENT_INDICATORS_CODES = TOOLS / "recipients_indicators.json"

    DATA = SRC / "data" / "cache"
    PYDEFLATE = DATA
    ODA_DATA = DATA

    COMPONENTS = SRC / "components"
