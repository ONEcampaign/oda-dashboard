"""What each dashboard view looks like: keys, columns, dtypes, time window and groups.

Group memberships come from src.data.config, which imports oda_data transitively. Copying
the group lists here would let them drift from what the pipeline builds.
"""

from dataclasses import dataclass

from src.data.config import (
    BASE_TIME,
    CRS_RECIPIENTS_ORDER,
    CURRENCIES,
    DONOR_GROUPS,
    EU27_EUI_NAME,
    FINANCING_TIME,
    GENDER_TIME,
    RECIPIENTS_ORDER,
    SECTORS_TIME,
)

PRICES: tuple[str, ...] = ("current", "constant")

# The 8 value columns every view publishes, in whole currency units.
VALUE_COLUMNS: tuple[str, ...] = tuple(
    f"value_{currency.lower()}_{price}" for currency in CURRENCIES for price in PRICES
)

# Dtypes as load_view returns them. Labels are arrow-backed strings (str(dtype) == "string").
# Contracts compare str(dtype) against these, with int/float width tolerance.
YEAR_DTYPE: str = "int16"
LABEL_DTYPE: str = "string"
# Published as int64 units; load_view widens them to float64 so nulls (which the real
# recipients and sectors views have) are NaN and the dtype does not depend on the data.
VALUE_DTYPE: str = "float64"
SHARE_DTYPE: str = "float32"

SAHEL_NAME: str = "Sahel countries"
FRANCE_PRIORITY_NAME: str = "France priority countries"

# DAC2A recipient groups in the recipients view: config.DAC2A_RECIPIENT_AGGREGATES minus
# RECIPIENTS_ORDER, kept as names here so validation reads the published view without the
# pipeline's codes (a test checks the two agree). A group missing here would be treated as a
# country by the recipient-sum check and show up there as an overshoot.
DAC2A_RECIPIENT_GROUPS: frozenset[str] = frozenset(
    {
        "ACP",
        "Africa",
        "America",
        "Asia",
        "Caribbean",
        "Caribbean & Central America",
        "Central America",
        "Countries not classified by the World Bank",
        "Eastern Africa",
        "Europe",
        "Far East Asia",
        "Land locked developing countries",
        "Melanesia",
        "Micronesia (region)",
        "Middle Africa",
        "Middle East",
        "North of Sahara",
        "Northern America",
        "Oceania",
        "Polynesia",
        "Small island developing states",
        "South & Central Asia",
        "South America",
        "South of Sahara",
        "Southern Africa",
        "Western Africa",
    }
)

# Donors that must always have data, by name.
CRITICAL_DONORS: tuple[str, ...] = (
    "Austria",
    "Belgium",
    "Denmark",
    "France",
    "Germany",
    "Italy",
    "Netherlands",
    "Norway",
    "Portugal",
    "Sweden",
    "Switzerland",
    "United Kingdom",
    "Finland",
    "Luxembourg",
    "Spain",
    "Czechia",
    "Slovak Republic",
    "Hungary",
    "Poland",
    "Canada",
    "United States",
    "Japan",
    "Korea",
    "New Zealand",
)

# Donor group name -> member donor names, from the config code -> name dicts.
DONOR_GROUP_MEMBERS: dict[str, frozenset[str]] = {
    group: frozenset(members.values()) for group, members in DONOR_GROUPS.items()
}

# Every donor row that is a sum of other donors rather than a reported donor.
AGGREGATE_DONORS: frozenset[str] = frozenset(DONOR_GROUPS) | {EU27_EUI_NAME}


