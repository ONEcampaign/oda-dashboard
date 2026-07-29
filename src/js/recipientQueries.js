import {FileAttachment} from "observablehq:stdlib";
import { convertUnitsToMillions } from "npm:@one-data/observable-themes/utils"
import {fillMissingYearIndicators} from "./utils.js";

/**
 * IMPORTANT: Value columns in the parquet file are stored as integers in UNITS (not millions).
 * All value_* columns must be divided by 1e6 to convert to millions for display.
 * Use the convertUnitsToMillions() helper function for this conversion.
 */

const [viewOptions, recipientsTable] = await Promise.all([
    FileAttachment("../data/analysis_tools/recipients_view_options.json").json(),
    FileAttachment("../data/scripts/recipients_view.parquet").parquet()
]);

const recipientsData = recipientsTable.toArray();

export const donorNames = viewOptions.donor_name;
export const recipientNames = viewOptions.recipient_name;
export const indicatorNames = viewOptions.indicator_name;
export const yearOptions = viewOptions.year;

const recipientsCache = new Map();

export function recipientsQueries(donor, recipient, indicator, currency, prices, timeRange) {
    const rows = fetchRecipientsSeries(donor, recipient, indicator, currency, prices, timeRange);

    const absolute = fillMissingYearIndicators(rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        indicator: row.indicator,
        value: row.value,
        unit: `${currency} ${prices} million`,
        source: "OECD DAC2A"
    })), timeRange);

    const relative = fillMissingYearIndicators(rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        indicator: row.indicator,
        value: row.pct_total_recipient * 100,
        unit: "% of total ODA",
        source: "OECD DAC2A"
    })), timeRange);

    const relativeDonor = fillMissingYearIndicators(rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        indicator: row.indicator,
        value: row.pct_total_donor != null ? row.pct_total_donor * 100 : null,
        unit: "% of total ODA provided",
        source: "OECD DAC2A"
    })), timeRange);

    return {absolute, relative, relativeDonor, rawData: rows};
}

export function transformTableData(rows, unit, currency, prices) {
    return rows.map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        indicator: row.indicator,
        value: unit === "value"
            ? row.value
            : unit === "pct_total_recipient"
                ? (row.pct_total_recipient != null ? row.pct_total_recipient * 100 : null)
                : (row.pct_total_donor != null ? row.pct_total_donor * 100 : null),
        unit: unit === "value"
            ? `${currency} ${prices} million`
            : unit === "pct_total_recipient"
                ? "% of received aid"
                : "% of provided aid",
        source: "OECD DAC2A"
    }));
}

function recipientsCacheKey({donor, recipient, indicator, currency, prices, timeRange}) {
    const indicatorKey = Array.isArray(indicator) ? [...indicator].sort().join(",") : String(indicator);
    const timeRangeKey = Array.isArray(timeRange) ? `${timeRange[0]}-${timeRange[1]}` : String(timeRange);
    return JSON.stringify({donor, recipient, indicator: indicatorKey, currency, prices, timeRange: timeRangeKey});
}

function fetchRecipientsSeries(donor, recipient, indicators, currency, prices, timeRange) {
    const cacheKey = recipientsCacheKey({donor, recipient, indicator: indicators, currency, prices, timeRange});
    if (!recipientsCache.has(cacheKey)) {
        recipientsCache.set(cacheKey, executeRecipientsSeries(donor, recipient, indicators, currency, prices, timeRange));
    }
    return recipientsCache.get(cacheKey);
}

function executeRecipientsSeries(donor, recipient, indicators, currency, prices, timeRange) {
    if (indicators.length === 0) return [];

    const valueColumn = `value_${currency}_${prices}`;

    return recipientsData
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
            pct_total_recipient: row.pct_total_recipient ?? null,
            pct_total_donor: row.pct_total_donor ?? null
        }))
        .sort((a, b) => {
            if (a.year !== b.year) return a.year - b.year;
            return a.indicator.localeCompare(b.indicator);
        });
}
