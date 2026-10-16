"""Tests for the World Bank income groups the CRS views use, from resolvekit."""

import pandas as pd

from src.data.analysis_tools.transformations import classify_income


def test_income_groups_and_ldcs():
    codes = pd.Series(["UKR", "AFG", "XKV", "SHN", "F_X", None])
    income, is_ldc = classify_income(codes)
    assert income.tolist() == [
        "Upper-Middle Income Countries (UMICs)",
        "Low Income Countries (LICs)",
        # The CRS spells Kosovo XKV; resolvekit resolves it to XKX.
        "Upper-Middle Income Countries (UMICs)",
        "Countries not classified by the World Bank",
        "Unallocated by income",
        "Unallocated by income",
    ]
    assert is_ldc.tolist() == [False, True, False, False, False, False]
