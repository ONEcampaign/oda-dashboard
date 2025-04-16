from oda_data import OECDClient, set_data_path
from oda_data.tools.groupings import provider_groupings
from oda_data.indicators.research.eu import get_eui_plus_bilateral_providers_indicator

from src.data.config import PATHS

eu_ids = provider_groupings()["eu27_total"]

set_data_path(PATHS.DATA)

# client = OECDClient(
#     years=range(2000, 2024),
#     providers=list(eu_ids),
#     # measure=["net_disbursement", "grant_equivalent"],
#     use_bulk_download=True,
# )

df = get_eui_plus_bilateral_providers_indicator(
    OECDClient(use_bulk_download=True),
    indicator="DAC1.10.1010"
)
