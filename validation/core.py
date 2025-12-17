"""Core validation orchestration."""

from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from validation.config import (
    CACHE_DIR,
    CDN_FILES_DIR,
    DATASETS,
    MAJOR_DONORS,
    MANIFESTS_DIR,
)
from validation.models import CheckResult, ValidationReport, Warning
from validation.checks import (
    check_schema,
    check_not_empty,
    check_no_duplicate_keys,
    check_value_columns_populated,
    check_value_bounds,
    check_name_mappings_complete,
    check_critical_dimensions,
)
from validation.anomalies import (
    detect_yoy_anomalies,
    detect_release_drift,
    detect_missing_expected_data,
    detect_new_or_removed_codes,
    detect_row_count_change,
    detect_indicator_coverage_gaps,
    detect_agency_drift,
    detect_sector_drift,
)
from validation import manifest as manifest_module
from validation.seek_data import fetch_seek_sectors_data, get_donor_names
from validation.seek_manifest import (
    get_seek_manifest_path,
    update_seek_manifest,
    get_previous_seek_release,
)
from validation.seek_anomalies import run_seek_validation


def validate_dataset(
    dataset_name: str,
    release: str,
    cache_dir: Path = None,
    cdn_files_dir: Path = None,
    dataset_config: dict = None,
    manifests_dir: Path = None,
    update_manifest: bool = True,
) -> ValidationReport:
    """
    Validate a single dataset.

    Args:
        dataset_name: Name of dataset (e.g., "financing_view")
        release: Release name (e.g., "dec_2024")
        cache_dir: Directory containing parquet files (default: CACHE_DIR)
        cdn_files_dir: Directory containing partitioned datasets (default: CDN_FILES_DIR)
        dataset_config: Dataset configuration (default: from DATASETS)
        manifests_dir: Directory for manifests (default: MANIFESTS_DIR)
        update_manifest: Whether to update the manifest after validation

    Returns:
        ValidationReport with results
    """
    cache_dir = cache_dir or CACHE_DIR
    cdn_files_dir = cdn_files_dir or CDN_FILES_DIR
    manifests_dir = manifests_dir or MANIFESTS_DIR
    config = dataset_config or DATASETS.get(dataset_name, {})

    report = ValidationReport(release=release)

    # Determine path based on whether dataset is partitioned
    is_partitioned = config.get("partitioned", False)
    if is_partitioned:
        parquet_path = cdn_files_dir / config.get("file", dataset_name)
    else:
        parquet_path = cache_dir / config.get("file", f"{dataset_name}.parquet")

    # Check file/directory exists
    if not parquet_path.exists():
        report.add_check_result(
            dataset_name,
            "file_exists",
            CheckResult(
                passed=False,
                errors=[
                    f"{'Directory' if is_partitioned else 'File'} not found: {parquet_path}"
                ],
            ),
        )
        return report

    report.add_check_result(dataset_name, "file_exists", CheckResult(passed=True))

    # Load data
    try:
        if is_partitioned:
            # Use dataset API for partitioned data
            dataset = ds.dataset(parquet_path, format="parquet", partitioning="hive")
            df = dataset.to_table().to_pandas(types_mapper=lambda x: None)
        else:
            df = pq.read_table(parquet_path).to_pandas()
    except Exception as e:
        report.add_check_result(
            dataset_name,
            "parquet_readable",
            CheckResult(passed=False, errors=[f"Failed to read parquet: {e}"]),
        )
        return report

    report.add_check_result(dataset_name, "parquet_readable", CheckResult(passed=True))

    # Load manifest for comparison
    manifest_path = manifests_dir / f"{dataset_name}.json"
    manifest = manifest_module.load_manifest(manifest_path)
    previous_release = _get_previous_release(manifest, release)

    # Run hard gate checks
    _run_hard_gates(report, dataset_name, df, config, previous_release)

    # Always run anomaly detection for comprehensive reporting
    _run_anomaly_detection(report, dataset_name, df, config, previous_release)

    # Update manifest if requested
    if update_manifest:
        manifest = manifest_module.update_manifest(
            manifest=manifest,
            release=release,
            df=df,
            value_column=config.get("value_column", "value_usd_constant"),
            key_columns=config.get("key_columns", []),
        )
        manifest["dataset"] = dataset_name
        manifests_dir.mkdir(parents=True, exist_ok=True)
        manifest_module.save_manifest(manifest, manifest_path)

    return report


