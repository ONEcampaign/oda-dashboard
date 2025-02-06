from scripts import config


def versions_dictionary() -> dict:
    versions = {}

    for price in config.PRICES:
        for currency in config.CURRENCIES:
            if price == "current":
                versions[f"{price}_{currency}"] = {
                    "prices": price,
                    "currency": currency,
                    "base_year": None,
                }
            else:
                versions[f"{price}_{currency}"] = {
                    "prices": price,
                    "currency": currency,
                    "base_year": config.BASE_YEAR,
                }

    return versions