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


base_year = 2023  # for currency conversions

time_range = [2000, 2023]


class PATHS:
    """Class to store the paths to the data."""

    SRC = Path(__file__).resolve().parent.parent

    SETTINGS = SRC / "data" / "settings"
    DONORS = SETTINGS / "donors.json"
    RECIPIENTS = SETTINGS / "recipients.json"

    DATA = SRC / "data" / "raw_data"
    PYDEFLATE = DATA / "pydeflate"
    ODA_DATA = DATA / "oda_data"

    COMPONENTS = SRC / "components"
