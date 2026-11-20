"""COVID-19 and health ODA by DAC member, from static inputs no code in this repo generates.

The series come from bi_plus_multi_health_spending_*.csv in topic_page/. oda-data only
supplies the DAC members' codes, so the series do not depend on the library version.
"""

import pandas as pd

from src.data.config import DAC_COUNTRIES, DAC_COUNTRIES_NAME, PATHS

# DAC member name -> code, for the static files, which carry names only.
DAC_MEMBER_CODES: dict[str, int] = {name: code for code, name in DAC_COUNTRIES.items()}
# The OECD's provider code for the DAC countries total.
DAC_COUNTRIES_CODE: int = 20001


def covid_bi_multi_dac() -> pd.DataFrame:
    """COVID-19 ODA per DAC member and year, plus the DAC total, as the static file has it."""
    df = pd.read_csv(
        PATHS.TOPIC_PAGE / "bi_plus_multi_health_spending_multiple_donors.csv"
    )
    df["donor_code"] = df["donor_name"].map(DAC_MEMBER_CODES)

    total = (
        df.groupby(["year"], as_index=False)["covid_oda"]
        .sum()
        .assign(donor_name=DAC_COUNTRIES_NAME, donor_code=DAC_COUNTRIES_CODE)
    )

    return pd.concat([df, total], ignore_index=True).rename(
        columns={"covid_oda": "value"}
    )
