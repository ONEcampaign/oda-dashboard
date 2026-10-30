"""Tests for the view invariants."""

from pathlib import Path

import numpy as np
import pytest

from src.data.config import (
    ALL_BILATERAL_DONORS,
    DAC_COUNTRIES_NAME,
    EU27_COUNTRIES_NAME,
    EU27_EUI_NAME,
    ODA_ELIGIBLE,
)
from src.data.validation.invariants import (
    CURRENCY_RATIO_MIN_UNITS,
    ROUNDING_UNIT,
    SHARE_MIN,
    check_base_year_prices,
    check_currency_ratio,
    check_group_members_present,
    check_group_sums,
    check_recipient_sums,
    check_share_range,
    check_share_sums,
    run_invariants,
)
from src.data.validation.io import LoadedView, iter_partitions
from src.data.validation.models import CheckResult, Severity
from src.data.validation.views import get_spec
from tests.data.validation.conftest import MakeView, write_hive

YEAR = 2020
BASE_YEAR = get_spec("recipients_view").time["base"]
G7 = "G7 countries"
# Groups whose members, in these tests, are exactly France and Germany.
FRANCE_GERMANY_GROUPS = (
    ALL_BILATERAL_DONORS,
    DAC_COUNTRIES_NAME,
    EU27_COUNTRIES_NAME,
    G7,
)
MILLION = 1_000_000.0


def _row(donor: str, recipient: str, value: float, **extra: object) -> dict:
    """One recipients/gender row in 2020."""
    return {
        "year": YEAR,
        "donor_name": donor,
        "recipient_name": recipient,
        "indicator_name": "Bilateral",
        "value_usd_current": value,
        **extra,
    }


def _with_groups(
    rows: list[dict], groups: tuple[str, ...] = FRANCE_GERMANY_GROUPS
) -> list[dict]:
    """Add a row per group summing France and Germany for each recipient."""
    totals: dict[str, float] = {}
    for row in rows:
        totals[row["recipient_name"]] = (
            totals.get(row["recipient_name"], 0) + row["value_usd_current"]
        )
    return rows + [_row(g, r, v) for g in groups for r, v in totals.items()]


def _by_check(results: list[CheckResult]) -> dict[str, CheckResult]:
    """Results by check name."""
    return {r.check: r for r in results}


def _failed(results: list[CheckResult]) -> dict[str, CheckResult]:
    """Failed results by check name."""
    return {r.check: r for r in results if not r.passed}


@pytest.fixture
def members() -> list[dict]:
    """France and Germany to Kenya and Mali."""
    return [
        _row("France", "Kenya", 10 * MILLION),
        _row("France", "Mali", 20 * MILLION),
        _row("Germany", "Kenya", 30 * MILLION),
        _row("Germany", "Mali", 40 * MILLION),
    ]


def test_group_sums_pass(make_view: MakeView, members: list[dict]) -> None:
    """Groups equal to their members' sum pass; absent members are ignored."""
    view = make_view("recipients_view", _with_groups(members))
    [result] = check_group_sums(view)
    assert result.passed, result.message


# Two members plus the group: three rounded values, 50 units each.
TWO_MEMBER_ROUNDING = ROUNDING_UNIT / 2 * 3


@pytest.mark.parametrize(
    ("excess", "passed"),
    [
        (TWO_MEMBER_ROUNDING, True),
        (TWO_MEMBER_ROUNDING + 1, False),
    ],
)
def test_group_sum_tolerance(make_view: MakeView, excess: float, passed: bool) -> None:
    """A group may differ by 1e-6 relative + 50 units per value; beyond fails as ERROR."""
    rows = _with_groups(
        [_row("France", "Mali", 1000.0), _row("Germany", "Mali", 2000.0)]
    )
    rows[-1]["value_usd_current"] += excess  # G7, Mali; relative part ~0.006 units
    [result] = check_group_sums(make_view("recipients_view", rows))
    assert result.passed is passed
    if not passed:
        assert result.severity is Severity.ERROR and result.blocking
        assert result.details[["group", "recipient_name"]].values.tolist() == [
            [G7, "Mali"]
        ]


