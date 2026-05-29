import {FileAttachment} from "observablehq:stdlib";
import { convertUnitsToMillions } from "npm:@one-data/observable-themes/utils"

/**
 * IMPORTANT: Value columns in the parquet file are stored as integers in UNITS (not millions).
 * All value_* columns must be divided by 1e6 to convert to millions for display.
 * Use the convertUnitsToMillions() helper function for this conversion.
 */

const [viewOptions, financingTable] = await Promise.all([
    FileAttachment("../data/analysis_tools/financing_view_options.json").json(),
    FileAttachment("../data/scripts/financing_view.parquet").parquet()
]);

const financingData = financingTable.toArray();

export const donorNames = viewOptions.donor_name;
export const indicatorNames = viewOptions.indicator_name;
export const yearOptions = viewOptions.year;

const financingCache = new Map();

// FINANCING VIEW
export function financingQueries(
    donor,
    indicator,
    currency,
    prices,
    timeRange
) {
    const rows = fetchFinancingSeries(donor, indicator, currency, prices, timeRange);

    const absolute = rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        indicator: row.indicator,
        type: row.type,
        value: row.value,
        unit: `${currency} ${prices} million`,
        source: "OECD DAC1"
    }));

    const relative = rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        indicator: row.indicator,
        type: row.type,
        value: indicator === "Total ODA"
            ? row.pct_of_gni * 100
            : row.pct_of_total_oda * 100,
        unit: indicator === "Total ODA"
            ? "% of GNI"
            : "% of total ODA",
        source: "OECD DAC1"
    }));

    return {absolute, relative, rawData: rows};
}

// Separate table transformation so unit changes don't trigger base query
export function transformTableData(rows, unit, currency, prices) {
    return rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        indicator: row.indicator,
        type: row.type,
        value: deriveTableValue(row, unit),
        unit: deriveTableUnit(unit, currency, prices),
        source: "OECD DAC1"
    }));
}

function financingCacheKey({donor, indicator, currency, prices, timeRange}) {
    const timeRangeKey = Array.isArray(timeRange) ? `${timeRange[0]}-${timeRange[1]}` : String(timeRange);
    return JSON.stringify({donor, indicator, currency, prices, timeRange: timeRangeKey});
}

function deriveTableValue(row, unit) {
    switch (unit) {
        case "gni_pct":
            return row.pct_of_gni * 100;
        case "total_pct":
            return row.pct_of_total_oda * 100;
        default:
            return row.value;
    }
}

function deriveTableUnit(unit, currency, prices) {
    if (unit === "gni_pct") return "% of GNI";
    if (unit === "total_pct") return "% of total ODA";
    return `${currency} ${prices} million`;
}

function fetchFinancingSeries(donor, indicator, currency, prices, timeRange) {
    const cacheKey = financingCacheKey({donor, indicator, currency, prices, timeRange});

    if (!financingCache.has(cacheKey)) {
        financingCache.set(cacheKey, executeFinancingSeries(donor, indicator, currency, prices, timeRange));
    }

    return financingCache.get(cacheKey);
}

function executeFinancingSeries(donor, indicator, currency, prices, timeRange) {
    const valueColumn = `value_${currency}_${prices}`;

    return financingData
        .filter(row =>
            row.donor_name === donor &&
            row.indicator_name === indicator &&
            row.year >= timeRange[0] &&
            row.year <= timeRange[1]
        )
        .map(row => ({
            year: row.year,
            donor: row.donor_name,
            indicator: row.indicator_name,
            type: row.type,
            value: convertUnitsToMillions(row[valueColumn]),
            pct_of_gni: row.pct_of_gni ?? null,
            pct_of_total_oda: row.pct_of_total_oda ?? null
        }))
        .sort((a, b) => a.year - b.year);
}
