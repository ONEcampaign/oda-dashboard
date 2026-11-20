"""The pipeline's one way into oda-data 3.0, oda-reader and pydeflate's DAC factors.

Every loader opens one ``oda.Context`` and runs its queries through ``run_query``, so each
result arrives with the same code dtypes and the repo's column names, its ``explain()`` text
is in the log, and its table releases are collected for ``options.json``. Currency
conversion reads its factors from the same DAC1 table through ``conversion_factors``.

The cache directory is resolved once, here: ``ODA_READER_CACHE_DIR`` if set, otherwise
``PATHS.DATA / "oda-reader"``. oda-data and oda-reader both read that environment variable,
so no call passes ``cache_dir=``.
"""

import os
import warnings
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path

import oda_data as oda
import oda_reader
import pandas as pd
import pydeflate

from src.data.config import CURRENCIES, PATHS, logger

_CACHE_ENV_VAR: str = "ODA_READER_CACHE_DIR"
ODA_CACHE_DIR: Path = Path(os.environ.get(_CACHE_ENV_VAR, PATHS.DATA / "oda-reader"))

# Columns oda-data 3.0 returns as strings holding numeric codes. They are cast to Int64.
CODE_COLUMNS: tuple[str, ...] = (
    "provider",
    "recipient",
    "sector",
    "channel",
    "line",
    "flow",
)

# Map from oda-data 3.0 column names to the names the loaders and transformations use.
# Columns not listed (recipient_name, broad_sector, score, allocation_status, ...) keep their names.
REPO_COLUMNS: dict[str, str] = {
    "provider": "donor_code",
    "provider_name": "donor_name",
    "recipient": "recipient_code",
    "sector": "purpose_code",
    "channel": "channel_code",
}

# DAC1 is the table pydeflate reads factors from.
_DAC1: str = "dac1"
_LIBRARIES: tuple[str, ...] = ("oda-data", "oda-reader", "pydeflate", "resolvekit")
PRICES: tuple[str, ...] = ("current", "constant")


def use_cache_dir() -> Path:
    """Point oda-reader (and so oda-data) at ODA_CACHE_DIR, creating it if needed.

    Must run before the first oda-reader access, because oda-reader reads the variable when
    it first resolves its cache root.

    Returns:
        The cache directory.
    """
    ODA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ[_CACHE_ENV_VAR] = str(ODA_CACHE_DIR)
    return ODA_CACHE_DIR


def scan_table(dataset: str, *, offline: bool = True) -> oda_reader.ScannedTable:
    """Return an oda-reader bulk table from the shared cache.

    Args:
        dataset: oda-reader dataset name, e.g. "crs" or "dac1".
        offline: Read only what the cache holds. CI registers every bulk file first.

    Returns:
        The scanned table, with its local parquet path and release.
    """
    use_cache_dir()
    return oda_reader.scan(dataset, offline=offline)


def scanned_release(table: oda_reader.ScannedTable) -> oda.Release:
    """The release of a scanned table, in the form query provenance records."""
    return oda.Release(
        token=table.release,
        downloaded=table.downloaded,
        label_release=table.label_release,
    )


def open_context(*, offline: bool = True) -> oda.Context:
    """Open the oda-data context every query of a loader runs in.

    Args:
        offline: Read only what the cache holds. CI registers every bulk file first.

    Returns:
        A context, to be used as a context manager.
    """
    use_cache_dir()
    return oda.Context(offline=offline)


def _release_dict(release: oda.Release) -> dict[str, str | None]:
    """Serialise a table release for JSON, the download time in ISO format."""
    return {
        "token": release.token,
        "downloaded": release.downloaded.isoformat(),
        "label_release": release.label_release,
    }