def test_group_sum_relative_tolerance(make_view: MakeView, members: list[dict]) -> None:
    """On large values the 1e-6 relative part adds to the rounding allowance."""
    rows = _with_groups(members)
    allowed = 1e-6 * 120 * MILLION + TWO_MEMBER_ROUNDING  # G7, Mali: 60M vs 60M
    rows[-1]["value_usd_current"] += allowed - 1
    assert check_group_sums(make_view("recipients_view", rows))[0].passed
    rows[-1]["value_usd_current"] += 2
    assert not check_group_sums(make_view("recipients_view", rows))[0].passed


def test_missing_group_row_counts_as_zero(
    make_view: MakeView, members: list[dict]
) -> None:
    """A group without a row where its members have values fails."""
    rows = [
        r
        for r in _with_groups(members)
        if not (r["donor_name"] == G7 and r["recipient_name"] == "Kenya")
    ]
    [result] = check_group_sums(make_view("recipients_view", rows))
    assert not result.passed
    assert result.details["group_value"].tolist() == [0.0]


def test_all_bilateral_is_dac_plus_non_dac(
    make_view: MakeView, members: list[dict]
) -> None:
    """All bilateral donors must equal DAC countries plus Non-DAC countries."""
    rows = _with_groups(members, (ALL_BILATERAL_DONORS, EU27_COUNTRIES_NAME, G7))
    rows += [_row(DAC_COUNTRIES_NAME, r, 1.0) for r in ("Kenya", "Mali")]
    [result] = check_group_sums(make_view("recipients_view", rows))
    assert set(result.details["group"]) == {DAC_COUNTRIES_NAME, ALL_BILATERAL_DONORS}


def test_eu27_eui_checked_in_gender_only(
    make_view: MakeView, members: list[dict]
) -> None:
    """EU27 & EU Institutions is a plain sum in gender but is not checked in recipients."""
    rows = _with_groups(members)
    rows = [{**r, "indicator_name": "Main target"} for r in rows]
    assert not check_group_sums(make_view("gender_view", rows))[0].passed
    assert check_group_sums(make_view("recipients_view", rows))[0].passed

    eui = [
        _row(EU27_EUI_NAME, r, v, indicator_name="Main target")
        for r, v in (("Kenya", 40 * MILLION), ("Mali", 60 * MILLION))
    ]
    assert check_group_sums(make_view("gender_view", rows + eui))[0].passed


def test_financing_skips_grants(make_view: MakeView) -> None:
    """Financing group sums skip Grants, whose group rows are not member sums."""
    rows = [
        {
            "year": YEAR,
            "donor_name": donor,
            "indicator_name": indicator,
            "type": "Flows",
            "value_usd_current": value,
        }
        for indicator in ("Total ODA", "Grants")
        for donor, value in (
            ("France", 1.0),
            ("Germany", 2.0),
            *((g, 3.0) for g in FRANCE_GERMANY_GROUPS),
        )
    ]
    rows[-1]["value_usd_current"] = 99.0  # G7 Grants
    assert check_group_sums(make_view("financing_view", rows))[0].passed


def test_group_members_present(make_view: MakeView, members: list[dict]) -> None:
    """Config members of a published group with no rows are a WARNING."""
    [result] = check_group_members_present(
        make_view("recipients_view", _with_groups(members))
    )
    assert not result.passed
    assert result.severity is Severity.WARNING and not result.blocking
    assert f"'{G7}': 5" in result.message
    g7 = result.details.loc[result.details["group"] == G7, "member"]
    assert set(g7) <= {"Canada", "Italy", "Japan", "United Kingdom", "United States"}


def _gender_recipients(eligible: float) -> list[dict]:
    """France to two countries, a region and ODA eligible countries."""
    return [
        {**_row("France", "Kenya", 10.0), "indicator_name": "Main target"},
        {**_row("France", "Mali", 20.0), "indicator_name": "Main target"},
        {**_row("France", "Africa", 30.0), "indicator_name": "Main target"},
        {**_row("France", ODA_ELIGIBLE, eligible), "indicator_name": "Main target"},
    ]


