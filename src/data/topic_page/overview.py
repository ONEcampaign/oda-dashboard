import pandas as pd
from bblocks import format_number

from src.data.analysis_tools.helper_functions import set_cache_dir

from oda_data import OECDClient, provider_groupings

from src.data.config import PATHS, logger
from src.data.topic_page.common import (
    LATEST_YEAR_AGG,
    CONSTANT_YEAR,
    update_key_number,
    add_change,
    START_YEAR,
    LATEST_YEAR_DETAIL,
    df_to_key_number,
)
from src.data.topic_page.sectors import total_sectors


def total_aid_key_number() -> None:
    """"""

    client = OECDClient(
        years=[LATEST_YEAR_AGG, LATEST_YEAR_AGG - 1],
        providers=20001,
        base_year=CONSTANT_YEAR,
        measure="grant_equivalent",
        use_bulk_download=True,
    )

    data = (
        client.get_indicators(indicators=["DAC1.10.11010"])
        .pipe(
            add_change, as_formatted_str=True, grouper=["donor_code", "one_indicator"]
        )
        .loc[lambda d: d.year == d.year.max()]
        .assign(
            value=lambda d: d.value * 1e6,
            pct_change=lambda d: d["pct_change"].str.replace("%", ""),
            first_line=lambda d: f"As of {d.year.item()}",
            second_line=lambda d: f"real change from {d.year.item() - 1}",
            centre=lambda d: round(d["pct_change"].astype(float) / 100, 2),
        )
        .filter(["first_line", "value", "second_line", "pct_change", "centre"])
    )

    data.to_csv(PATHS.TOPIC_PAGE / "sm_total_oda.csv", index=False)
    logger.info(f"Saved chart version of sm_total_oda.csv for {LATEST_YEAR_AGG}")

    kn = {
        "total_oda": f"{data['value'].item() / 1e9:,.1f} billion",
        "total_oda_change": f"{float(data['pct_change'].item()):.1f} %",
        "latest_year": f"{data['first_line'].item().split(' ')[-1]}",
    }

    update_key_number(f"{PATHS.TOPIC_PAGE}/oda_key_numbers.json", kn)
    logger.debug("Updated dynamic text ODA topic page oda_key_numbers.json")


def aid_gni_key_number() -> None:
    client = OECDClient(
        years=[LATEST_YEAR_AGG, LATEST_YEAR_AGG - 1],
        providers=20001,
        measure=["grant_equivalent", "net_disbursement"],
        use_bulk_download=True,
    )
    data = (
        client.get_indicators(indicators=["DAC1.40.1", "DAC1.10.11010"])
        .filter(["donor_name", "one_indicator", "year", "value"])
        .pivot(index=["donor_name", "year"], columns="one_indicator", values="value")
        .reset_index(drop=False)
        .assign(
            oda_gni=lambda d: round(d["DAC1.10.11010"] / d["DAC1.40.1"], 6),
            distance=lambda d: round(d["DAC1.40.1"] * 0.007 - d["DAC1.10.11010"], 1),
            first_line=f"As of {LATEST_YEAR_AGG}",
            second_line="Additional required to get to 0.7%",
        )
        .sort_values("year")
        .assign(centre=lambda d: d["oda_gni"].pct_change().round(4))
        .loc[lambda d: d["year"] == d["year"].max()]
        .filter(["first_line", "oda_gni", "second_line", "distance", "centre"])
    )

    # Save chart version
    data.to_csv(PATHS.TOPIC_PAGE / "oda_gni_sm.csv", index=False)
    logger.info(f"Saved chart version of oda_gni_sm.csv for {LATEST_YEAR_AGG}")

    # Save dynamic text version
    kn = {
        "oda_gni": f"{100 * data.oda_gni.item():,.2f}%",
        "oda_gni_distance": f"{data.distance.item() / 1e3:,.0f} billion",
    }

    update_key_number(f"{PATHS.TOPIC_PAGE}/oda_key_numbers.json", kn)
    logger.info("Updated dynamic text ODA topic page oda_key_numbers.json")


