import {FileAttachment} from "observablehq:stdlib";
import { convertUnitsToMillions } from "npm:@one-data/observable-themes/utils"
import {fillMissingYearIndicators} from "./utils.js";

/**
 * IMPORTANT: Value columns in the parquet file are stored as integers in UNITS (not millions).
 * All value_* columns must be divided by 1e6 to convert to millions for display.
 * Use the convertUnitsToMillions() helper function for this conversion.
 */

// Donors, recipients and marker scores are all identified by name; the loader publishes
// the option lists alongside the data.
const [viewOptions, genderTable] = await Promise.all([
    FileAttachment("../data/analysis_tools/gender_view_options.json").json(),
    FileAttachment("../data/scripts/gender_view.parquet").parquet()
]);

// Convert Arrow table to JavaScript array for fast in-memory filtering
const genderData = genderTable.toArray();

export const donorNames = viewOptions.donor_name;
export const recipientNames = viewOptions.recipient_name;
export const indicatorNames = viewOptions.indicator_name;
export const yearOptions = viewOptions.year;

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

    const indicators = indicator;

    const rows = fetchGenderSeries(
        donor,
        recipient,
        indicators,
        currency,
        prices,
        timeRange
    );

    const absolute = fillMissingYearIndicators(rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        indicator: row.indicator,
        value: row.value,
        unit: `${currency} ${prices} million`,
        source: "OECD CRS"
    })), timeRange);

    const relative = fillMissingYearIndicators(rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        indicator: row.indicator,
        value: row.pct_of_total * 100,
        unit: "% of all bilateral ODA",
        source: "OECD CRS"
    })), timeRange);

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
            : "% of all bilateral ODA",
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
    if (indicators.length === 0) {
        return [];
    }

    // In-memory filtering - much faster than DuckDB for simple queries on small dataset
    const valueColumn = `value_${currency}_${prices}`;

    return genderData
        .filter(row =>
            row.donor_name === donor &&
            row.recipient_name === recipient &&
            indicators.includes(row.indicator_name) &&
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
