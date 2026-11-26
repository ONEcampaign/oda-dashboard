"""The topic_page files the ODA article reads keep the shape its charts and text expect.

The article (cms.one.org article 26, "Official Development Assistance (ODA)") reads these
files from main through CMS data sources. Its Flourish charts bind columns by name and some
filter rows by donor name, and its text reads oda_key_numbers.json keys as
{{oda_topic.<key>}} tokens. Renaming any of them breaks the page without an error, so a
change here must go with the matching change in the CMS.
"""

import csv
import json
import re

import pytest

from src.data.config import DAC_COUNTRIES_NAME, PATHS
from src.data.topic_page.common import (
    KEY_NUMBER_KEYS,
    KEY_NUMBERS_FILE,
    LATEST_YEAR_AGG,
    LATEST_YEAR_DETAIL,
    LONG_START_YEAR,
    MINI_CHART_START_YEAR,
    ODA_COVID_START_YEAR,
    SECTORS_START_YEAR,
)
from src.data.topic_page.ukraine import PRE_INVASION_YEAR

# File -> (its exact header, the column holding the donor name, or None).
CHART_FILES: dict[str, tuple[list[str], str | None]] = {
    "sm_total_oda.csv": (
        ["first_line", "value", "second_line", "pct_change", "centre"],
        None,
    ),
    "oda_gni_sm.csv": (
        ["first_line", "oda_gni", "second_line", "distance", "centre"],
        None,
    ),
    "aid_to_income_latest.csv": (
        ["Year", "Donor", "Recipient", "ODA", "Share of total ODA", "Label"],
        "Donor",
    ),
    "aid_to_africa_ts.csv": (
        ["Year", "Donor", "Aid to Africa", "Share of total ODA", "Annual change"],
        "Donor",
    ),
    "aid_to_health_ts.csv": (
        [
            "Year",
            "Donor",
            "Recipient",
            "Sector",
            "Total aid to health",
            "Share of total ODA",
        ],
        "Donor",
    ),
    "aid_to_humanitarian_ts.csv": (
        [
            "Year",
            "Donor",
            "Recipient",
            "Sector",
            "Total Humanitarian Aid",
            "Share of total ODA",
        ],
        "Donor",
    ),
    "oda_gni_ts.csv": (
        ["name", "year", "ODA (left-axis)", "ODA/GNI (right-axis)"],
        "name",
    ),
    "oda_covid.csv": (
        [
            "Year",
            "Donor",
            "COVID ODA",
            "IDRC",
            "ODA to Ukraine",
            "Other ODA",
            "Total ODA",
            "Preliminary",
        ],
        "Donor",
    ),
    "oda_gni_single_year_ts.csv": (
        ["Donor", "Year", "Total ODA", "ODA short of 0.7% commitment", "ODA/GNI"],
        None,
    ),
    "key_sector_shares.csv": (
        [
            "Year",
            "name",
            "Humanitarian",
            "Education",
            "Health",
            "Refugees in Donor Countries",
            "Environment Protection",
        ],
        "name",
    ),
    "aid_to_ukraine_comparison.csv": (
        ["year", "donor_name", "recipient_name", "value"],
        None,
    ),
    "aid_to_regions_ts.csv": (
        [
            "year",
            "name",
            "Africa",
            "America",
            "Asia",
            "Developing countries, unspecified",
            "Europe",
            "Oceania",
            "note",
        ],
        "name",
    ),
    "aid_to_income_ts.csv": (
        [
            "name",
            "year",
            *(
                group + suffix
                for suffix in ("", " (value)")
                for group in (
                    "High income",
                    "Low income",
                    "Lower-middle income",
                    "Not classified by income",
                    "Upper-middle income",
                )
            ),
        ],
        "name",
    ),
}

# sector_totals.csv has one column per sector, ordered by the DAC countries total, so only its keys and the
# sectors the article names are pinned.
SECTOR_TOTALS_COLUMNS: list[str] = [
    "year",
    "name",
    "Humanitarian",
    "Education",
    "Health",
]

# Keys the article's text reads, by the release their figures come from. Aggregates (DAC1,
# March-April) run to LATEST_YEAR_AGG; granular data (CRS, December) to LATEST_YEAR_DETAIL.
# Text quoting a figure names its year with the matching token, {{oda_topic.latest_year}} or
# {{oda_topic.latest_year_detail}}, never a typed year (#33).
AGGREGATE_KEYS: list[str] = [
    "latest_year",
    "previous_year",
    "total_oda",
    "total_oda_change",
    "total_oda_change_abs",
    "total_oda_change_verb",
    "total_oda_change_noun",
    "oda_gni",
    "oda_gni_distance",
]
GRANULAR_KEYS: list[str] = [
    "latest_year_detail",
    "aid_to_africa",
    "aid_to_africa_share",
    "aid_to_health",
    "aid_to_health_share",
    "aid_to_humanitarian",
    "aid_to_humanitarian_share",
    "ukraine_share_of_total_oda",
    "ukraine_times_pre_invasion",
    "other_oda_change_abs",
    "other_oda_change_verb",
    "total_oda_change_since_pre_covid_abs",
    "total_oda_change_since_pre_covid_noun",
]
# Fixed reference years, not tied to a release.
REFERENCE_YEAR_KEYS: list[str] = ["pre_invasion_year", "pre_covid_year"]
TEXT_KEYS: list[str] = AGGREGATE_KEYS + GRANULAR_KEYS + REFERENCE_YEAR_KEYS
# Read as {{oda_topic.aid_to_incomes.<group>.share}}, with spaces in group names as "_".
INCOME_GROUP_KEYS: list[str] = [
    "Low income",
    "Lower-middle income",
    "Upper-middle income",
    "High income",
    "Not classified by income",
]
# The one nested key: income group -> value and share.
NESTED_KEYS: list[str] = ["aid_to_incomes"]
# A signed percentage with one decimal and no space before the sign, e.g. "-22.8%".
SIGNED_PERCENT = re.compile(r"-?\d+\.\d%")

