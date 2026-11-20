"""Tests for the oda-data 3.0 helpers and the transformations built on them."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import oda_data as oda
import pandas as pd
import pytest

from src.data.analysis_tools import oda as oda_tools
from src.data.analysis_tools import transformations
from src.data.analysis_tools.oda import ProvenanceLog, run_query, to_repo_frame
from src.data.analysis_tools.transformations import (
    CRS_REGION_COL,
    add_currencies_and_prices,
    get_crs_recipient_classifications,
)
from src.data.config import logger

DOWNLOADED = datetime(2026, 10, 14, 8, 30, tzinfo=UTC)


def _provenance(
    tables: dict[str, str],
    indicators: dict[str, int],
    reference_data: str = "sha256:abc",
) -> oda.Provenance:
    """Build a Provenance with the given table tokens, indicator and reference versions."""
    return oda.Provenance(
        oda_data="3.0.1",
        indicators=indicators,
        tables={
            t: oda.Release(token=tok, downloaded=DOWNLOADED)
            for t, tok in tables.items()
        },
        pydeflate="2.7.0",
        resolvekit="0.1.13",
        reference_data=reference_data,
        defaults={},
    )


@dataclass
class FakeQuery:
    """Stands in for oda.Query: a fixed result and provenance."""

    result: pd.DataFrame
    provenance: oda.Provenance
    explained: int = 0

    def explain(self) -> str:
        self.explained += 1
        return "Fake query. 2 rows."

    def to_pandas(self) -> pd.DataFrame:
        return self.result


@dataclass
class FakeContext:
    """Stands in for oda.Context, handing out one FakeQuery and keeping the call."""

    query_result: FakeQuery
    calls: list[tuple[str, dict]] = field(default_factory=list)

    def query(self, indicator: str, **kwargs: object) -> FakeQuery:
        self.calls.append((indicator, kwargs))
        return self.query_result


@pytest.fixture
def records(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """Capture the pipeline logger, which does not propagate to the root caplog watches."""
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.INFO)
    yield caplog
    logger.removeHandler(caplog.handler)


def _oda_result() -> pd.DataFrame:
    """A result shaped as oda-data 3.0 returns it: codes as strings, year as Int64."""
    return pd.DataFrame(
        {
            "provider": pd.array(["4", "918"], dtype="string"),
            "provider_name": pd.array(["France", "EU Institutions"], dtype="string"),
            "recipient": pd.array(["238", "9998"], dtype="string"),
            "sector": pd.array(["11110", "12220"], dtype="string"),
            "broad_sector": pd.array(["education", "health"], dtype="string"),
            "year": pd.array([2022, 2023], dtype="Int64"),
            "value": [1.5, 2.5],
        }
    )


def test_run_query_casts_codes_renames_and_records_provenance(records):
    fake = FakeQuery(_oda_result(), _provenance({"crs": "rel-1"}, {"x.y": 1}))
    ctx = FakeContext(fake)
    log = ProvenanceLog()

    out = run_query(ctx, "x.y", provenance=log, years=range(2022, 2024))

    assert ctx.calls == [("x.y", {"years": range(2022, 2024)})]
    assert fake.explained == 1
    assert "Fake query. 2 rows." in records.text
    assert list(out.columns) == [
        "donor_code",
        "donor_name",
        "recipient_code",
        "purpose_code",
        "broad_sector",
        "year",
        "value",
    ]
    for column in ("donor_code", "recipient_code", "purpose_code"):
        assert out[column].dtype == "Int64"
    assert out["year"].dtype == "int64"
    assert out["broad_sector"].tolist() == ["education", "health"]
    assert out["purpose_code"].tolist() == [11110, 12220]
    assert log.tables["crs"].token == "rel-1"
    assert log.indicators == {"x.y": 1}


def test_non_numeric_codes_raise():
    df = pd.DataFrame(
        {"provider": pd.array(["4", "eu"], dtype="string"), "year": [1, 2]}
    )
    with pytest.raises(ValueError, match="non-numeric"):
        to_repo_frame(df)


def test_missing_year_raises():
    df = pd.DataFrame({"year": pd.array([2022, None], dtype="Int64")})
    with pytest.raises(ValueError, match="no year"):
        to_repo_frame(df)


def test_provenance_refuses_a_second_reference_data_version():
    log = ProvenanceLog()
    log.record(_provenance({"crs": "rel-1"}, {}))
    log.record(_provenance({"crs": "rel-1"}, {}))
    assert log.to_dict()["reference_data"] == "sha256:abc"

    with pytest.raises(ValueError, match="Reference data"):
        log.record(_provenance({"crs": "rel-1"}, {}, reference_data="sha256:def"))


def test_provenance_merges_tables_and_refuses_a_second_release():
    log = ProvenanceLog()
    log.record(_provenance({"crs": "rel-1"}, {"a": 1}))
    log.record(_provenance({"crs": "rel-1", "multisystem": "rel-m"}, {"b": 2}))
    log.record_table("dac1", oda.Release(token="dac1-rel", downloaded=DOWNLOADED))

    out = log.to_dict()
    assert set(out["tables"]) == {"crs", "multisystem", "dac1"}
    assert out["tables"]["dac1"] == {
        "token": "dac1-rel",
        "downloaded": "2026-10-14T08:30:00+00:00",
        "label_release": None,
    }
    assert out["indicators"] == {"a": 1, "b": 2}
    assert set(out["libraries"]) == {
        "oda-data",
        "oda-reader",
        "pydeflate",
        "resolvekit",
    }

    with pytest.raises(ValueError, match="two releases"):
        log.record(_provenance({"crs": "rel-2"}, {}))
    with pytest.raises(ValueError, match="two releases"):
        log.record_table("dac1", oda.Release(token="other", downloaded=DOWNLOADED))


def _factors(nan_for: tuple[int, int] | None = None) -> pd.DataFrame:
    """Factors for donors 4 and 918 in 2022-23: EUR current 0.9, EUR constant 0.8."""
    rows = [
        (donor, year, "EUR", price, factor)
        for donor in (4, 918)
        for year in (2022, 2023)
        for price, factor in (("current", 0.9), ("constant", 0.8))
    ]
    factors = pd.DataFrame(
        rows, columns=["donor_code", "year", "currency", "price", "factor"]
    )
    if nan_for is not None:
        donor, year = nan_for
        hit = (factors["donor_code"] == donor) & (factors["year"] == year)
        factors.loc[hit, "factor"] = float("nan")
    return factors


def _usd_frame() -> pd.DataFrame:
    """Long current-USD frame: two donors, two years, one row with no value."""
    return pd.DataFrame(
        {
            "donor_code": pd.array([4, 4, 918, 918], dtype="Int64"),
            "year": [2022, 2023, 2022, 2023],
            "indicator": ["x"] * 4,
            "value": [10.0, 20.0, 30.0, None],
        }
    )


def test_currencies_multiply_by_factors_and_keep_rows(monkeypatch):
    seen = {}

    def fake_factors(**kwargs):
        seen.update(kwargs)
        return _factors()

    monkeypatch.setattr(transformations, "conversion_factors", fake_factors)
    df = _usd_frame()

    out = add_currencies_and_prices(df, base_year=2024)

    assert sorted(seen["entities"].unique()) == [4, 918]
    assert seen["base_year"] == 2024
    assert len(out) == 3 * len(df)
    assert list(out.columns) == [*df.columns, "currency", "price"]
    assert out.groupby(["currency", "price"], sort=False).size().index.tolist() == [
        ("USD", "current"),
        ("EUR", "current"),
        ("EUR", "constant"),
    ]
    eur_constant = out.query("currency == 'EUR' and price == 'constant'")
    assert eur_constant["value"].tolist()[:3] == pytest.approx([8.0, 16.0, 24.0])
    assert pd.isna(eur_constant["value"].iloc[3])
    assert out["donor_code"].dtype == "Int64"


def test_a_value_without_a_factor_raises(monkeypatch):
    monkeypatch.setattr(
        transformations, "conversion_factors", lambda **_: _factors(nan_for=(4, 2023))
    )
    with pytest.raises(ValueError, match=r"No EUR current factor for 1 rows"):
        add_currencies_and_prices(_usd_frame(), base_year=2024)


def test_a_missing_factor_on_a_row_without_value_is_fine(monkeypatch):
    monkeypatch.setattr(
        transformations, "conversion_factors", lambda **_: _factors(nan_for=(918, 2023))
    )
    out = add_currencies_and_prices(_usd_frame(), base_year=2024)
    assert len(out) == 12


@dataclass(frozen=True)
class FakeTable:
    """Stands in for oda_reader.ScannedTable."""

    path: Path
    columns: tuple[str, ...]
    release: str = "dac1-rel"
    label_release: str | None = None
    downloaded: datetime = DOWNLOADED


@dataclass(frozen=True)
class FakeFactorResult:
    """Stands in for pydeflate's DacConversionFactors."""

    factors: pd.DataFrame
    release: str