@dataclass
class ProvenanceLog:
    """The table releases, indicator versions and library versions behind one view.

    Each loader keeps one and passes it to every query and conversion, then writes
    ``to_dict()`` into its options as ``extra.provenance``. A view built from two releases
    of the same table would mix vintages, so recording a second token for a table raises.
    """

    tables: dict[str, oda.Release] = field(default_factory=dict)
    indicators: dict[str, int] = field(default_factory=dict)
    reference_data: str | None = None
    libraries: dict[str, str] = field(
        default_factory=lambda: {name: version(name) for name in _LIBRARIES}
    )

    def _add_table(self, table: str, release: oda.Release) -> None:
        """Record a table's release, raising if it differs from one already recorded."""
        held = self.tables.get(table)
        if held is not None and held.token != release.token:
            raise ValueError(
                f"Table {table!r} was read at two releases: {held.token!r} and "
                f"{release.token!r}. Pin one with oda.Context(releases=...)."
            )
        self.tables[table] = release

    def record(self, provenance: oda.Provenance) -> None:
        """Merge one query's provenance.

        Args:
            provenance: ``Query.provenance`` of the query just run.

        Raises:
            ValueError: If a table, indicator or the reference data was already recorded
                at another version.
        """
        for table, release in provenance.tables.items():
            self._add_table(table, release)
        for indicator, indicator_version in provenance.indicators.items():
            held = self.indicators.get(indicator)
            if held is not None and held != indicator_version:
                raise ValueError(
                    f"Indicator {indicator!r} ran at versions {held} and "
                    f"{indicator_version}."
                )
            self.indicators[indicator] = indicator_version
        held_reference = self.reference_data
        if held_reference is not None and held_reference != provenance.reference_data:
            raise ValueError(
                f"Reference data was read at two versions: {held_reference!r} and "
                f"{provenance.reference_data!r}."
            )
        self.reference_data = provenance.reference_data

    def record_table(self, table: str, release: oda.Release) -> None:
        """Record the release of a table read outside a query (scanned directly).

        Args:
            table: oda-reader dataset name, e.g. "dac1" for the conversion factors.
            release: From scanned_release.

        Raises:
            ValueError: If queries already recorded another release of the table.
        """
        self._add_table(table, release)

    def to_dict(self) -> dict[str, object]:
        """Return the log as JSON-ready values, datetimes in ISO format."""
        return {
            "tables": {
                table: _release_dict(release)
                for table, release in sorted(self.tables.items())
            },
            "indicators": dict(sorted(self.indicators.items())),
            "reference_data": self.reference_data,
            "libraries": self.libraries,
        }


def query(
    ctx: oda.Context,
    indicator: str,
    /,
    *,
    provenance: ProvenanceLog | None = None,
    **kwargs: object,
) -> oda.Query:
    """Build a query, run it, log what it read, and record its provenance.

    ``explain()`` executes the query and keeps the result, so logging it costs nothing
    extra. Every ``OdaDataWarning`` it raises (partial years, missing lines) reaches the log
    through ``logging.captureWarnings``, which config switches on. The filter here logs a
    repeat of an earlier warning text again.

    Args:
        ctx: From open_context.
        indicator: oda-data indicator id, e.g. "oecd.dac1.total_oda".
        provenance: Log to record the query's tables and versions in.
        **kwargs: Passed to ``ctx.query`` (years, providers, by, basis, ...).

    Returns:
        The executed query.
    """
    q = ctx.query(indicator, **kwargs)
    with warnings.catch_warnings():
        warnings.simplefilter("always", oda.OdaDataWarning)
        logger.info("%s:\n%s", indicator, q.explain())
    if provenance is not None:
        provenance.record(q.provenance)
    return q


def _to_int_codes(values: pd.Series, column: str) -> pd.Series:
    """Cast a column of numeric code strings to Int64, raising on any non-numeric code."""
    codes = pd.to_numeric(values, errors="coerce")
    bad = codes.isna() & values.notna()
    if bad.any():
        raise ValueError(
            f"{column} holds non-numeric codes: {sorted(values[bad].unique())[:10]}"
        )
    return codes.astype("Int64")


