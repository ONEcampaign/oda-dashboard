import numpy as np
from oda_data import OECDClient

from src.data.analysis_tools.helper_functions import set_cache_dir
from src.data.config import logger, PATHS
from src.data.topic_page.common import (
    LATEST_YEAR_AGG,
    CONSTANT_YEAR,
    LONG_START_YEAR,
    sort_dac_first,
)
from oda_data import provider_groupings, add_gni_share_column


def oda_gni_ts() -> None:
    """Create an overview chart which contains the latest total ODA value and
    the change in constant terms."""
    client = OECDClient(
        years=range(LONG_START_YEAR, LATEST_YEAR_AGG + 1),
        providers=list(provider_groupings()["dac_members"]) + [20001],
        base_year=CONSTANT_YEAR,
        measure=["net_disbursement", "grant_equivalent"],
        use_bulk_download=True,
    )

    data = (
        add_gni_share_column(client, "ONE.10.1010_11010")
        .filter(["donor_name", "year", "value", "gni_share_pct"])
        .astype({"gni_share_pct": float})
        .rename(
            columns={
                "value": "ODA (left-axis)",
                "gni_share_pct": "ODA/GNI (right-axis)",
                "donor_name": "name",
            }
        )
        .pipe(sort_dac_first, keep_current_sorting=True)
    )

    data["ODA/GNI (right-axis)"] = np.where(
        data["name"] == "EU Institutions", np.nan, data["ODA/GNI (right-axis)"]
    )

    # chart version
    data.to_csv(f"{PATHS.TOPIC_PAGE}/oda_gni_ts.csv", index=False)
    logger.info("Saved chart oda_gni_ts.csv")


def oda_gni_year_columns():
    client = OECDClient(
        years=range(LONG_START_YEAR, LATEST_YEAR_AGG + 1),
        providers=list(provider_groupings()["dac_countries"]) + [20001],
        base_year=CONSTANT_YEAR,
        measure=["net_disbursement", "grant_equivalent"],
        use_bulk_download=True,
    )

    oda_indicator = "ONE.10.1010_11010"
    gni_indicator = "DAC1.40.1"

    data = (
        client.get_indicators(indicators=[gni_indicator, oda_indicator])
        .filter(["donor_name", "one_indicator", "year", "value"])
        .pivot(index=["donor_name", "year"], columns="one_indicator", values="value")
        .reset_index(drop=False)
        .assign(
            oda_gni=lambda d: round(100 * d[oda_indicator] / d[gni_indicator], 3),
            missing=lambda d: round(d[gni_indicator] * 0.007 - d[oda_indicator], 1),
        )
        .assign(missing=lambda d: d.missing.apply(lambda v: v if v > 0 else 0))
        .assign(
            value=lambda df_: df_[oda_indicator].apply(
                lambda d: f"{d / 1e3:.2f} billion" if d > 1e3 else f"{d:.1f} million"
            ),
            missing=lambda df_: df_.missing.apply(
                lambda d: f"{d / 1e3:.2f} billion" if d > 1e3 else f"{d:.1f} million"
            ),
        )
        .filter(["donor_name", "year", "value", "missing", "oda_gni"], axis=1)
        .sort_values(["year", "oda_gni", "donor_name"], ascending=[False, False, True])
        .rename(
            {
                "value": "Total ODA",
                "oda_gni": "ODA/GNI",
                "donor_name": "Donor",
                "year": "Year",
                "missing": "ODA short of 0.7% commitment",
            },
            axis=1,
        )
    )

    # chart version
    data.to_csv(f"{PATHS.TOPIC_PAGE}/oda_gni_single_year_ts.csv", index=False)
    logger.info("Saved chart oda_gni_single_year_ts.csv")


if __name__ == "__main__":
    set_cache_dir(oda_data=True, pydeflate=True)
    oda_gni_ts()
    oda_gni_year_columns()
