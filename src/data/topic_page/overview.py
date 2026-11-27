"""The topic page overview: key numbers and the small charts beside them.

Every figure uses a dashboard view's definition, with DAC countries summed from its members:
Total ODA and ODA/GNI the financing view's, aid to Africa, regions and income groups the
recipients view's (DAC2A Part I, bilateral plus imputed multilateral), and sectors the sectors
view's.
"""

import pandas as pd

from src.data.analysis_tools.oda import ProvenanceLog, open_context
from src.data.analysis_tools.recipients import read_dac2a_part_i
from src.data.analysis_tools.transformations import drop_empty_values
from src.data.config import (
    DAC_COUNTRIES,
    DAC_COUNTRIES_NAME,
    MILLIONS_PER_BILLION,
    PATHS,
    PERCENT,
    RECIPIENTS_LINES,
    UNITS_PER_MILLION,
    UNSPECIFIED_RECIPIENT_CODE,
    logger,
)
from src.data.topic_page.common import (
    BILLION,
    CONSTANT_YEAR,
    KEY_NUMBERS_FILE,
    LATEST_YEAR_AGG,
    LATEST_YEAR_DETAIL,
    LONG_START_YEAR,
    MINI_CHART_START_YEAR,
    SECTORS_START_YEAR,
    add_change,
    describe_change,
    df_to_key_number,
    format_billions,
    format_percentage,
    oda_gni_table,
    sort_dac_first,
    to_usd_constant,
    update_key_number,
    with_dac_total,
)
from src.data.topic_page.sectors import sector_totals

AFRICA_CODE: int = 10_001
DEVELOPING_COUNTRIES_CODE: int = 10_100
DEVELOPING_COUNTRIES: str = "Developing Countries, Total"
# DAC2A income groups, labelled as the topic page shows them.
INCOME_GROUPS: dict[int, str] = {
    10_024: "Not classified by income",
    10_045: "Low income",
    10_046: "Lower-middle income",
    10_047: "Upper-middle income",
    10_048: "High income",
    10_049: "Not classified by income",
    DEVELOPING_COUNTRIES_CODE: DEVELOPING_COUNTRIES,
}
# DAC2A regions, labelled as the topic page shows them. Middle East is part of Asia, so it is
# left out to avoid counting it twice.
REGIONS: dict[int, str] = {
    10_001: "Africa",
    10_004: "America",
    10_007: "Asia",
    10_010: "Europe",
    10_012: "Oceania",
    UNSPECIFIED_RECIPIENT_CODE: "Developing countries, unspecified",
}

KEY_SECTORS: list[str] = [
    "Humanitarian",
    "Education",
    "Health",
    "Refugees in Donor Countries",
    "Environment Protection",
]


def _save_quoted_shares(df: pd.DataFrame, column: str, filename: str) -> None:
    """Write a chart CSV whose share column is wrapped in one pair of double quotes."""
    path = PATHS.TOPIC_PAGE / filename
    df.assign(**{column: lambda d: '"' + d[column] + '"'}).to_csv(path, index=False)
    path.write_text(path.read_text().replace('"""', '"'))
    logger.info("Saved chart version of %s", filename)


def _update_key_numbers(numbers: dict) -> None:
    """Merge numbers into the topic page's key numbers JSON."""
    update_key_number(PATHS.TOPIC_PAGE / KEY_NUMBERS_FILE, numbers)
    logger.info("Updated dynamic text ODA topic page %s", KEY_NUMBERS_FILE)


