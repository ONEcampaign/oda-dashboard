import {FileAttachment} from "observablehq:stdlib";
import {name2CodeMap} from "./utils.js";
import {createDuckDBClient} from "./duckdbFactory.js";

// Load only metadata required for recipient queries
const [donorOptions, recipientOptions, recipientsIndicators] = await Promise.all([
    FileAttachment("../data/analysis_tools/donors.json").json(),
    FileAttachment("../data/analysis_tools/recipients.json").json(),
    FileAttachment("../data/analysis_tools/recipients_indicators.json").json()
]);

// Lazy initialization: DuckDB instance is created on first query
let dbPromise = null;
function getDB() {
    if (!dbPromise) {
        const cacheBuster = navigator.userAgent.includes("Windows") ? `?t=${Date.now()}` : "";
        dbPromise = createDuckDBClient({
            recipients: FileAttachment("../data/scripts/recipients_view.parquet").href + cacheBuster
        }, 'recipients');
    }
    return dbPromise;
}

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
    timeRange,
    unit
) {

    const indicators = indicator.length > 0 ? indicator : [-1];

    const basePromise = fetchRecipientsSeries(
        donor,
        recipient,
        indicators,
        currency,
        prices,
        timeRange
    );

    const absolute = basePromise.then((rows) =>
        rows.map((row) => ({
            year: row.year,
            donor: row.donor,
            recipient: row.recipient,
            indicator: row.indicator,
            value: row.value,
            unit: `${currency} ${prices} million`,
            source: "OECD DAC2A"
        }))
    );

    const relative = basePromise.then((rows) =>
        rows.map((row) => ({
            year: row.year,
            donor: row.donor,
            recipient: row.recipient,
            indicator: row.indicator,
            value: row.pct_of_total_oda * 100,
            unit: "% of total ODA",
            source: "OECD DAC2A"
        }))
    );

    const table = basePromise.then((rows) =>
        rows.map((row) => ({
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
        }))
    );

    return {absolute, relative, table};

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

async function fetchRecipientsSeries(
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

async function executeRecipientsSeries(
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

    const indicatorSelection = indicators.join(", ");
    const valueColumn = `value_${currency}_${prices}`;

    const db = await getDB();
    const query = await db.query(
        `
            SELECT
                year,
                donor_name AS donor,
                recipient_name AS recipient,
                indicator_name AS indicator,
                ${valueColumn} AS value,
                pct_of_total_oda
            FROM recipients
            WHERE
                donor_code = ${donor}
                AND recipient_code = ${recipient}
                AND indicator IN (${indicatorSelection})
                AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
            ORDER BY year, indicator_name
        `
    );

    return query.toArray().map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        indicator: row.indicator,
        value: row.value ?? null,
        pct_of_total_oda: row.pct_of_total_oda ?? null
    }));
}
