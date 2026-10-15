"""Third-party compatibility patches, applied on import.

Importing this module has a side effect, which is the point: it repairs third-party behaviour
that would otherwise break the pipeline. One patch fixes a library incompatibility that would
raise the first time any code makes an HTTP request through ``requests-cache``, which is how
``oda_data`` and ``pydeflate`` fetch from the OECD. The other restores the donor code oda-reader
assigns to EU Institutions.

``config`` imports this module, so every module in the pipeline inherits the patches by virtue
of importing config. They have to be in place before the first request and the first OECD read,
which importing config comfortably guarantees. Nothing else needs to import it, and nothing
here should grow beyond patching third-party code.
"""

from collections.abc import Callable
from pathlib import Path

import requests.models as _rm
from oda_reader.schemas import (
    crs_translation as _crs_translation,
    dac1_translation as _dac1_translation,
    dac2_translation as _dac2_translation,
    multisystem_translation as _multisystem_translation,
)
from oda_reader.schemas.xml_tools import read_mapping as _read_mapping
from requests.adapters import HTTPAdapter as _HTTPAdapter
from requests.cookies import RequestsCookieJar as _RequestsCookieJar

# Fix for Python 3.13 + requests 2.32+ TYPE_CHECKING incompatibility.
# requests.models declares RequestsCookieJar and HTTPAdapter only under TYPE_CHECKING, so
# they're absent from runtime globals. Python 3.13's typing.get_type_hints() evaluates
# annotations strictly in the declaring module's globals, breaking attrs/cattrs when it
# processes CachedResponse (from requests-cache), which inherits from requests.models.Response.
_rm.RequestsCookieJar = _RequestsCookieJar
_rm.HTTPAdapter = _HTTPAdapter


# Fix for oda-reader >= 1.8 giving EU Institutions donor code 20918 instead of 918.
# Its area-code tables map both 918 and 20918 to "4EU001", and area_code_corrections.json says
# 918 should win. map_area_codes inverts the merged dict, so whichever code comes last wins, but
# the merge leaves the corrected 918 key in its original place, ahead of 20918. oda_data's
# provider groupings and pydeflate's EUR rate both expect 918. Moving corrected codes to the end
# restores the precedence the corrections file intends.
def _corrections_last(
    area_code_mapping: Callable[[], dict], corrections_path: Path
) -> Callable[[], dict]:
    """Wrap an oda-reader area_code_mapping so its corrected codes come last.

    Args:
        area_code_mapping: The module's original mapping function.
        corrections_path: oda-reader's area-code corrections file.

    Returns:
        A function returning the same mapping with corrected codes moved to the end.
    """
    corrected = set(_read_mapping(corrections_path, keys_as_int=True))

    def wrapped() -> dict:
        mapping = area_code_mapping()
        fixes = {k: v for k, v in mapping.items() if k in corrected}
        return {k: v for k, v in mapping.items() if k not in corrected} | fixes

    return wrapped


for _module in (_crs_translation, _dac1_translation, _dac2_translation):
    _module.area_code_mapping = _corrections_last(
        _module.area_code_mapping, _module.MAPPINGS["area_code_corrections"]
    )
# multisystem_translation binds dac2's function by name when it is imported.
_multisystem_translation.area_code_mapping = _dac2_translation.area_code_mapping
