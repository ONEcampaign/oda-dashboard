"""Cross-view checks: the dashboard views against the topic_page outputs.

The topic page and the dashboard read the same OECD data through different code, so where
they publish the same figure they should agree. Each comparison is a declarative CrossCheck:
an extractor for the topic_page side, one for the view side, both returning a long frame
keyed by some of ``year``, ``donor``, ``recipient`` and ``indicator`` with a ``value``
column, and a tolerance. The topic side is the reference: every topic row must have a view
counterpart within tolerance; view rows the topic does not publish are ignored.

Every result is non-blocking. A mismatch matched by an expected_deltas.toml entry with
``view = "cross_view"`` is reported as INFO with the entry's reason; anything else is an
ERROR. The ``indicator`` coordinate given to the matcher is the comparison's own label (a
sector name, an indicator, or the CrossCheck name when it has no such dimension).

Units: amounts are USD millions, shares are fractions.

``cross_view.provenance_consistency`` is the one check that does not involve the topic page:
every view whose options.json carries ``provenance`` (written by the oda-data 3 loaders) must
have read each table it shares with another view at the same release token.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import pandas as pd

from src.data.analysis_tools.naming import slugify
from src.data.config import (
    BILATERAL,
    DAC_COUNTRIES_NAME,
    GRANT_EQUIVALENT_START_YEAR,
    IMPUTED_MULTILATERAL,
    ODA_ELIGIBLE,
    RECIPIENT_NAME_OVERRIDES,
    SECTORS_TIME,
    TOTAL_ODA,
)
from src.data.validation.expected import DeltaKind, ExpectedDelta, find_explanation
from src.data.validation.io import (
    load_topic_page,
    load_view,
    parse_amount,
    read_hive_files,
    read_options,
    resolve_source,
)
from src.data.validation.models import CheckResult, Severity
from src.data.validation.views import get_spec

VIEW: str = "cross_view"
CHECK_PREFIX: str = "cross_view"

KEY_COLUMNS: tuple[str, ...] = ("year", "donor", "recipient", "indicator")
VALUE: str = "value"
TOPIC: str = "topic"
CANDIDATE: str = "view"

UNITS_PER_MILLION: float = 1e6
MILLIONS_PER_BILLION: float = 1e3
PERCENT: float = 100.0

# The topic page names the DAC aggregate differently in its sector and DAC2A outputs.
TOPIC_DAC_TOTAL: str = "DAC Countries, Total"
# Amount floor for the billions-rounded topic series: half of 0.1bn rounding, doubled.
BILLIONS_ROUNDING_FLOOR: float = 0.05 * MILLIONS_PER_BILLION

AFRICA: str = "Africa"
# Topic income group label -> recipients view name (the same DAC2A codes, 10045-10048).
# "Not classified by income" (DAC2A 10024 + 10049) has no counterpart, as the view drops 10024.
TOPIC_INCOME_GROUPS: dict[str, str] = {
    "Low income": RECIPIENT_NAME_OVERRIDES[10_045],
    "Lower-middle income": RECIPIENT_NAME_OVERRIDES[10_046],
    "Upper-middle income": RECIPIENT_NAME_OVERRIDES[10_047],
    "High income": RECIPIENT_NAME_OVERRIDES[10_048],
}
SECTOR_SHARE_COLUMNS: tuple[str, ...] = (
    "Humanitarian",
    "Education",
    "Health",
    "Refugees in Donor Countries",
    "Environment Protection",
)

type TopicReader = Callable[[str], pd.DataFrame]


@dataclass(frozen=True)
class Tolerance:
    """How far the view may sit from the topic value: max(absolute, relative × |topic|).

    Attributes:
        absolute: In the comparison's unit (USD millions or a fraction).
        relative: A fraction of the topic value.
    """

    absolute: float = 0.0
    relative: float = 0.0

    def allows(self, topic: pd.Series, view: pd.Series) -> pd.Series:
        """Whether each view value is within tolerance of its topic value."""
        limit = (topic.abs() * self.relative).clip(lower=self.absolute)
        return (view - topic).abs() <= limit


class ViewReader:
    """Loads each view at most once per run, and sectors only at one recipient."""

    def __init__(self, sources: dict[str, Path]) -> None:
        """Remember where each view lives; nothing is read until asked for.

        Args:
            sources: View name -> source directory, as io.default_sources() returns.
        """
        self._sources = sources
        self._loaded: dict[str, pd.DataFrame] = {}

    def source(self, name: str) -> Path:
        """A view's source directory.

        Raises:
            KeyError: No source given for the view.
        """
        if name not in self._sources:
            raise KeyError(f"No source given for {name}")
        return self._sources[name]

    def data(self, name: str) -> pd.DataFrame:
        """A whole flat view's rows (not for sectors_view, which is too large)."""
        if name not in self._loaded:
            self._loaded[name] = load_view(name, self.source(name)).data
        return self._loaded[name]

    @cached_property
    def sectors_oda_eligible(self) -> pd.DataFrame:
        """sectors_view rows for every donor at "ODA eligible countries".

        Reads only that recipient's partition of each donor, a few thousand rows, instead of
        the whole multi-million-row view.

        Raises:
            FileNotFoundError: No such partitions under the sectors source.
        """
        source = self.source("sectors_view")
        if (source / "sectors_view").is_dir():
            source = source / "sectors_view"
        pattern = f"donor_slug=*/recipient_slug={slugify(ODA_ELIGIBLE)}/*.parquet"
        files = sorted(source.glob(pattern))
        if not files:
            raise FileNotFoundError(f"No {pattern} under {source}")
        return read_hive_files(source, files, get_spec("sectors_view"))


