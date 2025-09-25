import {FileAttachment} from "observablehq:stdlib";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {name2CodeMap, getNameByCode, escapeSQL} from "./utils.js";

const [
    donorOptions,
    financingIndicators
] = await Promise.all([
    FileAttachment("../data/analysis_tools/donors.json").json(),
    FileAttachment('../data/analysis_tools/financing_indicators.json').json()
]);

const db = await DuckDBClient.of({
    financing: FileAttachment("../data/scripts/financing.parquet").href + (navigator.userAgent.includes("Windows") ? `?t=${Date.now()}` : ""),
    gni_table: FileAttachment("../data/scripts/gni_table.parquet").href + (navigator.userAgent.includes("Windows") ? `?t=${Date.now()}` : ""),
    current_conversion_table: FileAttachment("../data/scripts/current_conversion_table.csv").csv({typed: true}),
    constant_conversion_table: FileAttachment("../data/scripts/constant_conversion_table_2024.csv").csv({typed: true}),
});


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
    timeRange,
    unit
) {

    const basePromise = fetchFinancingSeries(
        donor,
        indicator,
        currency,
        prices,
        timeRange
    );

    const absolute = basePromise.then((rows) =>
        rows.map((row) => ({
            year: row.year,
            donor: row.donor,
            indicator: row.indicator,
            type: row.type,
            value: row.converted_value,
            unit: `${currency} ${prices} million`,
            source: "OECD DAC1"
        }))
    );

    const relative = basePromise.then((rows) =>
        rows.map((row) => ({
            year: row.year,
            donor: row.donor,
            indicator: row.indicator,
            type: row.type,
            value: deriveRelativeValue(row, indicator),
            unit: indicator === indicatorMapping.get("Total ODA")
                ? "% of GNI"
                : "% of total ODA",
            source: "OECD DAC1"
        }))
    );

    const table = basePromise.then((rows) =>
        rows.map((row) => {
            return {
                year: row.year,
                donor: row.donor,
                indicator: row.indicator,
                type: row.type,
                value: deriveTableValue(row, unit, indicator),
                unit: deriveTableUnit(unit, currency, prices, indicator),
                source: "OECD DAC1"
            };
        })
    );

    return {absolute, relative, table};

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

function deriveRelativeValue(row, indicator) {
    if (row.original_value == null) return null;

    if (indicator === indicatorMapping.get("Total ODA")) {
        return ratioAsPct(row.original_value, row.gni_value);
    }

    return ratioAsPct(row.original_value, row.total_original);
}

function deriveTableValue(row, unit, indicator) {
    switch (unit) {
        case "value":
            return row.converted_value;
        case "gni_pct":
            return ratioAsPct(row.original_value, row.gni_value);
        case "total_pct":
            return ratioAsPct(row.original_value, row.total_original);
        default:
            return row.converted_value;
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
        return indicator === indicatorMapping.get("Total ODA")
            ? "% of total ODA"
            : "% of total ODA";
    }

    return `${currency} ${prices} million`;
}

function ratioAsPct(numerator, denominator) {
    if (numerator == null || denominator == null || denominator === 0) {
        return null;
    }

    return (numerator / denominator) * 100;
}

async function fetchFinancingSeries(
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

async function executeFinancingSeries(
    donor,
    indicator,
    currency,
    prices,
    timeRange
) {
    const totalIndicatorCode = indicatorMapping.get("Total ODA");
    const indicatorsForQuery = indicator === totalIndicatorCode
        ? `${indicator}`
        : `${indicator}, ${totalIndicatorCode}`;

    const query = await db.query(
        `
            WITH filtered AS (
                SELECT
                    year,
                    donor_code AS donor,
                    indicator,
                    (value * 1.1 / 1.1) AS value
                FROM financing
                WHERE
                    donor_code IN (${donor})
                    AND indicator IN (${indicatorsForQuery})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
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
                    f.indicator,
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
                    original_value AS total_original,
                    converted_value AS total_converted
                FROM converted
                WHERE indicator = ${totalIndicatorCode}
            ),
            gni AS (
                SELECT
                    year,
                    SUM(value * 1.1 / 1.1) AS gni_value
                FROM gni_table
                WHERE
                    donor_code IN (${donor})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                GROUP BY year
            )
            SELECT
                c.year AS year,
                '${escapeSQL(getNameByCode(donorMapping, donor))}' AS donor,
                '${escapeSQL(getNameByCode(indicatorMapping, indicator))}' AS indicator,
                CASE
                    WHEN c.year < 2018 THEN 'Flows'
                    WHEN c.year >= 2018 THEN 'Grant equivalents'
                END AS type,
                c.converted_value,
                c.original_value,
                t.total_original,
                t.total_converted,
                g.gni_value
            FROM converted c
                LEFT JOIN totals t ON c.year = t.year
                LEFT JOIN gni g ON c.year = g.year
            WHERE c.indicator = ${indicator}
            ORDER BY c.year
        `
    );

    return query.toArray().map((row) => ({
        year: row.year,
        donor: row.donor,
        indicator: row.indicator,
        type: row.type,
        converted_value: row.converted_value ?? null,
        original_value: row.original_value ?? null,
        total_original: row.total_original ?? null,
        total_converted: row.total_converted ?? null,
        gni_value: row.gni_value ?? null
    }));
}
