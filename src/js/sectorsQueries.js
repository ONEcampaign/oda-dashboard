import {DuckDBClient} from "npm:@observablehq/duckdb";
import {FileAttachment} from "observablehq:stdlib";
import {name2CodeMap, getNameByCode} from "./utils.js";

/**
 * IMPORTANT: Value columns in the parquet file are stored as integers in UNITS (not millions).
 * All value_* columns must be divided by 1e6 to convert to millions for display.
 * This conversion is done in the DuckDB SQL queries below.
 */

// Load only metadata required for sectors queries
const [
    donorOptions,
    recipientOptions,
    sectorsIndicators,
    code2Subsector,
    subsector2Sector
] = await Promise.all([
    FileAttachment("../data/analysis_tools/donors.json").json(),
    FileAttachment("../data/analysis_tools/recipients.json").json(),
    FileAttachment("../data/analysis_tools/sectors_indicators.json").json(),
    FileAttachment("../data/analysis_tools/sub_sectors.json").json(),
    FileAttachment("../data/analysis_tools/sectors.json").json()
]);

// Export metadata to avoid duplicate loading in sectors.md
export {donorOptions, recipientOptions, sectorsIndicators, code2Subsector, subsector2Sector};

// Parquet dataset URL (partitioned by donor_code and recipient_code)
const PARQUET_DATASET_URL = "https://storage.googleapis.com/data-apps-one-data/sources/sectors_view";

// Lazy initialization: DuckDB instance is created on first query
let dbPromise = null;
function getDB() {
  if (!dbPromise) {
    dbPromise = DuckDBClient.of().then(async (db) => {
      // Configure for optimal HTTP parquet reads
      await db.query(`
        LOAD parquet;
        LOAD httpfs;

        SET enable_http_metadata_cache = true;
        SET http_timeout = 120000;
        SET force_download = false;
        SET enable_object_cache = true;
      `);
      return db;
    });
  }
  return dbPromise;
}

const donorMapping = name2CodeMap(donorOptions);
const recipientMapping = name2CodeMap(recipientOptions);

const indicatorLabelMap = new Map(
    Object.entries(sectorsIndicators).map(([code, label]) => [Number(code), label])
);

const sectorsCache = new Map();

function toArray(value) {
    return Array.isArray(value) ? value : [value];
}

function buildPartitionPaths({donor, recipient}) {
    const donors = toArray(donor);
    const recipients = toArray(recipient);

    const paths = new Set();
    for (const donorCode of donors) {
        for (const recipientCode of recipients) {
            paths.add(
                `${PARQUET_DATASET_URL}/donor_code=${donorCode}/recipient_code=${recipientCode}/part-0.parquet`
            );
        }
    }

    return [...paths];
}

function buildReadParquetClause(paths) {
    if (paths.length === 0) {
        return null;
    }

    if (paths.length === 1) {
        return `read_parquet('${paths[0]}', union_by_name=true)`;
    }

    const quoted = paths.map((path) => `'${path}'`).join(", ");
    return `read_parquet([${quoted}], union_by_name=true)`;
}

function isNotFoundError(error) {
    const message = error?.message?.toLowerCase() ?? "";
    return message.includes("404") || message.includes("not found") || message.includes("no files matched");
}

export function sectorsQueries(
    donor,
    recipient,
    indicator,
    selectedSector,
    currency,
    prices,
    timeRange
) {

    const indicators = indicator.length > 0 ? indicator : [-1];

    const donorName = getNameByCode(donorMapping, donor) ?? "Unknown";
    const recipientName = getNameByCode(recipientMapping, recipient) ?? "Unknown";
    const indicatorUnitLabel = indicators.length > 1
        ? "Bilateral + Imputed multilateral ODA"
        : indicatorLabelMap.get(indicators[0]) ?? "Total ODA";

    const basePromise = fetchSectorsSeries({
        donor,
        recipient,
        indicators,
        currency,
        prices,
        timeRange
    });

    const treemap = basePromise.then((rows) => buildTreemap(rows, {
        donorName,
        recipientName,
        currency,
        prices,
        timeRange,
        code2Subsector,
        subsector2Sector
    }));

    // Return base data for selected sector (granular: year + subsector)
    const selectedBase = basePromise.then((rows) => buildSelectedBase(rows, {
        donorName,
        recipientName,
        selectedSector,
        currency,
        prices,
        code2Subsector,
        subsector2Sector
    }));

    // Return base data for table (granular: year + subsector with all raw values)
    const tableBase = basePromise.then((rows) => buildTableBase(rows, {
        donorName,
        recipientName,
        selectedSector,
        currency,
        prices,
        indicatorUnitLabel,
        code2Subsector,
        subsector2Sector
    }));

    return {treemap, selectedBase, tableBase, indicatorUnitLabel};
}

