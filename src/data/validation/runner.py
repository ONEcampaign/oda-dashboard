"""Run every check family over the views and collect the results.

Per view: contracts on the whole view, then invariants and anomalies. A partitioned view
(sectors) is loaded whole for contracts, released, then streamed one recipient partition
at a time for invariants, so the second pass holds a single partition. Parity compares each
view with a baseline when one is given; cross-view compares the views with topic_page.
"""

import gc
from collections.abc import Iterable, Iterator, Mapping, Sequence
from itertools import chain
from pathlib import Path

from src.data.config import logger
from src.data.validation.anomalies import run_anomalies
from src.data.validation.contracts import has_required_columns, run_contracts
from src.data.validation.cross_view import run_cross_view
from src.data.validation.expected import ExpectedDelta, unused_entries
from src.data.validation.invariants import run_invariants
from src.data.validation.io import LoadedView, iter_partitions, load_view
from src.data.validation.models import CheckResult, Severity
from src.data.validation.parity import run_parity
from src.data.validation.views import get_spec

# The partition the anomaly check reads in a partitioned view: it holds each donor's key total.
ANOMALY_PARTITION: str = "oda-eligible-countries"
# The view name expected-delta bookkeeping results are reported under.
EXPECTED_VIEW: str = "expected_deltas"
# Failures to run a check at all, as opposed to a check that ran and failed.
_LOAD_ERRORS: tuple[type[Exception], ...] = (FileNotFoundError, KeyError, ValueError)


def source_roots(root: Path, views: Iterable[str]) -> dict[str, Path]:
    """Map each view to ``root/<view>``, the layout of a baseline or a copied build."""
    return {name: root / name for name in views}


def _failure(check: str, view: str, error: Exception, *, blocking: bool) -> CheckResult:
    """An ERROR result for a check family that could not run."""
    return CheckResult(
        check=check,
        view=view,
        passed=False,
        severity=Severity.ERROR,
        message=f"could not run: {type(error).__name__}: {error}",
        blocking=blocking,
    )


def _stream_partitions(
    first: tuple[str, LoadedView],
    rest: Iterator[tuple[str, LoadedView]],
    anomaly_parts: list[LoadedView],
) -> Iterator[LoadedView]:
    """Yield a view's partitions, keeping the anomaly partition aside for later."""
    for slug, part in chain([first], rest):
        if slug == ANOMALY_PARTITION:
            anomaly_parts.append(part)
        yield part


def run_view(
    name: str, source: Path, expected: Sequence[ExpectedDelta] = ()
) -> list[CheckResult]:
    """Run contracts, invariants and anomalies on one view.

    Only loading errors are caught. An error raised by a check propagates. A view that is empty or
    misses a required column gets its contract results only, since the other families
    would fail for the same reason.

    Args:
        name: A key of VIEWS.
        source: The view's directory.
        expected: Expected deltas; "anomaly" entries explain anomaly flags.

    Returns:
        The results; one blocking ERROR if the view could not be loaded.
    """
    try:
        view = load_view(name, source)
    except _LOAD_ERRORS as e:
        return [_failure("contracts.load", name, e, blocking=True)]

    results = run_contracts(view)
    if view.data.empty or not has_required_columns(view):
        return results
    if not get_spec(name).partitioned:
        return [*results, *run_invariants([view]), *run_anomalies(view, expected)]

    del view  # release the whole view before streaming its partitions
    gc.collect()
    # iter_partitions resolves and lists the files before its first yield, so the
    # first next() is the setup that can fail; later partitions are check-time reads.
    try:
        partitions = iter_partitions(name, source)
        first = next(partitions)
    except _LOAD_ERRORS as e:
        return [*results, _failure("invariants.load", name, e, blocking=True)]

    anomaly_parts: list[LoadedView] = []
    results += run_invariants(_stream_partitions(first, partitions, anomaly_parts))
    if not anomaly_parts:
        return [
            *results,
            CheckResult(
                check="anomalies.partition",
                view=name,
                passed=False,
                severity=Severity.ERROR,
                message=f"no {ANOMALY_PARTITION} partition: nothing to check",
            ),
        ]
    return [
        *results,
        *(r for part in anomaly_parts for r in run_anomalies(part, expected)),
    ]


def run_view_parity(
    name: str, candidate: Path, baseline: Path, expected: Sequence[ExpectedDelta]
) -> list[CheckResult]:
    """Compare one view with its baseline; a failure to read either is non-blocking."""
    try:
        return run_parity(name, candidate, baseline, expected)
    except _LOAD_ERRORS as e:
        return [_failure("parity.load", name, e, blocking=False)]


def run_validation(
    views: Sequence[str],
    sources: Mapping[str, Path],
    *,
    baseline_sources: Mapping[str, Path] | None,
    expected: list[ExpectedDelta],
    cross_view: bool,
) -> list[CheckResult]:
    """Run every check family.

    Args:
        views: The views to check.
        sources: View name -> source directory, for every view (cross-view reads them all).
        baseline_sources: View name -> baseline directory; None skips parity.
        expected: Expected deltas for parity and cross-view.
        cross_view: Whether to compare the views with topic_page.

    Returns:
        All results, in view order then parity then cross-view.
    """
    results: list[CheckResult] = []
    for name in views:
        logger.info("Checking %s (%s)", name, sources[name])
        results += run_view(name, sources[name], expected)
        if baseline_sources is not None:
            logger.info("Comparing %s with %s", name, baseline_sources[name])
            results += run_view_parity(
                name, sources[name], baseline_sources[name], expected
            )
    if cross_view:
        logger.info("Comparing the views with topic_page")
        results += run_cross_view(dict(sources), expected)
    return [
        *results,
        unused_expected_result(
            expected,
            anomaly_views=views,
            parity_views=views if baseline_sources is not None else (),
            cross_view=cross_view,
        ),
    ]


def unused_expected_result(
    expected: Sequence[ExpectedDelta],
    *,
    anomaly_views: Iterable[str],
    parity_views: Iterable[str],
    cross_view: bool,
) -> CheckResult:
    """A WARNING listing expected entries that explained nothing this run, else a pass.

    Only entries whose view and kind the run checked count; a parity entry is not unused
    in a run without --baseline. A stale entry blocks nothing but could later explain a
    real regression, so it should be removed.
    """
    unused = unused_entries(
        expected,
        anomaly_views=anomaly_views,
        parity_views=parity_views,
        cross_view=cross_view,
    )
    listed = "; ".join(f"{e.view} {e.kind.value}: {e.reason}" for e in unused)
    return CheckResult(
        check="expected.unused",
        view=EXPECTED_VIEW,
        passed=not unused,
        severity=Severity.WARNING,
        message=(
            f"{len(unused)} expected deltas explained nothing: {listed}"
            if unused
            else "Every expected delta in scope explained something"
        ),
        blocking=False,
    )
