import json
import os

import pandas as pd

LONG_START_YEAR: int = 2000
START_YEAR: int = 2010
SHORT_START_YEAR: int = 2015
LATEST_YEAR_AGG: int = 2025
LATEST_YEAR_DETAIL: int = 2024
CONSTANT_YEAR: int = 2025

BILLION: float = 1e9


def _format(series: pd.Series, template: str) -> pd.Series:
    """Format a numeric series as strings with a str.format template.

    Raises:
        ValueError: If the series is not numeric.
    """
    if not pd.api.types.is_numeric_dtype(series):
        raise ValueError(f"Expected a numeric series, got {series.dtype}")
    return series.map(template.format)


def format_percentage(series: pd.Series, decimals: int = 1) -> pd.Series:
    """Format shares where 1 means 100%, e.g. 0.1234 -> "12.3%"."""
    return _format(series, f"{{:,.{decimals}%}}")


def format_billions(series: pd.Series, decimals: int = 1) -> pd.Series:
    """Format absolute values in billions with thousands separators, e.g. 1.5e9 -> "1.5"."""
    return _format(series / BILLION, f"{{:,.{decimals}f}}")


def add_change(
    df: pd.DataFrame, grouper: list = None, as_formatted_str: bool = False
) -> pd.DataFrame:
    if grouper is None:
        grouper = ["donor_code", "indicator"]

    df["pct_change"] = df.groupby(grouper)["value"].pct_change()

    if not as_formatted_str:
        return df

    df["pct_change"] = format_percentage(df["pct_change"], decimals=1).replace("nan%", "")

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

    dac = df.query("name == 'DAC countries'").reset_index(drop=True)
    other = df.query("name != 'DAC countries'").reset_index(drop=True)

    return pd.concat([dac, other], ignore_index=True)