@dataclass(frozen=True)
class CrossCheck:
    """One topic_page figure compared with the view that should reproduce it.

    Attributes:
        name: Short name; the check is reported as "cross_view.<name>".
        topic: Reads the topic side, returning the keys plus ``value``.
        view: Reads the view side from a ViewReader, returning the same keys plus ``value``.
        keys: The KEY_COLUMNS both sides carry.
        tolerance: Allowed difference.
        note: What is compared and how, for the report.
        unit: "USD mn" or "share", for messages.
    """

    name: str
    topic: Callable[[TopicReader], pd.DataFrame]
    view: Callable[[ViewReader], pd.DataFrame]
    keys: tuple[str, ...]
    tolerance: Tolerance
    note: str
    unit: str = "USD mn"
    check: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate the keys and derive the reported check name."""
        unknown = set(self.keys) - set(KEY_COLUMNS)
        if unknown or "year" not in self.keys:
            raise ValueError(
                f"{self.name}: keys must include 'year' and be from {KEY_COLUMNS}, "
                f"got {self.keys}"
            )
        object.__setattr__(self, "check", f"{CHECK_PREFIX}.{self.name}")


# ---------------------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------------------


def _numbers(series: pd.Series) -> pd.Series:
    """Parse bare numeric strings ("1,234.5"), with empty strings as NaN.

    Raises:
        ValueError: A non-empty cell is not a number.
    """
    cleaned = series.str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(cleaned.where(cleaned != ""))


def _percent_strings(series: pd.Series) -> pd.Series:
    """Parse "26.8%" strings (possibly still quoted) into fractions."""
    cleaned = series.str.strip().str.strip('"').str.rstrip("%")
    return _numbers(cleaned) / PERCENT


def _latest_year(first_line: str) -> int:
    """The year in a small-multiple header such as "As of 2025".

    Raises:
        ValueError: The line does not end in a year.
    """
    token = first_line.rsplit(" ", 1)[-1]
    if not token.isdigit():
        raise ValueError(f"No year at the end of {first_line!r}")
    return int(token)


def _single_row(df: pd.DataFrame, name: str) -> pd.Series:
    """The only row of a one-row topic file.

    Raises:
        ValueError: The file does not have exactly one row.
    """
    if len(df) != 1:
        raise ValueError(f"{name} should have one row, has {len(df)}")
    return df.iloc[0]


def _require_columns(df: pd.DataFrame, columns: list[str], name: str) -> None:
    """Raise ValueError naming any of columns missing from df."""
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{name} is missing columns {missing}")


# ---------------------------------------------------------------------------------------
# Topic extractors
# ---------------------------------------------------------------------------------------


def topic_total_oda(read: TopicReader) -> pd.DataFrame:
    """oda_gni_ts "ODA (left-axis)": USD mn, constant 2025, DAC and members, by year."""
    df = read("oda_gni_ts")
    _require_columns(df, ["name", "year", "ODA (left-axis)"], "oda_gni_ts")
    return pd.DataFrame(
        {
            "year": df["year"].astype(int),
            "donor": df["name"],
            VALUE: _numbers(df["ODA (left-axis)"]),
        }
    ).dropna(subset=[VALUE])


def topic_total_oda_latest(read: TopicReader) -> pd.DataFrame:
    """sm_total_oda: DAC Total ODA in the latest year, USD units -> USD mn, constant 2025."""
    row = _single_row(read("sm_total_oda"), "sm_total_oda")
    return pd.DataFrame(
        {
            "year": [_latest_year(row["first_line"])],
            "donor": [DAC_COUNTRIES_NAME],
            VALUE: [float(row["value"]) / UNITS_PER_MILLION],
        }
    )


def topic_oda_gni(read: TopicReader) -> pd.DataFrame:
    """oda_gni_ts "ODA/GNI (right-axis)", a percentage rounded to 2 dp, as a fraction.

    EU Institutions has no GNI, so its empty cells are left out.
    """
    df = read("oda_gni_ts")
    _require_columns(df, ["name", "year", "ODA/GNI (right-axis)"], "oda_gni_ts")
    return pd.DataFrame(
        {
            "year": df["year"].astype(int),
            "donor": df["name"],
            VALUE: _numbers(df["ODA/GNI (right-axis)"]) / PERCENT,
        }
    ).dropna(subset=[VALUE])


def topic_oda_gni_latest(read: TopicReader) -> pd.DataFrame:
    """oda_gni_sm: DAC ODA/GNI in the latest year, already a fraction."""
    row = _single_row(read("oda_gni_sm"), "oda_gni_sm")
    return pd.DataFrame(
        {
            "year": [_latest_year(row["first_line"])],
            "donor": [DAC_COUNTRIES_NAME],
            VALUE: [float(row["oda_gni"])],
        }
    )


def topic_sector_shares(read: TopicReader) -> pd.DataFrame:
    """key_sector_shares: key sectors' shares of bilateral + imputed multilateral ODA.

    Long by (year, donor, sector), from SECTORS_TIME's start year (the view starts there),
    with the DAC total renamed to the views' name.
    """
    df = read("key_sector_shares")
    _require_columns(df, ["Year", "name", *SECTOR_SHARE_COLUMNS], "key_sector_shares")
    long = df.melt(
        id_vars=["Year", "name"],
        value_vars=list(SECTOR_SHARE_COLUMNS),
        var_name="indicator",
        value_name=VALUE,
    )
    long = pd.DataFrame(
        {
            "year": long["Year"].astype(int),
            "donor": long["name"].replace({TOPIC_DAC_TOTAL: DAC_COUNTRIES_NAME}),
            "indicator": long["indicator"],
            VALUE: _numbers(long[VALUE]),
        }
    )
    return long[long["year"] >= SECTORS_TIME["start"]].dropna(subset=[VALUE])


def _topic_sector_amount(
    file: str, value_column: str
) -> Callable[[TopicReader], pd.DataFrame]:
    """Build an extractor for aid_to_{health,humanitarian}_ts: bn constant 2024 -> USD mn.

    The topic series starts in 2010; years before SECTORS_TIME's start are left out, since
    the sectors view does not publish them.
    """

    def extract(read: TopicReader) -> pd.DataFrame:
        df = read(file)
        _require_columns(df, ["Year", "Donor", "Sector", value_column], file)
        long = pd.DataFrame(
            {
                "year": df["Year"].astype(int),
                "donor": df["Donor"].replace({TOPIC_DAC_TOTAL: DAC_COUNTRIES_NAME}),
                "indicator": df["Sector"],
                VALUE: _numbers(df[value_column]) * MILLIONS_PER_BILLION,
            }
        )
        return long[long["year"] >= SECTORS_TIME["start"]]

    extract.__doc__ = f"{file} {value_column!r}, USD mn constant 2024."
    return extract


def topic_africa_share(read: TopicReader) -> pd.DataFrame:
    """aid_to_africa_ts "Share of total ODA": DAC aid to Africa / to developing countries."""
    df = read("aid_to_africa_ts")
    _require_columns(df, ["Year", "Donor", "Share of total ODA"], "aid_to_africa_ts")
    return pd.DataFrame(
        {
            "year": df["Year"].astype(int),
            "donor": df["Donor"].replace({TOPIC_DAC_TOTAL: DAC_COUNTRIES_NAME}),
            "recipient": AFRICA,
            VALUE: _percent_strings(df["Share of total ODA"]),
        }
    )


def topic_income_groups(read: TopicReader) -> pd.DataFrame:
    """aid_to_income_latest "ODA" ("US$27.0 billion"), USD mn constant 2024.

    Only the four World Bank income groups; "Not classified by income" has no view
    counterpart.
    """
    df = read("aid_to_income_latest")
    _require_columns(df, ["Year", "Donor", "Recipient", "ODA"], "aid_to_income_latest")
    df = df[df["Recipient"].isin(TOPIC_INCOME_GROUPS)]
    return pd.DataFrame(
        {
            "year": df["Year"].astype(int),
            "donor": df["Donor"].replace({TOPIC_DAC_TOTAL: DAC_COUNTRIES_NAME}),
            "recipient": df["Recipient"].map(TOPIC_INCOME_GROUPS),
            VALUE: df["ODA"].map(parse_amount),
        }
    )


# ---------------------------------------------------------------------------------------
# View extractors
# ---------------------------------------------------------------------------------------


def _financing_total_oda(views: ViewReader) -> pd.DataFrame:
    """financing Total ODA rows under the DAC's headline measure for each year.

    Flows before GRANT_EQUIVALENT_START_YEAR, grant equivalents from it, as the topic's
    ONE.10.1010_11010 reads.
    """
    df = views.data("financing_view")
    headline_type = (df["year"] >= GRANT_EQUIVALENT_START_YEAR).map(
        {True: "Grant equivalents", False: "Flows"}
    )
    return df[(df["indicator_name"] == TOTAL_ODA) & (df["type"] == headline_type)]


def view_total_oda(views: ViewReader) -> pd.DataFrame:
    """financing Total ODA value_usd_constant (base 2025), USD mn, every donor and year."""
    df = _financing_total_oda(views)
    return pd.DataFrame(
        {
            "year": df["year"].astype(int),
            "donor": df["donor_name"].astype(str),
            VALUE: df["value_usd_constant"] / UNITS_PER_MILLION,
        }
    )


def view_oda_gni(views: ViewReader) -> pd.DataFrame:
    """financing Total ODA pct_of_gni (a fraction), every donor and year."""
    df = _financing_total_oda(views)
    return pd.DataFrame(
        {
            "year": df["year"].astype(int),
            "donor": df["donor_name"].astype(str),
            VALUE: df["pct_of_gni"].astype(float),
        }
    )


def _sectors_by_donor_sector(views: ViewReader) -> pd.DataFrame:
    """sectors constant USD at ODA eligible countries, both indicators, per donor/year/sector."""
    df = views.sectors_oda_eligible
    df = df[df["indicator_name"].isin([BILATERAL, IMPUTED_MULTILATERAL])]
    return (
        df.groupby(["year", "donor_name", "sector_name"], observed=True)[
            "value_usd_constant"
        ]
        .sum()
        .reset_index()
        .rename(columns={"donor_name": "donor", "sector_name": "indicator"})
        .astype({"year": int, "donor": str, "indicator": str})
    )


def view_sector_shares(views: ViewReader) -> pd.DataFrame:
    """Each sector's share of the donor-year total across sectors (constant 2024 USD)."""
    df = _sectors_by_donor_sector(views)
    total = df.groupby(["year", "donor"])["value_usd_constant"].transform("sum")
    return df.assign(**{VALUE: df["value_usd_constant"] / total}).drop(
        columns="value_usd_constant"
    )


