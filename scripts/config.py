from pathlib import Path


class PATHS:
    """Class to store the paths to the data and output folders."""

    project = Path(__file__).resolve().parent.parent
    scripts = project / "scripts"
    raw_data = scripts / 'raw_data'
    output = scripts / 'output'
    components = project / "src" / "components"


ANALYSIS_YEARS: dict = {"start": 2000, "end": 2023}
SECTORS_YEARS: dict = {"start": 2010, "end": 2022}
CURRENCIES: list = ["USD", "GBP", "EUR", "CAD"]
PRICES: list = ["current", "constant"]
BASE_YEAR: int = 2022

FINANCING_INDICATORS_FLOW = {
    "total_oda_flow_net": "Total ODA",
    "total_oda_bilateral_flow_net": "Bilateral",
    "total_oda_multilateral_flow_net": "Multilateral",
    "total_oda_grants_flow": "Grants",
    "total_oda_non_grants_flow": "Non-grants",
    "total_in_donor_students_flow": "In-donor student costs, total",
    "scholarships_flow": "In-donor scholarships",
    "imputed_students_flow": "In-donor imputed student costs",
    "idrc_flow": "In-donor refugee costs",
    "one_core_oda_flow": "Core ODA",
    "debt_relief_flow": "Debt relief",
    "total_psi_flow_linked": "Private sector instruments, total",
    "instrument_psi_flow_linked": "PSI, instrument",
    "institutional_psi_flow_linked": "PSI, institutional",


    "total_covid_oda_flow": "COVID-19 ODA, total",
    # "total_covid_vaccine_donations_oda_flow": "COVID-19 vaccine donations, total",
    #  (
    #      "total_covid_vaccine_donations_domestic_supply_oda_flow"
    #  ): "COVID-19 vaccine donations, domestic supply",
    #  (
    #      "total_covid_vaccine_donations_dev_purchase_oda_flow"
    #  ): "COVID-19 vaccine donations, purchased",
}

FINANCING_INDICATORS_GE = {
    "total_oda_ge": "Total ODA",
    "total_oda_bilateral_ge": "Bilateral",
    "total_oda_multilateral_ge": "Multilateral",
    "total_oda_grants_ge": "Grants",
    "total_oda_non_grants_ge": "Non-grants",
    "total_in_donor_students_ge_linked": "In-donor student costs, total",
    "scholarships_ge_linked": "In-donor scholarships",
    "imputed_students_ge": "In-donor imputed student costs",
    "idrc_ge_linked": "In-donor refugee costs",
    "debt_relief_ge": "Debt relief",
    "total_psi_ge": "Private sector instruments, total",
    "instrument_psi_ge": "PSI, Instrument",
    "one_core_oda_ge": "Core ODA",
    "institutional_psi_ge": "PSI, institutional",


    "total_covid_oda_ge": "COVID-19 ODA, total",
    # "total_covid_vaccine_donations_oda_ge_linked": "COVID-19 vaccine donations, total",
    # (
    #     "total_covid_vaccine_donations_domestic_supply_oda_ge_linked"
    # ): "COVID-19 vaccine donations, domestic supply",
    # (
    #     "total_covid_vaccine_donations_dev_purchase_oda_ge_linked"
    # ): "COVID-19 vaccine donations, purchased",
}

RECIPIENTS_INDICATORS: dict = {
    "recipient_imputed_multi_flow_net": "Imputed multilateral",
    "recipient_bilateral_flow_net": "Bilateral",
    "recipient_total_flow_net": "Total",
}

SECTORS_INDICATORS: dict = {
    "crs_bilateral_total_flow_gross_by_purpose": "Bilateral",
    "imputed_multi_flow_disbursement_gross": "Imputed multilateral",
    "gni": "GNI",
}

GENDER_INDICATORS: dict = {
    "crs_gender_significant_flow_disbursement_gross": "Significant",
    "crs_gender_principal_flow_disbursement_gross": "Principal",
    "crs_gender_not_targeted_flow_disbursement_gross": "Not targeted",
    "crs_gender_not_screened_flow_disbursement_gross": "Not screened",
    "crs_gender_allocable_flow_disbursement_gross": "Gender allocable",
    "crs_gender_total_flow_gross": "Gender, total",
}


COLUMNS: dict = {
    "donor_code": "Donor code",
    "donor_name": "Donor",
    "recipient_code": "Recipient code",
    "recipient_name": "Recipient",
    "indicator": "Indicator",
    "indicator_type": "Indicator type",
    "year": "Year",
    "gni_share": "GNI share",
    "share_of": "Share of",
    "share": "Share",
    "currency": "Currency",
    "prices": "Prices",
}

VALUES: dict = {
    "CAD": "Canadian Dollars",
    "EUR": "Euros",
    "GBP": "British Pounds",
    "USD": "US Dollars",
    "constant": "Constant",
    "current": "Current",
    "flow": "Flow",
    "grant equivalent": "Grant equivalent",
    "official": "Official definition",
}