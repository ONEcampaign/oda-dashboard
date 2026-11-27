import {DuckDBClient} from "npm:@observablehq/duckdb";
import {escapeSQL} from "npm:@one-data/observable-themes/utils";
import {COMBINED_INDICATOR_ODA} from "./config.js";

/**
 * IMPORTANT: Value columns in the parquet file are stored as integers in UNITS (not millions).
 * All value_* columns must be divided by 1e6 to convert to millions for display.
 * This conversion is done in the DuckDB SQL queries below.
 */

// The sectors data lives on the CDN, published by CI together with its options: the option
// lists, the opening selections, the name-to-slug maps, and the dataset version and partition
// list used to address partitions. Each version is immutable under its own directory, so a
// page never mixes partitions from two releases.
const CDN_URL = "https://storage.googleapis.com/data-apps-one-data/sources";
const OPTIONS_URL = `${CDN_URL}/sectors_view_options.json`;

const optionsResponse = await fetch(OPTIONS_URL);
if (!optionsResponse.ok) {
    throw new Error(`Sectors options unavailable (${optionsResponse.status}): ${OPTIONS_URL}`);
}
const viewOptions = await optionsResponse.json();
if (!viewOptions.dataset_version || !viewOptions.partition_pairs) {
    throw new Error(`Sectors options lack dataset_version or partition_pairs: ${OPTIONS_URL}`);
}
const PARQUET_DATASET_URL = `${CDN_URL}/sectors_view/${viewOptions.dataset_version}`;

export const donorNames = viewOptions.donor_name;
export const recipientNames = viewOptions.recipient_name;
export const indicatorNames = viewOptions.indicator_name;
export const sectorNames = viewOptions.sector_name;
export const yearOptions = viewOptions.year;
// From this year the CRS reports private sector instruments in a category the bilateral
// data leaves out.
export const psiExcludedFrom = viewOptions.psi_excluded_from;
// The selections the page opens on.
export const defaults = viewOptions.defaults;
export const subSectorsBySector = viewOptions.sub_sectors_by_sector;

const donorSlugs = viewOptions.donor_slugs;
const recipientSlugs = viewOptions.recipient_slugs;
// donor slug -> the recipient slugs it has a partition for.
const partitionPairs = new Map(
    Object.entries(viewOptions.partition_pairs).map(([donorSlug, recipients]) => [donorSlug, new Set(recipients)])
);

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
    }).catch((error) => {
      // Forget a failed start so the next query retries instead of reusing the rejection.
      dbPromise = null;
      throw error;
    });
  }
  return dbPromise;
}

const sectorsCache = new Map();
// Shape of the currency and prices parts of a value_<currency>_<prices> column name.
const SQL_IDENTIFIER_PART = /^[a-z]+$/;

function toArray(value) {
    return Array.isArray(value) ? value : [value];
}

function buildPartitionPaths({donor, recipient}) {
    const donors = toArray(donor);
    const recipients = toArray(recipient);

    const paths = new Set();
    for (const donorName of donors) {
        for (const recipientName of recipients) {
            const donorSlug = donorSlugs[donorName];
            const recipientSlug = recipientSlugs[recipientName];
            // An unlisted pair has no partition, so there is nothing to fetch: "No data".
            // Every listed pair exists, so any failure to read one is a real error.
            if (!partitionPairs.get(donorSlug)?.has(recipientSlug)) continue;
            paths.add(
                `${PARQUET_DATASET_URL}/donor_slug=${donorSlug}/recipient_slug=${recipientSlug}/part-0.parquet`
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

export function sectorsQueries(
    donor,
    recipient,
    indicator,
    selectedSector,
    currency,
    prices,
    timeRange
) {

    const indicators = indicator;

    const donorName = donor;
    const recipientName = recipient;
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
    }));

    // Return base data for selected sector (granular: year + subsector)
    const selectedBase = basePromise.then((rows) => buildSelectedBase(rows, {
        donorName,
        recipientName,
        selectedSector,
        currency,
        prices,
    }));

    // Return base data for table (granular: year + subsector with all raw values)
    const tableBase = basePromise.then((rows) => buildTableBase(rows, {
        donorName,
        recipientName,
        selectedSector,
        currency,
        prices,
    }));

    return {treemap, selectedBase, tableBase};
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
        const series = executeSectorsSeries({
            donor,
            recipient,
            indicators,
            currency,
            prices,
            timeRange
        });
        sectorsCache.set(cacheKey, series);
        // Evict a failed query so the same selection retries rather than replaying the error.
        series.catch(() => {
            if (sectorsCache.get(cacheKey) === series) sectorsCache.delete(cacheKey);
        });
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
    if (indicators.length === 0) {
        return [];
    }

    const indicatorSelection = indicators.map((name) => `'${escapeSQL(name)}'`).join(", ");
    const combineIndicators = indicators.length > 1;
    // These go into the SQL as an identifier and numbers, so check their shape first.
    if (!SQL_IDENTIFIER_PART.test(currency) || !SQL_IDENTIFIER_PART.test(prices)) {
        throw new Error(`Invalid currency or prices: ${currency}, ${prices}`);
    }
    if (!timeRange.every(Number.isInteger)) {
        throw new Error(`Invalid time range: ${timeRange}`);
    }
    const valueColumn = `value_${currency}_${prices}`;

    const partitionPaths = buildPartitionPaths({donor, recipient});
    const parquetClause = buildReadParquetClause(partitionPaths);

    // Return empty array if no paths to query
    if (!parquetClause) {
        return [];
    }

    const db = await getDB();

    return runSectorsQuery(db, {
        donor,
        recipient,
        indicatorSelection,
        combineIndicators,
        valueColumn,
        timeRange,
        parquetClause
    });
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
                        ? `'${escapeSQL(COMBINED_INDICATOR_ODA)}' AS indicator_label,`
                        : "indicator_name AS indicator_label,"
                    }
                    SUM(${valueColumn}) / 1e6 AS converted_value,
                    SUM(value_usd_current) / 1e6 AS original_value,
                    SUM(pct_total_donor) AS pct_total_donor,
                    SUM(pct_total_recipient) AS pct_total_recipient
                FROM ${parquetClause}
                WHERE
                    indicator_name IN (${indicatorSelection})
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
                pct_total_donor,
                pct_total_recipient
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
        pct_total_donor: row.pct_total_donor ?? null,
        pct_total_recipient: row.pct_total_recipient ?? null
    }));
}

