"""Turn check results into a markdown report and a pass/explained/warning/error summary.

A result's outcome follows one convention everywhere:

- passed: pass;
- failed with severity INFO: explained (an expected delta, not a failure);
- failed with severity WARNING: warning;
- failed with severity ERROR: error, which blocks only if the result is blocking, or under
  strict mode.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import pandas as pd

from src.data.validation.io import VALIDATION_DATA_DIR
from src.data.validation.models import CheckResult, Severity

REPORT_DIR: Path = VALIDATION_DATA_DIR / "reports"

# Detail tables longer than this are cut. The full detail stays in memory.
REPORT_DETAIL_ROWS: int = 20
_TIMESTAMP_FORMAT: str = "%Y%m%dT%H%M%SZ"
_UNKNOWN_FAMILY: str = "other"


class Outcome(StrEnum):
    """How a result counts in the summary."""

    PASS = "pass"
    EXPLAINED = "explained"
    WARNING = "warning"
    ERROR = "error"


def classify(result: CheckResult) -> Outcome:
    """Map a result to its outcome (see the module docstring)."""
    if result.passed:
        return Outcome.PASS
    match result.severity:
        case Severity.INFO:
            return Outcome.EXPLAINED
        case Severity.WARNING:
            return Outcome.WARNING
        case Severity.ERROR:
            return Outcome.ERROR


def is_blocking(result: CheckResult, *, strict: bool = False) -> bool:
    """Whether a result fails the run: a blocking ERROR, or any ERROR under strict."""
    return classify(result) is Outcome.ERROR and (result.blocking or strict)


def check_family(result: CheckResult) -> str:
    """The check family: the part of the check name before the first dot."""
    family, dot, _ = result.check.partition(".")
    return family if dot else _UNKNOWN_FAMILY


def summarize(results: Iterable[CheckResult]) -> pd.DataFrame:
    """Count outcomes per view and check family.

    Returns:
        One row per (view, family) with a column per Outcome, sorted by view and family.
    """
    counts: Counter[tuple[str, str, Outcome]] = Counter(
        (r.view, check_family(r), classify(r)) for r in results
    )
    keys = sorted({(view, family) for view, family, _ in counts})
    return pd.DataFrame(
        [
            {
                "view": view,
                "family": family,
                **{o.value: counts[(view, family, o)] for o in Outcome},
            }
            for view, family in keys
        ],
        columns=["view", "family", *(o.value for o in Outcome)],
    )


def count_outcomes(results: Iterable[CheckResult]) -> Counter[Outcome]:
    """Total results per outcome."""
    return Counter(classify(r) for r in results)


def _cell(value: object) -> str:
    """One markdown table cell: floats trimmed, pipes and newlines escaped."""
    text = f"{value:,.6g}" if isinstance(value, float) else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def markdown_table(frame: pd.DataFrame, *, max_rows: int = REPORT_DETAIL_ROWS) -> str:
    """Render a frame as a markdown table, cut to max_rows with a note when longer."""
    shown = frame.head(max_rows)
    header = "| " + " | ".join(_cell(c) for c in shown.columns) + " |"
    divider = "|" + "|".join(" --- " for _ in shown.columns) + "|"
    rows = [
        "| " + " | ".join(_cell(v) for v in row) + " |"
        for row in shown.itertuples(index=False, name=None)
    ]
    lines = [header, divider, *rows]
    if len(frame) > max_rows:
        lines.append(f"\n_Showing {max_rows} of {len(frame)} rows._")
    return "\n".join(lines)


def _render_result(result: CheckResult) -> str:
    """One result as a heading, its message and its detail table."""
    parts = [f"### `{result.check}` ({result.view})", "", result.message]
    if result.details is not None and len(result.details):
        parts += ["", markdown_table(result.details)]
    return "\n".join(parts)


def _render_section(heading: str, results: list[CheckResult]) -> str:
    """A section of results, or an empty string when there are none."""
    if not results:
        return ""
    body = "\n\n".join(_render_result(r) for r in results)
    return f"## {heading} ({len(results)})\n\n{body}"


def render_markdown(
    results: Iterable[CheckResult],
    *,
    title: str,
    sources: Mapping[str, Path],
    strict: bool = False,
) -> str:
    """Render the report.

    Args:
        results: Every result of the run.
        title: The report heading.
        sources: View name -> the source directory it was read from.
        strict: Whether every ERROR blocks, as in the run's exit code.

    Returns:
        Markdown: a summary table, then blocking failures, non-blocking errors, explained
        deltas and warnings. Passing results appear only in the summary.
    """
    results = list(results)
    outcomes = count_outcomes(results)
    blocking = [r for r in results if is_blocking(r, strict=strict)]
    non_blocking = [
        r
        for r in results
        if classify(r) is Outcome.ERROR and not is_blocking(r, strict=strict)
    ]
    explained = [r for r in results if classify(r) is Outcome.EXPLAINED]
    warnings = [r for r in results if classify(r) is Outcome.WARNING]

    summary = summarize(results)
    verdict = "FAILED" if blocking else "PASSED"
    totals = ", ".join(f"{outcomes[o]} {o.value}" for o in Outcome)
    source_lines = [f"- `{view}`: `{path}`" for view, path in sources.items()]
    sections = [
        f"# {title}",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M:%S} UTC. "
        f"Mode: {'strict' if strict else 'default'}.\n\n"
        f"**{verdict}**: {len(blocking)} blocking. Totals: {totals}.",
        "## Sources\n\n" + "\n".join(source_lines) if source_lines else "",
        "## Summary\n\n" + markdown_table(summary, max_rows=len(summary)),
        _render_section("Blocking failures", blocking),
        _render_section("Non-blocking errors", non_blocking),
        _render_section("Explained", explained),
        _render_section("Warnings", warnings),
    ]
    return "\n\n".join(s for s in sections if s) + "\n"


def write_report(markdown: str, directory: Path = REPORT_DIR) -> Path:
    """Write the report to validation_<UTC timestamp>.md in directory, creating it.

    Returns:
        The path written.
    """
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime(_TIMESTAMP_FORMAT)
    path = directory / f"validation_{stamp}.md"
    path.write_text(markdown)
    return path