def view_sector_amounts(views: ViewReader) -> pd.DataFrame:
    """Each sector's value_usd_constant (base 2024), USD mn, per donor and year."""
    df = _sectors_by_donor_sector(views)
    return df.assign(**{VALUE: df["value_usd_constant"] / UNITS_PER_MILLION}).drop(
        columns="value_usd_constant"
    )


def _recipients_both_indicators(
    views: ViewReader, recipients: list[str], column: str
) -> pd.DataFrame:
    """recipients view, Bilateral + Imputed multilateral summed, per year/donor/recipient."""
    df = views.data("recipients_view")
    df = df[
        df["recipient_name"].isin(recipients)
        & df["indicator_name"].isin([BILATERAL, IMPUTED_MULTILATERAL])
    ]
    return (
        df.groupby(["year", "donor_name", "recipient_name"], observed=True)[column]
        .sum(min_count=1)
        .reset_index()
        .rename(
            columns={
                "donor_name": "donor",
                "recipient_name": "recipient",
                column: VALUE,
            }
        )
        .astype({"year": int, "donor": str, "recipient": str})
    )


def view_africa_share(views: ViewReader) -> pd.DataFrame:
    """Africa / ODA eligible countries in value_usd_current, per donor and year."""
    df = _recipients_both_indicators(views, [AFRICA, ODA_ELIGIBLE], "value_usd_current")
    wide = df.pivot(index=["year", "donor"], columns="recipient", values=VALUE)
    if AFRICA not in wide or ODA_ELIGIBLE not in wide:
        raise ValueError(f"recipients_view lacks {AFRICA!r} or {ODA_ELIGIBLE!r} rows")
    return (
        (wide[AFRICA] / wide[ODA_ELIGIBLE])
        .rename(VALUE)
        .reset_index()
        .assign(recipient=AFRICA)
    )