function buildTreemap(rows, {
    donorName,
    recipientName,
    currency,
    prices,
    timeRange,
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
                pct_total_donor: row.pct_total_donor ?? null,
                pct_total_recipient: row.pct_total_recipient ?? null,
                currency,
                prices,
                source: "OECD CRS, MultiSystem",
                __order: orderIndex.get(subsectorName) ?? orderedSubsectors.length
            };
        })
        .sort((a, b) => (a.year - b.year) || (a.__order - b.__order))
        .map(({__order, ...rest}) => rest);
}

function valueForUnit({unit, convertedValue, originalValue, sectorTotal, pctTotalDonor, pctTotalRecipient}) {
    switch (unit) {
        case "value":
            return convertedValue ?? null;
        case "pct_sector":
            return ratioAsPct(originalValue, sectorTotal);
        case "pct_total_donor":
            return pctTotalDonor != null ? pctTotalDonor * 100 : null;
        case "pct_total_recipient":
            return pctTotalRecipient != null ? pctTotalRecipient * 100 : null;
        default:
            return convertedValue ?? null;
    }
}

function tableUnitLabel(unit, currency, prices, selectedSector) {
    if (unit === "value") {
        return `${currency} ${prices} million`;
    }

    if (unit === "pct_sector") {
        return pctSectorLabel(selectedSector);
    }

    if (unit === "pct_total_donor") {
        return "% of provided aid";
    }

    if (unit === "pct_total_recipient") {
        return "% of received aid";
    }

    return `${currency} ${prices} million`;
}

// One label for the share-of-sector unit, used by the unit dropdown and the table.
export function pctSectorLabel(sector) {
    return `% of ${sector} ODA`;
}

function ratioAsPct(numerator, denominator) {
    if (numerator == null || denominator == null || denominator === 0) {
        return null;
    }

    return (numerator / denominator) * 100;
}

// Sum that ignores nulls but stays null until a real number is added.
function addNullable(total, value) {
    if (value == null) return total;
    return (total ?? 0) + value;
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
    const {currency, prices, sector} = baseData[0];
    const unitLabel = tableUnitLabel(unit, currency, prices, sector);

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
                pctTotalDonor: row.pct_total_donor,
                pctTotalRecipient: row.pct_total_recipient
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
            // Shares start null so a year with no reported share stays missing, not 0%
            pctTotalDonor: null,
            pctTotalRecipient: null
        };
        entry.convertedValue += row.converted_value ?? 0;
        entry.originalValue += row.original_value ?? 0;
        entry.pctTotalDonor = addNullable(entry.pctTotalDonor, row.pct_total_donor);
        entry.pctTotalRecipient = addNullable(entry.pctTotalRecipient, row.pct_total_recipient);
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
                pctTotalDonor: entry.pctTotalDonor,
                pctTotalRecipient: entry.pctTotalRecipient
            }),
            unit: unitLabel,
            source: baseData[0].source
        }));
}
