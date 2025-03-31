import pandas as pd

from oda_data import Dac1Data, Indicators, set_data_path

from src.data.config import PATHS, time_range, logger

from src.data.analysis_tools.utils import get_dac_ids, add_index_column, convert_types, return_pa_table

set_data_path(PATHS.ODA_DATA)

donor_ids = get_dac_ids(PATHS.DONORS)

indicators_dac1 = {
    'ONE.10.1010_11010': 'Total ODA',
    # 'ONE.10.1010C', # Total Core ODA (ONE Definition)
    'DAC1.10.1015': 'Bilateral ODA',
    'DAC1.10.2000': 'Multilateral ODA',
    'DAC1.10.1600': 'Debt relief',
    'DAC1.10.1500': 'Scholarships and student costs in donor countries',
    'DAC1.10.1510': 'Scholarships/training in donor country',
    'DAC1.10.1520': 'Imputed student costs',
    'DAC1.10.1820': 'Refugees in donor countries',
    'DAC1.60.11030': 'Private sector instruments',
    'DAC1.60.11023': 'Private sector instruments - institutional approach',
    'DAC1.60.11024': 'Private sector instruments - instrument approach',
}


def get_dac1():

    dac1_raw = Indicators(
        years=range(time_range["start"], time_range["end"] + 1),
        providers= donor_ids,
        measure=["net_disbursement", "grant_equivalent"],
        use_bulk_download=True
    ).get_indicators(
        list(indicators_dac1.keys())
    )

    # Remove net disbursements after 2018
    dac1_raw = dac1_raw[~((dac1_raw["year"] >= 2018) & (dac1_raw["fund_flows"] == "Disbursements, net"))]


    dac1 = (
        dac1_raw.groupby(
            [
                'year',
                'donor_code',
                'one_indicator'
            ],
            dropna=False, observed=True
        )['value']
        .sum()
        .reset_index()
        .assign(indicator=lambda d: d["one_indicator"].map(indicators_dac1))
        .drop(columns=["one_indicator"])
    )

    return dac1

def get_grants():

    mapping = {
        "Disbursements, net": "Total ODA",
        "Grant equivalents": "Total ODA",
        "Disbursements, grants": "Grants"
    }

    grants_raw = Indicators(
        years=range(time_range["start"], time_range["end"] + 1),
        providers= donor_ids,
        measure=["net_disbursement_grant", "net_disbursement", "grant_equivalent"],
        use_bulk_download=True
    ).get_indicators(["DAC1.10.1010", "DAC1.10.11010"])

    # Remove net disbursements after 2018
    grants_raw = grants_raw[~((grants_raw["year"] >= 2018) & (grants_raw["fund_flows"] == "Disbursements, net"))]

    grants = (
        grants_raw
        .assign(indicator=lambda d: d["fund_flows"].map(mapping))
        .groupby(
            [
                'year',
                'donor_code',
                'indicator'
            ],
            dropna=False, observed=True
        )['value']
        .sum()
        .reset_index()
        .pivot(index=['year', 'donor_code'], columns='indicator', values="value")
        .reset_index()
        .assign(**{"Non-grants": lambda d: d['Total ODA'] - d['Grants']})
        .melt(id_vars=['year', 'donor_code'], value_vars=['Grants', 'Non-grants'])
    )

    return grants

def get_financing_data():

    dac1 = get_dac1()
    grants = get_grants()

    financing = pd.concat([dac1, grants])

    financing = add_index_column(
        df=financing,
        column='indicator',
        json_path=PATHS.TOOLS / 'financing_indicators.json'
    )

    return financing


def financing_to_parquet():

    df = get_financing_data()
    converted_df = convert_types(df)
    return_pa_table(converted_df)



if __name__ == "__main__":
    logger.info("Generating financing table...")
    financing_to_parquet()