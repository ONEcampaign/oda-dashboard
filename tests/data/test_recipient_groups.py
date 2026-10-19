"""Tests for the CRS views' recipient groups and the unspecified naming convention."""

import pandas as pd
import pytest

from src.data.analysis_tools.naming import normalize_crs_regions
from src.data.analysis_tools.transformations import (
    CRS_REGION_COL,
    INCOME_GROUP_COL,
    build_crs_recipient_group_totals,
)
from src.data.config import (
    CRS_CONTINENTS,
    CRS_REGION_ALIASES,
    CRS_REGIONS,
    CRS_UNCLASSIFIED_REGION,
)


def test_regional_region_values_fold_into_their_continent():
    regions = pd.Series(["Africa, regional", "Africa", "North of Sahara", None])
    assert normalize_crs_regions(regions).tolist() == [
        "Africa",
        "Africa",
        "North of Sahara",
        pd.NA,
    ]


def test_unknown_region_value_fails_loudly():
    with pytest.raises(ValueError, match="Atlantis, regional"):
        normalize_crs_regions(pd.Series(["Africa", "Atlantis, regional"]))


def test_aliases_point_at_known_regions():
    assert set(CRS_REGION_ALIASES.values()) <= CRS_REGIONS.keys()


def test_every_continent_has_regions():
    for continent in CRS_CONTINENTS:
        assert any(
            r.is_region and r.continent == continent for r in CRS_REGIONS.values()
        )


def test_continent_totals_include_unspecified_aid_and_skip_non_regions():
    rows = pd.DataFrame(
        {
            "year": [2023] * 4,
            "recipient_code": [189, 298, 248, 9998],
            "value": [1.0, 2.0, 4.0, 8.0],
            CRS_REGION_COL: [
                "North of Sahara",
                "Africa",
                "South of Sahara",
                "Regional and Unspecified",
            ],
            INCOME_GROUP_COL: ["Unallocated by income"] * 4,
        }
    )
    totals = pd.concat(build_crs_recipient_group_totals(rows, ["year"], {}))
    value = totals.groupby("recipient_name")["value"].sum()
    # Africa covers North and South of Sahara plus Africa's own unspecified aid.
    assert value["Africa"] == 7.0
    assert "Regional and Unspecified" not in value.index
    assert value["ODA eligible countries"] == 15.0


def test_unclassified_recipients_get_no_region_group_but_count_in_the_total():
    rows = pd.DataFrame(
        {
            "year": [2023] * 2,
            "recipient_code": [189, 1],
            "value": [1.0, 2.0],
            CRS_REGION_COL: ["North of Sahara", CRS_UNCLASSIFIED_REGION],
            INCOME_GROUP_COL: ["Unallocated by income"] * 2,
        }
    )
    totals = pd.concat(build_crs_recipient_group_totals(rows, ["year"], {}))
    value = totals.groupby("recipient_name")["value"].sum()
    assert CRS_UNCLASSIFIED_REGION not in value.index
    assert value["ODA eligible countries"] == 3.0