def view_income_groups(views: ViewReader) -> pd.DataFrame:
    """Income group value_usd_constant (base 2024), USD mn, per donor and year."""
    df = _recipients_both_indicators(
        views, list(TOPIC_INCOME_GROUPS.values()), "value_usd_constant"
    )
    return df.assign(**{VALUE: df[VALUE] / UNITS_PER_MILLION})


# ---------------------------------------------------------------------------------------
# The comparisons
# ---------------------------------------------------------------------------------------

CROSS_CHECKS: tuple[CrossCheck, ...] = (
    CrossCheck(
        name="total_oda",
        topic=topic_total_oda,
        view=view_total_oda,
        keys=("year", "donor"),
        tolerance=Tolerance(relative=0.005),
        note="oda_gni_ts ODA vs financing Total ODA, constant 2025 USD mn; flows "
        "before 2018, grant equivalents from 2018.",
    ),
    CrossCheck(
        name="total_oda_latest",
        topic=topic_total_oda_latest,
        view=view_total_oda,
        keys=("year", "donor"),
        tolerance=Tolerance(relative=0.005),
        note="sm_total_oda (DAC, latest year) vs financing Total ODA, constant 2025.",
    ),
    CrossCheck(
        name="oda_gni",
        topic=topic_oda_gni,
        view=view_oda_gni,
        keys=("year", "donor"),
        tolerance=Tolerance(absolute=0.0001),
        note="oda_gni_ts ODA/GNI (percent, 2 dp) vs financing Total ODA pct_of_gni.",
        unit="share",
    ),
    CrossCheck(
        name="oda_gni_latest",
        topic=topic_oda_gni_latest,
        view=view_oda_gni,
        keys=("year", "donor"),
        tolerance=Tolerance(absolute=0.0001),
        note="oda_gni_sm (DAC, latest year) vs financing Total ODA pct_of_gni.",
        unit="share",
    ),
    CrossCheck(
        name="sector_shares",
        topic=topic_sector_shares,
        view=view_sector_shares,
        keys=("year", "donor", "indicator"),
        tolerance=Tolerance(absolute=0.002),
        note="key_sector_shares vs sectors view at ODA eligible countries: sector / all "
        "sectors, bilateral + imputed multilateral, constant 2024 USD. Known cause of the "
        "~1.24x gap: key_sector_shares.csv was written 2026-06-16 with oda-data 2.5.0, "
        "whose CRSData kept bi_multi == 2 rows (DAC members' core contributions to "
        "multilaterals, all at recipient 9998), so its all-sectors denominator also counts "
        "them (DAC 2023: 314bn vs the view's 255bn; those rows sum to 63bn, 2013: 43bn vs "
        "a 38bn gap). Sector amounts agree; regenerating the topic CSVs clears it.",
        unit="share",
    ),
    CrossCheck(
        name="health",
        topic=_topic_sector_amount("aid_to_health_ts", "Total aid to health"),
        view=view_sector_amounts,
        keys=("year", "donor", "indicator"),
        tolerance=Tolerance(absolute=BILLIONS_ROUNDING_FLOOR, relative=0.01),
        note="aid_to_health_ts vs sectors view Health, DAC countries at ODA eligible "
        "countries, both indicators, constant 2024 USD mn.",
    ),
    CrossCheck(
        name="humanitarian",
        topic=_topic_sector_amount("aid_to_humanitarian_ts", "Total Humanitarian Aid"),
        view=view_sector_amounts,
        keys=("year", "donor", "indicator"),
        tolerance=Tolerance(absolute=BILLIONS_ROUNDING_FLOOR, relative=0.01),
        note="aid_to_humanitarian_ts vs sectors view Humanitarian, DAC countries at ODA "
        "eligible countries, both indicators, constant 2024 USD mn.",
    ),
    CrossCheck(
        name="africa_share",
        topic=topic_africa_share,
        view=view_africa_share,
        keys=("year", "donor", "recipient"),
        tolerance=Tolerance(absolute=0.005),
        note="aid_to_africa_ts share vs recipients view Africa / ODA eligible countries, "
        "DAC countries, both indicators, current USD (a share needs no base year).",
        unit="share",
    ),
    CrossCheck(
        name="income_groups",
        topic=topic_income_groups,
        view=view_income_groups,
        keys=("year", "donor", "recipient"),
        tolerance=Tolerance(absolute=BILLIONS_ROUNDING_FLOOR, relative=0.02),
        note="aid_to_income_latest (latest year) vs recipients view income "
        "groups, DAC countries, both indicators, constant 2024 USD mn. Known cause of the "
        "Low income gap (topic 27.0bn vs view 31.3bn, 2024): the topic CSV was written "
        "2026-06-17 from an earlier DAC2A release; today's DAC2A query for provider 20001 "
        "returns 31.25bn, so the view is current and the topic CSV is stale.",
    ),
)