def aid_to_africa_ts() -> None:
    client = OECDClient(
        years=range(START_YEAR, LATEST_YEAR_DETAIL + 1),
        providers=20001,
        recipients=[10001, 10100],
        base_year=CONSTANT_YEAR,
        measure=["net_disbursement"],
        use_bulk_download=True,
    )

    data = (
        client.get_indicators(indicators=["DAC2A.10.106", "DAC2A.10.206"])
        .rename(columns={"donor": "donor_name", "recipient": "recipient_name"})
        .groupby(["year", "donor_name", "recipient_name"], dropna=False)[["value"]]
        .sum()
        .reset_index(drop=False)
        .pivot(index=["year", "donor_name"], columns="recipient_name", values="value")
        .reset_index(drop=False)
    )

    data = (
        data.assign(
            share=lambda d: format_number(
                d["Africa, Total"] / d["Developing Countries, Total"],
                as_percentage=True,
                decimals=1,
            )
        )
        .rename(columns={"Africa, Total": "value"})
        .filter(["year", "donor_name", "value", "share"])
        .pipe(add_change, as_formatted_str=True, grouper="donor_name")
        .assign(
            value=lambda d: format_number(d.value * 1e6, as_billions=True, decimals=1),
        )
        .rename(
            columns={
                "year": "Year",
                "donor_name": "Donor",
                "value": "Aid to Africa",
                "share": "Share of total ODA",
                "pct_change": "Annual change"
            }
        )
    )
    # chart version
    data.to_csv(f"{PATHS.TOPIC_PAGE}/aid_to_africa_ts.csv", index=False)
    logger.info(f"Saved chart version of aid_to_africa_ts.csv for {LATEST_YEAR_AGG}")

    # Dynamic text version
    kn = {
        "aid_to_africa": f"{data['Aid to Africa'].values[-1]} billion",
        "aid_to_africa_share": f"{data['Share of total ODA'].values[-1]}",
    }
    update_key_number(f"{PATHS.TOPIC_PAGE}/oda_key_numbers.json", kn)
    logger.info("Updated dynamic text ODA topic page oda_key_numbers.json")


def aid_to_incomes_latest():
    recipients = {
        10024: "Not classified by income",
        10045: "Low income",
        10046: "Lower-middle income",
        10047: "Upper-middle income",
        10048: "High income",
        10049: "Not classified by income",
        10100: "Developing Countries, Total",
    }

    client = OECDClient(
        years=LATEST_YEAR_DETAIL,
        providers=20001,
        recipients=list(recipients),
        base_year=LATEST_YEAR_DETAIL,
        measure=["net_disbursement"],
        use_bulk_download=True,
    )

    data = (
        client.get_indicators(indicators=["DAC2A.10.106", "DAC2A.10.206"])
        .assign(recipient=lambda d: d.recipient_code.map(recipients))
        .groupby(["year", "donor_name", "recipient"], dropna=False)[["value"]]
        .sum()
        .reset_index(drop=False)
        .pivot(index=["year", "donor_name"], columns="recipient", values="value")
        .reset_index(drop=False)
        .melt(id_vars=["year", "donor_name", "Developing Countries, Total"])
        .assign(
            share=lambda d: (d.value / d["Developing Countries, Total"] * 100).round(1),
            value=lambda d: format_number(d.value * 1e6, as_billions=True, decimals=1),
            label=lambda d: d["recipient"] + ": " + d["share"].astype(str) + "%",
        )
        .rename(
            columns={
                "year": "Year",
                "donor_name": "Donor",
                "recipient": "Recipient",
                "value": "ODA",
                "share": "Share of total ODA",
                "label": "Label"
            })
        .filter(["Year", "Donor", "Recipient", "ODA", "Share of total ODA", "Label"], axis=1)
    )
    # chart version
    data.to_csv(f"{PATHS.TOPIC_PAGE}/aid_to_income_latest.csv", index=False)
    logger.debug("Saved chart version of aid_to_income_latest.csv")

    # Dynamic text version
    income_dict = df_to_key_number(
        data.rename(columns={"ODA": "value", "Share of total ODA": "share"})
        .assign(share=lambda d: d['share'].astype(str) + "%"),
        indicator_name="aid_to_incomes",
        id_column="Recipient",
        value_columns=["value", "share"],
    )

    update_key_number(f"{PATHS.TOPIC_PAGE}/oda_key_numbers.json", income_dict)
    logger.debug("Updated dynamic text ODA topic page oda_key_numbers.json")