# File -> (its year column, first year, last year). Every year in between is present.
YEAR_RANGES: dict[str, tuple[str, int, int]] = {
    "aid_to_income_latest.csv": ("Year", LATEST_YEAR_DETAIL, LATEST_YEAR_DETAIL),
    "aid_to_africa_ts.csv": ("Year", MINI_CHART_START_YEAR, LATEST_YEAR_DETAIL),
    "aid_to_health_ts.csv": ("Year", MINI_CHART_START_YEAR, LATEST_YEAR_DETAIL),
    "aid_to_humanitarian_ts.csv": ("Year", MINI_CHART_START_YEAR, LATEST_YEAR_DETAIL),
    "oda_gni_ts.csv": ("year", LONG_START_YEAR, LATEST_YEAR_AGG),
    "oda_gni_single_year_ts.csv": ("Year", LONG_START_YEAR, LATEST_YEAR_AGG),
    "oda_covid.csv": ("Year", ODA_COVID_START_YEAR, LATEST_YEAR_AGG),
    "key_sector_shares.csv": ("Year", SECTORS_START_YEAR, LATEST_YEAR_DETAIL),
    "sector_totals.csv": ("year", SECTORS_START_YEAR, LATEST_YEAR_DETAIL),
    "aid_to_ukraine_comparison.csv": ("year", PRE_INVASION_YEAR, LATEST_YEAR_DETAIL),
    "aid_to_regions_ts.csv": ("year", LONG_START_YEAR, LATEST_YEAR_DETAIL),
    "aid_to_income_ts.csv": ("year", LONG_START_YEAR, LATEST_YEAR_DETAIL),
}
# Single-row cards whose first line names the year of their figure.
CARD_YEARS: dict[str, int] = {
    "sm_total_oda.csv": LATEST_YEAR_AGG,
    "oda_gni_sm.csv": LATEST_YEAR_AGG,
}


def _read(filename: str) -> tuple[list[str], list[dict[str, str]]]:
    """A topic_page CSV's header and rows."""
    with (PATHS.TOPIC_PAGE / filename).open(newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


@pytest.mark.parametrize("filename", sorted(CHART_FILES))
def test_chart_file_keeps_its_header(filename: str) -> None:
    """Each chart file has exactly the columns its chart binds."""
    header, _ = _read(filename)
    assert header == CHART_FILES[filename][0]


@pytest.mark.parametrize(
    "filename",
    sorted(name for name, (_, column) in CHART_FILES.items() if column is not None),
)
def test_chart_file_has_dac_countries_rows(filename: str) -> None:
    """Files the charts filter by donor carry the DAC countries total under its name."""
    _, rows = _read(filename)
    column = CHART_FILES[filename][1]
    assert any(row[column] == DAC_COUNTRIES_NAME for row in rows)


def test_sector_totals_keeps_its_key_columns() -> None:
    """sector_totals.csv keeps its keys and the sectors the article names."""
    header, rows = _read("sector_totals.csv")
    assert set(SECTOR_TOTALS_COLUMNS) <= set(header)
    assert header[:2] == ["year", "name"]
    assert any(row["name"] == DAC_COUNTRIES_NAME for row in rows)


def _key_numbers() -> dict:
    """The committed oda_key_numbers.json."""
    return json.loads((PATHS.TOPIC_PAGE / KEY_NUMBERS_FILE).read_text())


def test_key_numbers_hold_exactly_the_keys_the_text_reads() -> None:
    """oda_key_numbers.json holds every key the article's text reads, as text, and no other."""
    numbers = _key_numbers()
    assert set(numbers) == set(TEXT_KEYS + NESTED_KEYS)
    assert all(isinstance(numbers[key], str) for key in TEXT_KEYS)
    assert set(numbers["aid_to_incomes"]) == set(INCOME_GROUP_KEYS)


def test_writers_declare_exactly_the_keys_the_text_reads() -> None:
    """The scripts' KEY_NUMBER_KEYS, which retires every other key, is the article's set."""
    assert set(TEXT_KEYS + NESTED_KEYS) == KEY_NUMBER_KEYS


def test_total_oda_change_format() -> None:
    """total_oda_change is a signed percentage with no space before the sign."""
    assert SIGNED_PERCENT.fullmatch(_key_numbers()["total_oda_change"])


@pytest.mark.parametrize("filename", sorted(YEAR_RANGES))
def test_chart_file_covers_its_years(filename: str) -> None:
    """Each chart file runs over its years, with none missing in between."""
    column, first, last = YEAR_RANGES[filename]
    _, rows = _read(filename)
    years = {int(row[column]) for row in rows}
    assert years == set(range(first, last + 1))


@pytest.mark.parametrize("filename", sorted(CARD_YEARS))
def test_card_names_its_year(filename: str) -> None:
    """The single-row cards say which year their figure is for."""
    _, rows = _read(filename)
    assert [row["first_line"] for row in rows] == [f"As of {CARD_YEARS[filename]}"]


def test_release_years_match_the_pipeline() -> None:
    """latest_year and latest_year_detail name the years the figures come from."""
    numbers = _key_numbers()
    assert numbers["latest_year"] == str(LATEST_YEAR_AGG)
    assert numbers["latest_year_detail"] == str(LATEST_YEAR_DETAIL)
