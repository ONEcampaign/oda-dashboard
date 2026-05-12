export const APP_TITLE = "ODA Dashboard"

export const APP_DESCRIPTION = "Explore how official development assistance (ODA) is financed, where it goes, and what it targets — broken down by sector and gender."

export const NAV_ITEMS = [
    { id: "financing",  label: "FINANCING",  href: "./" },
    { id: "recipients", label: "RECIPIENTS", href: "./recipients.html" },
    { id: "sectors",    label: "SECTORS",    href: "./sectors.html" },
    { id: "gender",     label: "GENDER",     href: "./gender.html" },
    { id: "faqs",       label: "FAQs",       href: "./faqs.html" }
]

export const CURRENCY_OPTIONS = [
    {label: "US Dollars", value: "usd"},
    {label: "Euros", value: "eur"},
    {label: "Canada Dollars", value: "cad"},
    {label: "British Pounds", value: "gbp"}
]

export const PRICES_OPTIONS = [
    {label: "Constant", value: "constant"},
    {label: "Current", value: "current"}
]

export const SCALE = 6 // Raw data is in million units