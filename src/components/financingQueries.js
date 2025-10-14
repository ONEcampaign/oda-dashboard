import {FileAttachment} from "observablehq:stdlib";
import {name2CodeMap, convertUnitsToMillions} from "./utils.js";

/**
 * IMPORTANT: Value columns in the parquet file are stored as integers in UNITS (not millions).
 * All value_* columns must be divided by 1e6 to convert to millions for display.
 * Use the convertUnitsToMillions() helper function for this conversion.
 */

// Load metadata and parquet data in parallel
const [donorOptions, financingIndicators, financingTable] = await Promise.all([
    FileAttachment("../data/analysis_tools/donors.json").json(),
    FileAttachment("../data/analysis_tools/financing_indicators.json").json(),
    FileAttachment("../data/scripts/financing_view.parquet").parquet()
]);

// Convert Arrow table to JavaScript array for fast in-memory filtering
const financingData = financingTable.toArray();

// Export for use in index.md to avoid duplicate loading
export {donorOptions, financingIndicators};

const donorMapping = name2CodeMap(donorOptions, {})

const indicatorMapping = new Map(
    Object.entries(financingIndicators).map(([k, v]) => [v, Number(k)])
);

const financingCache = new Map();

// FINANCING VIEW
export function financingQueries(
    donor,
    indicator,
    currency,
    prices,
    timeRange
) {

    const rows = fetchFinancingSeries(
        donor,
        indicator,
        currency,
        prices,
        timeRange
    );

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
        value: indicator === indicatorMapping.get("Total ODA")
            ? row.pct_of_gni * 100
            : row.pct_of_total_oda * 100,
        unit: indicator === indicatorMapping.get("Total ODA")
            ? "% of GNI"
            : "% of total ODA",
        source: "OECD DAC1"
    }));

    // Return raw rows for table transformation
    return {absolute, relative, rawData: rows};
}

// Separate table transformation so unit changes don't trigger base query
export function transformTableData(rows, unit, indicator, currency, prices) {
    return rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        indicator: row.indicator,
        type: row.type,
        value: deriveTableValue(row, unit, indicator),
        unit: deriveTableUnit(unit, currency, prices, indicator),
        source: "OECD DAC1"
    }));
}

function financingCacheKey({donor, indicator, currency, prices, timeRange}) {
    const donorKey = Array.isArray(donor) ? [...donor].sort().join(",") : String(donor);
    const timeRangeKey = Array.isArray(timeRange) ? `${timeRange[0]}-${timeRange[1]}` : String(timeRange);
    return JSON.stringify({
        donor: donorKey,
        indicator,
        currency,
        prices,
        timeRange: timeRangeKey
    });
}

function deriveTableValue(row, unit, indicator) {
    switch (unit) {
        case "value":
            return row.value;
        case "gni_pct":
            return row.pct_of_gni * 100;
        case "total_pct":
            return row.pct_of_total_oda * 100;
        default:
            return row.value;
    }
}

function deriveTableUnit(unit, currency, prices, indicator) {
    if (unit === "value") {
        return `${currency} ${prices} million`;
    }

    if (unit === "gni_pct") {
        return "% of GNI";
    }

    if (unit === "total_pct") {
        return "% of total ODA";
    }

    return `${currency} ${prices} million`;
}

function fetchFinancingSeries(
    donor,
    indicator,
    currency,
    prices,
    timeRange
) {
    const cacheKey = financingCacheKey({donor, indicator, currency, prices, timeRange});

    if (!financingCache.has(cacheKey)) {
        financingCache.set(cacheKey, executeFinancingSeries(
            donor,
            indicator,
            currency,
            prices,
            timeRange
        ));
    }

    return financingCache.get(cacheKey);
}

function executeFinancingSeries(
    donor,
    indicator,
    currency,
    prices,
    timeRange
) {
    // In-memory filtering - much faster than DuckDB for small datasets
    const valueColumn = `value_${currency}_${prices}`;

    return financingData
        .filter(row =>
            row.donor_code === donor &&
            row.indicator === indicator &&
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