# ---------------------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------------------


def compare(spec: CrossCheck, topic: pd.DataFrame, view: pd.DataFrame) -> pd.DataFrame:
    """Join the two sides on the spec's keys and flag each topic row.

    Args:
        spec: The comparison.
        topic: Topic rows (keys + value). Duplicate keys raise.
        view: View rows (keys + value); rows the topic lacks are dropped.

    Returns:
        One row per topic row: the keys, ``topic``, ``view`` (NaN when the view has no
        such row), ``diff``, ``rel_diff`` and ``within`` (False when the view row is
        missing).

    Raises:
        ValueError: Duplicate keys on either side.
    """
    keys = list(spec.keys)
    for side, df in (("topic", topic), ("view", view)):
        dupes = df.duplicated(keys)
        if dupes.any():
            raise ValueError(
                f"{spec.name}: duplicate {side} keys, e.g. "
                f"{df.loc[dupes, keys].head(3).to_dict('records')}"
            )
    merged = topic[[*keys, VALUE]].merge(
        view[[*keys, VALUE]],
        on=keys,
        how="left",
        suffixes=(f"_{TOPIC}", f"_{CANDIDATE}"),
    )
    merged = merged.rename(
        columns={f"{VALUE}_{TOPIC}": TOPIC, f"{VALUE}_{CANDIDATE}": CANDIDATE}
    )
    merged["diff"] = merged[CANDIDATE] - merged[TOPIC]
    merged["rel_diff"] = merged["diff"] / merged[TOPIC].abs()
    merged["within"] = merged[CANDIDATE].notna() & spec.tolerance.allows(
        merged[TOPIC], merged[CANDIDATE]
    )
    return merged.sort_values(keys).reset_index(drop=True)


