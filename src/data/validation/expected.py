"""Deltas we expect between two builds, or between a view and the topic page, with reasons.

Parity and cross-view checks report a delta that matches an entry as INFO "explained
(reason)" and an unmatched one as ERROR. The file is TOML, one ``[[delta]]`` table per entry:

    [[delta]]
    view = "financing_view"          # or "cross_view"
    kind = "value"                   # "value", "missing_in_candidate", "new_in_candidate"
    reason = "PSI read in grant equivalents from 2023"
    years = [2023, 2024]             # optional filters; omitted means any
    donors = ["France"]
    indicators = ["Private sector instruments"]
    recipients = []                  # an empty list also means any
    columns = ["value_usd_current"]  # optional: the value or share columns it covers
    max_rel = 0.05                   # optional, "value" only: explains |rel diff| <= this
    max_abs = 11000                  # optional, "value" only: explains |diff| <= this
    paths = ["year.start"]           # optional: options.json paths, see below

With both max_rel and max_abs set, a delta within either is explained. max_abs is in the
column's unit: currency units for value columns, a fraction for share columns.

``paths`` explains options.json differences by dotted path: a changed scalar (kind
"value", e.g. "year.start") or a key added or removed (kind "new_in_candidate" or
"missing_in_candidate", e.g. "psi_excluded_from"). An entry with paths explains only
options deltas, and cannot carry max_rel or max_abs. Donor, recipient and indicator list
items in the options are matched by the donors, recipients and indicators filters instead.
"""

import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from src.data.validation.io import VALIDATION_DATA_DIR

DEFAULT_EXPECTED_DELTAS_PATH: Path = VALIDATION_DATA_DIR / "expected_deltas.toml"

_FILTER_FIELDS: tuple[str, ...] = (
    "years",
    "donors",
    "indicators",
    "recipients",
    "columns",
    "paths",
)
_BOUND_FIELDS: tuple[str, ...] = ("max_rel", "max_abs")
_ALLOWED_FIELDS: frozenset[str] = frozenset(
    {"view", "kind", "reason", *_BOUND_FIELDS, *_FILTER_FIELDS}
)


class DeltaKind(StrEnum):
    """What sort of difference an entry explains."""

    VALUE = "value"  # the key exists on both sides and a value differs
    MISSING_IN_CANDIDATE = "missing_in_candidate"  # key only in the baseline
    NEW_IN_CANDIDATE = "new_in_candidate"  # key only in the candidate


@dataclass(frozen=True)
class ExpectedDelta:
    """One explained difference.

    Attributes:
        view: The view the delta is in, or "cross_view".
        reason: Why it is expected; shown in the report.
        kind: The sort of difference.
        years, donors, indicators, recipients, columns: Filters. None means any value
            matches.
        paths: Dotted options.json paths the entry explains (options deltas only).
        max_rel: For kind "value", the largest |relative difference| explained.
        max_abs: For kind "value", the largest |difference| explained, in the column's
            unit. With neither bound set, a delta of any size matches; with both, a delta
            within either matches.
    """

    view: str
    reason: str
    kind: DeltaKind = DeltaKind.VALUE
    years: frozenset[int] | None = None
    donors: frozenset[str] | None = None
    indicators: frozenset[str] | None = None
    recipients: frozenset[str] | None = None
    columns: frozenset[str] | None = None
    paths: frozenset[str] | None = None
    max_rel: float | None = None
    max_abs: float | None = None

    def matches(
        self,
        *,
        view: str,
        kind: DeltaKind | str,
        year: int | None = None,
        donor: str | None = None,
        indicator: str | None = None,
        recipient: str | None = None,
        column: str | None = None,
        path: str | None = None,
        rel_diff: float | None = None,
        abs_diff: float | None = None,
    ) -> bool:
        """Whether this entry explains one delta.

        A filter set on the entry requires the delta to give that dimension with a value in
        the filter; a delta that leaves it out (None) does not match. With a bound set,
        the delta must give that difference and be within it (within either, with both).

        Args:
            view: The delta's view, or "cross_view".
            kind: The delta's kind.
            year, donor, indicator, recipient, column: The delta's coordinates; None if
                the delta has no such dimension (e.g. no recipient in financing_view).
            path: For an options delta, its dotted options.json path.
            rel_diff: (candidate - baseline) / |baseline| for a value delta.
            abs_diff: |candidate - baseline| for a value delta, in the column's unit.
        """
        if view != self.view or kind != self.kind:
            return False
        for allowed, value in (
            (self.years, year),
            (self.donors, donor),
            (self.indicators, indicator),
            (self.recipients, recipient),
            (self.columns, column),
            (self.paths, path),
        ):
            if allowed is not None and (value is None or value not in allowed):
                return False
        if self.max_rel is None and self.max_abs is None:
            return True
        within_rel = (
            self.max_rel is not None
            and rel_diff is not None
            and abs(rel_diff) <= self.max_rel
        )
        within_abs = (
            self.max_abs is not None
            and abs_diff is not None
            and abs(abs_diff) <= self.max_abs
        )
        return within_rel or within_abs


