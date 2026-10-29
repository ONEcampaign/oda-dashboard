"""Imputed multilateral spending, read the same way by every script that needs it."""

from collections.abc import Iterable, Iterator

import oda_data as oda
import pandas as pd

from src.data.analysis_tools.oda import ProvenanceLog, query, to_repo_frame
from src.data.config import CRS_RECIPIENTS, UNSPECIFIED_RECIPIENT_CODE, logger

IMPUTED_MULTILATERAL_ODA: str = "one.crs.imputed_multilateral_oda"

# The dimensions read, and the oda-data columns kept of the result.
_BY: list[str] = ["provider", "recipient", "sector", "channel", "year"]
_COLUMNS: list[str] = [*_BY, "value"]


def iter_imputed_multilateral(
    ctx: oda.Context,
    *,
    years: Iterable[int],
    providers: Iterable[int],
    provenance: ProvenanceLog | None = None,
) -> Iterator[pd.DataFrame]:
    """Read imputed multilateral spending by purpose and channel, one year at a time.

    A query covering every year peaks at about 7.5 GiB inside oda-data's engine; one query
    per year peaks at about 2.3 GiB, so callers aggregate each year before the next is read.

    oda-data leaves core funding it cannot allocate, and fixed-purpose proxies, without a
    recipient. Dropping those rows would understate imputed multilateral by $3-5bn a year,
    so they are recorded under UNSPECIFIED_RECIPIENT_CODE, as DAC2A records them. No
    recipients= filter is passed, since oda-data would drop exactly those rows.

    Args:
        ctx: From open_context.
        years: Years to read.
        providers: Donor codes to read.
        provenance: Log to record the MultiSystem and CRS releases in.

    Yields:
        One frame per year in current USD millions, with donor_code, recipient_code,
        purpose_code, channel_code, year and value. purpose_code is null for unallocated
        core funding.

    Raises:
        ValueError: If a row has a recipient outside CRS_RECIPIENTS.
    """
    providers = list(providers)
    for year in years:
        q = query(
            ctx,
            IMPUTED_MULTILATERAL_ODA,
            years=[year],
            providers=providers,
            by=_BY,
            provenance=provenance,
        )
        raw = to_repo_frame(q.to_arrow().select(_COLUMNS).to_pandas())
        del q

        no_recipient = raw["recipient_code"].isna()
        logger.info(
            "Imputed multilateral %s with no recipient, recorded as %s: %s USD million",
            year,
            UNSPECIFIED_RECIPIENT_CODE,
            f"{raw.loc[no_recipient, 'value'].sum():,.1f}",
        )
        raw["recipient_code"] = raw["recipient_code"].fillna(UNSPECIFIED_RECIPIENT_CODE)

        outside = ~raw["recipient_code"].isin(CRS_RECIPIENTS)
        if outside.any():
            raise ValueError(
                f"Imputed multilateral {year} recipients outside CRS_RECIPIENTS: "
                f"{sorted(raw.loc[outside, 'recipient_code'].unique())}"
            )
        yield raw
