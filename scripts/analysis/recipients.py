""""Scripts to produce the financing view of our ODA dashboard."""

import pandas as pd
from oda_data import ODAData, set_data_path
from oda_data.tools.groupings import recipient_groupings

from scripts import config
from scripts.analysis.common import DASHBOARD_DONORS, EU27
from scripts.analysis_tools.versions import versions_dictionary
from scripts.analysis_tools.get_unique_values import get_unique_values

# Set the path to the raw data folder
set_data_path(config.PATHS.raw_data)

DAC_GROUPS = {
    10001: "Africa, total",
    10004: "America, total",
    10007: "Asia, total",
    10010: "Europe, total",
    10012: "Oceania, total",
    10045: "Low income",
    10046: "Lower-middle income",
    10047: "Upper-middle income",
    10048: "High income",
    10049: "Not classified by income",
    10203: "Fragile states, total",
    10016: "LDCs, total",
    10017: "Other LICs, total",
    10018: "LMICs, total",
    10019: "UMICs, total",
    10024: "Unallocated by income",
    9998: "Unspecified developing countries",
    10100: "Developing countries, total",
}

ONE_GROUPS = {
    "sahel": recipient_groupings()["sahel"] | {10100: "Developing countries, total"},
    "france_priority": recipient_groupings()["france_priority"]
                       | {10100: "Developing countries, total"},
}


def get_share_of_component(df: pd.DataFrame) -> pd.DataFrame:
    """Use aid to All developing countries, Total as in order to calculate the
    share spent on other groups by type of aid."""

    # for components, extrac the aid going to All developing countries, Total
    all_recipients = df.query("recipient_name == 'Developing countries, total'").filter(
        ["year", "donor_code", "indicator", "value"], axis=1
    )

    # Calculate the share of total aid going to All developing countries, Total
    df = (
        df.merge(
            all_recipients,
            on=["year", "donor_code", "indicator"],
            how="left",
            suffixes=("", "_all"),
        )
        .assign(share_of_indicator=lambda d: round(100 * d.value / d.value_all, 5))
        .drop(columns=["value_all"])
    )

    return df


def _get_data_individual_donors(
        donors: dict, recipients: dict, prices: str, currency: str, base_year: int
) -> pd.DataFrame:

    oda = ODAData(
        years=range(config.ANALYSIS_YEARS["start"], config.ANALYSIS_YEARS["end"] + 1),
        donors=list(donors),
        recipients=list(recipients),
        prices=prices,
        currency=currency,
        base_year=base_year,
        include_names=True,
    )

    data = (
        oda.load_indicator(list(config.RECIPIENTS_INDICATORS))
        .add_share_of_total(True)
        .add_share_of_gni()
        .get_data()
        .assign(
            indicator=lambda d: d.indicator.map(config.RECIPIENTS_INDICATORS),
            share_of=lambda d: d.share_of.map(config.RECIPIENTS_INDICATORS),
            recipient_name=lambda d: d.recipient_code.map(recipients),
        )
    )

    return data


def _get_data_donors_group(
        donors: dict,
        donor_group_name: str,
        donor_group_code: int,
        recipients: dict,
        prices: str,
        currency: str,
        base_year: int,
) -> pd.DataFrame:
    oda = ODAData(
        years=range(config.ANALYSIS_YEARS["start"], config.ANALYSIS_YEARS["end"] + 1),
        donors=list(donors),
        recipients=list(recipients),
        prices=prices,
        currency=currency,
        base_year=base_year,
        include_names=True,
    )

    # Get all data
    data = (
        oda.load_indicator(list(config.RECIPIENTS_INDICATORS) + ["gni"])
        .simplify_output_df(
            columns_to_keep=[
                "year",
                "recipient_code",
                "indicator",
                "currency",
                "prices",
            ]
        )
        .get_data()
        .assign(
            donor_name=donor_group_name,
            donor_code=donor_group_code,
            indicator=lambda d: d.indicator.map(
                config.RECIPIENTS_INDICATORS | {"gni": "GNI"}
            ),
            recipient_name=lambda d: d.recipient_code.map(recipients),
        )
    )

    # Add share of GNI
    gni = data.query("indicator == 'GNI'").filter(["year", "value"], axis=1)

    data = (
        data.query("indicator != 'GNI'")
        .merge(gni, how="left", on="year", suffixes=("", "_gni"))
        .assign(gni_share=lambda d: round(100 * d.value / d.value_gni, 5))
        .drop(columns=["value_gni"])
    )

    # Add share of total
    total = data.query(
        "indicator == 'Total' and recipient_name=='Developing countries, total'"
    ).filter(["year", "value"], axis=1)

    data = (
        data.merge(total, how="left", on="year", suffixes=("", "_total"))
        .assign(
            share=lambda d: round(100 * d.value / d.value_total, 5), share_of="Total"
        )
        .drop(columns=["value_total"])
    )

    return data


