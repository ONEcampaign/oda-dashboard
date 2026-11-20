"""Tests for the view specs and group memberships."""

import pytest

from src.data.config import (
    ALL_BILATERAL_DONORS,
    DAC_COUNTRIES_NAME,
    EU27_EUI_NAME,
    ODA_ELIGIBLE,
)
from src.data.validation.views import (
    AGGREGATE_DONORS,
    CRITICAL_DONORS,
    DONOR_GROUP_MEMBERS,
    VALUE_COLUMNS,
    VIEWS,
    get_spec,
    recipient_aggregates,
)


def test_four_views() -> None:
    """The four dashboard views are specified, keyed by their own name."""
    assert set(VIEWS) == {
        "financing_view",
        "recipients_view",
        "gender_view",
        "sectors_view",
    }
    assert all(name == spec.name for name, spec in VIEWS.items())


def test_value_columns() -> None:
    """Eight value columns: four currencies by two prices."""
    assert len(VALUE_COLUMNS) == 8
    assert "value_usd_current" in VALUE_COLUMNS
    assert "value_cad_constant" in VALUE_COLUMNS


@pytest.mark.parametrize("spec", VIEWS.values(), ids=list(VIEWS))
def test_dtype_table_covers_required_columns(spec) -> None:
    """Every required column has an expected dtype, and nothing else does."""
    assert set(spec.dtypes) == set(spec.required_columns)
    assert spec.dtypes["year"] == "int16"
    assert spec.dtypes["donor_name"] == "string"
    assert spec.dtypes["value_usd_current"] == "float64"


def test_keys() -> None:
    """Keys as published."""
    assert VIEWS["financing_view"].keys == (
        "year",
        "donor_name",
        "indicator_name",
        "type",
    )
    assert VIEWS["sectors_view"].keys[-2:] == ("sector_name", "sub_sector_name")
    assert VIEWS["sectors_view"].partitioned
    assert not VIEWS["recipients_view"].partitioned


def test_time_windows() -> None:
    """Each view carries its config window."""
    assert VIEWS["financing_view"].time["base"] == 2025
    assert VIEWS["sectors_view"].time["start"] == 2013


def test_get_spec_unknown() -> None:
    """An unknown view name lists the known ones."""
    with pytest.raises(KeyError, match="financing_view"):
        get_spec("nope")


def test_donor_group_members_are_names() -> None:
    """Members are donor names, and all bilateral is DAC plus non-DAC."""
    dac = DONOR_GROUP_MEMBERS[DAC_COUNTRIES_NAME]
    assert "France" in dac
    assert (
        DONOR_GROUP_MEMBERS[ALL_BILATERAL_DONORS]
        == dac | DONOR_GROUP_MEMBERS["Non-DAC countries"]
    )


def test_aggregate_donors() -> None:
    """Groups and the EU27 + institutions bloc are aggregates; countries are not."""
    assert EU27_EUI_NAME in AGGREGATE_DONORS
    assert DAC_COUNTRIES_NAME in AGGREGATE_DONORS
    assert "France" not in AGGREGATE_DONORS


def test_critical_donors_are_members() -> None:
    """Every critical donor is a DAC member by name."""
    assert set(CRITICAL_DONORS) <= DONOR_GROUP_MEMBERS[DAC_COUNTRIES_NAME]


@pytest.mark.parametrize("view", ["recipients_view", "gender_view", "sectors_view"])
def test_recipient_aggregates(view: str) -> None:
    """Totals and groups are aggregates; countries are not."""
    aggregates = recipient_aggregates(view)
    assert ODA_ELIGIBLE in aggregates
    assert "Sahel countries" in aggregates
    assert "Kenya" not in aggregates
    assert "Africa, unspecified" not in aggregates


def test_recipient_aggregates_dac2a_groups() -> None:
    """The recipients view also treats DAC2A groups as aggregates."""
    assert "Small island developing states" in recipient_aggregates("recipients_view")
    assert "Small island developing states" not in recipient_aggregates("sectors_view")


def test_recipient_aggregates_financing() -> None:
    """The financing view has no recipients."""
    with pytest.raises(ValueError, match="recipient_name"):
        recipient_aggregates("financing_view")
