"""Standalone EU27 + EU Institutions sectoral aggregation.

Computes the EU27+EUI bloc total per (year, recipient, sub-sector) for three
indicators: Bilateral, Imputed multilateral, and their combination.

The "Imputed multilateral" indicator removes flows attributable to EU27 members
via the EU institutional channels {42000, 42001, 42003, 42004, 42999} before
summing. This avoids double-counting EUI's bilateral activity that would
otherwise appear twice when a user adds Bilateral + Imputed multilateral for
the EU27+EUI bloc — once as provider 918's CRS rows, and once as the EUI-channel
attribution inside each EU27 member's imputed multilateral.

The EUI channel set was empirically derived against the local MultiSystem cache:
EU27 members report core contributions only to {42001, 42003, 42004, 42999};
42000 is included defensively for older / future revisions. Each of these
channels maps to an agency under provider 918's CRS bilateral (EC, EDF, EIB,
Macro-Financial Assistance, Misc), so excluding the full set is the symmetric
correction.

Caveats:
  * EUI's own imputed multilateral (its contributions to non-EU multilaterals
    like UN agencies) is included in full — those flows do not double-count
    with EU27 members because purpose shares for non-EUI multilaterals are
    derived from those multilaterals' own CRS bilateral, not EUI's.
  * `EU27 → EUI → other_multi` flows appear once in EUI's imp_multi
    (`EUI → UN → purposes`) and not in EU27 members' imp_multi via the EUI
    channel (whose purpose shares come from EUI's CRS bilateral, which excludes
    EUI's contributions to other multilaterals). No double-count.
  * Year ranges shorter than 3 years will fail inside
    `multilateral_spending_shares_by_channel_and_purpose_smoothed`'s rolling
    window. This module validates the input and raises a clear error.
  * Values are returned in USD current (millions, per the underlying
    `imputed_multilateral_by_purpose` and CRS `usd_disbursement` convention).
    No pydeflate currency or price expansion.
"""

import pandas as pd
from oda_data import CRSData
from oda_data.indicators.research.sector_imputations import (
    imputed_multilateral_by_purpose,
)
from oda_data.tools import sector_lists
from oda_data.tools.groupings import provider_groupings

from src.data.analysis_tools.helper_functions import get_dac_ids, set_cache_dir
from src.data.config import PATHS

EUI_CHANNEL_CODES: frozenset[int] = frozenset({42000, 42001, 42003, 42004, 42999})
EUI_PROVIDER_CODE: int = 918
BLOC_NAME: str = "EU27 + EU Institutions"

INDICATOR_BILATERAL: str = "Bilateral"
INDICATOR_IMPUTED_MULTI: str = "Imputed multilateral"
INDICATOR_COMBINED: str = "Bilateral + Imputed multilateral"

_UNALLOCATED_SUB_SECTOR: str = "Unallocated/unspecificed"  # spelling matches sectors_view.py
_BLOC_KEYS: list[str] = ["year", "recipient_code", "sub_sector"]


def _eu27_provider_codes() -> list[int]:
    """Return the 27 EU member-state provider codes (excludes 918).

    `provider_groupings()["eu27_total"]` deliberately includes provider 918
    (EU Institutions) so callers like `get_eui_plus_bilateral_providers_indicator`
    can use it as a single input set. We need the strict 27-country list so we
    can read EU27 members and EUI separately without double-counting EUI.
    """
    return sorted(
        int(c) for c in provider_groupings()["eu27_total"] if int(c) != EUI_PROVIDER_CODE
    )


def _purpose_to_subsector() -> dict[int, str]:
    return {
        int(code): name
        for name, codes in sector_lists.get_sector_groups().items()
        for code in codes
    }


def _setup(
    years: range | list[int],
    recipients: list[int] | None,
) -> tuple[list[int], list[int]]:
    """Validate inputs, resolve defaults, prime the oda_data cache."""
    years_list = sorted(set(int(y) for y in years))
    if len(years_list) < 3:
        raise ValueError(
            "Need at least 3 years to populate the 3-year rolling window used "
            "by `multilateral_spending_shares_by_channel_and_purpose_smoothed`. "
            f"Got {years_list!r}."
        )
    recipients_list = (
        list(recipients) if recipients is not None else get_dac_ids(PATHS.RECIPIENTS)
    )
    set_cache_dir(oda_data=True, pydeflate=False)
    return years_list, recipients_list


def _crs_bilateral_by_purpose(
    years: list[int],
    providers: list[int],
    recipients: list[int],
) -> pd.DataFrame:
    raw = CRSData(years=years).read(
        using_bulk_download=True,
        additional_filters=[
            ("donor_code", "in", providers),
            ("recipient_code", "in", recipients),
            ("category", "in", [10, 60]),
        ],
        columns=[
            "year",
            "donor_code",
            "recipient_code",
            "purpose_code",
            "usd_disbursement",
        ],
    )
    return raw.rename(columns={"usd_disbursement": "value"})


def _imputed_multi_by_purpose(
    years: list[int],
    providers: list[int],
    recipients: list[int],
) -> pd.DataFrame:
    # measure / currency / base_year are fixed per the module's documented
    # contract (USD current, gross disbursement). Don't parameterise.
    raw = imputed_multilateral_by_purpose(
        years=years,
        providers=providers,
        measure="gross_disbursement",
        currency="USD",
        base_year=None,
    )
    return raw.loc[raw["recipient_code"].isin(recipients)]


