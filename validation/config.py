"""Configuration for data validation."""

from pathlib import Path

# Paths
VALIDATION_DIR = Path(__file__).parent
PROJECT_ROOT = VALIDATION_DIR.parent

# Where parquet files are cached by Observable Framework
CACHE_DIR = PROJECT_ROOT / "src" / ".observablehq" / "cache" / "data" / "scripts"

# Where partitioned datasets are stored (e.g., sectors_view)
CDN_FILES_DIR = PROJECT_ROOT / "cdn_files"

# Where validation artifacts are stored
VALIDATION_DATA_DIR = PROJECT_ROOT / "validation_data"
MANIFESTS_DIR = VALIDATION_DATA_DIR / "manifests"
REPORTS_DIR = VALIDATION_DATA_DIR / "reports"

# Donors that must always have data. Names, because every view is now keyed by name.
CRITICAL_DONORS: list[str] = [
    "Austria",
    "Belgium",
    "Denmark",
    "France",
    "Germany",
    "Italy",
    "Netherlands",
    "Norway",
    "Portugal",
    "Sweden",
    "Switzerland",
    "United Kingdom",
    "Finland",
    "Luxembourg",
    "Spain",
    "Czechia",
    "Slovak Republic",
    "Hungary",
    "Poland",
    "Canada",
    "United States",
    "Japan",
    "Korea",
    "New Zealand",
]

# Dataset definitions
DATASETS = {
    "financing_view": {
        "file": "financing_view.parquet",
        "key_columns": [
            "year",
            "donor_name",
            "indicator_name",
            "type",
        ],
        "value_column": "value_usd_constant",
        "required_columns": [
            "year",
            "donor_name",
            "indicator_name",
            "type",
            "value_usd_current",
            "value_usd_constant",
            "value_eur_current",
            "value_eur_constant",
            "value_gbp_current",
            "value_gbp_constant",
            "value_cad_current",
            "value_cad_constant",
        ],
        "critical_donors": CRITICAL_DONORS,
    },
    "recipients_view": {
        "file": "recipients_view.parquet",
        "key_columns": [
            "year",
            "donor_name",
            "recipient_name",
            "indicator_name",
        ],
        "value_column": "value_usd_constant",
        "required_columns": [
            "year",
            "donor_name",
            "recipient_name",
            "indicator_name",
            "value_usd_current",
            "value_usd_constant",
            "value_eur_current",
            "value_eur_constant",
            "value_gbp_current",
            "value_gbp_constant",
            "value_cad_current",
            "value_cad_constant",
        ],
        "critical_donors": CRITICAL_DONORS,
    },
    "gender_view": {
        "file": "gender_view.parquet",
        "key_columns": [
            "year",
            "donor_name",
            "recipient_name",
            "indicator_name",
        ],
        "value_column": "value_usd_constant",
        "required_columns": [
            "year",
            "donor_name",
            "recipient_name",
            "indicator_name",
            "value_usd_current",
            "value_usd_constant",
            "value_eur_current",
            "value_eur_constant",
            "value_gbp_current",
            "value_gbp_constant",
            "value_cad_current",
            "value_cad_constant",
        ],
        "critical_donors": CRITICAL_DONORS,
    },
    "sectors_view": {
        "file": "sectors_view",  # Directory, not .parquet file
        "partitioned": True,  # Flag for partitioned dataset
        "key_columns": [
            "year",
            "donor_name",
            "recipient_name",
            "indicator_name",
            "sector_name",
            "sub_sector_name",
        ],
        "value_column": "value_usd_constant",
        "required_columns": [
            "year",
            "donor_name",
            "recipient_name",
            "indicator_name",
            "sector_name",
            "sub_sector_name",
            "value_usd_current",
            "value_usd_constant",
            "value_eur_current",
            "value_eur_constant",
            "value_gbp_current",
            "value_gbp_constant",
            "value_cad_current",
            "value_cad_constant",
        ],
        "critical_donors": CRITICAL_DONORS,
    },
}

# Fallback for datasets that do not name their own critical donors.
MAJOR_DONORS = CRITICAL_DONORS

# The same idea for the SEEK checks, which are deliberately not name-based: they read raw CRS,
# which still carries donor_code, and their manifest is keyed by code to match.
#
# These are exactly the codes SEEK checked before the dashboard views moved to names — France,
# Germany, Italy, Netherlands, the UK, Canada and the US. That migration turned the shared
# MAJOR_DONORS into a list of names, which SEEK kept reading as codes, so every lookup missed
# and its three missing-donor checks silently stopped firing. Keeping a separate list is what
# lets the views be name-based without disabling SEEK.
#
# Code 7 is the Netherlands. The original list annotated it as Japan (which is 701), so Japan
# has in fact never been covered here — left as it was rather than quietly widening the check.
SEEK_CRITICAL_DONORS: list[int] = [4, 5, 6, 7, 12, 301, 302]

# Anomaly detection settings
ANOMALY_Z_SCORE_THRESHOLD = 2.0  # Flag if >2 standard deviations from historical mean
ANOMALY_Z_SCORE_HIGH = 3.0  # High priority if >3 standard deviations

# Value bounds, in whole currency units (the views publish units; the frontend divides by 1e6).
#
# The point of this bound is to catch a unit-scale mistake — a value left in millions, or
# multiplied by 1e6 twice. The largest legitimate single value across the four views is about
# 2.6e11 (roughly $261bn, an aggregate donor's total in one year), so 1e15 leaves ~4,000x
# headroom for genuine growth while still catching a 1e6 error by three orders of magnitude.
# It was previously 1e18, which no unit error could ever have exceeded.
MAX_SANE_VALUE = 1e15

# SEEK validation settings
# Purpose code filters from SEEK R code for sector-specific validation
SEEK_HEALTH_PURPOSE_CODES = [
    120,
    121,
    12110,
    12181,
    12182,
    12191,
    122,
    12220,
    12230,
    12240,
    12250,
    12261,
    12262,
    12263,
    12264,
    12281,
    123,
    12310,
    12320,
    12330,
    12340,
    12350,
    12382,
    130,
    13010,
    13020,
    13030,
    13040,
    13081,
]

SEEK_AGRICULTURE_PURPOSE_CODES = [
    31110,
    31120,
    31130,
    31140,
    31150,
    31161,
    31162,
    31163,
    31164,
    31165,
    31166,
    31181,
    31182,
    31191,
    31192,
    31193,
    31194,
    31195,
    31210,
    31220,
    31261,
    31281,
    31282,
    31291,
    31310,
    31320,
    31381,
    31382,
    31391,
    43040,
    43041,
    43042,
    43050,
    43060,
    43071,
    43072,
    43073,
    43081,
    43082,
]

# SEEK validation thresholds (Z-score based, matching existing anomaly detection pattern)
SEEK_Z_SCORE_THRESHOLD = 2.0  # Medium warning if >2 standard deviations
SEEK_Z_SCORE_HIGH = 3.0  # High priority if >3 standard deviations
SEEK_PCT_CHANGE_THRESHOLD = 0.20  # Fallback: medium warning if >20% change
SEEK_PCT_CHANGE_HIGH = 0.40  # Fallback: high priority if >40% change
