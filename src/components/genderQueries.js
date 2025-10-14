import {FileAttachment} from "observablehq:stdlib";
import {name2CodeMap, convertUnitsToMillions} from "./utils.js";

/**
 * IMPORTANT: Value columns in the parquet file are stored as integers in UNITS (not millions).
 * All value_* columns must be divided by 1e6 to convert to millions for display.
 * Use the convertUnitsToMillions() helper function for this conversion.
 */

// Load metadata and parquet data in parallel
const [donorOptions, recipientOptions, genderIndicators, genderTable] = await Promise.all([
    FileAttachment("../data/analysis_tools/donors.json").json(),
    FileAttachment("../data/analysis_tools/recipients.json").json(),
    FileAttachment("../data/analysis_tools/gender_indicators.json").json(),
    FileAttachment("../data/scripts/gender_view.parquet").parquet()
]);

// Convert Arrow table to JavaScript array for fast in-memory filtering
const genderData = genderTable.toArray();

// Export for use in gender.md to avoid duplicate loading
export {donorOptions, recipientOptions, genderIndicators};

const donorMapping = name2CodeMap(donorOptions, {});
const recipientMapping = name2CodeMap(recipientOptions);

const genderCache = new Map();

// GENDER VIEW
export function genderQueries(
    donor,
    recipient,
    indicator,
    currency,
    prices,
    timeRange
) {

    const indicators = indicator.length > 0 ? indicator : [-1];

    const rows = fetchGenderSeries(
        donor,
        recipient,
        indicators,
        currency,
        prices,
        timeRange
    );

    const absolute = rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        indicator: row.indicator,
        value: row.value,
        unit: `${currency} ${prices} million`,
        source: "OECD CRS"
    }));

    const relative = rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        indicator: row.indicator,
        value: row.pct_of_total * 100,
        unit: "% of total ODA",
        source: "OECD CRS"
    }));

    // Return raw rows for table transformation
    return {absolute, relative, rawData: rows};
}

// Separate table transformation so unit changes don't trigger re-query
export function transformTableData(rows, unit, currency, prices) {
    return rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        indicator: row.indicator,
        value: unit === "value"
            ? row.value
            : row.pct_of_total * 100,
        unit: unit === "value"
            ? `${currency} ${prices} million`
            : "% of total ODA",
        source: "OECD CRS"
    }));
}

function genderCacheKey({donor, recipient, indicator, currency, prices, timeRange}) {
    const donorKey = Array.isArray(donor) ? [...donor].sort().join(",") : String(donor);
    const recipientKey = Array.isArray(recipient) ? [...recipient].sort().join(",") : String(recipient);
    const indicatorKey = Array.isArray(indicator) ? [...indicator].sort().join(",") : String(indicator);
    const timeRangeKey = Array.isArray(timeRange) ? `${timeRange[0]}-${timeRange[1]}` : String(timeRange);

    return JSON.stringify({
        donor: donorKey,
        recipient: recipientKey,
        indicator: indicatorKey,
        currency,
        prices,
        timeRange: timeRangeKey
    });
}

function ratioAsPct(numerator, denominator) {
    if (numerator == null || denominator == null || denominator === 0) {
        return null;
    }

    return (numerator / denominator) * 100;
}

function fetchGenderSeries(
    donor,
    recipient,
    indicators,
    currency,
    prices,
    timeRange
) {
    const cacheKey = genderCacheKey({donor, recipient, indicator: indicators, currency, prices, timeRange});

    if (!genderCache.has(cacheKey)) {
        genderCache.set(cacheKey, executeGenderSeries(
            donor,
            recipient,
            indicators,
            currency,
            prices,
            timeRange
        ));
    }

    return genderCache.get(cacheKey);
}

function executeGenderSeries(
    donor,
    recipient,
    indicators,
    currency,
    prices,
    timeRange
) {
    if (indicators.length === 0 || (indicators.length === 1 && indicators[0] === -1)) {
        return [];
    }

    // In-memory filtering - much faster than DuckDB for simple queries on small dataset
    const valueColumn = `value_${currency}_${prices}`;

    return genderData
        .filter(row =>
            row.donor_code === donor &&
            row.recipient_code === recipient &&
            indicators.includes(row.indicator) &&
            row.year >= timeRange[0] &&
            row.year <= timeRange[1]
        )
        .map(row => ({
            year: row.year,
            donor: row.donor_name,
            recipient: row.recipient_name,
            indicator: row.indicator_name,
            value: convertUnitsToMillions(row[valueColumn]),
            pct_of_total: row.pct_of_total_oda ?? null
        }))
        .sort((a, b) => {
            if (a.year !== b.year) return a.year - b.year;
            return a.indicator.localeCompare(b.indicator);
        });
}
