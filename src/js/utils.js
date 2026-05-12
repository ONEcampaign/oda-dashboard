
export function plotHeight(width) {
    if (width < 480) return Math.round(width * 0.7)
    if (width < 768) return Math.round(width * 0.5)
    return Math.round(width * 0.45)
}

// Donor group synthetic codes (must match config.py DONOR_GROUPS)
const DONOR_GROUP_CODES = {
    "All bilateral donors": 20_000,
    "DAC countries": 20_001,
    "EU27 countries": 20_002,
    "EU27 + EU Institutions": 20_003,
    "G7 countries": 20_004,
    "non-DAC countries": 20_005,
};

// Recipient group synthetic codes (must match config.py RECIPIENT_GROUPS)
const RECIPIENT_GROUP_CODES = {
    "Developing countries": 100_000,
    "Africa": 100_001,
    "America": 100_002,
    "Asia": 100_003,
    "Caribbean": 100_004,
    "Central America": 100_006,
    "Central America and the Caribbean": 10_005,
    "Eastern Africa": 100_007,
    "Europe": 100_008,
    "Far East Asia": 100_009,
    "Fragile and conflict-affected countries": 100_010,
    "France priority countries": 100_011,
    "Least developed countries": 100_012,
    "Low income countries": 100_013,
    "Lower-middle income countries": 100_014,
    "Melanesia": 100_015,
    "Micronesia": 100_016,
    "Middle Africa": 100_017,
    "Middle East": 100_018,
    "North America": 100_019,
    "Northern Africa": 100_02,
    "Oceania": 100_021,
    "Polynesia": 100_022,
    "Sahel countries": 100_023,
    "South America": 100_024,
    "Southern Africa": 100_025,
    "Southern and Central Asia": 100_026,
    "Sub-Saharan Africa": 10_003,
    "Upper-middle income countries": 100_028,
    "Western Africa": 100_029,
    "Middle income countries": 100_030,
};

export function name2CodeMap(obj, { removeEUIBilateral = true, removeEU27EUI = false, useRecipientGroups = false } = {}) {
    const map = new Map();
    const groupCodes = useRecipientGroups ? RECIPIENT_GROUP_CODES : DONOR_GROUP_CODES;

    for (const [code, { name, groups }] of Object.entries(obj)) {
        // Add country/recipient name → code (single element)
        if (!map.has(name)) {
            map.set(name, Number(code));
        }

        // Add each group → collect member codes
        for (const group of groups) {
            if (!map.has(group)) map.set(group, []);
            map.get(group).push(Number(code));
        }
    }

    // Replace group arrays with synthetic codes
    for (const [groupName, syntheticCode] of Object.entries(groupCodes)) {
        if (map.has(groupName)) {
            map.set(groupName, syntheticCode);
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

/**
 * For stacked area/bar charts, missing year-indicator rows cause visual distortion.
 * This fills any gap in (year × indicator) with value: 0, leaving all other fields
 * copied from the first row (donor, recipient, unit, source, etc.).
 * Only indicators that already appear in the data are considered — it never invents
 * a series that has no data at all.
 *
 * @param {Array} rows - Already-mapped plot rows with at least {year, indicator, value}
 * @param {[number, number]} timeRange - [startYear, endYear] inclusive
 * @returns {Array} rows with zero-filled gaps, sorted by year then indicator
 */
export function fillMissingYearIndicators(rows, timeRange) {
    if (rows.length === 0) return rows;

    const indicators = [...new Set(rows.map(r => r.indicator))];
    const existing = new Set(rows.map(r => `${r.year}|${r.indicator}`));
    const template = rows[0];
    const extras = [];

    for (let year = timeRange[0]; year <= timeRange[1]; year++) {
        for (const indicator of indicators) {
            if (!existing.has(`${year}|${indicator}`)) {
                extras.push({...template, year, indicator, value: 0});
            }
        }
    }

    if (extras.length === 0) return rows;

    return [...rows, ...extras].sort((a, b) =>
        a.year !== b.year ? a.year - b.year : a.indicator.localeCompare(b.indicator)
    );
}

/**
 * Build a Map from indicator name → sequential index for the given page, sorted alphabetically.
 * @param {Record<string, { page: string, name: string }>} data
 * @param {string} page
 * @returns {Map<string, number>}
 */
export function generateIndicatorMap(data, page) {
    const names = new Set()

    for (const key in data) {
        const entry = data[key]
        if (entry.page === page && typeof entry.name === "string") {
            names.add(entry.name)
        }
    }

    const sortedNames = [...names].sort()
    const nameToId = new Map()
    sortedNames.forEach((name, index) => { nameToId.set(name, index) })

    return nameToId
}

/**
 * Generate an HTML `<ul>` string for a grouped list of sectors or countries.
 * Returns the raw HTML — insert via `innerHTML` or `dangerouslySetInnerHTML`.
 * @param {Object} data
 * @param {"sectors"|"countries"} mode
 * @returns {string}
 */
export function generateList(data, mode) {
    if (mode === "sectors") {
        const grouped = Object.entries(data).reduce((acc, [subsector, sector]) => {
            (acc[sector] ??= []).push(subsector)
            return acc
        }, {})

        const items = Object.entries(grouped)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([sector, subsectors]) =>
                subsectors.length === 1
                    ? `<li><strong>${sector}</strong></li>`
                    : `<li><strong>${sector}</strong>: ${subsectors.join("; ")}</li>`
            )
            .join("")

        return `<ul class="group-list">${items}</ul>`
    }

    if (mode === "countries") {
        const groupToCountries = {}

        for (const donor of Object.values(data)) {
            for (const group of donor.groups) {
                (groupToCountries[group] ??= []).push(donor.name)
            }
        }

        const items = Object.entries(groupToCountries)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([group, countries]) => {
                let content
                if (group === "All bilateral donors") {
                    content = "DAC and Non-DAC countries"
                } else if (group === "Developing countries") {
                    content = "All recipient countries and regions"
                } else {
                    content = countries.join("; ")
                }
                return `<li><strong>${group}</strong>: ${content}</li>`
            })
            .join("")

        return `<ul class="group-list">${items}</ul>`
    }

    return `<p>Unsupported mode: ${mode}</p>`
}