def _explain(
    row: pd.Series, spec: CrossCheck, expected: list[ExpectedDelta]
) -> ExpectedDelta | None:
    """The expected delta explaining one out-of-tolerance row, if any."""
    missing = pd.isna(row[CANDIDATE])
    rel_diff = None if missing or pd.isna(row["rel_diff"]) else float(row["rel_diff"])
    return find_explanation(
        expected,
        view=VIEW,
        kind=DeltaKind.MISSING_IN_CANDIDATE if missing else DeltaKind.VALUE,
        year=int(row["year"]),
        donor=row.get("donor"),
        recipient=row.get("recipient"),
        indicator=row.get("indicator", spec.name),
        rel_diff=rel_diff,
    )


def _results_for(
    spec: CrossCheck, compared: pd.DataFrame, expected: list[ExpectedDelta]
) -> list[CheckResult]:
    """Turn one comparison's rows into results: a pass, explained INFOs, one ERROR."""
    if compared.empty:
        return [
            _result(
                spec, passed=False, severity=Severity.ERROR, message="no topic rows"
            )
        ]

    outside = compared[~compared["within"]]
    if outside.empty:
        return [
            _result(
                spec,
                passed=True,
                severity=Severity.ERROR,
                message=f"{len(compared)} values within tolerance. {spec.note}",
            )
        ]

    explanations = pd.Series(
        [_explain(row, spec, expected) for _, row in outside.iterrows()],
        index=outside.index,
        dtype=object,
    )
    results: list[CheckResult] = []
    for entry in dict.fromkeys(e for e in explanations if e is not None):
        rows = outside[explanations.map(lambda e, entry=entry: e == entry)]
        results.append(
            _result(
                spec,
                passed=False,
                severity=Severity.INFO,
                message=f"{len(rows)} of {len(compared)} values outside tolerance, "
                f"explained ({entry.reason})",
                details=rows,
            )
        )

    unexplained = outside[explanations.isna()]
    if not unexplained.empty:
        missing = int(unexplained[CANDIDATE].isna().sum())
        worst_text = _largest_gap(spec, unexplained)
        results.append(
            _result(
                spec,
                passed=False,
                severity=Severity.ERROR,
                message=f"{len(unexplained)} of {len(compared)} values outside "
                f"tolerance ({missing} missing from the view){worst_text}. {spec.note}",
                details=unexplained,
            )
        )
    return results


