""""Scripts to produce the financing view of our ODA dashboard."""
import copy
from functools import partial

import pandas as pd
from oda_data import ODAData, set_data_path
from pydeflate import set_pydeflate_path

from scripts import config
from scripts.analysis.common import DASHBOARD_DONORS, EU27
from scripts.analysis_tools.versions import versions_dictionary
from scripts.analysis_tools.get_unique_values import get_unique_values

# Set the path to the raw data folder
set_data_path(config.PATHS.raw_data)
set_pydeflate_path(config.PATHS.raw_data)


# -------------------------- Helper functions -------------------------- #
# ---------------------------------------------------------------------- #


def _group_financing_data(data: pd.DataFrame) -> pd.DataFrame:
    data_cols = [
        c
        for c in data.columns
        if c
           not in [
               "value",
               "donor_code",
               "donor_name",
               "share",
               "gni_share",
               "indicator_type",
           ]
    ]

    return data.groupby(data_cols, dropna=False)["value"].sum().reset_index()


def _get_totals_for_share(oda: ODAData, share_indicators: list) -> pd.DataFrame:
    oda_ = copy.deepcopy(oda)
    oda_.indicators_data = {}

    share_data = (
        oda_.load_indicator(indicators=share_indicators)
        .get_data(share_indicators)
        .drop(columns=["share", "donor_code", "donor_name", "gni_share"])
    )
    try:
        share_data = share_data.drop(columns=["share_of"])
    except KeyError:
        pass

    share_cols = [c for c in share_data if c != "value"]

    return (
        share_data.groupby(share_cols, dropna=False)
        .sum()
        .reset_index()
        .rename({"indicator": "share_of"}, axis=1)
    )


def _get_gni_data_for_group(oda: ODAData) -> pd.DataFrame:
    gni_data = (
        oda.load_indicator(indicators="gni")
        .get_data("gni")
        .drop(columns=["share", "indicator", "donor_code", "donor_name"])
    )

    gni_cols = [c for c in gni_data if c != "value"]

    return gni_data.groupby(gni_cols, dropna=False).sum().reset_index()


def _get_institutions_spending(
        indicators: dict, currency: str, prices: str, base_year: int
) -> pd.DataFrame:
    data_institutions = ODAData(
        years=range(config.ANALYSIS_YEARS["start"], config.ANALYSIS_YEARS["end"] + 1),
        donors=918,
        currency=currency,
        prices=prices,
        base_year=base_year,
        include_names=True,
    )

    for _ in list(indicators):
        try:
            data_institutions.load_indicator(indicators=_)
        except KeyError:
            pass

    return (
        data_institutions.add_share_of_total()
        .get_data()
        .assign(share=lambda d: d.share.fillna(100))
        .filter(["year", "indicator", "currency", "prices", "value", "share"], axis=1)
    )


# -------------------------- Data Functions -------------------------------- #
# -------------------------------------------------------------------------- #


def get_financing_data(
        indicators: dict,
        indicator_type: str,
        donors: dict,
        currency: str,
        prices: str,
        base_year: int = None,
        **kwargs,
) -> pd.DataFrame:
    oda = ODAData(
        years=range(config.ANALYSIS_YEARS["start"], config.ANALYSIS_YEARS["end"] + 1),
        donors=list(donors),
        currency=currency,
        prices=prices,
        base_year=base_year,
        include_names=True,
    )

    return (
        oda.load_indicator(indicators=list(indicators))
        .add_share_of_total(include_share_of=True)
        .add_share_of_gni()
        .get_data()
        .replace({"indicator": indicators, "share_of": indicators})
        .assign(indicator_type=indicator_type)
    )


