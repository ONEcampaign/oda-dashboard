"""Data models for validation results."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class CheckResult:
    """Result of a single validation check."""

    passed: bool
    errors: list[str] = field(default_factory=list)

    @classmethod
    def combine(cls, results: list["CheckResult"]) -> "CheckResult":
        """Combine multiple check results into one."""
        all_errors = []
        for r in results:
            all_errors.extend(r.errors)
        return cls(
            passed=all(r.passed for r in results),
            errors=all_errors,
        )


@dataclass
class Warning:
    """A non-blocking warning about potential data issues."""

    level: Literal["high", "medium", "info"]
    dataset: str
    message: str


@dataclass
class ValidationReport:
    """Complete validation report for a data release."""

    release: str
    timestamp: datetime = field(default_factory=datetime.now)
    check_results: dict[str, dict[str, CheckResult]] = field(default_factory=dict)
    warnings: list[Warning] = field(default_factory=list)

    @property
    def has_blocking_errors(self) -> bool:
        """True if any hard gate check failed."""
        for dataset_results in self.check_results.values():
            for result in dataset_results.values():
                if not result.passed:
                    return True
        return False

    def add_check_result(
        self, dataset: str, check_name: str, result: CheckResult
    ) -> None:
        """Add a check result to the report."""
        if dataset not in self.check_results:
            self.check_results[dataset] = {}
        self.check_results[dataset][check_name] = result

    def add_warning(self, warning: Warning) -> None:
        """Add a warning to the report."""
        self.warnings.append(warning)

    def get_warnings_by_level(self, level: str) -> list[Warning]:
        """Get all warnings of a specific level."""
        return [w for w in self.warnings if w.level == level]