def _get_previous_release(manifest: dict, current_release: str) -> dict:
    """Get the most recent release before the current one."""
    releases = manifest.get("releases", {})
    if not releases:
        return {}

    # Get releases sorted by name (assuming naming like dec_2024, jun_2024)
    release_names = sorted(releases.keys(), reverse=True)

    for name in release_names:
        if name != current_release:
            return releases[name]

    return {}


def _run_hard_gates(
    report: ValidationReport,
    dataset_name: str,
    df: pd.DataFrame,
    config: dict,
    previous_release: dict,
) -> None:
    """Run all hard gate checks."""

    # Schema validation
    expected_schema = {
        "columns": config.get("required_columns", []),
        "dtypes": {},  # We're flexible on dtypes for now
    }
    report.add_check_result(
        dataset_name,
        "schema",
        check_schema(df, expected_schema),
    )

    # Not empty
    report.add_check_result(
        dataset_name,
        "not_empty",
        check_not_empty(df),
    )

    # No duplicate keys
    report.add_check_result(
        dataset_name,
        "no_duplicate_keys",
        check_no_duplicate_keys(df, config.get("key_columns", [])),
    )

    # Value columns populated
    report.add_check_result(
        dataset_name,
        "value_columns_populated",
        check_value_columns_populated(df),
    )

    # Value bounds
    report.add_check_result(
        dataset_name,
        "value_bounds",
        check_value_bounds(df),
    )

    # Name mappings
    report.add_check_result(
        dataset_name,
        "name_mappings",
        check_name_mappings_complete(df),
    )

    # Critical dimensions
    latest_year = df["year"].max() if "year" in df.columns else None
    report.add_check_result(
        dataset_name,
        "critical_dimensions",
        check_critical_dimensions(
            df,
            expected_latest_year=latest_year,
            critical_donors=config.get("critical_donors", MAJOR_DONORS),
        ),
    )


def _run_anomaly_detection(
    report: ValidationReport,
    dataset_name: str,
    df: pd.DataFrame,
    config: dict,
    previous_release: dict,
) -> None:
    """Run anomaly detection and add warnings to report."""
    value_column = config.get("value_column", "value_usd_constant")
    latest_year = df["year"].max() if "year" in df.columns else None

    # Year-over-year anomalies
    if latest_year:
        warnings = detect_yoy_anomalies(df, latest_year, value_column)
        for w in warnings:
            w.dataset = dataset_name
            report.add_warning(w)

    # Release drift
    if previous_release:
        warnings = detect_release_drift(
            df, previous_release, "previous release", value_column
        )
        for w in warnings:
            w.dataset = dataset_name
            report.add_warning(w)

        # Row count change
        prev_count = previous_release.get("row_count", 0)
        warnings = detect_row_count_change(len(df), prev_count, dataset_name)
        for w in warnings:
            report.add_warning(w)

        # New/removed codes
        warnings = detect_new_or_removed_codes(df, previous_release)
        for w in warnings:
            w.dataset = dataset_name
            report.add_warning(w)

        # Indicator coverage gaps
        warnings = detect_indicator_coverage_gaps(df, previous_release, value_column)
        for w in warnings:
            w.dataset = dataset_name
            report.add_warning(w)

        # Agency drift (for multilateral data)
        warnings = detect_agency_drift(df, previous_release, value_column)
        for w in warnings:
            w.dataset = dataset_name
            report.add_warning(w)

        # Sector drift (for sectors_view)
        donor_names_map = {}
        if "donor_name" in df.columns:
            donor_names_map = df.groupby("donor_code")["donor_name"].first().to_dict()
        warnings = detect_sector_drift(
            df, previous_release, value_column, donor_names_map
        )
        for w in warnings:
            w.dataset = dataset_name
            report.add_warning(w)

    # Missing expected data
    major_donors = {
        code: f"Donor {code}" for code in config.get("critical_donors", MAJOR_DONORS)
    }
    if "donor_name" in df.columns:
        # Get actual names from data
        donor_names = df.groupby("donor_code")["donor_name"].first().to_dict()
        major_donors = {
            code: donor_names.get(code, f"Donor {code}")
            for code in config.get("critical_donors", MAJOR_DONORS)
        }

    warnings = detect_missing_expected_data(df, major_donors, value_column)
    for w in warnings:
        w.dataset = dataset_name
        report.add_warning(w)