@dataclass(frozen=True)
class ViewSpec:
    """The shape of one dashboard view.

    Attributes:
        name: View name, e.g. "financing_view"; also its directory name.
        keys: Columns that uniquely identify a row.
        value_columns: The 8 value_{usd,eur,gbp,cad}_{current,constant} columns.
        share_columns: The pct_* columns, as fractions.
        time: {"start", "end", "base"} years, the config window for this view.
        partitioned: True when the published view is a hive dataset (sectors).
        dtypes: Column -> expected str(dtype) as load_view returns it, for every
            required column (keys, values and shares).
    """

    name: str
    keys: tuple[str, ...]
    value_columns: tuple[str, ...]
    share_columns: tuple[str, ...]
    time: dict[str, int]
    partitioned: bool
    dtypes: dict[str, str]

    @property
    def required_columns(self) -> tuple[str, ...]:
        """Keys, then value columns, then share columns."""
        return (*self.keys, *self.value_columns, *self.share_columns)


def _make_spec(
    name: str,
    *,
    keys: tuple[str, ...],
    share_columns: tuple[str, ...],
    time: dict[str, int],
    partitioned: bool = False,
) -> ViewSpec:
    """Build a ViewSpec, deriving its dtype table from the column roles."""
    dtypes = {
        **{key: YEAR_DTYPE if key == "year" else LABEL_DTYPE for key in keys},
        **dict.fromkeys(VALUE_COLUMNS, VALUE_DTYPE),
        **dict.fromkeys(share_columns, SHARE_DTYPE),
    }
    return ViewSpec(
        name=name,
        keys=keys,
        value_columns=VALUE_COLUMNS,
        share_columns=share_columns,
        time=dict(time),
        partitioned=partitioned,
        dtypes=dtypes,
    )


_RECIPIENT_KEYS: tuple[str, ...] = (
    "year",
    "donor_name",
    "recipient_name",
    "indicator_name",
)

VIEWS: dict[str, ViewSpec] = {
    spec.name: spec
    for spec in (
        _make_spec(
            "financing_view",
            keys=("year", "donor_name", "indicator_name", "type"),
            share_columns=("pct_of_total_oda", "pct_of_gni"),
            time=FINANCING_TIME,
        ),
        _make_spec(
            "recipients_view",
            keys=_RECIPIENT_KEYS,
            share_columns=("pct_total_donor", "pct_total_recipient"),
            time=BASE_TIME,
        ),
        _make_spec(
            "gender_view",
            keys=_RECIPIENT_KEYS,
            share_columns=("pct_of_total_oda",),
            time=GENDER_TIME,
        ),
        _make_spec(
            "sectors_view",
            keys=(*_RECIPIENT_KEYS, "sector_name", "sub_sector_name"),
            share_columns=("pct_total_donor", "pct_total_recipient"),
            time=SECTORS_TIME,
            partitioned=True,
        ),
    )
}


def get_spec(name: str) -> ViewSpec:
    """Look up a view's spec by name.

    Raises:
        KeyError: If the view is unknown, naming the known views.
    """
    try:
        return VIEWS[name]
    except KeyError:
        raise KeyError(f"Unknown view {name!r}; known views: {sorted(VIEWS)}") from None


def recipient_aggregates(view_name: str) -> frozenset[str]:
    """Recipient names in a view that are groups rather than single recipients.

    Recipients not in this set are countries, or "<area>, unspecified" codes, both of which
    sum to "ODA eligible countries".

    Args:
        view_name: "recipients_view", "gender_view" or "sectors_view".

    Returns:
        For the CRS views (gender, sectors), CRS_RECIPIENTS_ORDER. For the recipients view,
        RECIPIENTS_ORDER plus the Sahel and France priority lists plus the DAC2A groups.

    Raises:
        ValueError: For a view without recipients (financing_view).
        KeyError: For an unknown view.
    """
    spec = get_spec(view_name)
    if "recipient_name" not in spec.keys:
        raise ValueError(f"{view_name} has no recipient_name column")
    if view_name == "recipients_view":
        return frozenset(
            {
                *RECIPIENTS_ORDER,
                SAHEL_NAME,
                FRANCE_PRIORITY_NAME,
                *DAC2A_RECIPIENT_GROUPS,
            }
        )
    return frozenset(CRS_RECIPIENTS_ORDER)