def test_recipient_sums_gender(make_view: MakeView) -> None:
    """In CRS views, ODA eligible countries equals its countries; groups are excluded.

    Two countries and the total: 150 units of rounding allowance (plus ~0 relative).
    """
    for eligible in (30.0, 30.0 + 150.0):
        view = make_view("gender_view", _gender_recipients(eligible))
        assert check_recipient_sums(view)[0].passed
    [result] = check_recipient_sums(make_view("gender_view", _gender_recipients(181.0)))
    assert not result.passed and result.severity is Severity.ERROR
    assert result.details["difference"].tolist() == [151.0]


@pytest.mark.parametrize(
    ("eligible", "failed"),
    [
        (1000.0, set()),
        (1005.0, set()),  # 0.5% short
        (1100.0, {"invariants.recipient_sum_gap"}),
        (850.0, set()),  # 150 over: within two countries' + the total's rounding
        (849.0, {"invariants.recipient_sum_overshoot"}),
    ],
)
def test_recipient_sums_recipients_view(
    make_view: MakeView, eligible: float, failed: set[str]
) -> None:
    """Recipients: never above the total (ERROR), short by at most 1% (WARNING)."""
    rows = [
        _row("France", "Kenya", 600.0),
        _row("France", "Africa, unspecified", 400.0),
        _row("France", "Africa", 1000.0),
        _row("France", ODA_ELIGIBLE, eligible),
    ]
    results = check_recipient_sums(make_view("recipients_view", rows))
    assert set(_failed(results)) == failed


def test_share_range_severity(make_view: MakeView) -> None:
    """Out-of-range shares are an ERROR for gender and a WARNING elsewhere."""
    rows = [
        _row(
            "France",
            "Kenya",
            1.0,
            pct_of_total_oda=1.5,
            pct_total_donor=SHARE_MIN - 0.5,
        )
    ]
    gender = _by_check(check_share_range(make_view("gender_view", rows)))
    recipients = _by_check(check_share_range(make_view("recipients_view", rows)))
    assert set(recipients) == {"invariants.share_range", "invariants.share_nulls"}
    gender_range = gender["invariants.share_range"]
    recipients_range = recipients["invariants.share_range"]
    assert gender_range.severity is Severity.ERROR and not gender_range.passed
    assert gender["invariants.share_range_net_flows"].passed
    assert recipients_range.severity is Severity.WARNING and not recipients_range.passed


def test_gender_share_range_net_flows(make_view: MakeView) -> None:
    """Gender: out-of-range shares in a group with a negative value are a WARNING."""
    net = [
        {**_row("France", "Kenya", v, pct_of_total_oda=s), "indicator_name": marker}
        for marker, v, s in (("Main target", -50.0, -1.0), ("Not targeted", 100.0, 2.0))
    ]
    gross = [_row("France", "Mali", 100.0, pct_of_total_oda=1.5)]
    results = _by_check(check_share_range(make_view("gender_view", net + gross)))
    gross_result = results["invariants.share_range"]
    net_result = results["invariants.share_range_net_flows"]
    assert gross_result.severity is Severity.ERROR and gross_result.blocking
    assert gross_result.details["recipient_name"].tolist() == ["Mali"]
    assert net_result.severity is Severity.WARNING and not net_result.blocking
    assert sorted(net_result.details["share"].tolist()) == [-1.0, 2.0]


def test_share_nulls_error_above_one_percent(make_view: MakeView) -> None:
    """Null shares are a WARNING, an ERROR above 1% of rows."""
    rows = [_row("France", f"R{i}", 1.0, pct_of_total_oda=0.5) for i in range(200)]
    rows[0]["pct_of_total_oda"] = np.nan
    nulls = _by_check(check_share_range(make_view("gender_view", rows)))
    assert nulls["invariants.share_nulls"].severity is Severity.WARNING
    assert not nulls["invariants.share_nulls"].passed

    rows[1]["pct_of_total_oda"] = rows[2]["pct_of_total_oda"] = np.nan
    nulls = _by_check(check_share_range(make_view("gender_view", rows)))
    assert nulls["invariants.share_nulls"].severity is Severity.ERROR