def get_recipients_data(
        donors: dict,
        recipients: dict,
        prices: str,
        currency: str,
        base_year: bool = None,
        donor_group: bool = False,
        donor_group_name: str = None,
        donor_group_code: int = None,
        custom_group: bool = False,
        custom_group_name: str = None,
) -> pd.DataFrame:
    if custom_group is False:
        if custom_group_name is not None:
            raise ValueError("A group name is only valid if custom group is true")

    if custom_group and custom_group_name is None:
        raise ValueError("A group name must be provided if custom group is true")

    if donor_group and donor_group_name is None:
        raise ValueError("A group name must be provided if donor group is true")

    if donor_group:
        data = _get_data_donors_group(
            donors=donors,
            donor_group_name=donor_group_name,
            donor_group_code=donor_group_code,
            recipients=recipients,
            prices=prices,
            currency=currency,
            base_year=base_year,
        )
    else:
        data = _get_data_individual_donors(
            donors=donors,
            recipients=recipients,
            prices=prices,
            currency=currency,
            base_year=base_year,
        )

    # Transform share of bilateral into share of total
    data = get_share_of_component(data)

    if custom_group:
        cols = [
            c
            for c in data.columns
            if c
               not in [
                   "recipient_name",
                   "recipient_code",
                   "value",
                   "share",
                   "gni_share",
                   "share_of_indicator",
               ]
        ]
        data = (
            data.loc[lambda d: d.recipient_name != "Developing countries, total"]
            .groupby(cols, dropna=False)
            .sum(numeric_only=True)
            .reset_index()
            .drop(columns=["recipient_code"])
            .assign(recipient_name=custom_group_name)
        )

    return data


def _recipients_dict_export(recipients: dict, donors: dict, versions: dict, **kwargs):
    recipients_versions = []

    for k, version in versions.items():
        recipients_versions.append(
            get_recipients_data(
                donors=donors, recipients=recipients, **version, **kwargs
            )
        )

    return pd.concat(recipients_versions, ignore_index=True)


def add_indicator_descriptions(df: pd.DataFrame) -> pd.DataFrame:
    import json

    # Read the indicators.json file
    with open(config.PATHS.scripts / "analysis_tools/indicators.json", "r") as f:
        indicators = json.load(f)

    names = config.RECIPIENTS_INDICATORS
    indicators = {names[k]: v for k, v in indicators.items() if k in names}

    return df.assign(description=lambda d: d.Indicator.map(indicators).fillna(""))


def recipients_pipeline(
        donors: dict,
        donor_group: bool = False,
        donor_group_name: str = None,
        donor_group_code: int = None,
) -> pd.DataFrame:
    versions = versions_dictionary()

    basic_data = _recipients_dict_export(
        DAC_GROUPS,
        donors=donors,
        versions=versions,
        donor_group=donor_group,
        donor_group_name=donor_group_name,
        donor_group_code=donor_group_code,
    )

    sahel = _recipients_dict_export(
        ONE_GROUPS["sahel"],
        donors=donors,
        versions=versions,
        custom_group=True,
        custom_group_name="Sahel",
        donor_group=donor_group,
        donor_group_name=donor_group_name,
        donor_group_code=donor_group_code,
    )

    france_priority = _recipients_dict_export(
        ONE_GROUPS["france_priority"],
        donors=donors,
        versions=versions,
        custom_group=True,
        custom_group_name="France priority countries",
        donor_group=donor_group,
        donor_group_name=donor_group_name,
        donor_group_code=donor_group_code,
    )

    return (
        pd.concat([basic_data, sahel, france_priority], ignore_index=True)
        .drop_duplicates()
        .drop(columns=["donor_code", "recipient_code"])
        .rename(columns=config.COLUMNS)
        .replace(config.VALUES, regex=False)
    )


def export_recipients_data() -> None:
    individual_donors = recipients_pipeline(donors=DASHBOARD_DONORS)
    eu27 = recipients_pipeline(
        donors=EU27, donor_group=True, donor_group_name="EU27", donor_group_code=90027
    )

    data = pd.concat([individual_donors, eu27], ignore_index=True)

    # Add indicator descriptions
    data = add_indicator_descriptions(data)

    # Export the data
    data.to_csv(config.PATHS.output / "recipients.csv", index=False)

    get_unique_values(data, "Recipients")


if __name__ == "__main__":
    ...
    export_recipients_data()  # df = pd.read_csv(settings.PATHS.output / "recipients.csv")