def to_repo_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Cast oda-data's code columns to Int64 and year to int, then use the repo's names.

    Args:
        df: A ``Query.to_pandas()`` result.

    Returns:
        The frame with integer codes and REPO_COLUMNS renamed where present.

    Raises:
        ValueError: If a code is not numeric or a year is missing.
    """
    df = df.copy()
    for column in CODE_COLUMNS:
        if column in df.columns:
            df[column] = _to_int_codes(df[column], column)
    if "year" in df.columns:
        if df["year"].isna().any():
            raise ValueError("oda-data returned rows with no year.")
        df["year"] = df["year"].astype("int64")
    return df.rename(columns=REPO_COLUMNS)


def run_query(
    ctx: oda.Context,
    indicator: str,
    /,
    *,
    provenance: ProvenanceLog | None = None,
    **kwargs: object,
) -> pd.DataFrame:
    """Run a query and return its result with integer codes and the repo's column names.

    Args:
        ctx: From open_context.
        indicator: oda-data indicator id.
        provenance: Log to record the query's tables and versions in.
        **kwargs: Passed to ``ctx.query``.

    Returns:
        The result, through to_repo_frame.
    """
    q = query(ctx, indicator, provenance=provenance, **kwargs)
    return to_repo_frame(q.to_pandas())


def _factor_units(
    currencies: Iterable[str], base_year: int
) -> list[tuple[str, str, int | None]]:
    """Every (currency, price, base year) to convert to, except USD current itself."""
    return [
        (currency, price, base_year if price == "constant" else None)
        for currency in currencies
        for price in PRICES
        if (currency, price) != ("USD", "current")
    ]


def conversion_factors(
    *,
    entities: Iterable[int],
    years: Iterable[int],
    base_year: int,
    currencies: Iterable[str] = CURRENCIES,
    provenance: ProvenanceLog | None = None,
) -> pd.DataFrame:
    """Read the factors that convert current USD into every currency and price.

    One DAC1 scan feeds every pydeflate call, so all factors share one release, and that
    release is the one recorded in provenance. Entities with no DAC1 rate of their own take
    the DAC total's (pydeflate's fallback) and are logged.

    Args:
        entities: DAC donor codes to read factors for.
        years: Years to read factors for.
        base_year: Base year of the constant prices.
        currencies: Target currencies. USD current is left out because its factor is 1.
        provenance: Log to record the DAC1 release in.

    Returns:
        One row per donor_code, year, currency and price, with the factor. A factor may be
        NaN where DAC1 has no data for that donor-year. The caller decides if that matters.

    Raises:
        ValueError: If pydeflate read a different DAC1 release from the one scanned.
    """
    entities, years = sorted(set(entities)), sorted(set(years))
    dac1 = scan_table(_DAC1)
    frames = []
    for currency, price, unit_base_year in _factor_units(currencies, base_year):
        result = pydeflate.get_oecd_dac_conversion_factors(
            dac1,
            entities=entities,
            years=years,
            target_currency=currency,
            base_year=unit_base_year,
        )
        if result.release != dac1.release:
            raise ValueError(
                f"pydeflate read DAC1 release {result.release!r}, not the scanned "
                f"{dac1.release!r}."
            )
        factors = result.factors
        fallback = sorted(
            factors.loc[factors["fallback"], "entity_code"].unique().tolist()
        )
        if fallback:
            logger.info(
                "%s %s factors: donor codes %s have no DAC1 rate of their own and use "
                "the DAC total's",
                currency,
                price,
                fallback,
            )
        frames.append(
            factors.rename(columns={"entity_code": "donor_code"})
            .drop(columns="fallback")
            .assign(currency=currency, price=price)
        )

    if provenance is not None:
        provenance.record_table(_DAC1, scanned_release(dac1))
    return pd.concat(frames, ignore_index=True)[
        ["donor_code", "year", "currency", "price", "factor"]
    ]
