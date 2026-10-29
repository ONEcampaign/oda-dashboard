"""Tests for the recipients and gender views' data handling."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from src.data.analysis_tools import recipients
from src.data.analysis_tools.gender import derive_not_screened
from src.data.analysis_tools.oda import ProvenanceLog
from src.data.analysis_tools.recipients import (
    aggregate_recipient_names,
    canonical_recipients,
    check_recipient_sums,
    read_dac2a_part_i,
)
from src.data.config import (
    DAC2A_API_ONLY_RECIPIENTS,
    DAC2A_LDC_CODE,
    DAC2A_RECIPIENT_AGGREGATES,
    DAC2A_RECIPIENTS,
    EXCLUDED_DAC2A_RECIPIENTS,
    LDC_LABEL,
    RECIPIENTS_ORDER,
)
from src.data.validation.views import DAC2A_RECIPIENT_GROUPS


def dac2a(rows: list[tuple[int | None, str]]) -> pd.DataFrame:
    """Build DAC2A rows from (recipient_code, recipient_name)."""
    return pd.DataFrame(rows, columns=["recipient_code", "recipient_name"]).astype(
        {"recipient_code": "Int64"}
    )


def test_canonical_recipients_keep_the_views_display_names():
    df = dac2a(
        [
            (248, "Kenya"),
            (10_100, "Developing Countries, Total"),
            (10_001, "Africa, Total"),
            (247, "Cote d'Ivoire"),
            (679, "South Asia, regional"),
            (1028, "Middle Africa, regional"),
        ]
    )
    assert canonical_recipients(df)["recipient_name"].tolist() == [
        "Kenya",
        "ODA eligible countries",
        "Africa",
        "C\u00f4te d\u2019Ivoire",
        "Southern Asia, unspecified",
        "Middle Africa, unspecified",
    ]


def test_canonical_recipients_raises_on_a_missing_code():
    with pytest.raises(ValueError, match="without a recipient code"):
        canonical_recipients(dac2a([(248, "Kenya"), (None, "Indus Basin")]))


def test_canonical_recipients_raises_when_two_codes_share_a_name():
    with pytest.raises(ValueError, match="shared by more than one code"):
        canonical_recipients(dac2a([(248, "Kenya"), (249, "Kenya")]))


def test_aggregate_recipient_names_are_the_pinned_groups_in_the_data():
    df = canonical_recipients(
        dac2a([(10_001, "Africa, Total"), (298, "Africa, regional"), (248, "Kenya")])
    )
    assert aggregate_recipient_names(df) == ["Africa"]


def test_recipient_list_uses_bulk_codes_and_no_excluded_recipient():
    assert not DAC2A_RECIPIENTS & EXCLUDED_DAC2A_RECIPIENTS
    assert not DAC2A_RECIPIENTS & DAC2A_API_ONLY_RECIPIENTS.keys()
    assert set(DAC2A_API_ONLY_RECIPIENTS.values()) <= DAC2A_RECIPIENTS
    assert set(RECIPIENTS_ORDER) - {LDC_LABEL} <= set(
        DAC2A_RECIPIENT_AGGREGATES.values()
    )
    assert DAC2A_LDC_CODE not in DAC2A_RECIPIENTS
    assert len(set(DAC2A_RECIPIENT_AGGREGATES.values())) == len(
        DAC2A_RECIPIENT_AGGREGATES
    )


def test_validation_knows_every_pinned_group():
    pinned = set(DAC2A_RECIPIENT_AGGREGATES.values()) - set(RECIPIENTS_ORDER)
    assert pinned == DAC2A_RECIPIENT_GROUPS


def _sums(rows: list[tuple[int, float]]) -> pd.DataFrame:
    """One donor-year of rows from (recipient_code, value)."""
    return pd.DataFrame(rows, columns=["recipient_code", "value"]).assign(
        donor_code=4, year=2023, indicator_name="Bilateral"
    )


def test_countries_may_fall_short_of_the_total():
    # 10001 is a group and is left out of the countries' sum.
    check_recipient_sums(_sums([(248, 2.0), (249, 3.0), (10_001, 9.0), (10_100, 6.0)]))


def test_countries_above_the_total_raise():
    with pytest.raises(ValueError, match="1 donor-years"):
        check_recipient_sums(_sums([(248, 2.0), (249, 3.0), (10_100, 4.0)]))


DOWNLOADED = datetime(2026, 10, 29, 13, 42, tzinfo=UTC)


@dataclass(frozen=True)
class FakeTable:
    """Stands in for oda_reader.ScannedTable."""

    path: Path
    columns: tuple[str, ...]
    release: str = "dac2a-rel"
    label_release: str | None = None
    downloaded: datetime = DOWNLOADED


def _raw_dac2a() -> pd.DataFrame:
    """Raw DAC2A rows: France (4) to Kenya (248) in 2023, with rows the read must skip."""
    rows = [
        # part, aid type, data type, year, value
        (1, 206, "A", 2023, 10.0),
        (1, 206, "A", 2023, 5.0),  # summed with the row above
        (1, 106, "A", 2023, 3.0),
        (2, 206, "A", 2023, 100.0),  # Part II
        (1, 206, "D", 2023, 50.0),  # constant prices
        (1, 240, "A", 2023, 70.0),  # gross disbursements
        (1, 206, "A", 2015, 7.0),  # outside the years
    ]
    return pd.DataFrame(
        [
            {
                "recipient_code": 248,
                "recipient_name": "Kenya",
                "donor_code": 4,
                "donor_name": "France",
                "part_code": part,
                "aidtype_code": line,
                "data_type_code": data_type,
                "year": year,
                "value": value,
            }
            for part, line, data_type, year, value in rows
        ]
    ).astype({"recipient_code": "int32", "donor_code": "int32", "year": "int32"})


def test_dac2a_read_keeps_part_i_current_prices_and_records_the_release(
    monkeypatch, tmp_path
):
    path = tmp_path / "dac2a.parquet"
    raw = _raw_dac2a()
    raw.to_parquet(path)
    monkeypatch.setattr(
        recipients, "scan_table", lambda dataset: FakeTable(path, tuple(raw.columns))
    )
    log = ProvenanceLog()

    out = read_dac2a_part_i(
        lines={206: "Bilateral", 106: "Imputed multilateral"},
        years=[2022, 2023],
        providers=[4],
        recipients=[248],
        provenance=log,
    ).set_index("indicator_name")

    assert out["value"].to_dict() == {"Bilateral": 15.0, "Imputed multilateral": 3.0}
    assert set(out["donor_code"]) == {4}
    assert set(out["recipient_code"]) == {248}
    assert set(out["donor_name"]) == {"France"}
    assert log.tables["dac2a"].token == "dac2a-rel"


def test_dac2a_read_raises_on_a_missing_column(monkeypatch, tmp_path):
    monkeypatch.setattr(
        recipients,
        "scan_table",
        lambda dataset: FakeTable(tmp_path / "x.parquet", ("donor_code", "value")),
    )
    with pytest.raises(ValueError, match="part_code"):
        read_dac2a_part_i(
            lines={206: "Bilateral"}, years=[2023], providers=[4], recipients=[248]
        )


def test_not_screened_is_allocable_minus_screened():
    index = pd.MultiIndex.from_tuples(
        [(2023, 302), (2023, 4)], names=["year", "donor_code"]
    )
    scores = {
        "principal": pd.Series([1.0, 2.0], index=index),
        "significant": pd.Series([3.0, 0.0], index=index),
        "not_targeted": pd.Series([6.0, 1.0], index=index),
    }
    allocable = pd.Series([10.0, 8.0], index=index)
    out = derive_not_screened(scores, allocable).set_index(
        ["donor_code", "indicator_name"]
    )
    assert out.loc[(302, "Not screened"), "value"] == 0.0
    assert out.loc[(4, "Not screened"), "value"] == 5.0
    assert out.groupby(level="donor_code")["value"].sum().to_dict() == {
        4: 8.0,
        302: 10.0,
    }


def test_not_screened_rejects_screened_rows_outside_the_allocable_total():
    index = pd.MultiIndex.from_tuples([(2023, 302)], names=["year", "donor_code"])
    other = pd.MultiIndex.from_tuples([(2023, 4)], names=["year", "donor_code"])
    scores = {"principal": pd.Series([1.0], index=other)}
    with pytest.raises(ValueError, match="outside the allocable total"):
        derive_not_screened(scores, pd.Series([1.0], index=index))


def test_ldc_members_come_from_the_crs_classification_and_record_its_release(
    monkeypatch,
):
    calls = []

    def fake_classifications(years, recipients):
        calls.append((years, recipients))
        return pd.DataFrame(), {248: "Kenya"} if 248 in recipients else {}

    monkeypatch.setattr(
        recipients, "get_crs_recipient_classifications", fake_classifications
    )
    monkeypatch.setattr(
        recipients,
        "scan_table",
        lambda dataset: FakeTable(Path("crs.parquet"), (), release="crs-rel"),
    )
    log = ProvenanceLog()

    members = recipients.read_ldc_members(
        years=[2023, 2022], recipients=[248, 248, 30], provenance=log
    )

    assert members == {248: "Kenya"}
    assert calls == [([2022, 2023], [30, 248])]
    assert log.tables["crs"].token == "crs-rel"
    with pytest.raises(ValueError, match="No recipient"):
        recipients.read_ldc_members(years=[2023], recipients=[30])