function sectorsCacheKey({donor, recipient, indicators, currency, prices, timeRange}) {
    const donorKey = Array.isArray(donor) ? [...donor].sort().join(",") : String(donor);
    const recipientKey = Array.isArray(recipient) ? [...recipient].sort().join(",") : String(recipient);
    const indicatorKey = Array.isArray(indicators) ? [...indicators].sort().join(",") : String(indicators);
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

async function fetchSectorsSeries({
    donor,
    recipient,
    indicators,
    currency,
    prices,
    timeRange
}) {
    const cacheKey = sectorsCacheKey({donor, recipient, indicators, currency, prices, timeRange});

    if (!sectorsCache.has(cacheKey)) {
        sectorsCache.set(cacheKey, executeSectorsSeries({
            donor,
            recipient,
            indicators,
            currency,
            prices,
            timeRange
        }));
    }

    return sectorsCache.get(cacheKey);
}

async function executeSectorsSeries({
    donor,
    recipient,
    indicators,
    currency,
    prices,
    timeRange
}) {
    if (indicators.length === 0 || (indicators.length === 1 && indicators[0] === -1)) {
        return [];
    }

    const indicatorSelection = indicators.join(", ");
    const combineIndicators = indicators.length > 1;
    const valueColumn = `value_${currency}_${prices}`;

    const partitionPaths = buildPartitionPaths({donor, recipient});
    const parquetClause = buildReadParquetClause(partitionPaths);

    // Return empty array if no paths to query
    if (!parquetClause) {
        return [];
    }

    const db = await getDB();

    try {
        return await runSectorsQuery(db, {
            donor,
            recipient,
            indicatorSelection,
            combineIndicators,
            valueColumn,
            timeRange,
            parquetClause
        });
    } catch (error) {
        // Return empty array for 404/not found errors (partition doesn't exist)
        if (isNotFoundError(error)) {
            return [];
        }
        // Re-throw other errors
        throw error;
    }
}

async function runSectorsQuery(db, {
    parquetClause,
    donor,
    recipient,
    indicatorSelection,
    combineIndicators,
    valueColumn,
    timeRange
}) {
    if (!parquetClause) {
        return [];
    }

    const query = await db.query(
        `
            WITH aggregated AS (
                SELECT
                    year,
                    donor_name AS donor,
                    recipient_name AS recipient,
                    sector_name,
                    sub_sector_name AS sub_sector,
                    ${combineIndicators
                        ? "'Bilateral + Imputed multilateral ODA' AS indicator_label,"
                        : "indicator_name AS indicator_label,"
                    }
                    SUM(${valueColumn}) / 1e6 AS converted_value,
                    SUM(value_usd_current) / 1e6 AS original_value
                FROM ${parquetClause}
                WHERE
                    donor_code = ${donor}
                    AND recipient_code = ${recipient}
                    AND indicator IN (${indicatorSelection})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                GROUP BY year, donor_name, recipient_name, sector_name, sub_sector_name${combineIndicators ? "" : ", indicator_name"}
            )
            SELECT
                year,
                donor,
                recipient,
                sector_name,
                sub_sector,
                indicator_label,
                converted_value,
                original_value,
                SUM(original_value) OVER (PARTITION BY year) AS indicator_original_value
            FROM aggregated
            ORDER BY year, sub_sector
        `
    );

    return query.toArray().map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
        sector_name: row.sector_name,
        sub_sector: row.sub_sector,
        indicator: row.indicator_label,
        converted_value: row.converted_value ?? null,
        original_value: row.original_value ?? null,
        indicator_total_original: row.indicator_original_value ?? null
    }));
}

