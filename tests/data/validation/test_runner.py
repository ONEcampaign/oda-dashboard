"""Tests for the runner: orchestration, load failures and the parity and cross-view gates."""

from pathlib import Path

import pytest

from src.data.validation import runner
from src.data.validation.models import CheckResult, Severity
from src.data.validation.runner import (
    ANOMALY_PARTITION,
    run_validation,
    run_view,
    run_view_parity,
    source_roots,
)
from src.data.validation.views import VIEWS
from tests.data.validation.conftest import write_flat


def ok(check: str, view: str = "financing_view") -> CheckResult:
    """A passing result."""
    return CheckResult(check, view, True, Severity.ERROR, "ok")


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stub every check family, recording the order they run in."""
    log: list[str] = []

    def record(name: str, family: str):
        def stub(*args, **kwargs) -> list[CheckResult]:
            log.append(f"{family}:{name(args)}")
            return [ok(f"{family}.stub", name(args))]

        return stub

    monkeypatch.setattr(runner, "run_view", record(lambda a: a[0], "view"))
    monkeypatch.setattr(runner, "run_view_parity", record(lambda a: a[0], "parity"))
    monkeypatch.setattr(
        runner, "run_cross_view", record(lambda a: "cross_view", "cross")
    )
    return log


def test_source_roots_maps_views_under_the_root() -> None:
    assert source_roots(Path("/r"), ["a", "b"]) == {
        "a": Path("/r/a"),
        "b": Path("/r/b"),
    }


def test_run_validation_runs_each_family_in_order(calls: list[str]) -> None:
    sources = {name: Path("/s") / name for name in VIEWS}

    results = run_validation(
        ["financing_view", "gender_view"],
        sources,
        baseline_sources=source_roots(Path("/b"), VIEWS),
        expected=[],
        cross_view=True,
    )

    assert calls == [
        "view:financing_view",
        "parity:financing_view",
        "view:gender_view",
        "parity:gender_view",
        "cross:cross_view",
    ]
    assert len(results) == 5


def test_run_validation_skips_parity_without_baseline_and_cross_view_when_off(
    calls: list[str],
) -> None:
    sources = {name: Path("/s") / name for name in VIEWS}

    run_validation(
        ["financing_view"],
        sources,
        baseline_sources=None,
        expected=[],
        cross_view=False,
    )

    assert calls == ["view:financing_view"]


def test_run_view_reports_a_missing_view_as_a_blocking_error(tmp_path: Path) -> None:
    results = run_view("financing_view", tmp_path / "nowhere")

    assert len(results) == 1
    assert results[0].check == "contracts.load"
    assert not results[0].passed
    assert results[0].severity is Severity.ERROR
    assert results[0].blocking
    assert "FileNotFoundError" in results[0].message


def test_run_view_parity_failure_is_non_blocking(tmp_path: Path) -> None:
    results = run_view_parity("financing_view", tmp_path / "a", tmp_path / "b", [])

    assert [r.check for r in results] == ["parity.load"]
    assert not results[0].passed
    assert not results[0].blocking


def test_run_view_runs_all_families_on_a_flat_view(
    monkeypatch: pytest.MonkeyPatch, make_view
) -> None:
    view = make_view(
        "financing_view",
        [
            {
                "year": 2024,
                "donor_name": "France",
                "indicator_name": "Total ODA",
                "type": "Flows",
            }
        ],
    )
    monkeypatch.setattr(runner, "load_view", lambda name, source: view)
    monkeypatch.setattr(runner, "run_contracts", lambda v: [ok("contracts.x")])
    monkeypatch.setattr(runner, "run_invariants", lambda parts: [ok("invariants.x")])
    monkeypatch.setattr(runner, "run_anomalies", lambda v: [ok("anomalies.x")])

    results = run_view("financing_view", Path("/unused"))

    assert [r.check for r in results] == ["contracts.x", "invariants.x", "anomalies.x"]


def test_run_view_streams_partitions_and_checks_anomalies_on_one(
    monkeypatch: pytest.MonkeyPatch, make_view
) -> None:
    rows = [
        {
            "year": 2024,
            "donor_name": "France",
            "recipient_name": "Kenya",
            "indicator_name": "Bilateral",
            "sector_name": "Health",
            "sub_sector_name": "Basic Health",
        }
    ]
    view = make_view("sectors_view", rows)
    partitions = [("kenya", view), (ANOMALY_PARTITION, view)]
    seen_by_invariants: list[object] = []
    seen_by_anomalies: list[object] = []

    def invariants(parts) -> list[CheckResult]:
        seen_by_invariants.extend(parts)  # consumes the stream, as the real check does
        return [ok("invariants.x", "sectors_view")]

    def anomalies(v) -> list[CheckResult]:
        seen_by_anomalies.append(v)
        return [ok("anomalies.x", "sectors_view")]

    monkeypatch.setattr(runner, "load_view", lambda name, source: view)
    monkeypatch.setattr(
        runner, "iter_partitions", lambda name, source: iter(partitions)
    )
    monkeypatch.setattr(runner, "run_contracts", lambda v: [ok("contracts.x")])
    monkeypatch.setattr(runner, "run_invariants", invariants)
    monkeypatch.setattr(runner, "run_anomalies", anomalies)

    results = run_view("sectors_view", Path("/unused"))

    assert [r.check for r in results] == ["contracts.x", "invariants.x", "anomalies.x"]
    assert len(seen_by_invariants) == 2
    assert seen_by_anomalies == [view]


def test_run_view_warns_when_the_anomaly_partition_is_missing(
    monkeypatch: pytest.MonkeyPatch, make_view
) -> None:
    view = make_view(
        "sectors_view",
        [
            {
                "year": 2024,
                "donor_name": "France",
                "recipient_name": "Kenya",
                "indicator_name": "Bilateral",
                "sector_name": "Health",
                "sub_sector_name": "Basic Health",
            }
        ],
    )
    monkeypatch.setattr(runner, "load_view", lambda name, source: view)
    monkeypatch.setattr(
        runner, "iter_partitions", lambda name, source: iter([("kenya", view)])
    )
    monkeypatch.setattr(runner, "run_contracts", lambda v: [])
    monkeypatch.setattr(runner, "run_invariants", lambda parts: list(parts) and [])

    results = run_view("sectors_view", Path("/unused"))

    assert [r.check for r in results] == ["anomalies.partition"]
    assert results[0].severity is Severity.WARNING
    assert not results[0].passed


def test_run_view_reports_a_missing_column_as_a_contract_error(
    tmp_path: Path, make_view
) -> None:
    view = make_view(
        "financing_view",
        [
            {
                "year": 2024,
                "donor_name": "France",
                "indicator_name": "Total ODA",
                "type": "Flows",
                "value_usd_current": 1_000_000,
            }
        ],
    )
    view.data = view.data.drop(columns="value_usd_constant")
    source = write_flat(view, tmp_path / "financing_view")

    results = run_view("financing_view", source)

    assert [r.check for r in results] == ["contracts.non_empty", "contracts.columns"]
    columns = results[1]
    assert not columns.passed
    assert columns.severity is Severity.ERROR
    assert "value_usd_constant" in columns.message


def test_run_view_lets_a_check_error_propagate(
    monkeypatch: pytest.MonkeyPatch, make_view
) -> None:
    view = make_view(
        "financing_view",
        [
            {
                "year": 2024,
                "donor_name": "France",
                "indicator_name": "Total ODA",
                "type": "Flows",
            }
        ],
    )

    def broken(parts) -> list[CheckResult]:
        raise KeyError("bug in a check")

    monkeypatch.setattr(runner, "load_view", lambda name, source: view)
    monkeypatch.setattr(runner, "run_contracts", lambda v: [])
    monkeypatch.setattr(runner, "run_invariants", broken)

    with pytest.raises(KeyError, match="bug in a check"):
        run_view("financing_view", Path("/unused"))
