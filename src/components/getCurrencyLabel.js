export function getCurrencyLabel(unit, {
    long = true,
    value = "",
    preffixOnly = false,
    suffixOnly = false,
})
{

    let prefix, suffix;

    if (long) {
        suffix = "Million"
    }
    else (
        suffix = "M"
    )

    if (unit === "US Dollars") {
        prefix = "US$"
    }
    else if (unit === "Euros") {
        prefix = "€"
    }
    else if (unit === "Canadian Dollars") {
        prefix =  "CA$"
    }
    else if (unit === "British Pounds") {
        prefix = "£"
    }

    if (preffixOnly) {
        return `${prefix}`
    }
    if (value === "") {
        return `${prefix} ${suffix}`
    }
    else {
        return `${prefix}${value} ${suffix}`
    }

}