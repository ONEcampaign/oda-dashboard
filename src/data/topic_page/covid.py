import pandas as pd
from oda_data import provider_groupings

from src.data.config import PATHS


def covid_bi_multi_dac() -> pd.DataFrame:
    df = pd.read_csv(
        PATHS.TOPIC_PAGE / "bi_plus_multi_health_spending_multiple_donors.csv"
    )

    codes = {v: k for k, v in provider_groupings()["dac_members"].items()}

    df["donor_code"] = df["donor_name"].map(codes)

    total = (
        df.groupby(["year"], as_index=False)["covid_oda"]
        .sum()
        .assign(donor_name="DAC countries", donor_code=20001)
    )

    df = pd.concat([df, total], ignore_index=True).rename(
        columns={"covid_oda": "value"}
    )

    return df
