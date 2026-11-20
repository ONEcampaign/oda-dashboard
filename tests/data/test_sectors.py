"""Tests for the sectors view: the oda.sectors lookup, the imputed read and the EU bloc."""

from dataclasses import dataclass, field

import oda_data as oda
import pandas as pd
import pyarrow as pa
import pytest

from src.data.analysis_tools import sectors
from src.data.analysis_tools.imputations import iter_imputed_multilateral
from src.data.analysis_tools.oda import ProvenanceLog
from src.data.analysis_tools.sectors import assign_sub_sector, sector_lookup
from src.data.config import (
    EUI_CHANNEL_CODES,
    UNALLOCATED_SUB_SECTOR,
    UNSPECIFIED_RECIPIENT_CODE,
)
from src.data.scripts.sectors_view import get_eu27_eui_imputed

FRANCE, GERMANY, NORWAY, EU_INSTITUTIONS = 4, 5, 8, 918
KENYA = 248


def test_lookup_names_the_dashboards_seventy_sub_sectors():
    purpose_to_sub_sector, sub_sector_to_sector = sector_lookup()
    assert len(set(purpose_to_sub_sector.values())) == 70
    assert set(purpose_to_sub_sector.values()) == set(sub_sector_to_sector)


@pytest.mark.parametrize(
    ("code", "sub_sector", "sector"),
    [
        (11220, "Basic Education", "Education"),
        (15113, "Anti-corruption organisations and institutions", "Civil society"),
        (14010, "Water Supply & Sanitation", "Water Supply & Sanitation"),
        # Only in the broad Multi-sector group, so named by BROAD_ONLY_SUB_SECTORS.
        (43010, "Multi-Sector", "Multi-sector"),
        # A row reported at a DAC5 heading, with no finer purpose code.
        (998, UNALLOCATED_SUB_SECTOR, UNALLOCATED_SUB_SECTOR),
    ],
)
def test_lookup_maps_purpose_codes_to_sub_sector_and_sector(code, sub_sector, sector):
    purpose_to_sub_sector, sub_sector_to_sector = sector_lookup()
    assert purpose_to_sub_sector[code] == sub_sector
    assert sub_sector_to_sector[sub_sector] == sector


def test_lookup_refuses_groups_that_do_not_nest(monkeypatch):
    groups = {
        "a": oda.SectorGroup(name="a", label="A", members=(11110, 11120)),
        "b": oda.SectorGroup(name="b", label="B", members=(11120, 11130)),
    }

    class Namespace:
        @staticmethod
        def values():
            return groups.values()

    sector_lookup.cache_clear()
    monkeypatch.setattr(sectors.oda, "sectors", Namespace())
    try:
        with pytest.raises(ValueError, match="do not nest"):
            sector_lookup()
    finally:
        sector_lookup.cache_clear()


def test_missing_or_unknown_purpose_codes_are_unallocated():
    df = pd.DataFrame(
        {"purpose_code": pd.array([11220, None, 1], dtype="Int64"), "value": 1.0}
    )
    assert assign_sub_sector(df)["sub_sector"].tolist() == [
        "Basic Education",
        UNALLOCATED_SUB_SECTOR,
        UNALLOCATED_SUB_SECTOR,
    ]


def test_eu_bloc_drops_member_contributions_through_eu_channels():
    eu_channel = min(EUI_CHANNEL_CODES)
    raw = pd.DataFrame(
        {
            "year": 2023,
            "donor_code": [FRANCE, FRANCE, EU_INSTITUTIONS, NORWAY],
            "recipient_code": KENYA,
            "channel_code": [eu_channel, 44000, eu_channel, 44000],
            "sub_sector": "Basic Education",
            "value": [10.0, 3.0, 7.0, 5.0],
        }
    )
    bloc = get_eu27_eui_imputed(raw).set_index("donor_code")["value"]
    # France keeps only its non-EU channel; the institutions keep everything; Norway is out.
    assert bloc.to_dict() == {FRANCE: 3.0, EU_INSTITUTIONS: 7.0}


@dataclass
class FakeQuery:
    """Stands in for oda.Query, returning one year's rows as Arrow."""

    table: pa.Table

    def explain(self) -> str:
        return "Fake imputed query."

    @property
    def provenance(self) -> oda.Provenance:
        return oda.Provenance(
            oda_data="3.0.1",
            indicators={"one.crs.imputed_multilateral_oda": 1},
            tables={},
            pydeflate="2.7.0",
            resolvekit="0.1.13",
            reference_data="sha256:abc",
            defaults={},
        )

    def to_arrow(self) -> pa.Table:
        return self.table


@dataclass
class FakeContext:
    """Stands in for oda.Context: one query per year, keeping each call."""

    calls: list[dict] = field(default_factory=list)

    def query(self, indicator: str, **kwargs: object) -> FakeQuery:
        self.calls.append(kwargs)
        (year,) = kwargs["years"]
        return FakeQuery(
            pa.table(
                {
                    "provider": [str(GERMANY), str(GERMANY)],
                    "provider_name": ["Germany", "Germany"],
                    "recipient": [str(KENYA), None],
                    "sector": ["11220", None],
                    "channel": ["44000", "44000"],
                    "year": [year, year],
                    "value": [1.0, 2.0],
                }
            )
        )


def test_imputed_is_read_one_year_at_a_time_with_no_recipient_filter():
    ctx = FakeContext()
    frames = list(
        iter_imputed_multilateral(
            ctx, years=[2022, 2023], providers=[GERMANY], provenance=ProvenanceLog()
        )
    )

    assert [call["years"] for call in ctx.calls] == [[2022], [2023]]
    assert all("recipients" not in call for call in ctx.calls)
    assert [frame["year"].unique().tolist() for frame in frames] == [[2022], [2023]]
    # Money with no recipient goes to the unspecified code, and only the needed columns
    # are kept, under the repo's names.
    assert frames[0]["recipient_code"].tolist() == [KENYA, UNSPECIFIED_RECIPIENT_CODE]
    assert list(frames[0].columns) == [
        "donor_code",
        "recipient_code",
        "purpose_code",
        "channel_code",
        "year",
        "value",
    ]


def test_imputed_recipients_outside_the_crs_list_raise():
    class OutsideContext(FakeContext):
        def query(self, indicator: str, **kwargs: object) -> FakeQuery:
            q = super().query(indicator, **kwargs)
            return FakeQuery(q.table.set_column(2, "recipient", pa.array(["1", "1"])))

    with pytest.raises(ValueError, match="outside CRS_RECIPIENTS"):
        next(iter_imputed_multilateral(OutsideContext(), years=[2023], providers=[5]))
