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

# Dataset definitions
DATASETS = {
    "financing_view": {
        "file": "financing_view.parquet",
        "key_columns": ["year", "donor_code", "indicator_name", "type"],
        "value_column": "value_usd_constant",  # Primary value column for stats
        "required_columns": [
            "year",
            "donor_code",
            "donor_name",
            "indicator",
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
        "critical_donors": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 18, 22, 50, 68, 69, 75, 76, 301, 302, 701, 742, 820],
    },
    "recipients_view": {
        "file": "recipients_view.parquet",
        "key_columns": ["year", "donor_code", "recipient_code", "indicator"],
        "value_column": "value_usd_constant",
        "required_columns": [
            "year",
            "donor_code",
            "donor_name",
            "recipient_code",
            "recipient_name",
            "indicator",
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
        "critical_donors": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 18, 22, 50, 68, 69, 75, 76, 301, 302, 701, 742, 820],
    },
    "gender_view": {
        "file": "gender_view.parquet",
        "key_columns": ["year", "donor_code", "recipient_code", "indicator"],
        "value_column": "value_usd_constant",
        "required_columns": [
            "year",
            "donor_code",
            "donor_name",
            "recipient_code",
            "recipient_name",
            "indicator",
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
        "critical_donors": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 18, 22, 50, 68, 69, 75, 76, 301, 302, 701, 742, 820],
    },
    "sectors_view": {
        "file": "sectors_view",  # Directory, not .parquet file
        "partitioned": True,  # Flag for partitioned dataset
        "key_columns": ["year", "donor_code", "recipient_code", "indicator", "sub_sector_code"],
        "value_column": "value_usd_constant",
        "required_columns": [
            "year",
            "donor_code",
            "donor_name",
            "recipient_code",
            "recipient_name",
            "indicator",
            "indicator_name",
            "sector_name",
            "sub_sector_code",
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
        "critical_donors": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 18, 22, 50, 68, 69, 75, 76, 301, 302, 701, 742, 820],
    },
}

# Major donors that must always have data (DAC country codes)
# 1=Austria, 2=Belgium, 3=Denmark, 4=France, 5=Germany, 6=Italy, 7=Japan, etc.
MAJOR_DONORS = [4, 5, 6, 7, 12, 301, 302]  # France, Germany, Italy, Japan, UK, USA, Canada

# Anomaly detection settings
ANOMALY_Z_SCORE_THRESHOLD = 2.0  # Flag if >2 standard deviations from historical mean
ANOMALY_Z_SCORE_HIGH = 3.0  # High priority if >3 standard deviations

# Value bounds (in units, i.e., actual currency units not millions)
MAX_SANE_VALUE = 1e18  # 1 trillion in units (frontend divides by 1e6)
