"""
Entry point for data validation of the dashboard views.

Usage:
    PYTHONPATH=. uv run python src/data/scripts/validate.py [--views VIEW ...]
        [--source-dir DIR] [--baseline DIR] [--expected PATH] [--no-cross-view]
        [--strict] [--report-dir DIR]

Contracts, invariants and anomalies always run. Parity runs when --baseline is given;
cross-view comparison with topic_page runs unless --no-cross-view. A source or baseline DIR
holds one directory per view (DIR/<view>). Exits 1 on blocking failures.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from src.data.config import logger
from src.data.validation.expected import (
    DEFAULT_EXPECTED_DELTAS_PATH,
    load_expected_deltas,
)
from src.data.validation.io import default_sources
from src.data.validation.models import CheckResult
from src.data.validation.report import (
    REPORT_DIR,
    Outcome,
    count_outcomes,
    is_blocking,
    render_markdown,
    write_report,
)
from src.data.validation.runner import run_validation, source_roots
from src.data.validation.views import VIEWS

REPORT_TITLE: str = "Dashboard data validation"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description="Validate the built dashboard data.")
    parser.add_argument(
        "--views",
        nargs="+",
        choices=sorted(VIEWS),
        default=list(VIEWS),
        help="Views to check (default: all). Cross-view still reads every view.",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Directory with one subdirectory per view (default: the local build).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Baseline directory with one subdirectory per view; enables parity.",
    )
    parser.add_argument(
        "--expected",
        type=Path,
        default=DEFAULT_EXPECTED_DELTAS_PATH,
        help="TOML file of expected deltas.",
    )
    parser.add_argument(
        "--no-cross-view",
        action="store_true",
        help="Skip the comparison with topic_page.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Every ERROR blocks, including parity and cross-view ones.",
    )
    parser.add_argument(
        "--report-dir", type=Path, default=REPORT_DIR, help="Where to write the report."
    )
    return parser.parse_args(argv)


def log_summary(results: list[CheckResult], *, strict: bool) -> list[CheckResult]:
    """Log the outcome counts and each blocking failure; returns the blocking failures."""
    outcomes = count_outcomes(results)
    logger.info(
        "Results: %s",
        ", ".join(f"{outcomes[o]} {o.value}" for o in Outcome),
    )
    blocking = [r for r in results if is_blocking(r, strict=strict)]
    for r in blocking:
        logger.error("BLOCKING %s (%s): %s", r.check, r.view, r.message)
    return blocking


def main(argv: Sequence[str] | None = None) -> int:
    """Run the validation, write the report and return the exit code."""
    args = parse_args(argv)
    sources = (
        source_roots(args.source_dir, VIEWS)
        if args.source_dir is not None
        else default_sources()
    )
    baseline_sources = (
        source_roots(args.baseline, args.views) if args.baseline is not None else None
    )
    expected = load_expected_deltas(args.expected)

    results = run_validation(
        args.views,
        sources,
        baseline_sources=baseline_sources,
        expected=expected,
        cross_view=not args.no_cross_view,
    )

    markdown = render_markdown(
        results,
        title=REPORT_TITLE,
        sources={name: sources[name] for name in args.views},
        strict=args.strict,
    )
    logger.info("Report written to %s", write_report(markdown, args.report_dir))

    blocking = log_summary(results, strict=args.strict)
    if blocking:
        logger.error("VALIDATION FAILED: %s blocking failure(s)", len(blocking))
        return 1
    logger.info("VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
