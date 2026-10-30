"""The result type every validation check returns."""

from dataclasses import dataclass, field
from enum import StrEnum

import pandas as pd

# A failing check keeps at most this many offending rows, so a broken view with millions of
# bad rows cannot balloon the report or memory. The report shows fewer still.
MAX_DETAIL_ROWS: int = 50


class Severity(StrEnum):
    """How much a failed check matters."""

    ERROR = "error"  # blocks: contract/invariant failure, or unexplained delta under --strict
    WARNING = "warning"  # reported, does not block
    INFO = "info"


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check on one view.

    Attributes:
        check: Dotted check name, e.g. "contracts.unique_keys".
        view: The view checked, e.g. "financing_view", or "cross_view".
        passed: Whether the check passed.
        severity: The severity the check carries if it failed. Kept on passing results too,
            so the report can say what a check would have been.
        message: One-line human-readable outcome.
        details: Offending rows, truncated to MAX_DETAIL_ROWS on construction. None when
            there is nothing row-level to show. Excluded from equality.
        blocking: Whether a failure fails the run. False for parity and cross-view results,
            which block only under --strict.
    """

    check: str
    view: str
    passed: bool
    severity: Severity
    message: str
    details: pd.DataFrame | None = field(default=None, compare=False)
    blocking: bool = True

    def __post_init__(self) -> None:
        """Validate the severity and cap the detail rows."""
        if not isinstance(self.severity, Severity):
            raise TypeError(f"severity must be a Severity, got {self.severity!r}")
        if self.details is not None and len(self.details) > MAX_DETAIL_ROWS:
            # frozen: the only way to store the truncated frame
            object.__setattr__(self, "details", self.details.head(MAX_DETAIL_ROWS))