def _financing_row(donor: str, year: int, **extra: object) -> dict:
    """One financing Total ODA row."""
    return {
        "year": year,
        "donor_name": donor,
        "indicator_name": "Total ODA",
        "type": "Flows",
        "value_usd_current": 1.0,
        "pct_of_total_oda": 1.0,
        "pct_of_gni": 0.003,
        **extra,
    }


def test_gni_share_nulls_are_a_warning_by_donor(make_view: MakeView) -> None:
    """Null pct_of_gni is always a WARNING, counted per donor, and kept out of share_nulls."""
    rows = [_financing_row("France", y) for y in range(2000, 2021)]
    rows += [_financing_row("Kuwait", y, pct_of_gni=np.nan) for y in range(2000, 2021)]
    results = _by_check(check_share_range(make_view("financing_view", rows)))
    assert results["invariants.share_nulls"].passed
    gni = results["invariants.share_nulls_gni"]
    assert not gni.passed and gni.severity is Severity.WARNING and not gni.blocking
    assert "'Kuwait': 21" in gni.message


def test_gni_share_nulls_only_where_the_view_has_it(make_view: MakeView) -> None:
    """Views without pct_of_gni have no GNI null result."""
    results = _by_check(
        check_share_range(make_view("gender_view", [_row("A", "B", 1.0)]))
    )
    assert "invariants.share_nulls_gni" not in results


def test_gender_shares_sum_to_one(make_view: MakeView) -> None:
    """Gender marker shares sum to 1 per donor, recipient and year."""
    rows = [
        {
            **_row("France", "Kenya", 1.0, pct_of_total_oda=share),
            "indicator_name": marker,
        }
        for marker, share in (("Main target", 0.25), ("Not targeted", 0.75))
    ]
    assert check_share_sums(make_view("gender_view", rows))[0].passed
    rows[0]["pct_of_total_oda"] = 0.3
    [result] = check_share_sums(make_view("gender_view", rows))
    assert not result.passed
    assert result.details["off_by"].tolist() == [pytest.approx(0.05)]


def test_financing_total_share_is_one(make_view: MakeView) -> None:
    """Financing Total ODA has pct_of_total_oda 1; other indicators are not summed."""
    rows = [
        {
            "year": YEAR,
            "donor_name": "France",
            "indicator_name": indicator,
            "type": "Flows",
            "value_usd_current": 1.0,
            "pct_of_total_oda": share,
        }
        for indicator, share in (("Total ODA", 1.0), ("Grants", 0.7))
    ]
    assert check_share_sums(make_view("financing_view", rows))[0].passed


def _currency_rows(
    donor: str, ratios: tuple[float, float], value: float = CURRENCY_RATIO_MIN_UNITS
) -> list[dict]:
    """Two rows for a donor whose usd constant/current ratios are as given."""
    return [
        _row(donor, recipient, value, value_usd_constant=value * ratio)
        for recipient, ratio in zip(("Kenya", "Mali"), ratios, strict=True)
    ]


def test_currency_ratio(make_view: MakeView) -> None:
    """A second constant/current ratio within a donor-year is a WARNING, for USD only here."""
    view = make_view("recipients_view", _currency_rows("France", (1.1, 1.1001)))
    [result] = check_currency_ratio(view)
    assert not result.passed and result.severity is Severity.WARNING
    assert result.details[["donor_name", "currency"]].values.tolist() == [
        ["France", "USD"]
    ]

    assert check_currency_ratio(
        make_view("recipients_view", _currency_rows("France", (1.1, 1.1 + 1e-6)))
    )[0].passed


def test_currency_ratio_skips_aggregates_and_small_rows(make_view: MakeView) -> None:
    """Aggregate donors and rows under the size floor are not compared."""
    rows = _currency_rows(DAC_COUNTRIES_NAME, (1.1, 1.2)) + _currency_rows(
        "France", (1.1, 1.2), value=CURRENCY_RATIO_MIN_UNITS - 1
    )
    assert check_currency_ratio(make_view("recipients_view", rows))[0].passed


