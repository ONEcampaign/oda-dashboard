"""The topic page's COVID-19 series must stay what the static input says, whatever oda-data does."""

import pandas as pd
import pytest

from src.data.config import DAC_COUNTRIES_NAME, PATHS
from src.data.topic_page.covid import covid_bi_multi_dac

# DAC countries' COVID-19 ODA per year, USD millions, as published before oda-data 3.
DAC_COVID_ODA: dict[int, float] = {
    2020: 7_215.06,
    2021: 13_355.94,
    2022: 16_774.40,
    2023: 7_295.37,
    2024: 4_940.40,
}


@pytest.fixture(scope="module")
def covid() -> pd.DataFrame:
    return covid_bi_multi_dac()


def test_dac_covid_sums_are_unchanged(covid):
    dac = covid.loc[covid["donor_name"] == DAC_COUNTRIES_NAME].set_index("year")
    assert dac["value"].to_dict() == pytest.approx(DAC_COVID_ODA, abs=0.005)


def test_every_donor_in_the_input_is_a_dac_member(covid):
    unmatched = covid.loc[covid["donor_code"].isna(), "donor_name"].unique()
    assert list(unmatched) == []


def test_oda_covid_csv_publishes_the_series(covid):
    published = pd.read_csv(PATHS.TOPIC_PAGE / "oda_covid.csv")
    expected = covid.rename(columns={"donor_name": "Donor", "year": "Year"})[
        ["Donor", "Year", "value"]
    ]
    merged = published.merge(
        expected, on=["Donor", "Year"], how="outer", indicator=True
    )

    # Every input row reaches the CSV; donor-years without COVID-19 ODA publish 0.
    assert (merged["_merge"] != "right_only").all()
    assert merged["COVID ODA"].to_numpy() == pytest.approx(
        merged["value"].fillna(0).to_numpy(), abs=1e-9
    )
