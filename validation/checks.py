"""Hard gate validation checks that block deployment on failure."""

import pandas as pd
from validation.models import CheckResult
from validation.config import MAX_SANE_VALUE


def check_schema(df: pd.DataFrame, expected: dict) -> CheckResult:
    """
    Hard gate: Schema must match expected structure.

    Args:
        df: DataFrame to validate
        expected: Dict with 'columns' (list) and 'dtypes' (dict)

    Returns:
        CheckResult with pass/fail and any errors
    """
    errors = []

    # Check for missing columns
    expected_cols = set(expected.get("columns", []))
    actual_cols = set(df.columns)
    missing = expected_cols - actual_cols
    if missing:
        errors.append(f"Missing columns: {sorted(missing)}")

    # Check for type mismatches
    expected_dtypes = expected.get("dtypes", {})
    for col, expected_dtype in expected_dtypes.items():
        if col not in df.columns:
            continue  # Already reported as missing
        actual_dtype = str(df[col].dtype)
        if not _types_compatible(actual_dtype, expected_dtype):
            errors.append(
                f"Column '{col}': expected {expected_dtype}, got {actual_dtype}"
            )

    return CheckResult(passed=len(errors) == 0, errors=errors)


def _types_compatible(actual: str, expected: str) -> bool:
    """Check if actual dtype is compatible with expected dtype."""
    # Normalize type names
    actual = actual.lower()
    expected = expected.lower()

    # Direct match
    if actual == expected:
        return True

    # Int16/Int32/Int64 are compatible with each other and int64
    int_types = {"int16", "int32", "int64"}
    if actual in int_types and expected in int_types:
        return True

    # Float32/Float64 are compatible
    float_types = {"float32", "float64"}
    if actual in float_types and expected in float_types:
        return True

    # Nullable int types (Int16, Int32, Int64) compatible with non-nullable
    if actual.replace("int", "").isdigit() and expected.replace("int", "").isdigit():
        return True

    return False


def check_not_empty(df: pd.DataFrame) -> CheckResult:
    """
    Hard gate: Dataset must have rows.

    Args:
        df: DataFrame to validate

    Returns:
        CheckResult with pass/fail
    """
    if len(df) == 0:
        return CheckResult(passed=False, errors=["Dataset is empty (0 rows)"])
    return CheckResult(passed=True)


def check_no_duplicate_keys(df: pd.DataFrame, key_columns: list[str]) -> CheckResult:
    """
    Hard gate: No duplicate rows for the same key combination.

    Args:
        df: DataFrame to validate
        key_columns: Columns that form the unique key

    Returns:
        CheckResult with pass/fail
    """
    # Filter to only columns that exist
    existing_keys = [c for c in key_columns if c in df.columns]
    if not existing_keys:
        return CheckResult(passed=True)  # No keys to check

    dupes = df.duplicated(subset=existing_keys, keep=False)
    if dupes.any():
        count = dupes.sum()
        # Get a sample of duplicate keys
        sample = df[dupes][existing_keys].drop_duplicates().head(5)
        sample_str = sample.to_dict("records")
        return CheckResult(
            passed=False,
            errors=[f"{count} duplicate rows on {existing_keys}. Sample: {sample_str}"],
        )
    return CheckResult(passed=True)


def check_value_columns_populated(df: pd.DataFrame) -> CheckResult:
    """
    Hard gate: Value columns must have actual data, not all null.

    Args:
        df: DataFrame to validate

    Returns:
        CheckResult with pass/fail
    """
    errors = []
    value_cols = [c for c in df.columns if c.startswith("value_")]

    for col in value_cols:
        non_null = df[col].notna().sum()
        if non_null == 0:
            errors.append(f"Column '{col}' is entirely null ({len(df)} rows)")

    return CheckResult(passed=len(errors) == 0, errors=errors)


def check_value_bounds(df: pd.DataFrame) -> CheckResult:
    """
    Hard gate: Values must be within physically possible bounds.

    Args:
        df: DataFrame to validate

    Returns:
        CheckResult with pass/fail
    """
    errors = []
    value_cols = [c for c in df.columns if c.startswith("value_")]

    for col in value_cols:
        # Check for insanely large values (indicates unit error)
        max_val = df[col].max()
        if pd.notna(max_val) and max_val > MAX_SANE_VALUE:
            errors.append(
                f"Column '{col}' max value {max_val:,.0f} exceeds sanity limit {MAX_SANE_VALUE:,.0f}"
            )

    return CheckResult(passed=len(errors) == 0, errors=errors)


def check_name_mappings_complete(df: pd.DataFrame) -> CheckResult:
    """
    Hard gate: All codes must have corresponding names.

    Args:
        df: DataFrame to validate

    Returns:
        CheckResult with pass/fail
    """
    errors = []

    # Check donor mappings
    if "donor_code" in df.columns and "donor_name" in df.columns:
        unmapped = df[df["donor_name"].isna()]["donor_code"].unique()
        if len(unmapped) > 0:
            errors.append(f"Unmapped donor codes: {sorted(unmapped)[:10]}")

    # Check recipient mappings
    if "recipient_code" in df.columns and "recipient_name" in df.columns:
        unmapped = df[df["recipient_name"].isna()]["recipient_code"].unique()
        if len(unmapped) > 0:
            errors.append(f"Unmapped recipient codes: {sorted(unmapped)[:10]}")

    # Check indicator mappings
    if "indicator" in df.columns and "indicator_name" in df.columns:
        unmapped = df[df["indicator_name"].isna()]["indicator"].unique()
        if len(unmapped) > 0:
            errors.append(f"Unmapped indicator codes: {list(unmapped)[:10]}")

    return CheckResult(passed=len(errors) == 0, errors=errors)


def check_critical_dimensions(
    df: pd.DataFrame,
    expected_latest_year: int,
    critical_donors: list[int],
) -> CheckResult:
    """
    Hard gate: Critical donors and years must be present.

    Args:
        df: DataFrame to validate
        expected_latest_year: The latest year that must exist
        critical_donors: Donor codes that must have data

    Returns:
        CheckResult with pass/fail
    """
    errors = []

    # Check latest year exists
    if "year" in df.columns:
        years = df["year"].unique()
        if expected_latest_year not in years:
            errors.append(
                f"Missing latest year: {expected_latest_year}. Years present: {sorted(years)[-5:]}"
            )

    # Check critical donors exist
    if "donor_code" in df.columns:
        donors = set(df["donor_code"].unique())
        missing_donors = [d for d in critical_donors if d not in donors]
        if missing_donors:
            errors.append(f"Missing critical donors: {missing_donors}")

    return CheckResult(passed=len(errors) == 0, errors=errors)