def test_conversion_factors_log_fallbacks_and_record_dac1(monkeypatch, records):
    calls = []

    def fake_get(dac1, *, entities, years, target_currency, base_year):
        calls.append((target_currency, base_year))
        factors = pd.DataFrame(
            {
                "entity_code": [4, 87],
                "year": [2023, 2023],
                "factor": [0.9, 0.9],
                "fallback": [False, base_year is not None],
            }
        )
        return FakeFactorResult(factors, dac1.release)

    monkeypatch.setattr(
        oda_tools, "scan_table", lambda dataset: FakeTable(Path("dac1.parquet"), ())
    )
    monkeypatch.setattr(
        oda_tools.pydeflate, "get_oecd_dac_conversion_factors", fake_get
    )
    log = ProvenanceLog()

    out = oda_tools.conversion_factors(
        entities=[87, 4, 4],
        years=[2023],
        base_year=2024,
        currencies=["USD", "EUR"],
        provenance=log,
    )

    assert calls == [("USD", 2024), ("EUR", None), ("EUR", 2024)]
    assert list(out.columns) == ["donor_code", "year", "currency", "price", "factor"]
    assert len(out) == 6
    assert "USD constant factors: donor codes [87]" in records.text
    assert "EUR constant factors: donor codes [87]" in records.text
    assert "EUR current factors" not in records.text
    assert log.tables["dac1"].token == "dac1-rel"