def validate_seek_sectors(
    release: str,
    manifests_dir: Path = None,
    update_manifest: bool = True,
) -> ValidationReport:
    """
    Validate SEEK-style sector data at purpose-code level.

    This validation:
    1. Fetches purpose-code level data via seek/sectors.py
    2. Compares totals, health, and agriculture by donor vs previous release
    3. Flags anomalies using Z-score thresholds

    Args:
        release: Release name (e.g., "april_2025" - represents OECD data release)
        manifests_dir: Directory for manifests (default: MANIFESTS_DIR)
        update_manifest: Whether to update the manifest after validation

    Returns:
        ValidationReport with SEEK validation results
    """
    manifests_dir = manifests_dir or MANIFESTS_DIR
    report = ValidationReport(release=release)

    # Fetch purpose-code level data
    try:
        df = fetch_seek_sectors_data()
    except Exception as e:
        report.add_check_result(
            "seek_sectors",
            "data_fetch",
            CheckResult(passed=False, errors=[f"Failed to fetch SEEK data: {e}"]),
        )
        return report

    report.add_check_result("seek_sectors", "data_fetch", CheckResult(passed=True))

    # Check data is not empty
    if len(df) == 0:
        report.add_check_result(
            "seek_sectors",
            "not_empty",
            CheckResult(passed=False, errors=["SEEK data is empty"]),
        )
        return report

    report.add_check_result("seek_sectors", "not_empty", CheckResult(passed=True))

    # Load manifest and get most recent previous release (automatic comparison)
    manifest_path = get_seek_manifest_path()
    manifest = manifest_module.load_manifest(manifest_path)
    previous_release = get_previous_seek_release(manifest)

    # Build donor names map
    donor_names = get_donor_names(df)

    # Run SEEK anomaly detection
    if previous_release:
        warnings = run_seek_validation(
            df=df,
            previous_release=previous_release,
            donor_names=donor_names,
        )
        for w in warnings:
            report.add_warning(w)
    else:
        # First run - just log info
        report.add_warning(
            Warning(
                level="info",
                dataset="seek_sectors",
                message="SEEK validation baseline established (no previous release to compare)",
            )
        )

    # Update manifest
    if update_manifest:
        manifest = update_seek_manifest(
            manifest=manifest,
            release=release,
            df=df,
        )
        manifests_dir.mkdir(parents=True, exist_ok=True)
        manifest_module.save_manifest(manifest, manifest_path)

    return report


def validate_all(
    release: str,
    cache_dir: Path = None,
    cdn_files_dir: Path = None,
    manifests_dir: Path = None,
    update_manifests: bool = True,
    include_seek: bool = True,
) -> ValidationReport:
    """
    Validate all datasets.

    Args:
        release: Release name (e.g., "dec_2024")
        cache_dir: Directory containing parquet files
        cdn_files_dir: Directory containing partitioned datasets
        manifests_dir: Directory for manifests
        update_manifests: Whether to update manifests after validation
        include_seek: Whether to include SEEK sector validation (default: True)

    Returns:
        Combined ValidationReport for all datasets
    """
    combined_report = ValidationReport(release=release)

    for dataset_name in DATASETS:
        dataset_report = validate_dataset(
            dataset_name=dataset_name,
            release=release,
            cache_dir=cache_dir,
            cdn_files_dir=cdn_files_dir,
            manifests_dir=manifests_dir,
            update_manifest=update_manifests,
        )

        # Merge results
        for dataset, checks in dataset_report.check_results.items():
            for check_name, result in checks.items():
                combined_report.add_check_result(dataset, check_name, result)

        for warning in dataset_report.warnings:
            combined_report.add_warning(warning)

    # Add SEEK validation if requested
    if include_seek:
        seek_report = validate_seek_sectors(
            release=release,
            manifests_dir=manifests_dir,
            update_manifest=update_manifests,
        )

        # Merge SEEK results
        for dataset, checks in seek_report.check_results.items():
            for check_name, result in checks.items():
                combined_report.add_check_result(dataset, check_name, result)

        for warning in seek_report.warnings:
            combined_report.add_warning(warning)

    return combined_report
