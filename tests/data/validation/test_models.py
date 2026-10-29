"""Tests for CheckResult and Severity."""

import pandas as pd
import pytest

from src.data.validation.models import MAX_DETAIL_ROWS, CheckResult, Severity


def _result(**overrides: object) -> CheckResult:
    """A passing result, with fields overridden."""
    fields: dict = {
        "check": "contracts.unique_keys",
        "view": "financing_view",
        "passed": True,
        "severity": Severity.ERROR,
        "message": "ok",
    } | overrides
    return CheckResult(**fields)


def test_defaults_are_blocking_without_details() -> None:
    """A result blocks by default and carries no details."""
    result = _result()
    assert result.blocking is True
    assert result.details is None


def test_details_are_truncated() -> None:
    """Details longer than MAX_DETAIL_ROWS are cut to it."""
    details = pd.DataFrame({"x": range(MAX_DETAIL_ROWS + 10)})
    result = _result(passed=False, details=details)
    assert result.details is not None
    assert len(result.details) == MAX_DETAIL_ROWS


def test_short_details_kept_whole() -> None:
    """Details within the cap are kept as given."""
    details = pd.DataFrame({"x": range(3)})
    assert _result(details=details).details is details


def test_severity_must_be_enum() -> None:
    """A bare string severity is rejected."""
    with pytest.raises(TypeError, match="Severity"):
        _result(severity="error")


def test_frozen() -> None:
    """Results are immutable."""
    with pytest.raises(AttributeError):
        _result().passed = False  # type: ignore[misc]  # asserting the frozen guard


def test_equality_ignores_details() -> None:
    """Two results differing only in details compare equal, without comparing frames."""
    a = _result(details=pd.DataFrame({"x": [1]}))
    b = _result(details=pd.DataFrame({"x": [2]}))
    assert a == b


def test_severity_is_str() -> None:
    """Severity values render as their lowercase names."""
    assert f"{Severity.WARNING}" == "warning"