def _drop_eui_channels(df: pd.DataFrame) -> pd.DataFrame:
    if "channel_code" not in df.columns:
        raise KeyError(
            "Expected `channel_code` column on imputed-multilateral frame; "
            "it should be preserved through `_compute_imputations` since the "
            "merge key is `[channel_code, year]`. Upstream API may have changed."
        )
    return df.loc[~df["channel_code"].isin(EUI_CHANNEL_CODES)]


def _attach_subsector(df: pd.DataFrame) -> pd.DataFrame:
    mapping = _purpose_to_subsector()
    return df.assign(
        sub_sector=df["purpose_code"].map(mapping).fillna(_UNALLOCATED_SUB_SECTOR)
    )


def _collapse_to_bloc(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(_BLOC_KEYS, dropna=False, observed=True)["value"]
        .sum()
        .reset_index()
    )


def _compute_bilateral_bloc(
    years: list[int], recipients: list[int]
) -> pd.DataFrame:
    eu27 = _eu27_provider_codes()
    combined = pd.concat(
        [
            _crs_bilateral_by_purpose(years, eu27, recipients),
            _crs_bilateral_by_purpose(years, [EUI_PROVIDER_CODE], recipients),
        ],
        ignore_index=True,
    )
    return _collapse_to_bloc(_attach_subsector(combined))


def _compute_imp_multi_bloc(
    years: list[int], recipients: list[int]
) -> pd.DataFrame:
    eu27 = _eu27_provider_codes()
    eu27_imp = _drop_eui_channels(_imputed_multi_by_purpose(years, eu27, recipients))
    eui_imp = _imputed_multi_by_purpose(years, [EUI_PROVIDER_CODE], recipients)
    combined = pd.concat([eu27_imp, eui_imp], ignore_index=True)
    return _collapse_to_bloc(_attach_subsector(combined))


def _combined_bloc(
    bilateral_bloc: pd.DataFrame, imp_bloc: pd.DataFrame
) -> pd.DataFrame:
    return _collapse_to_bloc(
        pd.concat([bilateral_bloc, imp_bloc], ignore_index=True)
    )


def _drop_zeros(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[df["value"] != 0].reset_index(drop=True)


def eu27_eui_bilateral_by_sector(
    years: range | list[int],
    recipients: list[int] | None = None,
) -> pd.DataFrame:
    """Bloc-level Bilateral CRS aggregate for the EU27+EUI bloc.

    Sums EU27 member CRS bilateral and provider 918's CRS bilateral. No
    channel-level adjustment is needed here — Bilateral is disjoint from
    Imputed multilateral within the indicator.
    """
    years_list, recipients_list = _setup(years, recipients)
    return _drop_zeros(_compute_bilateral_bloc(years_list, recipients_list))


def eu27_eui_imputed_multi_by_sector(
    years: range | list[int],
    recipients: list[int] | None = None,
) -> pd.DataFrame:
    """Bloc-level Imputed multilateral for the EU27+EUI bloc.

    EU27 members' imputed multilateral has the EUI channel set removed (so the
    EUI bilateral flow is not attributed back as imputed-multi). EUI's own
    imputed multilateral (contributions to non-EU multilaterals) is included
    in full.
    """
    years_list, recipients_list = _setup(years, recipients)
    return _drop_zeros(_compute_imp_multi_bloc(years_list, recipients_list))


def eu27_eui_combined_by_sector(
    years: range | list[int],
    recipients: list[int] | None = None,
) -> pd.DataFrame:
    """Bloc-level Bilateral + Imputed multilateral for the EU27+EUI bloc.

    The combined indicator the dashboard UI offers — but computed without the
    EU27/EUI double-count that the weighted approach addresses only
    approximately.
    """
    years_list, recipients_list = _setup(years, recipients)
    bilateral = _compute_bilateral_bloc(years_list, recipients_list)
    imp_multi = _compute_imp_multi_bloc(years_list, recipients_list)
    return _drop_zeros(_combined_bloc(bilateral, imp_multi))


def eu27_eui_sector_aggregates(
    years: range | list[int],
    recipients: list[int] | None = None,
) -> pd.DataFrame:
    """Primary entry point. Returns all three indicators in long form.

    Columns: year, recipient_code, sub_sector, indicator, value.
    indicator is one of `INDICATOR_BILATERAL`, `INDICATOR_IMPUTED_MULTI`,
    `INDICATOR_COMBINED`.
    """
    years_list, recipients_list = _setup(years, recipients)
    bilateral = _compute_bilateral_bloc(years_list, recipients_list)
    imp_multi = _compute_imp_multi_bloc(years_list, recipients_list)
    combined = _combined_bloc(bilateral, imp_multi)

    out = pd.concat(
        [
            bilateral.assign(indicator=INDICATOR_BILATERAL),
            imp_multi.assign(indicator=INDICATOR_IMPUTED_MULTI),
            combined.assign(indicator=INDICATOR_COMBINED),
        ],
        ignore_index=True,
    )
    return _drop_zeros(out)[[*_BLOC_KEYS, "indicator", "value"]]
