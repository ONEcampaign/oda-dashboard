export function getCurrencyLabel(currency, {
                                    long = true,
                                    value = ""
                                })
{
    let unit;
    if (long) {
        unit = "million"
    } else (
        unit = "M"
    )
    let symbol;
    if (currency === "US Dollars") {
        symbol = "US$"
    } else if (currency === "Euros") {
        symbol = "€"
    } else if (currency === "Canadian Dollars") {
        symbol =  "CA$"
    } else if (currency === "British Pounds") {
        symbol = "£"
    }
    if (value === "") {
        return `${symbol} ${unit}`
    } else {
        return `${symbol} ${value} ${unit}`
    }

}