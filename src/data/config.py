import pandas as pd
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


base_year: int = 2023  # for currency conversions

TIME_RANGE: dict = {"start": 2000, "end": 2023}

FINANCING_INDICATORS = {
    "ONE.10.1010_11010": "Total ODA",
    # 'ONE.10.1010C', # Total Core ODA (ONE Definition)
    "DAC1.10.1015": "Bilateral ODA",
    "DAC1.10.2000": "Multilateral ODA",
    "DAC1.10.1600": "Debt relief",
    "DAC1.10.1500": "Scholarships and student costs in donor countries",
    "DAC1.10.1510": "Scholarships/training in donor country",
    "DAC1.10.1520": "Imputed student costs",
    "DAC1.10.1820": "Refugees in donor countries",
    "DAC1.60.11030": "Private sector instruments",
    "DAC1.60.11023": "Private sector instruments - institutional approach",
    "DAC1.60.11024": "Private sector instruments - instrument approach",
}

RECIPIENTS_INDICATORS = {
    "DAC2A.10.206": "Bilateral",
    "DAC2A.10.106": "Imputed multilateral",
}

GENDER_INDICATORS = {
    "principal": "Main target",
    "significant": "Secondary target",
    "not_targeted": "Not targeted",
    "not_screened": "Not screened",
}


class PATHS:
    """Class to store the paths to the data."""

    SRC = Path(__file__).resolve().parent.parent

    TOOLS = SRC / "data" / "analysis_tools"
    INDICATORS = TOOLS / "indicators.json"
    DONORS = TOOLS / "donors.json"
    RECIPIENTS = TOOLS / "recipients.json"

    DATA = SRC / "data" / "cache"
    PYDEFLATE = DATA
    ODA_DATA = DATA

    COMPONENTS = SRC / "components"