def find_explanation(
    expected: list[ExpectedDelta],
    *,
    view: str,
    kind: DeltaKind | str,
    year: int | None = None,
    donor: str | None = None,
    indicator: str | None = None,
    recipient: str | None = None,
    column: str | None = None,
    path: str | None = None,
    rel_diff: float | None = None,
    abs_diff: float | None = None,
) -> ExpectedDelta | None:
    """The first entry that explains a delta, or None if none does.

    Arguments are as for ExpectedDelta.matches.
    """
    for entry in expected:
        if entry.matches(
            view=view,
            kind=kind,
            year=year,
            donor=donor,
            indicator=indicator,
            recipient=recipient,
            column=column,
            path=path,
            rel_diff=rel_diff,
            abs_diff=abs_diff,
        ):
            return entry
    return None


def _filter_set[T](
    raw: dict, field: str, item_type: type[T], where: str
) -> frozenset[T] | None:
    """Read an optional list filter; an absent or empty list means any value."""
    values = raw.get(field)
    if values is None:
        return None
    if not isinstance(values, list) or not all(
        isinstance(v, item_type) and not isinstance(v, bool) for v in values
    ):
        raise ValueError(f"{where}: {field} must be a list of {item_type.__name__}")
    return frozenset(values) or None


def _bound(raw: dict, name: str, kind: DeltaKind, where: str) -> float | None:
    """Read an optional max_rel / max_abs: a number >= 0, for kind "value" only."""
    value = raw.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{where}: {name} must be a number")
    if value < 0:
        raise ValueError(f"{where}: {name} must be >= 0")
    if kind is not DeltaKind.VALUE:
        raise ValueError(f"{where}: {name} applies only to kind 'value'")
    return float(value)


def _parse_entry(raw: object, where: str) -> ExpectedDelta:
    """Validate one [[delta]] table and build its ExpectedDelta."""
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: must be a table")
    unknown = raw.keys() - _ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"{where}: unknown fields {sorted(unknown)}")
    for required in ("view", "reason"):
        if not isinstance(raw.get(required), str) or not raw[required].strip():
            raise ValueError(f"{where}: {required} must be a non-empty string")

    try:
        kind = DeltaKind(raw.get("kind", DeltaKind.VALUE))
    except ValueError:
        allowed = [k.value for k in DeltaKind]
        raise ValueError(f"{where}: kind must be one of {allowed}") from None

    max_rel, max_abs = (_bound(raw, name, kind, where) for name in _BOUND_FIELDS)
    paths = _filter_set(raw, "paths", str, where)
    if paths is not None and (max_rel is not None or max_abs is not None):
        raise ValueError(f"{where}: paths cannot be combined with max_rel or max_abs")

    return ExpectedDelta(
        view=raw["view"],
        reason=raw["reason"],
        kind=kind,
        years=_filter_set(raw, "years", int, where),
        donors=_filter_set(raw, "donors", str, where),
        indicators=_filter_set(raw, "indicators", str, where),
        recipients=_filter_set(raw, "recipients", str, where),
        columns=_filter_set(raw, "columns", str, where),
        paths=paths,
        max_rel=max_rel,
        max_abs=max_abs,
    )


def load_expected_deltas(
    path: Path = DEFAULT_EXPECTED_DELTAS_PATH,
) -> list[ExpectedDelta]:
    """Read and validate the expected deltas file.

    Args:
        path: The TOML file. A file with no ``[[delta]]`` tables gives an empty list.

    Raises:
        FileNotFoundError: The file does not exist.
        ValueError: Malformed TOML, or an entry with unknown or invalid fields.
    """
    if not path.is_file():
        raise FileNotFoundError(f"No expected deltas file at {path}")
    try:
        document = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"{path}: invalid TOML: {e}") from e

    unknown = document.keys() - {"delta"}
    if unknown:
        raise ValueError(f"{path}: unknown top-level keys {sorted(unknown)}")
    entries = document.get("delta", [])
    if not isinstance(entries, list):
        raise ValueError(f"{path}: 'delta' must be an array of tables ([[delta]])")
    return [
        _parse_entry(raw, f"{path} [[delta]] #{i + 1}") for i, raw in enumerate(entries)
    ]
