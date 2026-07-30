
export function plotHeight(width) {
    if (width < 480) return Math.round(width * 0.7)
    if (width < 768) return Math.round(width * 0.5)
    return Math.round(width * 0.45)
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

