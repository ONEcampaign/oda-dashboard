import {FileAttachment} from "observablehq:stdlib";
import {name2CodeMap, convertUnitsToMillions} from "./utils.js";

/**
 * IMPORTANT: Value columns in the parquet file are stored as integers in UNITS (not millions).
 * All value_* columns must be divided by 1e6 to convert to millions for display.
 * Use the convertUnitsToMillions() helper function for this conversion.
 */

// Load metadata and parquet data in parallel
const [donorOptions, recipientOptions, recipientsIndicators, recipientsTable] = await Promise.all([
    FileAttachment("../data/analysis_tools/donors.json").json(),
    FileAttachment("../data/analysis_tools/recipients.json").json(),
    FileAttachment("../data/analysis_tools/recipients_indicators.json").json(),
    FileAttachment("../data/scripts/recipients_view.parquet").parquet()
]);

// Convert Arrow table to JavaScript array for fast in-memory filtering
const recipientsData = recipientsTable.toArray();

// Export for use in recipients.md to avoid duplicate loading
export {donorOptions, recipientOptions, recipientsIndicators};

const donorMapping = name2CodeMap(donorOptions, {})

const recipientMapping = name2CodeMap(recipientOptions, { useRecipientGroups: true })


const recipientsCache = new Map();

// RECIPIENTS VIEW
export function recipientsQueries(
    donor,
    recipient,
    indicator,
    currency,
    prices,
    timeRange
) {

    const indicators = indicator.length > 0 ? indicator : [-1];

    const rows = fetchRecipientsSeries(
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
        source: "OECD DAC2A"
    }));

    const relative = rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        indicator: row.indicator,
        value: row.pct_of_total_oda * 100,
        unit: "% of total ODA",
        source: "OECD DAC2A"
    }));

    // Return raw rows for table transformation
    return {absolute, relative, rawData: rows};
}

// Separate table transformation so unit changes don't trigger base query
export function transformTableData(rows, unit, currency, prices) {
    return rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        indicator: row.indicator,
        value: unit === "value"
            ? row.value
            : row.pct_of_total_oda * 100,
        unit: unit === "value"
            ? `${currency} ${prices} million`
            : "% of bilateral + imputed multilateral ODA",
        source: "OECD DAC2A"
    }));
}

function recipientsCacheKey({donor, recipient, indicator, currency, prices, timeRange}) {
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

function fetchRecipientsSeries(
    donor,
    recipient,
    indicators,
    currency,
    prices,
    timeRange
) {
    const cacheKey = recipientsCacheKey({donor, recipient, indicator: indicators, currency, prices, timeRange});

    if (!recipientsCache.has(cacheKey)) {
        recipientsCache.set(cacheKey, executeRecipientsSeries(
            donor,
            recipient,
            indicators,
            currency,
            prices,
            timeRange
        ));
    }

    return recipientsCache.get(cacheKey);
}

function executeRecipientsSeries(
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

    // In-memory filtering - much faster than DuckDB for simple queries on 11MB dataset
    const valueColumn = `value_${currency}_${prices}`;

    return recipientsData
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
            pct_of_total_oda: row.pct_of_total_oda ?? null
        }))
        .sort((a, b) => {
            if (a.year !== b.year) return a.year - b.year;
            return a.indicator.localeCompare(b.indicator);
        });
}