def _largest_gap(spec: CrossCheck, rows: pd.DataFrame) -> str:
    """Describe the largest gap among rows, or "" if none of them has a view value."""
    if not rows["diff"].notna().any():
        return ""
    worst = rows.loc[rows["diff"].abs().idxmax()]
    where = " ".join(str(worst[k]) for k in spec.keys)
    return (
        f"; largest: {where} topic {worst[TOPIC]:,.4f} vs view {worst[CANDIDATE]:,.4f} "
        f"{spec.unit} ({worst['rel_diff']:+.2%})"
    )


def _result(
    spec: CrossCheck,
    *,
    passed: bool,
    severity: Severity,
    message: str,
    details: pd.DataFrame | None = None,
) -> CheckResult:
    """A non-blocking cross-view CheckResult."""
    return CheckResult(
        check=spec.check,
        view=VIEW,
        passed=passed,
        severity=severity,
        message=message,
        details=None if details is None else details.reset_index(drop=True),
        blocking=False,
    )


def run_check(
    spec: CrossCheck,
    views: ViewReader,
    expected: list[ExpectedDelta],
    read_topic: TopicReader = load_topic_page,
) -> list[CheckResult]:
    """Run one comparison; a side that cannot be read becomes an ERROR result.

    Args:
        spec: The comparison.
        views: The views to read from.
        expected: Expected deltas; only ``view = "cross_view"`` entries can match.
        read_topic: Reads a topic_page file by name as raw strings.
    """
    try:
        topic = spec.topic(read_topic)
        view = spec.view(views)
        compared = compare(spec, topic, view)
    except (FileNotFoundError, KeyError, ValueError) as e:
        return [
            _result(
                spec,
                passed=False,
                severity=Severity.ERROR,
                message=f"could not run: {type(e).__name__}: {e}",
            )
        ]
    return _results_for(spec, compared, expected)


PROVENANCE_KEY: str = "provenance"
PROVENANCE_CHECK: str = f"{CHECK_PREFIX}.provenance_consistency"