def aid_to_sectors_ts() -> None:
    """"""
    data = (
        total_sectors(
            years=range(START_YEAR, LATEST_YEAR_DETAIL + 1),
            as_total=True,
            broad=True,
            base_year=LATEST_YEAR_DETAIL,
        )
        .assign(recipient="All Developing Countries", donor="DAC Countries, Total")
        .groupby(
            ["year", "donor", "recipient", "sub_sector"], dropna=False, observed=True
        )["value"]
        .sum()
        .reset_index(drop=False)
    )

    data["share"] = format_number(
        data["value"]
        / data.groupby(["year", "donor", "recipient"])["value"].transform("sum"),
        decimals=1,
        as_percentage=True,
    )

    data["value"] = format_number(data["value"] * 1e6, as_billions=True, decimals=1)

    data = data.rename(
        columns={
            "year": "Year",
            "donor": "Donor",
            "recipient": "Recipient",
            "sub_sector": "Sector",
            "share": "Share of total ODA"
    })

    # Health
    data_health = data.loc[lambda d: d.Sector.isin(["Health"])].rename(
        columns={"value": "Total aid to health"}
    )

    # chart version
    data_health.to_csv(f"{PATHS.TOPIC_PAGE}/aid_to_health_ts.csv", index=False)
    logger.debug("Saved chart version of aid_to_health_ts.csv")

    kn = {
        "aid_to_health": f"{data_health['Total aid to health'].values[-1]} billion",
        "aid_to_health_share": f"{data_health['Share of total ODA'].values[-1]}",
    }
    update_key_number(f"{PATHS.TOPIC_PAGE}/oda_key_numbers.json", kn)
    logger.debug("Updated dynamic text ODA topic page oda_key_numbers.json")

    # Humanitarian
    data_humanitarian = data.loc[lambda d: d.Sector.isin(["Humanitarian"])].rename(
        columns={"value": "Total Humanitarian Aid"}
    )
    # chart version
    data_humanitarian.to_csv(
        f"{PATHS.TOPIC_PAGE}/aid_to_humanitarian_ts.csv", index=False
    )
    logger.info("Saved chart version of aid_to_humanitarian_ts.csv")

    # Dynamic text version
    kn = {
        "aid_to_humanitarian": f"{data_humanitarian['Total Humanitarian Aid'].values[-1]} billion",
        "aid_to_humanitarian_share": f"{data_humanitarian['Share of total ODA'].values[-1]}",
    }
    update_key_number(f"{PATHS.TOPIC_PAGE}/oda_key_numbers.json", kn)
    logger.debug("Updated dynamic text ODA topic page oda_key_numbers.json")


KEY_SECTORS: list[str] = [
    "Humanitarian",
    "Education",
    "Health",
    "Refugees in Donor Countries",
    "Environment Protection",
]


def key_sector_shares() -> None:
    """Generate sector shares of total bilateral + imputed multilateral ODA, by donor and year."""
    donor_names: dict[int, str] = provider_groupings()["dac_countries"] | {
        20001: "DAC Countries, Total"
    }

    raw = total_sectors(
        years=range(START_YEAR, LATEST_YEAR_DETAIL + 1),
        as_total=True,
        broad=True,
        base_year=LATEST_YEAR_DETAIL,
    )

    # Sum across all recipients → one row per year/donor/sector
    by_donor = (
        raw.groupby(["year", "donor_code", "sub_sector"], dropna=False, observed=True)[
            "value"
        ]
        .sum()
        .reset_index()
    )

    # Build DAC total as the sum of individual donors
    # (20001 is not in the CRS/imputed-multilateral micro-data)
    dac_total = (
        by_donor.groupby(["year", "sub_sector"], dropna=False, observed=True)["value"]
        .sum()
        .reset_index()
        .assign(donor_code=20001)
    )

    data = (
        pd.concat([by_donor, dac_total], ignore_index=True)
        .assign(name=lambda d: d["donor_code"].map(donor_names))
        .loc[lambda d: d["name"].notna()]
    )

    data["share"] = (
        data["value"]
        / data.groupby(["year", "donor_code"])["value"].transform("sum")
    ).round(4)

    result = (
        data.pivot(index=["year", "name"], columns="sub_sector", values="share")
        .rename_axis(None, axis=1)
        .reset_index()
        .filter(["year", "name"] + KEY_SECTORS, axis=1)
        # DAC total first within each year, then donors alphabetically
        .assign(_sort=lambda d: d["name"].where(d["name"] != "DAC Countries, Total", ""))
        .sort_values(["year", "_sort"])
        .drop(columns="_sort")
        .reset_index(drop=True)
        .rename(
            columns={
                "year": "Year",
                "donor": "Donor"
            }
        )
    )

    result.to_csv(PATHS.TOPIC_PAGE / "key_sector_shares.csv", index=False)
    logger.info("Saved chart version of key_sector_shares.csv")


if __name__ == "__main__":
    set_cache_dir(oda_data=True, pydeflate=True)

    # total_aid_key_number()
    # aid_gni_key_number()
    # aid_to_africa_ts()
    aid_to_incomes_latest()
    # aid_to_sectors_ts()
    # key_sector_shares()