function buildTreemap(rows, {
    donorName,
    recipientName,
    currency,
    prices,
    timeRange,
    code2Subsector,
    subsector2Sector
}) {
    if (!rows.length) return [];

    const unit = `${currency} ${prices} million`;
    const period = timeRange[0] === timeRange[1]
        ? `${timeRange[0]}`
        : `${timeRange[0]}-${timeRange[1]}`;

    const aggregated = new Map();
    for (const row of rows) {
        const sectorName = row.sector_name ?? "Other";
        const key = `${sectorName}|${row.indicator}`;
        const total = aggregated.get(key) ?? 0;
        aggregated.set(key, total + (row.converted_value ?? 0));
    }

    return Array.from(aggregated.entries())
        .map(([key, value]) => {
            const [sectorName, indicatorLabel] = key.split("|");
            return {
                period,
                donor: donorName,
                recipient: recipientName,
                sector: sectorName,
                indicator: indicatorLabel,
                value,
                unit,
                source: "OECD CRS, MultiSystem"
            };
        })
        .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
}

// Build base data for selected sector (always granular: year + subsector)
function buildSelectedBase(rows, {
    donorName,
    recipientName,
    selectedSector,
    currency,
    prices,
    code2Subsector,
    subsector2Sector
}) {
    const relevantRows = rows.filter((row) => {
        const sectorName = row.sector_name ?? "Other";
        return sectorName === selectedSector;
    });

    if (!relevantRows.length) return [];

    const unit = `${currency} ${prices} million`;

    // Calculate subsector totals for ordering
    const subsectorTotals = new Map();
    for (const row of relevantRows) {
        const subsectorName = row.sub_sector ?? "Other";
        subsectorTotals.set(subsectorName, (subsectorTotals.get(subsectorName) ?? 0) + (row.converted_value ?? 0));
    }

    const orderedSubsectors = [...subsectorTotals.entries()]
        .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))
        .map(([name]) => name);
    const orderIndex = new Map(orderedSubsectors.map((name, index) => [name, index]));

    // Return granular data (year + subsector)
    return relevantRows
        .map((row) => {
            const subsectorName = row.sub_sector ?? "Other";
            return {
                year: row.year,
                donor: donorName,
                recipient: recipientName,
                sector: selectedSector,
                sub_sector: subsectorName,
                indicator: row.indicator,
                value: row.converted_value ?? null,
                unit,
                source: "OECD CRS, MultiSystem",
                __order: orderIndex.get(subsectorName) ?? orderedSubsectors.length
            };
        })
        .sort((a, b) => (a.year - b.year) || (a.__order - b.__order))
        .map(({__order, ...rest}) => rest);
}

// Build base data for table (always granular: year + subsector with raw values)
function buildTableBase(rows, {
    donorName,
    recipientName,
    selectedSector,
    currency,
    prices,
    indicatorUnitLabel,
    code2Subsector,
    subsector2Sector
}) {
    const relevantRows = rows.filter((row) => {
        const sectorName = row.sector_name ?? "Other";
        return sectorName === selectedSector;
    });

    if (!relevantRows.length) return [];

    // Calculate sector totals by year for pct_sector calculations
    const sectorTotalsByYear = new Map();
    for (const row of relevantRows) {
        sectorTotalsByYear.set(
            row.year,
            (sectorTotalsByYear.get(row.year) ?? 0) + (row.original_value ?? 0)
        );
    }

    // Calculate subsector totals for ordering
    const subsectorTotals = new Map();
    for (const row of relevantRows) {
        const subsectorName = row.sub_sector ?? "Other";
        subsectorTotals.set(subsectorName, (subsectorTotals.get(subsectorName) ?? 0) + (row.converted_value ?? 0));
    }
    const orderedSubsectors = [...subsectorTotals.entries()]
        .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))
        .map(([name]) => name);
    const orderIndex = new Map(orderedSubsectors.map((name, index) => [name, index]));

    // Return granular data with all raw values for unit conversions
    return relevantRows
        .map((row) => {
            const subsectorName = row.sub_sector ?? "Other";
            return {
                year: row.year,
                donor: donorName,
                recipient: recipientName,
                sector: selectedSector,
                sub_sector: subsectorName,
                indicator: row.indicator,
                converted_value: row.converted_value ?? null,
                original_value: row.original_value ?? null,
                sector_total: sectorTotalsByYear.get(row.year) ?? null,
                indicator_total: row.indicator_total_original ?? null,
                currency,
                prices,
                indicatorUnitLabel,
                source: "OECD CRS, MultiSystem",
                __order: orderIndex.get(subsectorName) ?? orderedSubsectors.length
            };
        })
        .sort((a, b) => (a.year - b.year) || (a.__order - b.__order))
        .map(({__order, ...rest}) => rest);
}

