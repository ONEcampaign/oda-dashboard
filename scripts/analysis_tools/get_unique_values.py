import json
from scripts import config

def get_unique_values(df, view_name):
    """
    Extracts unique values for specified columns from a pandas DataFrame
    and saves them to a single JavaScript object in a JS file.

    Parameters:
        df (pd.DataFrame): The input DataFrame.
        view_name (str): The name of the view to extract unique values from.

    Returns:
        None
    """
    js_data = {}

    if view_name == "Financing":
        column_variable_map = {
            "Year": "timeRange",
            "Indicator": "indicators",
            "Donor name": "donors",
            "Currency": "currencies",
            "Prices": "prices",
            "Indicator type": "indicatorTypes",
        }
    elif view_name == "Recipients":
        column_variable_map = {
            "Year": "timeRange",
            "Indicator": "indicators",
            "Donor name": "donors",
            "Recipient name": "recipients",
            "Currency": "currencies",
            "Prices": "prices"
        }
    elif view_name == "Sectors":
        column_variable_map = {
            "Year": "timeRange",
            "Indicator": "indicators",
            "Donor name": "donors",
            "Recipient name": "recipients",
            "Currency": "currencies",
            "Prices": "prices",
            "Sector": "sectors",
            "Sub-sector": "subsectors"
        }

    columns = list(column_variable_map.keys())

    for column in columns:
        variable_name = column_variable_map.get(column, column)  # Use mapped variable name if provided
        if column == "Year":
            # Special case: min and max year
            min_year = int(df[column].min())
            max_year = int(df[column].max())
            js_data[variable_name] = [min_year, max_year]
        else:
            # Extract unique values, sort, and store them
            unique_values = df[column].dropna().unique()
            unique_values = sorted(unique_values)
            js_data[variable_name] = unique_values

    # Write all unique values as a single object to the JavaScript file
    with open(config.PATHS.components / f"uniqueValues{view_name}.js", 'w', encoding="utf-8") as json_file:
        json_file.write("// Generated by get_unique_values\n")
        json_file.write(f"export const uniqueValues{view_name} = ")
        json.dump(js_data, json_file, indent=2, ensure_ascii=False)
        json_file.write(";\n")
