"""End-to-end tests of validate.main(): the exit code the deploy gate acts on."""

from pathlib import Path

import pytest

from src.data.config import DAC_COUNTRIES_NAME
from src.data.scripts import validate
from src.data.validation.views import (
    CRITICAL_DONORS,
    DONOR_GROUP_MEMBERS,
    VALUE_COLUMNS,
    get_spec,
)
from tests.data.validation.conftest import build_view, write_flat

VIEW: str = "financing_view"
TYPES: tuple[str, ...] = ("Flows", "Grant equivalents")
# Each critical donor's Total ODA; their DAC countries sum lands inside the anchor band.
DONOR_VALUE: float = 1e10


def _financing_rows() -> list[dict]:
    """Total ODA for the critical donors and every group they make up, in the first and
    last year of the window, for both types. The view passes every blocking check."""
    time = get_spec(VIEW).time
    donors = {donor: DONOR_VALUE for donor in CRITICAL_DONORS}
    groups = {
        group: sum(v for d, v in donors.items() if d in members)
        for group, members in DONOR_GROUP_MEMBERS.items()
    }
    groups = {group: value for group, value in groups.items() if value}
    assert groups[DAC_COUNTRIES_NAME] == DONOR_VALUE * len(CRITICAL_DONORS)
    return [
        {
            "year": year,
            "donor_name": donor,
            "indicator_name": "Total ODA",
            "type": type_,
            "value_usd_current": value,
            "pct_of_total_oda": 1.0,
            "pct_of_gni": 0.005,
        }
        for year in (time["start"], time["end"])
        for donor, value in {**donors, **groups}.items()
        for type_ in TYPES
    ]


@pytest.fixture
def expected_path(tmp_path: Path) -> Path:
    """An expected deltas file with no entries."""
    path = tmp_path / "expected.toml"
    path.write_text("# no entries\n")
    return path


def _main(source: Path, expected: Path, tmp_path: Path) -> int:
    """Run validate.main() on one view, without cross-view."""
    return validate.main(
        [
            "--views",
            VIEW,
            "--source-dir",
            str(source),
            "--expected",
            str(expected),
            "--no-cross-view",
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )


def test_clean_build_exits_zero(tmp_path: Path, expected_path: Path) -> None:
    """A view that passes every blocking check exits 0 and writes a report."""
    write_flat(build_view(VIEW, _financing_rows()), tmp_path / "src" / VIEW)
    assert _main(tmp_path / "src", expected_path, tmp_path) == 0
    assert len(list((tmp_path / "reports").glob("validation_*.md"))) == 1


def test_units_slip_exits_one(tmp_path: Path, expected_path: Path) -> None:
    """Values scaled by 1e-6 trip the anchor, a blocking failure: exit 1."""
    view = build_view(VIEW, _financing_rows())
    view.data[list(VALUE_COLUMNS)] *= 1e-6
    write_flat(view, tmp_path / "src" / VIEW)
    assert _main(tmp_path / "src", expected_path, tmp_path) == 1


def test_missing_view_exits_one(tmp_path: Path, expected_path: Path) -> None:
    """A view that is not there at all blocks."""
    (tmp_path / "src").mkdir()
    assert _main(tmp_path / "src", expected_path, tmp_path) == 1
