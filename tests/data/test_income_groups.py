"""Tests for the World Bank income groups the CRS views use, from resolvekit."""

import pandas as pd
import pytest
import resolvekit as rk

from src.data.analysis_tools import transformations
from src.data.analysis_tools.transformations import classify_income


def test_income_groups_and_ldcs():
    codes = pd.Series(["UKR", "AFG", "XKV", "SHN", "F_X", None])
    income, is_ldc = classify_income(codes)
    assert income.tolist() == [
        "Upper-Middle Income Countries (UMICs)",
        "Low Income Countries (LICs)",
        # The CRS spells Kosovo XKV; CRS_ISO3_OVERRIDES maps it to XKX.
        "Upper-Middle Income Countries (UMICs)",
        "Countries not classified by the World Bank",
        "Unallocated by income",
        "Unallocated by income",
    ]
    assert is_ldc.tolist() == [False, True, False, False, False, False]


def test_an_ambiguous_code_outside_the_overrides_raises(monkeypatch):
    real = rk.default()

    class AmbiguousOnZZZ:
        """Delegates to resolvekit, but finds the made-up code ZZZ ambiguous."""

        def members_of(self, group: str, *, as_codes: str) -> list[str]:
            return real.members_of(group, as_codes=as_codes)

        def resolve(self, code: str, *, to: str) -> str | None:
            if code == "ZZZ":
                raise rk.AmbiguousResolutionError()
            return real.resolve(code, to=to)

    monkeypatch.setattr(transformations.rk, "default", AmbiguousOnZZZ)
    with pytest.raises(ValueError, match=r"\['ZZZ'\].*CRS_ISO3_OVERRIDES"):
        classify_income(pd.Series(["AFG", "ZZZ"]))


def test_the_overrides_settle_a_code_before_resolvekit(monkeypatch):
    monkeypatch.setitem(transformations.CRS_ISO3_OVERRIDES, "ZZZ", None)
    income, _ = classify_income(pd.Series(["ZZZ"]))
    assert income.tolist() == ["Unallocated by income"]
