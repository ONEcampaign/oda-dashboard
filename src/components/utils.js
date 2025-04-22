import { html } from "htl";

export function formatString(str, options = {fileMode: false}) {
    let result = str.replace(/, Total/g, '');

    if (options.fileMode) {
        result = result.toLowerCase().replace(/\s+/g, "_");
    }

    return result;
}

export function formatValue(value) {
    // Handle null values
    if (value == null) {
        return {value: 0, label: "0"};
    }

    // Round to two decimal places for the value
    const roundedValue = parseFloat(value.toFixed(2));

    // Determine the label
    let label;
    if (value === 0) {
        label = "< 0.01";
    } else {
        label = roundedValue.toLocaleString("en-US", {
            minimumFractionDigits: 1,
            maximumFractionDigits: 2
        });
    }

    // Return both rounded value and label
    return {value: roundedValue, label};
}


export function getCurrencyLabel(tag, {
    currencyOnly = false,
    currencyLong = false,
    unitsOnly = false,
    unitsLong = true,
    inSentence = false,
    value = "",
} = {}) {

    const currencyMap = {
        "usd": currencyLong ? "US Dollars" : "US$",
        "eur": currencyLong ? "Euros" : "€",
        "cad": currencyLong ? "Canada Dollars" : "CA$",
        "gbp": currencyLong ? "British Pounds" : "£",
    };

    const currency = currencyMap[tag] ?? tag;
    const units = unitsLong ? "Million" : "M";

    if (inSentence) {
        return `${currency} (millions)`;
    }

    if (currencyOnly) return currency;
    if (unitsOnly) return units;

    return value === "" ? `${currency} ${units}` : `${currency}${value} ${units}`;
}


export function name2CodeMap(obj, { removeEUIBilateral = true, removeEU27EUI = false } = {}) {
    const map = new Map();

    for (const [code, { name, groups }] of Object.entries(obj)) {
        // Add country name → code
        if (!map.has(name)) map.set(name, []);
        map.get(name).push(Number(code));

        // Add each group → code
        for (const group of groups) {
            if (!map.has(group)) map.set(group, []);
            map.get(group).push(Number(code));
        }
    }

    if (removeEUIBilateral) {
        map.delete("EU Institutions, bilateral");
    }

    if (removeEU27EUI) {
        map.delete("EU27 + EU Institutions");
    }

    return map;
}


export function getNameByCode(map, codes) {
    const codeArray = Array.isArray(codes) ? codes : [codes];
    const target = codeArray.map(String).sort().join(",");

    for (const [name, codeListRaw] of map.entries()) {
        const codeList = Array.isArray(codeListRaw) ? codeListRaw : [codeListRaw];
        const listKey = codeList.map(String).sort().join(",");

        if (listKey === target) {
            return name;
        }
    }

    return undefined;
}


export function generateIndicatorMap(data, page) {
    // Step 1: Filter entries by page and collect unique names
    const names = new Set();

    for (const key in data) {
        const entry = data[key];
        if (entry.page === page && typeof entry.name === "string") {
            names.add(entry.name);
        }
    }

    // Step 2: Sort names alphabetically and assign incremental IDs
    const sortedNames = [...names].sort();
    const nameToId = new Map();

    sortedNames.forEach((name, index) => {
        nameToId.set(name, index);
    });

    return nameToId;
}

export function escapeSQL(str) {
    return str.replace(/'/g, "''");
}

export function decodeHTML(html) {
    const txt = document.createElement("textarea");
    txt.innerHTML = html;
    return txt.value;
}

export function generateList(data, mode) {
    if (mode === "sectors") {
        const grouped = Object.entries(data).reduce((acc, [subsector, sector]) => {
            (acc[sector] ??= []).push(subsector);
            return acc;
        }, {});

        return html`
      <ul class="group-list">
        ${
            Object.entries(grouped)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([sector, subsectors]) =>
                    subsectors.length === 1
                        ? html`<li><strong>${sector}</strong></li>`
                        : html`<li><strong>${sector}</strong>: ${subsectors.join("; ")}</li>`
                )
        }
      </ul>
    `;
    }

    if (mode === "countries") {
        const groupToCountries = {};

        for (const donor of Object.values(data)) {
            for (const group of donor.groups) {
                (groupToCountries[group] ??= []).push(donor.name);
            }
        }

        return html`
      <ul class="group-list">
        ${
            Object.entries(groupToCountries)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([group, countries]) => {
                    let content;
                    if (group === "All bilateral donors") {
                        content = "DAC and Non-DAC countries";
                    } else if (group === "Developing countries") {
                        content = "All recipient countries and regions";
                    } else {
                        content = countries.join("; ");
                    }

                    return html`<li><strong>${group}</strong>: ${content}</li>`;
                })
        }
      </ul>
    `;
    }

    return html`<p>Unsupported mode: ${mode}</p>`;
}