def test_base_year_prices(make_view: MakeView) -> None:
    """In the base year constant equals current; other years are not compared."""
    rows = [
        {
            **_row("France", "Kenya", MILLION, value_eur_constant=2 * MILLION),
            "year": BASE_YEAR,
        },
        _row("France", "Mali", MILLION, value_eur_constant=2 * MILLION),
    ]
    [result] = check_base_year_prices(make_view("recipients_view", rows))
    assert not result.passed and result.severity is Severity.ERROR
    assert result.details[["recipient_name", "currency"]].values.tolist() == [
        ["Kenya", "EUR"]
    ]


@pytest.mark.parametrize(("excess", "passed"), [(101.0, True), (102.0, False)])
def test_base_year_tolerance(make_view: MakeView, excess: float, passed: bool) -> None:
    """Base year: constant may differ from current by 1e-6 relative + one rounding unit."""
    allowed = 1e-6 * MILLION + ROUNDING_UNIT
    assert allowed == 101.0
    row = {
        **_row("France", "Kenya", MILLION, value_eur_constant=MILLION + excess),
        "year": BASE_YEAR,
    }
    [result] = check_base_year_prices(make_view("recipients_view", [row]))
    assert result.passed is passed


def test_check_returns_nothing_for_other_views(make_view: MakeView) -> None:
    """An invariant that does not apply to a view returns no result."""
    rows = [
        {
            "year": YEAR,
            "donor_name": "France",
            "indicator_name": "Total ODA",
            "type": "Flows",
            "value_usd_current": 1.0,
        }
    ]
    assert check_recipient_sums(make_view("financing_view", rows)) == []


def _sectors_view(make_view: MakeView) -> LoadedView:
    """A sectors view with groups, countries and ODA eligible, whose shares are consistent."""
    base = {
        "indicator_name": "Bilateral",
        "sector_name": "Health",
        "sub_sector_name": "Basic Health",
        "pct_total_donor": 0.0,
        "pct_total_recipient": 0.0,
    }
    rows = []
    for donor, kenya, mali in (("France", 1.0, 2.0), ("Germany", 3.0, 4.0)):
        total = kenya + mali
        rows += [
            {**_row(donor, "Kenya", kenya * MILLION), **base},
            {**_row(donor, "Mali", mali * MILLION), **base},
            {
                **_row(donor, ODA_ELIGIBLE, total * MILLION),
                **base,
                "pct_total_donor": 1.0,
            },
        ]
    for group in (*FRANCE_GERMANY_GROUPS, EU27_EUI_NAME):
        rows += [
            {**_row(group, "Kenya", 4 * MILLION), **base},
            {**_row(group, "Mali", 6 * MILLION), **base},
            {**_row(group, ODA_ELIGIBLE, 10 * MILLION), **base, "pct_total_donor": 1.0},
        ]
    rows[0]["pct_total_recipient"] = 2.0  # one out-of-range share
    rows[1]["value_usd_current"] += 500.0  # France, Mali: breaks two sums
    return make_view("sectors_view", rows)


def test_partitioned_run_matches_whole_view(
    make_view: MakeView, tmp_path: Path
) -> None:
    """Running over recipient partitions gives the same results as the whole view."""
    view = _sectors_view(make_view)
    hive = write_hive(view, tmp_path / "sectors_view")
    whole = run_invariants([view])
    parts = run_invariants(v for _, v in iter_partitions("sectors_view", hive))

    def summary(results: list[CheckResult]) -> list[tuple]:
        return [(r.check, r.passed, r.severity, r.message) for r in results]

    assert summary(parts) == summary(whole)
    assert set(_failed(whole)) == {
        "invariants.group_sums",
        "invariants.group_members_present",
        "invariants.recipient_sums",
        "invariants.share_range",
    }


def test_run_invariants_rejects_bad_parts(
    make_view: MakeView, members: list[dict]
) -> None:
    """No parts, or parts of two views, raise."""
    with pytest.raises(ValueError, match="at least one"):
        run_invariants([])
    recipients = make_view("recipients_view", members)
    gender = make_view("gender_view", members)
    with pytest.raises(ValueError, match="different views"):
        run_invariants([recipients, gender])
