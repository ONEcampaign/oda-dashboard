import {FileAttachment} from "observablehq:stdlib";
import {name2CodeMap} from "./utils.js";
import {donorOptions, financingIndicators} from "./sharedMetadata.js";
import {createDuckDBClient} from "./duckdbFactory.js";

// Lazy initialization: DuckDB instance is created on first query
let dbPromise = null;
function getDB() {
    if (!dbPromise) {
        const cacheBuster = navigator.userAgent.includes("Windows") ? `?t=${Date.now()}` : "";
        dbPromise = createDuckDBClient({
            financing: FileAttachment("../data/scripts/financing_view.parquet").href + cacheBuster
        }, 'financing');
    }
    return dbPromise;
}

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
            value: row.value,
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
            value: indicator === indicatorMapping.get("Total ODA")
                ? row.pct_of_gni * 100
                : row.pct_of_total_oda * 100,
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
    const db = await getDB();
    const valueColumn = `value_${currency}_${prices}`;

    const query = await db.query(
        `
            SELECT
                year,
                donor_name AS donor,
                indicator_name AS indicator,
                type,
                ${valueColumn} AS value,
                pct_of_gni,
                pct_of_total_oda
            FROM financing
            WHERE
                donor_code = ${donor}
                AND indicator = ${indicator}
                AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
            ORDER BY year
        `
    );

    return query.toArray().map((row) => ({
        year: row.year,
        donor: row.donor,
        indicator: row.indicator,
        type: row.type,
        value: row.value ?? null,
        pct_of_gni: row.pct_of_gni ?? null,
        pct_of_total_oda: row.pct_of_total_oda ?? null
    }));
}
