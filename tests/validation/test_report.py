"""Tests for report generation."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from validation.models import CheckResult, Warning, ValidationReport
from validation.report import generate_report_markdown, save_report


class TestGenerateReportMarkdown:
    def test_generates_header(self):
        report = ValidationReport(release="dec_2024")
        md = generate_report_markdown(report)
        assert "dec_2024" in md
        assert "Data Validation Report" in md

    def test_shows_passed_checks(self):
        report = ValidationReport(release="dec_2024")
        report.add_check_result("financing_view", "schema", CheckResult(passed=True))
        report.add_check_result("financing_view", "not_empty", CheckResult(passed=True))
        md = generate_report_markdown(report)
        assert "PASSED" in md
        assert "schema" in md.lower()

    def test_shows_failed_checks(self):
        report = ValidationReport(release="dec_2024")
        report.add_check_result(
            "financing_view",
            "schema",
            CheckResult(passed=False, errors=["Missing column: year"])
        )
        md = generate_report_markdown(report)
        assert "FAILED" in md or "BLOCKED" in md
        assert "Missing column: year" in md

    def test_shows_warnings_by_level(self):
        report = ValidationReport(release="dec_2024")
        report.add_warning(Warning(level="high", dataset="financing_view", message="High priority issue"))
        report.add_warning(Warning(level="medium", dataset="financing_view", message="Medium priority issue"))
        report.add_warning(Warning(level="info", dataset="financing_view", message="Info message"))

        md = generate_report_markdown(report)
        assert "High Priority" in md
        assert "Medium Priority" in md
        assert "High priority issue" in md


class TestSaveReport:
    def test_saves_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = ValidationReport(release="dec_2024")
            report.add_check_result("test", "schema", CheckResult(passed=True))

            path = Path(tmpdir) / "reports"
            save_report(report, path)

            # Check file was created
            files = list(path.glob("*.md"))
            assert len(files) == 1
            assert "dec_2024" in files[0].name