def test_conversion_factors_refuse_a_mismatched_release(monkeypatch):
    monkeypatch.setattr(
        oda_tools, "scan_table", lambda dataset: FakeTable(Path("dac1.parquet"), ())
    )
    monkeypatch.setattr(
        oda_tools.pydeflate,
        "get_oecd_dac_conversion_factors",
        lambda dac1, **_: FakeFactorResult(pd.DataFrame(), "another"),
    )
    with pytest.raises(ValueError, match="release"):
        oda_tools.conversion_factors(entities=[4], years=[2023], base_year=2024)


def test_a_scanned_table_release_is_recorded_like_a_query_one():
    table = FakeTable(Path("dac2a.parquet"), (), release="dac2a-rel")
    log = ProvenanceLog()
    log.record_table("dac2a", oda_tools.scanned_release(table))
    log.record(_provenance({"dac2a": "dac2a-rel"}, {}))

    assert log.to_dict()["tables"]["dac2a"]["token"] == "dac2a-rel"
    with pytest.raises(ValueError, match="two releases"):
        log.record(_provenance({"dac2a": "other"}, {}))


_CRS_COLUMNS = (
    "year",
    "recipient_code",
    "recipient_name",
    "de_recipientcode",
    "region_name",
)


def _crs_rows() -> pd.DataFrame:
    """CRS transactions exercising the modal reduction.

    Ethiopia (238) 2022: region Africa (2 raw "Africa" + 2 "Africa, regional", folded) beats
    South of Sahara (3), and one name is blank. 2023: a 1-1 tie between South of Sahara
    and Middle East goes to the value that sorts first. Recipient 1 has no region at all.
    Recipient 2 is outside the requested recipients.
    """
    rows = [
        *[(2022, 238, "Ethiopia", "ETH", "Africa")] * 2,
        *[(2022, 238, "Ethiopia", "ETH", "Africa, regional")] * 2,
        *[(2022, 238, None, "ETH", "South of Sahara")] * 3,
        (2023, 238, "Ethiopia", "ETH", "South of Sahara"),
        (2023, 238, "Ethiopia", "ETH", "Middle East"),
        (2022, 1, "Somewhere", None, None),
        (2022, 2, "Elsewhere", None, "Asia"),
        (2021, 238, "Ethiopia", "ETH", "Asia"),
    ]
    return pd.DataFrame(rows, columns=list(_CRS_COLUMNS))


def _use_crs(monkeypatch, tmp_path: Path, rows: pd.DataFrame) -> None:
    """Point the classification reader at a parquet file of the given rows."""
    path = tmp_path / "crs.parquet"
    rows.to_parquet(path)
    monkeypatch.setattr(
        transformations,
        "scan_table",
        lambda dataset: FakeTable(path, tuple(rows.columns)),
    )


def test_classifications_take_the_modal_value_per_recipient_year(
    monkeypatch, tmp_path, records
):
    _use_crs(monkeypatch, tmp_path, _crs_rows())

    classified, ldcs = get_crs_recipient_classifications(range(2022, 2024), [238, 1])

    assert classified[["recipient_code", "year"]].values.tolist() == [
        [1, 2022],
        [238, 2022],
        [238, 2023],
    ]
    ethiopia = classified.set_index(["recipient_code", "year"]).loc[238]
    assert ethiopia.loc[2022, CRS_REGION_COL] == "Africa"
    assert ethiopia.loc[2023, CRS_REGION_COL] == "Middle East"
    assert ethiopia.loc[2022, "recipient_name"] == "Ethiopia"
    assert pd.isna(classified.set_index("recipient_code").loc[1, CRS_REGION_COL])
    assert ldcs == {238: "Ethiopia"}
    assert "report more than one recipient_region" in records.text
    assert list(classified.columns) == [
        "recipient_code",
        "year",
        "recipient_name",
        CRS_REGION_COL,
        "income_group",
    ]


def test_classifications_raise_on_a_missing_column(monkeypatch, tmp_path):
    _use_crs(monkeypatch, tmp_path, _crs_rows().drop(columns="region_name"))
    with pytest.raises(ValueError, match="region_name"):
        get_crs_recipient_classifications(2022)
