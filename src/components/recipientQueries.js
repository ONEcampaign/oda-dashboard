import {FileAttachment} from "observablehq:stdlib";
import {name2CodeMap, getNameByCode, escapeSQL} from "./utils.js";
import {
    donorOptions,
    recipientOptions,
    recipientsIndicators
} from "./sharedMetadata.js";
import {createDuckDBClient} from "./duckdbFactory.js";

// Lazy initialization: DuckDB instance is created on first query
let dbPromise = null;
function getDB() {
    if (!dbPromise) {
        const cacheBuster = navigator.userAgent.includes("Windows") ? `?t=${Date.now()}` : "";
        dbPromise = createDuckDBClient({
            recipients: FileAttachment("../data/scripts/recipients.parquet").href + cacheBuster,
            current_conversion_table: FileAttachment("../data/scripts/current_conversion_table.csv").csv({typed: true}),
            constant_conversion_table: FileAttachment("../data/scripts/constant_conversion_table_2023.csv").csv({typed: true})
        }, 'recipients');
    }
    return dbPromise;
}

const donorMapping = name2CodeMap(donorOptions, {})

const recipientMapping = name2CodeMap(recipientOptions)


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
            value: row.converted_value,
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
            value: ratioAsPct(row.original_value, row.total_value),
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
                ? row.converted_value
                : ratioAsPct(row.original_value, row.total_value),
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

function ratioAsPct(numerator, denominator) {
    if (numerator == null || denominator == null || denominator === 0) {
        return null;
    }

    return (numerator / denominator) * 100;
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

    const indicatorCase = Object.entries(recipientsIndicators)
        .map(([code, label]) => `WHEN indicator = ${code} THEN '${escapeSQL(label)}'`)
        .join("\n");

    const indicatorSelection = indicators.join(", ");

    const db = await getDB();
    const query = await db.query(
        `
            WITH filtered AS (
                SELECT
                    year,
                    donor_code AS donor,
                    recipient_code AS recipient,
                    indicator,
                    value
                FROM recipients
                WHERE
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                    AND indicator IN (${indicatorSelection})
            ),
            conversion AS (
                SELECT
                    year,
                    ${prices === "constant" ? "dac_code AS donor," : ""}
                    ${currency}_${prices} AS factor
                FROM
                    ${prices}_conversion_table
                    ${prices === "constant" ? `WHERE dac_code IN (${donor})` : ""}
            ),
            converted AS (
                SELECT
                    f.year,
                    CASE
                        ${indicatorCase}
                    END AS indicator_label,
                    SUM(f.value) AS original_value,
                    SUM(f.value * c.factor) AS converted_value
                FROM filtered f
                    JOIN conversion c
                        ON f.year = c.year
                        ${prices === "constant" ? "AND f.donor = c.donor" : ""}
                GROUP BY f.year, f.indicator
            ),
            totals AS (
                SELECT
                    year,
                    SUM(value) AS total_value
                FROM recipients
                WHERE
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                GROUP BY year
            )
            SELECT
                c.year,
                '${escapeSQL(getNameByCode(donorMapping, donor))}' AS donor,
                '${escapeSQL(getNameByCode(recipientMapping, recipient))}' AS recipient,
                c.indicator_label,
                c.converted_value,
                c.original_value,
                t.total_value
            FROM converted c
                LEFT JOIN totals t ON c.year = t.year
            ORDER BY c.year, c.indicator_label
        `
    );

    return query.toArray().map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        indicator: row.indicator_label,
        converted_value: row.converted_value ?? null,
        original_value: row.original_value ?? null,
        total_value: row.total_value ?? null
    }));
}
