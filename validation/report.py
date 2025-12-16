"""Report generation for validation results."""

from datetime import datetime
from pathlib import Path

from validation.models import ValidationReport, CheckResult
from validation.config import REPORTS_DIR


def generate_report_markdown(report: ValidationReport) -> str:
    """
    Generate a markdown report from validation results.

    Args:
        report: ValidationReport with check results and warnings

    Returns:
        Markdown string
    """
    lines = []

    # Header
    lines.append("# Data Validation Report")
    lines.append(f"**Release:** {report.release}")
    lines.append(f"**Generated:** {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

    # Status summary
    high_count = len(report.get_warnings_by_level("high"))
    medium_count = len(report.get_warnings_by_level("medium"))
    info_count = len(report.get_warnings_by_level("info"))

    if report.has_blocking_errors:
        status = "BLOCKED"
    elif high_count > 0:
        status = (
            f"WARNINGS ({high_count} high, {medium_count} medium, {info_count} info)"
        )
    elif medium_count > 0:
        status = f"WARNINGS ({medium_count} medium, {info_count} info)"
    elif info_count > 0:
        status = f"INFO ({info_count} items)"
    else:
        status = "PASSED"

    lines.append(f"**Status:** {status}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Hard Gates section
    lines.append("## Hard Gates")
    lines.append("")

    if report.has_blocking_errors:
        lines.append("### BLOCKED")
        lines.append("")
    else:
        lines.append("### PASSED")
        lines.append("")

    lines.append("| Dataset | Check | Status |")
    lines.append("|---------|-------|--------|")

    for dataset, checks in report.check_results.items():
        for check_name, result in checks.items():
            status_str = "Pass" if result.passed else "**FAIL**"
            lines.append(f"| {dataset} | {check_name} | {status_str} |")

    lines.append("")

    # Show errors if any
    all_errors = []
    for dataset, checks in report.check_results.items():
        for check_name, result in checks.items():
            for error in result.errors:
                all_errors.append((dataset, check_name, error))

    if all_errors:
        lines.append("### Errors")
        lines.append("")
        for dataset, check_name, error in all_errors:
            lines.append(f"- **{dataset}/{check_name}**: {error}")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Warnings section
    lines.append("## Warnings")
    lines.append("")

    # High priority
    high_warnings = report.get_warnings_by_level("high")
    if high_warnings:
        lines.append(f"### High Priority ({len(high_warnings)})")
        lines.append("")
        _add_warnings_by_dataset(lines, high_warnings)

    # Medium priority
    medium_warnings = report.get_warnings_by_level("medium")
    if medium_warnings:
        lines.append(f"### Medium Priority ({len(medium_warnings)})")
        lines.append("")
        _add_warnings_by_dataset(lines, medium_warnings)

    # Info
    info_warnings = report.get_warnings_by_level("info")
    if info_warnings:
        lines.append(f"### Info ({len(info_warnings)})")
        lines.append("")
        _add_warnings_by_dataset(lines, info_warnings)

    if not high_warnings and not medium_warnings and not info_warnings:
        lines.append("No warnings.")
        lines.append("")

    return "\n".join(lines)


def _add_warnings_by_dataset(lines: list[str], warnings: list) -> None:
    """Group warnings by dataset and add to lines."""
    by_dataset: dict[str, list] = {}
    for w in warnings:
        if w.dataset not in by_dataset:
            by_dataset[w.dataset] = []
        by_dataset[w.dataset].append(w)

    for dataset, dataset_warnings in sorted(by_dataset.items()):
        if dataset:
            lines.append(f"**{dataset}**")
        for w in dataset_warnings:
            lines.append(f"- {w.message}")
        lines.append("")


def save_report(report: ValidationReport, output_dir: Path = None) -> Path:
    """
    Save report to a markdown file.

    Args:
        report: ValidationReport to save
        output_dir: Directory to save to (defaults to REPORTS_DIR)

    Returns:
        Path to saved file
    """
    if output_dir is None:
        output_dir = REPORTS_DIR

    output_dir.mkdir(parents=True, exist_ok=True)

    filename = (
        f"validation_{report.release}_{report.timestamp.strftime('%Y%m%d_%H%M%S')}.md"
    )
    path = output_dir / filename

    content = generate_report_markdown(report)
    path.write_text(content)

    return path