def get_financing_group(
        group_code: int,
        group_name: str,
        indicators: dict,
        indicator_type: str,
        donors: dict,
        currency: str,
        prices: str,
        base_year: int = None,
        **kwargs,
) -> pd.DataFrame:
    oda = ODAData(
        years=range(config.ANALYSIS_YEARS["start"], config.ANALYSIS_YEARS["end"] + 1),
        donors=list(donors),
        currency=currency,
        prices=prices,
        base_year=base_year,
        include_names=True,
    )

    data = (
        oda.load_indicator(indicators=list(indicators))
        .add_share_of_total(True)
        .add_share_of_gni()
        .get_data()
    )

    # Store the original order of columns
    order = data.columns.tolist()

    # identify the required 'total' indicators
    share_indicators = [
        share for share in data.loc[data.share_of.notna()].share_of.unique()
    ]

    # Group the data to remove donor codes and names
    data = _group_financing_data(data)

    # Get the totals data
    share_data = _get_totals_for_share(oda, share_indicators)

    # Get the gni data
    gni_data = _get_gni_data_for_group(oda)

    data = (
        data.merge(
            share_data,
            on=[c for c in share_data if c != "value"],
            how="left",
            suffixes=("", "_share"),
        )
        .merge(
            gni_data,
            on=["year", "currency", "prices"],
            how="left",
            suffixes=("", "_gni"),
        )
        .assign(
            share=lambda d: round(100 * d.value / d.value_share, 8),
            gni_share=lambda d: round(100 * d.value / d.value_gni, 8),
            donor_code=group_code,
            donor_name=group_name,
        )
        .filter(order, axis=1)
    )

    return data.replace({"indicator": indicators, "share_of": indicators}).assign(
        indicator_type=indicator_type
    )


def get_eu_total_financing(
        group_code: int,
        group_name: str,
        indicators: dict,
        indicator_type: str,
        donors: dict,
        currency: str,
        prices: str,
        base_year: int = None,
        **kwargs,
) -> pd.DataFrame:
    # Get data for all EU27 countries plus the EU institutions
    oda = ODAData(
        years=range(config.ANALYSIS_YEARS["start"], config.ANALYSIS_YEARS["end"] + 1),
        donors=list(donors) + [918],
        currency=currency,
        prices=prices,
        base_year=base_year,
        include_names=True,
    )

    data = (
        oda.load_indicator(indicators=list(indicators))
        .add_share_of_total(True)
        .add_share_of_gni()
        .get_data()
    )

    # Store the original order of columns
    order = data.columns.tolist()

    # identify the required 'total' indicators
    share_indicators = [
        share for share in data.loc[data.share_of.notna()].share_of.unique()
    ]

    # Extract share of mapping. This will be used to ensure consistency when the data
    # is merged
    share_of_mapping = (
        data[["indicator", "share_of"]]
        .drop_duplicates()
        .set_index("indicator")
        .to_dict()["share_of"]
    )

    indicator = "eu_core_flow" if indicator_type == "flow" else "eu_core_ge_linked"

    # Get core contributions data for the group
    core_contributions = get_financing_group(
        group_code=group_code,
        group_name=group_name,
        indicators={indicator: indicator},
        indicator_type=indicator_type,
        donors=donors,
        currency=currency,
        prices=prices,
        base_year=base_year,
    ).drop(columns=["share", "gni_share", "indicator"])

    # Get the spending data for the institutions
    institutions_data = _get_institutions_spending(
        indicators=indicators, currency=currency, prices=prices, base_year=base_year
    )

    # Merge the data into an imputed dataset. The resulting values are "negative" so that
    # they can be subtracted from the group total data.
    imputed = (
        institutions_data.merge(
            core_contributions,
            on=["year", "currency", "prices"],
            how="left",
            suffixes=("", "_core"),
        )
        .assign(
            value=lambda d: -d.value_core * d.share / 100,
            share_of=lambda d: d.indicator.map(share_of_mapping),
        )
        .drop(["value_core", "share"], axis=1)
    )

    # Combine the datasets
    data = pd.concat([data, imputed], ignore_index=True)

    # Group the data to remove donor codes and names
    data = _group_financing_data(data)

    # Get the totals data
    share_data = _get_totals_for_share(oda, share_indicators)

    # Get the gni data
    gni_data = _get_gni_data_for_group(oda)

    # Merge the values with the shares and gni shares
    data = (
        data.merge(
            share_data,
            on=[c for c in share_data if c != "value"],
            how="left",
            suffixes=("", "_share"),
        )
        .merge(
            gni_data,
            on=["year", "currency", "prices"],
            how="left",
            suffixes=("", "_gni"),
        )
        .assign(
            share=lambda d: round(100 * d.value / d.value_share, 8),
            gni_share=lambda d: round(100 * d.value / d.value_gni, 8),
            donor_code=group_code,
            donor_name=group_name,
        )
        .filter(order, axis=1)
    )

    return data.replace({"indicator": indicators, "share_of": indicators}).assign(
        indicator_type=indicator_type
    )


