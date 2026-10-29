"""Tests for the EU27 + EU Institutions weighting."""

from dataclasses import dataclass, field

import pandas as pd
import pytest

from src.data.analysis_tools.eu import (
    EU_INSTITUTIONS_CONTRIBUTIONS_LINE,
    eu_institutions_weight,
    eui_weights,
    weight_eu_institutions,
)
from src.data.config import EU_COUNTRIES, EU_INSTITUTIONS_CODE

FRANCE, GERMANY, US = 4, 5, 302


@dataclass
class FakeQuery:
    """Stands in for oda.Query: a fixed result."""

    result: pd.DataFrame

    def explain(self) -> str:
        return "Fake query."

    def to_pandas(self) -> pd.DataFrame:
        return self.result


@dataclass
class FakeContext:
    """Stands in for oda.Context: one fixed result per indicator, keeping every call."""

    results: dict[str, pd.DataFrame]
    calls: list[tuple[str, dict]] = field(default_factory=list)

    def query(self, indicator: str, **kwargs: object) -> FakeQuery:
        self.calls.append((indicator, kwargs))
        return FakeQuery(self.results[indicator])


def oda_rows(rows: list[tuple[int, int, float]]) -> pd.DataFrame:
    """Build an oda-data result from (provider, year, value), codes as strings."""
    return pd.DataFrame(
        {
            "provider": [str(p) for p, _, _ in rows],
            "year": pd.array([y for _, y, _ in rows], dtype="Int64"),
            "value": [v for _, _, v in rows],
        }
    )


def frame(rows: list[tuple[int, float]]) -> pd.DataFrame:
    """Build a frame with year and value from (year, value)."""
    return pd.DataFrame(rows, columns=["year", "value"])


def test_weight_is_the_share_not_funded_by_members():
    # 2.x: weight = 1 - sum(EU27 line 2102) / 918 total ODA.
    contributions = frame([(2020, 30.0), (2020, 10.0), (2021, 25.0)])
    total = frame([(2020, 100.0), (2021, 50.0)])
    assert eu_institutions_weight(contributions, total) == pytest.approx(
        {2020: 0.6, 2021: 0.5}
    )


def test_weight_needs_both_sides_in_every_year():
    with pytest.raises(ValueError, match="different years"):
        eu_institutions_weight(
            frame([(2020, 1.0)]), frame([(2020, 10.0), (2021, 10.0)])
        )


def test_weight_outside_zero_to_one_raises():
    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        eu_institutions_weight(frame([(2020, 120.0)]), frame([(2020, 100.0)]))


def test_eui_weights_reads_members_line_2102_and_918_total_on_one_basis():
    ctx = FakeContext(
        {
            "oecd.dac1.lines": oda_rows([(FRANCE, 2020, 20.0), (GERMANY, 2020, 30.0)]),
            "oecd.dac1.total_oda": oda_rows([(EU_INSTITUTIONS_CODE, 2020, 200.0)]),
        }
    )
    weights = eui_weights(ctx, [2020], basis="grant_equivalent")

    assert weights == pytest.approx({2020: 0.75})
    lines_call, total_call = (kwargs for _, kwargs in ctx.calls)
    assert lines_call["lines"] == [EU_INSTITUTIONS_CONTRIBUTIONS_LINE]
    assert lines_call["providers"] == list(EU_COUNTRIES)
    assert total_call["providers"] == [EU_INSTITUTIONS_CODE]
    assert {lines_call["basis"], total_call["basis"]} == {"grant_equivalent"}


def test_eui_weights_raises_on_a_year_with_no_data():
    ctx = FakeContext(
        {
            "oecd.dac1.lines": oda_rows([(FRANCE, 2020, 20.0)]),
            "oecd.dac1.total_oda": oda_rows([(EU_INSTITUTIONS_CODE, 2020, 200.0)]),
        }
    )
    with pytest.raises(ValueError, match=r"no data for \[2021\]"):
        eui_weights(ctx, [2020, 2021], basis="net_disbursement")


def test_only_the_institutions_are_weighted():
    df = pd.DataFrame(
        {
            "donor_code": [EU_INSTITUTIONS_CODE, EU_INSTITUTIONS_CODE, FRANCE],
            "year": [2020, 2021, 2020],
            "value": [100.0, 100.0, 50.0],
        }
    )
    weighted = weight_eu_institutions(df, {2020: 0.5, 2021: 0.25})
    assert weighted["value"].tolist() == [50.0, 25.0, 50.0]
    assert df["value"].tolist() == [100.0, 100.0, 50.0]


def test_an_institutions_row_without_a_weight_raises():
    df = pd.DataFrame(
        {
            "donor_code": [EU_INSTITUTIONS_CODE, US],
            "year": [2025, 2025],
            "value": [1.0, 1.0],
        }
    )
    with pytest.raises(ValueError, match=r"years \[2025\]"):
        weight_eu_institutions(df, {2024: 0.5})
