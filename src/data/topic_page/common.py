import json
import os

import pandas as pd
from bblocks import format_number

LONG_START_YEAR: int = 2000
START_YEAR: int = 2010
LATEST_YEAR_AGG: int = 2023
LATEST_YEAR_DETAIL: int = 2023
CONSTANT_YEAR: int = 2023


def add_change(
    df: pd.DataFrame, grouper: list = None, as_formatted_str: bool = False
) -> pd.DataFrame:
    if grouper is None:
        grouper = ["donor_code", "indicator"]

    df["pct_change"] = df.groupby(grouper)["value"].pct_change()

    if not as_formatted_str:
        return df

    df["pct_change"] = format_number(
        df["pct_change"],
        as_percentage=True,
        decimals=1,
    ).replace("nan%", "")

    return df


def update_key_number(path: str, new_dict: dict) -> None:
    """Update a key number json by updating it with a new dictionary"""

    # Check if the file exists, if not create
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump({}, f)

    with open(path, "r") as f:
        data = json.load(f)

    for k in new_dict.keys():
        data[k] = new_dict[k]

    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def df_to_key_number(
    df: pd.DataFrame,
    indicator_name: str,
    id_column: str,
    value_columns: str | list[str],
) -> dict:
    if isinstance(value_columns, str):
        value_columns = [value_columns]

    return (
        df.assign(indicator=indicator_name)
        .filter(["indicator", id_column] + value_columns, axis=1)
        .groupby(["indicator"])
        .apply(
            lambda x: x.set_index(id_column)[value_columns]
            .astype(str)
            .to_dict(orient="index")
        )
        .to_dict()
    )


def sort_dac_first(df: pd.DataFrame, keep_current_sorting=True):
    if not keep_current_sorting:
        df = df.sort_values(["year", "name"], ascending=[True, False])

    dac = df.query("name == 'DAC Countries, Total'").reset_index(drop=True)
    other = df.query("name != 'DAC Countries, Total'").reset_index(drop=True)

    return pd.concat([dac, other], ignore_index=True)