# ------------------- Partial functions for versions of data --------------- #
# -------------------------------------------------------------------------- #

get_flows_financing_data = partial(
    get_financing_data,
    indicators=config.FINANCING_INDICATORS_FLOW,
    indicator_type="flow",
)

get_ge_financing_data = partial(
    get_financing_data,
    indicators=config.FINANCING_INDICATORS_GE,
    indicator_type="grant equivalent",
)

get_flows_financing_data_group = partial(
    get_financing_group,
    indicators=config.FINANCING_INDICATORS_FLOW,
    indicator_type="flow",
)

get_ge_financing_data_group = partial(
    get_financing_group,
    indicators=config.FINANCING_INDICATORS_GE,
    indicator_type="grant equivalent",
)

get_flows_financing_data_eutot = partial(
    get_eu_total_financing,
    indicators=config.FINANCING_INDICATORS_FLOW,
    indicator_type="flow",
)

get_ge_financing_data_eutot = partial(
    get_eu_total_financing,
    indicators=config.FINANCING_INDICATORS_GE,
    indicator_type="grant equivalent",
)


def _get_combined_data(
        versions: dict,
        donors: dict,
        flows_callable: callable,
        ge_callable: callable,
        **kwargs,
) -> pd.DataFrame:
    # Empty lists for flows and grant equivalents
    dfs_flow = []
    dfs_ge = []

    for k, version in versions.items():
        dfs_flow.append(flows_callable(donors=donors, **version, **kwargs))
        dfs_ge.append(ge_callable(donors=donors, **version, **kwargs))

    data_flow = pd.concat(dfs_flow, ignore_index=True)
    data_ge = pd.concat(dfs_ge, ignore_index=True).loc[lambda d: d.year >= 2018]

    # combine the data
    return pd.concat([data_flow, data_ge], ignore_index=True)


def add_indicator_descriptions(df: pd.DataFrame) -> pd.DataFrame:
    import json

    # Read the indicators.json file
    with open(config.PATHS.scripts / "analysis_tools/indicators.json", "r") as f:
        indicators = json.load(f)

    names = config.FINANCING_INDICATORS_GE | config.FINANCING_INDICATORS_FLOW
    indicators = {names[k]: v for k, v in indicators.items() if k in names}

    return df.assign(description=lambda d: d.indicator.map(indicators).fillna(""))


def export_financing_data() -> None:
    # Load a dictionary describing the different versions
    versions = versions_dictionary()

    # Individual donor data (including dac totals)
    data = _get_combined_data(
        versions=versions,
        flows_callable=get_flows_financing_data,
        ge_callable=get_ge_financing_data,
        donors=DASHBOARD_DONORS,
    )

    # EU Countries data
    group_data = _get_combined_data(
        versions=versions,
        flows_callable=get_flows_financing_data_group,
        ge_callable=get_ge_financing_data_group,
        group_code=927,
        group_name="EU-27",
        donors=EU27,
    )

    # EU total data
    eu_data = _get_combined_data(
        versions=versions,
        flows_callable=get_flows_financing_data_eutot,
        ge_callable=get_ge_financing_data_eutot,
        group_code=91827,
        group_name="EU-27 + Institutions",
        donors=EU27,
    )

    # Combine the data
    data = pd.concat([data, group_data, eu_data], ignore_index=True)

    # Create official definition
    official = data.query(
        "year < 2018 and indicator_type == 'flow' or "
        "year >= 2018 and indicator_type == 'grant equivalent'"
    ).assign(indicator_type="official")

    # Combine the data
    data = pd.concat([data, official], ignore_index=True)

    # Add indicator descriptions
    # data = data.pipe(add_indicator_descriptions)

    # rename columns and values
    data = data.rename(columns=config.COLUMNS).replace(config.VALUES, regex=False)

    # Export the data
    data.to_csv(config.PATHS.output / "financing.csv", index=False)

    get_unique_values(data, "Financing")


if __name__ == "__main__":
    ...

    export_financing_data()  # df = pd.read_csv(config.PATHS.output / "financing.csv")