"""Tests for validation data models."""

import pytest
from validation.models import CheckResult, Warning, ValidationReport


class TestCheckResult:
    def test_passed_check(self):
        result = CheckResult(passed=True)
        assert result.passed is True
        assert result.errors == []

    def test_failed_check_with_errors(self):
        result = CheckResult(passed=False, errors=["Missing column: year"])
        assert result.passed is False
        assert "Missing column: year" in result.errors

    def test_combine_all_passed(self):
        r1 = CheckResult(passed=True)
        r2 = CheckResult(passed=True)
        combined = CheckResult.combine([r1, r2])
        assert combined.passed is True
        assert combined.errors == []

    def test_combine_one_failed(self):
        r1 = CheckResult(passed=True)
        r2 = CheckResult(passed=False, errors=["Error 1"])
        combined = CheckResult.combine([r1, r2])
        assert combined.passed is False
        assert "Error 1" in combined.errors


class TestWarning:
    def test_warning_creation(self):
        w = Warning(
            level="high",
            dataset="financing_view",
            message="Germany: 2024 change is +28%"
        )
        assert w.level == "high"
        assert w.dataset == "financing_view"
        assert "Germany" in w.message


class TestValidationReport:
    def test_empty_report(self):
        report = ValidationReport(release="dec_2024")
        assert report.has_blocking_errors is False
        assert len(report.warnings) == 0

    def test_report_with_blocking_errors(self):
        result = CheckResult(passed=False, errors=["Schema mismatch"])
        report = ValidationReport(release="dec_2024")
        report.add_check_result("financing_view", "schema", result)
        assert report.has_blocking_errors is True

    def test_report_with_warnings(self):
        report = ValidationReport(release="dec_2024")
        report.add_warning(Warning(
            level="high",
            dataset="financing_view",
            message="Test warning"
        ))
        assert len(report.warnings) == 1
        assert report.has_blocking_errors is False
