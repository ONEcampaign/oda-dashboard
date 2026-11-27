export function plotHeight(width) {
    if (width < 480) return Math.round(width * 0.7)
    if (width < 768) return Math.round(width * 0.5)
    return Math.round(width * 0.45)
}

/**
 * For stacked area/bar charts, missing year-indicator rows cause visual distortion.
 * This fills any gap in (year × indicator) with `fillValue`, leaving all other fields
 * copied from the first row (donor, recipient, unit, source, etc.).
 * Only indicators that already appear in the data are considered — it never invents
 * a series that has no data at all.
 *
 * @param {Array} rows - Already-mapped plot rows with at least {year, indicator, value}
 * @param {[number, number]} timeRange - [startYear, endYear] inclusive
 * @param {number|null} [fillValue=0] - value for gaps; pass null for shares, where a gap is missing data, not 0%
 * @returns {Array} rows with gaps filled, sorted by year then indicator
 */
export function fillMissingYearIndicators(rows, timeRange, fillValue = 0) {
    if (rows.length === 0) return rows;

    const indicators = [...new Set(rows.map(r => r.indicator))];
    const existing = new Set(rows.map(r => `${r.year}|${r.indicator}`));
    const template = rows[0];
    const extras = [];

    for (let year = timeRange[0]; year <= timeRange[1]; year++) {
        for (const indicator of indicators) {
            if (!existing.has(`${year}|${indicator}`)) {
                extras.push({...template, year, indicator, value: fillValue});
            }
        }
    }

    if (extras.length === 0) return rows;

    return [...rows, ...extras].sort((a, b) =>
        a.year !== b.year ? a.year - b.year : a.indicator.localeCompare(b.indicator)
    );
}

/**
 * Describe a year-by-series Plot chart for screen readers.
 * @param {Array} rows - Plot rows with a `Year` Date and a series field
 * @param {string} seriesField - Field that names each series (the chart's fill)
 * @returns {string}
 */
export function plotAriaDescription(rows, seriesField) {
    if (rows.length === 0) return "No data.";
    const years = rows.map(row => row.Year.getFullYear());
    const series = [...new Set(rows.map(row => row[seriesField]))].filter(name => name != null);
    return `Years ${Math.min(...years)} to ${Math.max(...years)}. Series: ${series.join(", ")}.`;
}
