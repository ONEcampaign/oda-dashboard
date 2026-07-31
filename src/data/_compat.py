"""Third-party compatibility patches, applied on import.

Importing this module has a side effect, which is the point: it repairs a library
incompatibility that would otherwise raise the first time any code makes an HTTP request
through ``requests-cache`` — which is how ``oda_data`` and ``pydeflate`` fetch from the OECD.

``config`` imports this module, so every module in the pipeline inherits the patch by virtue of
importing config. The patch has to be in place before the first cached request, which importing
config comfortably guarantees. Nothing else needs to import it, and nothing here should grow
beyond patching third-party code.
"""

# Fix for Python 3.13 + requests 2.32+ TYPE_CHECKING incompatibility.
# requests.models declares RequestsCookieJar and HTTPAdapter only under TYPE_CHECKING, so
# they're absent from runtime globals. Python 3.13's typing.get_type_hints() evaluates
# annotations strictly in the declaring module's globals, breaking attrs/cattrs when it
# processes CachedResponse (from requests-cache), which inherits from requests.models.Response.
import requests.models as _rm
from requests.adapters import HTTPAdapter as _HTTPAdapter
from requests.cookies import RequestsCookieJar as _RequestsCookieJar

_rm.RequestsCookieJar = _RequestsCookieJar
_rm.HTTPAdapter = _HTTPAdapter