def _provenance_result(
    *,
    passed: bool,
    severity: Severity,
    message: str,
    details: pd.DataFrame | None = None,
) -> CheckResult:
    """A non-blocking provenance_consistency CheckResult."""
    return CheckResult(
        check=PROVENANCE_CHECK,
        view=VIEW,
        passed=passed,
        severity=severity,
        message=message,
        details=details,
        blocking=False,
    )


def _table_tokens(provenance: object) -> dict[str, str]:
    """Table -> release token from one view's provenance block.

    Raises:
        ValueError: The block is not shaped like ProvenanceLog.to_dict().
    """
    tables = provenance.get("tables") if isinstance(provenance, dict) else None
    if not isinstance(tables, dict):
        raise ValueError("provenance has no 'tables' object")
    tokens = {}
    for table, release in tables.items():
        token = release.get("token") if isinstance(release, dict) else None
        if not isinstance(token, str):
            raise ValueError(f"provenance table {table!r} has no token")
        tokens[table] = token
    return tokens


def check_provenance_consistency(sources: dict[str, Path]) -> list[CheckResult]:
    """Check that every view with provenance read each shared table at one release.

    Args:
        sources: View name -> source directory.

    Returns:
        Non-blocking results: an ERROR for each view whose options cannot be read or whose
        provenance is malformed, a passed INFO naming views without provenance (skipped), and
        a pass or an ERROR listing the tables read at more than one token. Nothing when
        there are no sources.
    """
    if not sources:
        return []
    results: list[CheckResult] = []
    tokens: dict[str, dict[str, str]] = {}
    skipped: list[str] = []
    for name, source in sorted(sources.items()):
        try:
            _, options_path = resolve_source(name, source)
            provenance = read_options(options_path).get(PROVENANCE_KEY)
            if provenance is None:
                skipped.append(name)
                continue
            tokens[name] = _table_tokens(provenance)
        except (FileNotFoundError, ValueError) as e:
            results.append(
                _provenance_result(
                    passed=False,
                    severity=Severity.ERROR,
                    message=f"{name}: could not read provenance: {e}",
                )
            )

    if skipped:
        results.append(
            _provenance_result(
                passed=True,
                severity=Severity.INFO,
                message=f"skipped, no provenance in options.json: {', '.join(skipped)}",
            )
        )

    rows = pd.DataFrame(
        [
            {"table": table, "view": view, "token": token}
            for view, view_tokens in tokens.items()
            for table, token in view_tokens.items()
        ],
        columns=["table", "view", "token"],
    )
    per_table = rows.groupby("table")["token"].nunique()
    clashing = sorted(per_table[per_table > 1].index)
    if clashing:
        results.append(
            _provenance_result(
                passed=False,
                severity=Severity.ERROR,
                message=f"tables read at more than one release: {', '.join(clashing)}",
                details=rows[rows["table"].isin(clashing)].reset_index(drop=True),
            )
        )
    elif tokens:
        listed = ", ".join(
            f"{table} {token}"
            for table, token in rows.drop_duplicates("table")[["table", "token"]]
            .sort_values("table")
            .itertuples(index=False)
        )
        results.append(
            _provenance_result(
                passed=True,
                severity=Severity.ERROR,
                message=f"{len(tokens)} views agree on every shared table: {listed}",
            )
        )
    return results


def run_cross_view(
    sources: dict[str, Path],
    expected: list[ExpectedDelta],
    *,
    checks: tuple[CrossCheck, ...] = CROSS_CHECKS,
    read_topic: TopicReader = load_topic_page,
) -> list[CheckResult]:
    """Compare the views with the topic_page outputs.

    Args:
        sources: View name -> source directory (io.default_sources() or a baseline).
        expected: Expected deltas, as load_expected_deltas returns them.
        checks: The comparisons to run.
        read_topic: Reads a topic_page file by name as raw strings.

    Returns:
        Non-blocking results, at least one per comparison: a pass, INFO for explained
        mismatches (grouped by reason), and one ERROR for the unexplained ones. Then the
        provenance_consistency results.
    """
    views = ViewReader(sources)
    return [
        result
        for spec in checks
        for result in run_check(spec, views, expected, read_topic)
    ] + check_provenance_consistency(sources)
