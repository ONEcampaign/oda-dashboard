"""Tests for the report: outcome classification, the summary and the markdown."""

import re
from pathlib import Path

import pandas as pd
import pytest

from src.data.validation.models import CheckResult, Severity
from src.data.validation.report import (
    REPORT_DETAIL_ROWS,
    Outcome,
    check_family,
    classify,
    count_outcomes,
    is_blocking,
    markdown_table,
    render_markdown,
    summarize,
    write_report,
)


def result(
    check: str = "contracts.keys",
    view: str = "financing_view",
    *,
    passed: bool = False,
    severity: Severity = Severity.ERROR,
    blocking: bool = True,
    details: pd.DataFrame | None = None,
) -> CheckResult:
    """A CheckResult with a message derived from the check name."""
    return CheckResult(
        check=check,
        view=view,
        passed=passed,
        severity=severity,
        message=f"message of {check}",
        details=details,
        blocking=blocking,
    )


@pytest.mark.parametrize(
    ("passed", "severity", "expected"),
    [
        (True, Severity.ERROR, Outcome.PASS),
        (True, Severity.INFO, Outcome.PASS),
        (False, Severity.INFO, Outcome.EXPLAINED),
        (False, Severity.WARNING, Outcome.WARNING),
        (False, Severity.ERROR, Outcome.ERROR),
    ],
)
def test_classify(passed: bool, severity: Severity, expected: Outcome) -> None:
    assert classify(result(passed=passed, severity=severity)) is expected


@pytest.mark.parametrize(
    ("kwargs", "strict", "expected"),
    [
        ({"blocking": True}, False, True),
        ({"blocking": False}, False, False),
        ({"blocking": False}, True, True),
        ({"passed": True}, True, False),
        ({"severity": Severity.WARNING}, True, False),
        ({"severity": Severity.INFO, "blocking": False}, True, False),
    ],
)
def test_is_blocking(kwargs: dict, strict: bool, expected: bool) -> None:
    assert is_blocking(result(**kwargs), strict=strict) is expected


def test_check_family_is_the_prefix() -> None:
    assert check_family(result("cross_view.total_oda")) == "cross_view"
    assert check_family(result("nodots")) == "other"


def test_summarize_counts_per_view_and_family() -> None:
    results = [
        result("contracts.a", passed=True),
        result("contracts.b", passed=True),
        result("contracts.c"),
        result("parity.x", severity=Severity.INFO),
        result("parity.y", view="gender_view", severity=Severity.WARNING),
    ]

    summary = summarize(results).set_index(["view", "family"])

    assert summary.loc[("financing_view", "contracts")].to_dict() == {
        "pass": 2,
        "explained": 0,
        "warning": 0,
        "error": 1,
    }
    assert summary.loc[("financing_view", "parity"), "explained"] == 1
    assert summary.loc[("gender_view", "parity"), "warning"] == 1


def test_summarize_empty_keeps_columns() -> None:
    assert list(summarize([]).columns) == [
        "view",
        "family",
        "pass",
        "explained",
        "warning",
        "error",
    ]


def test_count_outcomes() -> None:
    counts = count_outcomes([result(passed=True), result(), result()])

    assert counts[Outcome.PASS] == 1
    assert counts[Outcome.ERROR] == 2
    assert counts[Outcome.WARNING] == 0


def test_markdown_table_cuts_long_frames_and_escapes_pipes() -> None:
    frame = pd.DataFrame({"name": ["a|b"] * 30, "value": [1234.5678] * 30})

    table = markdown_table(frame)

    assert "a\\|b" in table
    assert "1,234.57" in table
    assert f"Showing {REPORT_DETAIL_ROWS} of 30 rows" in table
    assert table.count("a\\|b") == REPORT_DETAIL_ROWS


def render(results: list[CheckResult], *, strict: bool = False) -> str:
    return render_markdown(
        results,
        title="Title",
        sources={"financing_view": Path("/build/financing_view")},
        strict=strict,
    )


def test_render_sections_follow_the_outcomes() -> None:
    markdown = render(
        [
            result("contracts.ok", passed=True),
            result("contracts.blocked"),
            result("parity.soft", blocking=False),
            result("parity.known", severity=Severity.INFO, blocking=False),
            result("anomalies.yoy", severity=Severity.WARNING),
        ]
    )

    assert markdown.startswith("# Title")
    assert "**FAILED**: 1 blocking" in markdown
    assert "## Blocking failures (1)" in markdown
    assert "## Non-blocking errors (1)" in markdown
    assert "## Explained (1)" in markdown
    assert "## Warnings (1)" in markdown
    assert "`/build/financing_view`" in markdown
    blocked = markdown.index("### `contracts.blocked`")
    soft = markdown.index("### `parity.soft`")
    assert blocked < soft < markdown.index("### `parity.known`")
    assert "contracts.ok" not in markdown  # passes show only in the summary counts


def test_render_strict_makes_non_blocking_errors_block() -> None:
    results = [result("parity.soft", blocking=False)]

    assert "**PASSED**" in render(results)
    strict = render(results, strict=True)
    assert "**FAILED**: 1 blocking" in strict
    assert "## Non-blocking errors" not in strict


def test_render_details_are_capped() -> None:
    details = pd.DataFrame({"year": range(50), "value": [1.0] * 50})

    markdown = render([result(details=details)])

    rows = re.findall(r"^\| \d+ \|", markdown, flags=re.MULTILINE)
    assert len(rows) == REPORT_DETAIL_ROWS
    assert "Showing 20 of 50 rows" in markdown


def test_render_all_passing_has_only_the_summary() -> None:
    markdown = render([result(passed=True)])

    assert "**PASSED**: 0 blocking" in markdown
    assert "## Summary" in markdown
    assert "## Blocking failures" not in markdown


def test_write_report_names_the_file_by_utc_timestamp(tmp_path: Path) -> None:
    path = write_report("# body\n", tmp_path / "reports")

    assert path.parent == tmp_path / "reports"
    assert re.fullmatch(r"validation_\d{8}T\d{6}Z\.md", path.name)
    assert path.read_text() == "# body\n"
