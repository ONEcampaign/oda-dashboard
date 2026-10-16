"""
Entry point for data validation.

Usage:
    PYTHONPATH=. uv run python src/data/scripts/validate.py <release> [--no-seek]

    from src.data.scripts.validate import run_validation

    report = run_validation(release="dec_2024")
    report = run_validation(release="dec_2024", update_manifests=False)
    report = run_validation(release="dec_2024", save_report=False)
    report = run_validation(release="dec_2024", include_seek=False)  # Skip SEEK validation
"""

import argparse

from validation import validate_all, save_report
from src.data.config import logger


def run_validation(
    release: str,
    update_manifests: bool = True,
    save_report_file: bool = True,
    include_seek: bool = True,
) -> dict:
    """
    Run data validation for a release.

    Args:
        release: Release name (e.g., "dec_2024")
        update_manifests: Whether to update manifests after validation
        save_report_file: Whether to save report to file
        include_seek: Whether to include SEEK sector validation (default: True)

    Returns:
        Dict with validation results:
        - passed: bool
        - report: ValidationReport object
        - report_path: Path to saved report (if saved)
        - summary: Dict with warning counts
    """
    logger.info(f"Validating data for release: {release}")

    # Run validation
    report = validate_all(
        release=release,
        update_manifests=update_manifests,
        include_seek=include_seek,
    )

    # Save report if requested
    report_path = None
    if save_report_file:
        report_path = save_report(report)
        logger.info(f"Report saved to: {report_path}")

    # Compute summary
    high_count = len(report.get_warnings_by_level("high"))
    medium_count = len(report.get_warnings_by_level("medium"))
    info_count = len(report.get_warnings_by_level("info"))

    summary = {
        "high": high_count,
        "medium": medium_count,
        "info": info_count,
    }

    # Log results
    if report.has_blocking_errors:
        logger.error("VALIDATION FAILED - Blocking errors detected")
        for dataset, checks in report.check_results.items():
            for check_name, result in checks.items():
                if not result.passed:
                    for error in result.errors:
                        logger.error(f"  {dataset}/{check_name}: {error}")
    elif high_count > 0:
        logger.warning(
            f"VALIDATION PASSED with warnings: {high_count} high, {medium_count} medium, {info_count} info"
        )
    else:
        logger.info(
            f"VALIDATION PASSED: {medium_count} medium, {info_count} info warnings"
        )

    return {
        "passed": not report.has_blocking_errors,
        "report": report,
        "report_path": report_path,
        "summary": summary,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate the built dashboard data.")
    parser.add_argument("release", help='Name to record this release under, e.g. "2026_10"')
    parser.add_argument(
        "--no-seek", action="store_true", help="Skip the SEEK sector validation"
    )
    args = parser.parse_args()

    result = run_validation(release=args.release, include_seek=not args.no_seek)
    if not result["passed"]:
        raise SystemExit(1)
