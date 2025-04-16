import pandas as pd
from oda_data import OECDClient, provider_groupings
import numpy as np

from src.data.analysis_tools.helper_functions import set_cache_dir
from src.data.topic_page.common import (
    LATEST_YEAR_AGG,
    CONSTANT_YEAR,
    SHORT_START_YEAR,
)


def dac_to_ukraine_total() -> pd.DataFrame:
    """Create an overview chart which contains the latest total ODA value and
    the change in constant terms."""

    shared_args = {
        "providers": list(provider_groupings()["dac_countries"]),
        "recipients": [85],
        "use_bulk_download": True,
        "base_year": CONSTANT_YEAR,
    }

    multilateral_client = OECDClient(
        years=range(SHORT_START_YEAR, LATEST_YEAR_AGG + 1),
        measure=["net_disbursement"],
        **shared_args,
    )

    ge_client = OECDClient(
        years=range(2018, LATEST_YEAR_AGG + 1),
        measure=["grant_equivalent"],
        **shared_args,
    )

    flows_client = OECDClient(
        years=range(SHORT_START_YEAR, 2018 + 1),
        measure=["net_disbursement"],
        **shared_args,
    )

    imputed_multi_indicator = "DAC2A.10.106"
    bilateral_net_indicator = "DAC2A.10.206"
    bilateral_ge_indicator = "CRS.P.10"

    multi = multilateral_client.get_indicators(indicators=[imputed_multi_indicator])
    ge_data = ge_client.get_indicators(indicators=[bilateral_ge_indicator]).loc[
        lambda d: d.value != 0
    ]
    flow_data = flows_client.get_indicators(indicators=[bilateral_net_indicator])

    data = (
        pd.concat([multi, ge_data, flow_data], ignore_index=True)
        .filter(
            ["donor_name", "recipient_name", "one_indicator", "year", "prices", "value"]
        )
        .pivot(
            index=["donor_name", "recipient_name", "prices", "year"],
            columns="one_indicator",
            values="value",
        )
        .fillna(0)
        .reset_index(drop=False)
        .assign(indicator="aid_to_ukraine")
    )

    data[bilateral_ge_indicator] = np.where(
        data.year < 2018, 0, data[bilateral_ge_indicator]
    )

    data["value"] = (
        data[bilateral_net_indicator]
        + data[bilateral_ge_indicator]
        + data[imputed_multi_indicator]
    )

    idx = ["year", "donor_name", "recipient_name", "indicator", "prices"]

    data = data.filter(idx + ["value"])

    dac_total = (
        data.assign(donor_name="DAC countries")
        .groupby(idx, dropna=False, observed=True)[["value"]]
        .sum()
        .reset_index()
    )

    data = pd.concat([data, dac_total], ignore_index=True)

    return data


if __name__ == "__main__":
    set_cache_dir(oda_data=True, pydeflate=True)