def _with_named_dac_total(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Append the DAC countries total and name every member from DAC_COUNTRIES."""
    data = with_dac_total(df, group_cols)
    data["donor_name"] = data["donor_name"].fillna(
        data["donor_code"].map(DAC_COUNTRIES)
    )
    return data


def _save_dac_first(df: pd.DataFrame, filename: str) -> None:
    """Write a chart CSV sorted by year and name, with every DAC countries row first."""
    sort_dac_first(df.sort_values(["year", "name"], ignore_index=True)).to_csv(
        PATHS.TOPIC_PAGE / filename, index=False
    )
    logger.info("Saved chart version of %s", filename)


def total_aid_key_number(dac: pd.DataFrame) -> None:
    """Write sm_total_oda.csv and the Total ODA key numbers: the latest year and real change.

    Args:
        dac: oda_gni_table rows for DAC countries in the latest two years.
    """
    data = (
        dac.sort_values("year")
        .assign(
            value=lambda d: d["oda_constant"],
            pct_change=lambda d: d["value"].pct_change(),
        )
        .loc[lambda d: d["year"] == d["year"].max()]
    )
    year = int(data["year"].item())
    change = describe_change(float(data["pct_change"].item()))
    data = data.assign(
        value=lambda d: d["value"] * UNITS_PER_MILLION,
        pct_change=lambda d: format_percentage(d["pct_change"], decimals=1).str.replace(
            "%", ""
        ),
        first_line=f"As of {year}",
        second_line=f"real change from {year - 1}",
        centre=lambda d: (d["pct_change"].astype(float) / PERCENT).round(2),
    )[["first_line", "value", "second_line", "pct_change", "centre"]]

    data.to_csv(PATHS.TOPIC_PAGE / "sm_total_oda.csv", index=False)
    logger.info("Saved chart version of sm_total_oda.csv for %s", year)

    _update_key_numbers(
        {
            "total_oda": f"{data['value'].item() / BILLION:,.1f} billion",
            "total_oda_change": f"{float(data['pct_change'].item()):.1f}%",
            "total_oda_change_abs": change["abs"],
            "total_oda_change_verb": change["verb"],
            "total_oda_change_noun": change["noun"],
            "latest_year": str(year),
            "previous_year": str(year - 1),
            "latest_year_detail": str(LATEST_YEAR_DETAIL),
        }
    )


def aid_gni_key_number(dac: pd.DataFrame) -> None:
    """Write oda_gni_sm.csv and the ODA/GNI key numbers for the latest year.

    The distance to 0.7% is in current USD millions.

    Args:
        dac: oda_gni_table rows for DAC countries in the latest two years.
    """
    year = int(dac["year"].max())
    data = (
        dac.sort_values("year")
        .assign(
            oda_gni=lambda d: d["oda_gni"].round(6),
            distance=lambda d: d["gap_current"].round(1),
            first_line=f"As of {year}",
            second_line="Additional required to get to 0.7%",
        )
        .assign(centre=lambda d: d["oda_gni"].pct_change().round(4))
        .loc[lambda d: d["year"] == year]
    )[["first_line", "oda_gni", "second_line", "distance", "centre"]]

    data.to_csv(PATHS.TOPIC_PAGE / "oda_gni_sm.csv", index=False)
    logger.info("Saved chart version of oda_gni_sm.csv for %s", year)

    _update_key_numbers(
        {
            "oda_gni": f"{PERCENT * data['oda_gni'].item():,.2f}%",
            "oda_gni_distance": f"{data['distance'].item() / MILLIONS_PER_BILLION:,.0f} billion",
        }
    )


def recipients_by_donor(
    *,
    recipients: dict[int, str],
    years: range,
    base_year: int,
    provenance: ProvenanceLog,
) -> pd.DataFrame:
    """Read each DAC member's bilateral plus imputed multilateral ODA to DAC2A recipients.

    Read as the recipients view reads it: DAC2A Part I lines 206 and 106, net flows, per
    member, converted per donor, with the DAC countries total summed from its members. Zero
    rows are dropped first, as the view drops them: some fall in donor-years without a
    conversion factor (newer members before they reported), which the conversion refuses.

    Args:
        recipients: DAC2A recipient code -> label; codes sharing a label are summed.
        years: Contiguous years to read.
        base_year: Base year of the constant prices.
        provenance: Log to record the DAC2A release and the conversion factors in.

    Returns:
        donor_name, year, recipient (the label), current and constant (USD millions), for
        every DAC member and the DAC countries total.
    """
    raw = drop_empty_values(
        read_dac2a_part_i(
            lines=RECIPIENTS_LINES,
            years=years,
            providers=DAC_COUNTRIES,
            recipients=recipients,
            provenance=provenance,
        ),
        "DAC2A",
    )
    keys = ["donor_code", "year", "recipient"]
    current = (
        raw.assign(recipient=raw["recipient_code"].map(recipients))
        .groupby(keys, as_index=False)["value"]
        .sum()
    )
    constant = to_usd_constant(current, base_year=base_year, provenance=provenance)
    prices = [
        _with_named_dac_total(df, ["year", "recipient"])
        .set_index(["donor_name", "year", "recipient"])["value"]
        .rename(name)
        for name, df in (("current", current), ("constant", constant))
    ]
    return pd.concat(prices, axis=1).reset_index()


def dac_to_recipients(
    *,
    recipients: dict[int, str],
    years: range,
    base_year: int,
    provenance: ProvenanceLog,
) -> pd.DataFrame:
    """The DAC countries total from recipients_by_donor (same arguments).

    Returns:
        year, recipient (the label), current and constant (USD millions).
    """
    data = recipients_by_donor(
        recipients=recipients, years=years, base_year=base_year, provenance=provenance
    )
    return data.loc[data["donor_name"] == DAC_COUNTRIES_NAME].drop(columns="donor_name")


def aid_to_africa_ts(provenance: ProvenanceLog) -> None:
    """Write aid_to_africa_ts.csv and the aid to Africa key numbers.

    Amounts are constant USD of CONSTANT_YEAR. The share of total ODA is computed in current
    USD, as the recipients view computes its shares. The file starts in MINI_CHART_START_YEAR;
    the year before it is read so its first annual change has a previous year.

    Args:
        provenance: Log to record every read in.
    """
    data = dac_to_recipients(
        recipients={
            AFRICA_CODE: "Africa",
            DEVELOPING_COUNTRIES_CODE: DEVELOPING_COUNTRIES,
        },
        years=range(MINI_CHART_START_YEAR - 1, LATEST_YEAR_DETAIL + 1),
        base_year=CONSTANT_YEAR,
        provenance=provenance,
    ).pivot(index="year", columns="recipient", values=["current", "constant"])

    data = (
        pd.DataFrame(
            {
                "year": data.index,
                "donor_name": DAC_COUNTRIES_NAME,
                "value": data[("constant", "Africa")].to_numpy(),
                "share": format_percentage(
                    data[("current", "Africa")]
                    / data[("current", DEVELOPING_COUNTRIES)],
                    decimals=1,
                ).to_numpy(),
            }
        )
        .pipe(add_change, as_formatted_str=True, grouper="donor_name")
        .assign(value=lambda d: format_billions(d["value"] * UNITS_PER_MILLION))
        .rename(
            columns={
                "year": "Year",
                "donor_name": "Donor",
                "value": "Aid to Africa",
                "share": "Share of total ODA",
                "pct_change": "Annual change",
            }
        )
    )
    _save_quoted_shares(
        data.loc[data["Year"] >= MINI_CHART_START_YEAR],
        "Share of total ODA",
        "aid_to_africa_ts.csv",
    )

    _update_key_numbers(
        {
            "aid_to_africa": f"{data['Aid to Africa'].to_numpy()[-1]} billion",
            "aid_to_africa_share": f"{data['Share of total ODA'].to_numpy()[-1]}",
        }
    )


def aid_to_incomes_latest(provenance: ProvenanceLog) -> None:
    """Write aid_to_income_latest.csv and the aid by income group key numbers.

    Amounts are constant USD of CONSTANT_YEAR; shares are of the DAC countries' ODA to
    developing countries.

    Args:
        provenance: Log to record every read in.
    """
    totals = dac_to_recipients(
        recipients=INCOME_GROUPS,
        years=range(LATEST_YEAR_DETAIL, LATEST_YEAR_DETAIL + 1),
        base_year=CONSTANT_YEAR,
        provenance=provenance,
    )
    developing = totals.loc[
        totals["recipient"] == DEVELOPING_COUNTRIES, ["year", "constant"]
    ].rename(columns={"constant": "developing"})

    data = (
        totals.loc[totals["recipient"] != DEVELOPING_COUNTRIES]
        .merge(developing, on="year", validate="m:1")
        .sort_values(["year", "recipient"])
        .assign(
            donor_name=DAC_COUNTRIES_NAME,
            share=lambda d: (d["constant"] / d["developing"] * PERCENT).round(1),
            value=lambda d: format_billions(d["constant"] * UNITS_PER_MILLION),
            label=lambda d: d["recipient"] + ": " + d["share"].astype(str) + "%",
        )
        .rename(
            columns={
                "year": "Year",
                "donor_name": "Donor",
                "recipient": "Recipient",
                "value": "ODA",
                "share": "Share of total ODA",
                "label": "Label",
            }
        )[["Year", "Donor", "Recipient", "ODA", "Share of total ODA", "Label"]]
    )
    data.assign(ODA=lambda d: "US$" + d["ODA"] + " billion").to_csv(
        PATHS.TOPIC_PAGE / "aid_to_income_latest.csv", index=False
    )
    logger.info("Saved chart version of aid_to_income_latest.csv")

    _update_key_numbers(
        df_to_key_number(
            data.rename(columns={"ODA": "value", "Share of total ODA": "share"}).assign(
                share=lambda d: d["share"].astype(str) + "%"
            ),
            indicator_name="aid_to_incomes",
            id_column="Recipient",
            value_columns=["value", "share"],
        )
    )


def _region_note(row: pd.Series, regions: list[str]) -> str:
    """The regions chart's tooltip: each region's amount in USD millions, one per line."""
    return "<br>".join(
        f"<b>{region}:</b> {row[region]:,.1f} million"
        for region in regions
        if pd.notna(row[region])
    )


def aid_to_regions_ts(provenance: ProvenanceLog) -> None:
    """Write aid_to_regions_ts.csv: ODA to each region per DAC member and year.

    Amounts are constant USD millions of CONSTANT_YEAR, one column per region, plus an HTML
    note listing every region for the chart's tooltip.

    Args:
        provenance: Log to record every read in.
    """
    regions = sorted(REGIONS.values())
    data = (
        recipients_by_donor(
            recipients=REGIONS,
            years=range(LONG_START_YEAR, LATEST_YEAR_DETAIL + 1),
            base_year=CONSTANT_YEAR,
            provenance=provenance,
        )
        .pivot(index=["year", "donor_name"], columns="recipient", values="constant")
        .reindex(columns=regions)
        .round(2)
        .rename_axis(None, axis=1)
        .reset_index()
        .rename(columns={"donor_name": "name"})
    )
    data["note"] = data.apply(_region_note, axis=1, regions=regions)
    _save_dac_first(data, "aid_to_regions_ts.csv")


def aid_to_incomes_ts(provenance: ProvenanceLog) -> None:
    """Write aid_to_income_ts.csv: ODA to each income group per DAC member and year.

    Amounts are constant USD billions of CONSTANT_YEAR. Each group's column appears twice,
    the second named "<group> (value)", as the article's chart is bound to both.

    Args:
        provenance: Log to record every read in.
    """
    groups = {
        code: name
        for code, name in INCOME_GROUPS.items()
        if code != DEVELOPING_COUNTRIES_CODE
    }
    data = (
        recipients_by_donor(
            recipients=groups,
            years=range(LONG_START_YEAR, LATEST_YEAR_DETAIL + 1),
            base_year=CONSTANT_YEAR,
            provenance=provenance,
        )
        .pivot(index=["donor_name", "year"], columns="recipient", values="constant")
        .reindex(columns=sorted(set(groups.values())))
        .div(MILLIONS_PER_BILLION)
        .round(2)
        .rename_axis(None, axis=1)
    )
    data = (
        data.join(data.add_suffix(" (value)"))
        .reset_index()
        .rename(columns={"donor_name": "name"})
    )
    _save_dac_first(data, "aid_to_income_ts.csv")


def sector_totals_ts(sectors: pd.DataFrame) -> None:
    """Write sector_totals.csv: ODA per broad sector, DAC member and year.

    Amounts are constant USD millions of CONSTANT_YEAR. Sectors are ordered by the DAC
    countries total summed over every year in the file, largest first.

    Args:
        sectors: From sector_totals.
    """
    data = _with_named_dac_total(sectors, ["year", "sector"])
    dac = data.loc[data["donor_name"] == DAC_COUNTRIES_NAME]
    order = dac.groupby("sector")["value"].sum().sort_values(ascending=False).index
    if set(order) != set(data["sector"]):
        raise ValueError("Some sectors have no DAC countries total to order them by")
    wide = (
        data.pivot(index=["year", "donor_name"], columns="sector", values="value")
        .reindex(columns=order)
        .round(1)
        .rename_axis(None, axis=1)
        .reset_index()
        .rename(columns={"donor_name": "name"})
    )
    _save_dac_first(wide, "sector_totals.csv")


def _dac_sector_amounts(sectors: pd.DataFrame) -> pd.DataFrame:
    """DAC countries per year and sector, with each sector's share of all sectors."""
    data = with_dac_total(sectors, ["year", "sector"]).loc[
        lambda d: d["donor_name"] == DAC_COUNTRIES_NAME
    ]
    data = data.assign(
        share=format_percentage(
            data["value"] / data.groupby("year")["value"].transform("sum"), decimals=1
        ),
        value=format_billions(data["value"] * UNITS_PER_MILLION),
        recipient="All Developing Countries",
    )
    return data.rename(
        columns={
            "year": "Year",
            "donor_name": "Donor",
            "recipient": "Recipient",
            "sector": "Sector",
            "share": "Share of total ODA",
        }
    )[["Year", "Donor", "Recipient", "Sector", "value", "Share of total ODA"]]


def aid_to_sectors_ts(sectors: pd.DataFrame) -> None:
    """Write aid_to_{health,humanitarian}_ts.csv and their key numbers.

    The files start in MINI_CHART_START_YEAR; the shares use every sector of each year.

    Args:
        sectors: From sector_totals, constant USD of CONSTANT_YEAR.
    """
    data = _dac_sector_amounts(sectors)

    for sector, column, filename, key in (
        ("Health", "Total aid to health", "aid_to_health_ts.csv", "aid_to_health"),
        (
            "Humanitarian",
            "Total Humanitarian Aid",
            "aid_to_humanitarian_ts.csv",
            "aid_to_humanitarian",
        ),
    ):
        rows = (
            data.loc[data["Sector"] == sector]
            .sort_values("Year")
            .rename(columns={"value": column})
        )
        _save_quoted_shares(
            rows.loc[rows["Year"] >= MINI_CHART_START_YEAR],
            "Share of total ODA",
            filename,
        )
        _update_key_numbers(
            {
                key: f"{rows[column].to_numpy()[-1]} billion",
                f"{key}_share": f"{rows['Share of total ODA'].to_numpy()[-1]}",
            }
        )


def key_sector_shares(sectors: pd.DataFrame) -> None:
    """Write key_sector_shares.csv: key sectors' shares of each donor's sector total.

    Args:
        sectors: From sector_totals.
    """
    data = _with_named_dac_total(sectors, ["year", "sector"])
    data["share"] = (
        data["value"] / data.groupby(["year", "donor_name"])["value"].transform("sum")
    ).round(4)

    result = (
        data.pivot(index=["year", "donor_name"], columns="sector", values="share")
        .rename_axis(None, axis=1)
        .reset_index()
        .rename(columns={"donor_name": "name"})
        .reindex(columns=["year", "name", *KEY_SECTORS])
        # DAC total first within each year, then donors alphabetically
        .assign(_sort=lambda d: d["name"].where(d["name"] != DAC_COUNTRIES_NAME, ""))
        .sort_values(["year", "_sort"])
        .drop(columns="_sort")
        .reset_index(drop=True)
        .rename(columns={"year": "Year"})
    )

    result.to_csv(PATHS.TOPIC_PAGE / "key_sector_shares.csv", index=False)
    logger.info("Saved chart version of key_sector_shares.csv")


def main() -> None:
    """Write every overview chart and key number."""
    provenance = ProvenanceLog()
    with open_context() as ctx:
        dac = oda_gni_table(
            ctx,
            years=range(LATEST_YEAR_AGG - 1, LATEST_YEAR_AGG + 1),
            providers=DAC_COUNTRIES,
            base_year=CONSTANT_YEAR,
            provenance=provenance,
        ).loc[lambda d: d["donor_name"] == DAC_COUNTRIES_NAME]
        total_aid_key_number(dac)
        aid_gni_key_number(dac)
        aid_to_africa_ts(provenance)
        aid_to_incomes_latest(provenance)
        aid_to_regions_ts(provenance)
        aid_to_incomes_ts(provenance)

        sectors = sector_totals(
            ctx,
            years=range(SECTORS_START_YEAR, LATEST_YEAR_DETAIL + 1),
            base_year=CONSTANT_YEAR,
            provenance=provenance,
        )
    aid_to_sectors_ts(sectors)
    key_sector_shares(sectors)
    sector_totals_ts(sectors)


if __name__ == "__main__":
    main()