function valueForUnit({unit, convertedValue, originalValue, sectorTotal, indicatorTotal}) {
    switch (unit) {
        case "value":
            return convertedValue ?? null;
        case "pct_sector":
            return ratioAsPct(originalValue, sectorTotal);
        case "pct_total":
            return ratioAsPct(originalValue, indicatorTotal);
        default:
            return convertedValue ?? null;
    }
}

function tableUnitLabel(unit, currency, prices, selectedSector, indicatorUnitLabel) {
    if (unit === "value") {
        return `${currency} ${prices} million`;
    }

    if (unit === "pct_sector") {
        return `% of ${selectedSector}`;
    }

    if (unit === "pct_total") {
        return `% of ${indicatorUnitLabel}`;
    }

    return `${currency} ${prices} million`;
}

function ratioAsPct(numerator, denominator) {
    if (numerator == null || denominator == null || denominator === 0) {
        return null;
    }

    return (numerator / denominator) * 100;
}

// Export transformation functions for reactive UI updates

// Transform selected data based on breakdown flag
export function transformSelectedData(baseData, breakdown) {
    if (!baseData || baseData.length === 0) return [];

    // If breakdown is enabled, return granular data as-is
    if (breakdown) {
        return baseData;
    }

    // Otherwise, aggregate by year only
    const aggregatedByYear = new Map();
    for (const row of baseData) {
        const entry = aggregatedByYear.get(row.year) ?? {
            year: row.year,
            donor: row.donor,
            recipient: row.recipient,
            sector: row.sector,
            indicator: row.indicator,
            value: 0,
            unit: row.unit,
            source: row.source
        };
        entry.value += row.value ?? 0;
        aggregatedByYear.set(row.year, entry);
    }

    return [...aggregatedByYear.values()].sort((a, b) => a.year - b.year);
}

// Transform table data based on unit and breakdown flags
export function transformTableData(baseData, unit, breakdown) {
    if (!baseData || baseData.length === 0) return [];

    // First row has metadata we need
    const {currency, prices, sector, indicatorUnitLabel} = baseData[0];
    const unitLabel = tableUnitLabel(unit, currency, prices, sector, indicatorUnitLabel);

    if (breakdown) {
        // Return granular data with unit applied
        return baseData.map((row) => ({
            year: row.year,
            donor: row.donor,
            recipient: row.recipient,
            sector: row.sector,
            sub_sector: row.sub_sector,
            indicator: row.indicator,
            value: valueForUnit({
                unit,
                convertedValue: row.converted_value,
                originalValue: row.original_value,
                sectorTotal: row.sector_total,
                indicatorTotal: row.indicator_total
            }),
            unit: unitLabel,
            source: row.source
        }));
    }

    // Aggregate by year only
    const aggregatedByYear = new Map();
    for (const row of baseData) {
        const entry = aggregatedByYear.get(row.year) ?? {
            year: row.year,
            donor: row.donor,
            recipient: row.recipient,
            sector: row.sector,
            indicator: row.indicator,
            convertedValue: 0,
            originalValue: 0,
            indicatorTotal: row.indicator_total
        };
        entry.convertedValue += row.converted_value ?? 0;
        entry.originalValue += row.original_value ?? 0;
        entry.indicatorTotal = row.indicator_total ?? entry.indicatorTotal;
        aggregatedByYear.set(row.year, entry);
    }

    return [...aggregatedByYear.values()]
        .sort((a, b) => a.year - b.year)
        .map((entry) => ({
            year: entry.year,
            donor: entry.donor,
            recipient: entry.recipient,
            sector: entry.sector,
            indicator: entry.indicator,
            value: valueForUnit({
                unit,
                convertedValue: entry.convertedValue,
                originalValue: entry.originalValue,
                sectorTotal: entry.originalValue,
                indicatorTotal: entry.indicatorTotal
            }),
            unit: unitLabel,
            source: baseData[0].source
        }));
}
