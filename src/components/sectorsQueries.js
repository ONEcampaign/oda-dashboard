import {FileAttachment} from "observablehq:stdlib";
import {name2CodeMap, getNameByCode, escapeSQL} from "./utils.js";
import {
    donorOptions,
    recipientOptions,
    sectorsIndicators,
    code2Subsector,
    subsector2Sector
} from "./sharedMetadata.js";
import {createDuckDBClient} from "./duckdbFactory.js";

// Lazy initialization: DuckDB instance is created on first query
let dbPromise = null;
function getDB() {
    if (!dbPromise) {
        const cacheBuster = navigator.userAgent.includes("Windows") ? `?t=${Date.now()}` : "";
        dbPromise = createDuckDBClient({
            sectors: FileAttachment("../data/scripts/sectors.parquet").href + cacheBuster,
            current_conversion_table: FileAttachment("../data/scripts/current_conversion_table.csv").csv({typed: true}),
            constant_conversion_table: FileAttachment("../data/scripts/constant_conversion_table_2023.csv").csv({typed: true})
        }, 'sectors');
    }
    return dbPromise;
}

const donorMapping = name2CodeMap(donorOptions);
const recipientMapping = name2CodeMap(recipientOptions);

const indicatorLabelMap = new Map(
    Object.entries(sectorsIndicators).map(([code, label]) => [Number(code), label])
);

const indicatorCase = Object.entries(sectorsIndicators)
    .map(([code, label]) => `WHEN indicator = ${code} THEN '${escapeSQL(label)}'`)
    .join("\n");

const sectorsCache = new Map();

export function sectorsQueries(
    donor,
    recipient,
    indicator,
    selectedSector,
    currency,
    prices,
    timeRange,
    breakdown,
    unit
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

    const selected = basePromise.then((rows) => buildSelected(rows, {
        donorName,
        recipientName,
        selectedSector,
        breakdown,
        currency,
        prices,
        code2Subsector,
        subsector2Sector
    }));

    const table = basePromise.then((rows) => buildTable(rows, {
        donorName,
        recipientName,
        selectedSector,
        breakdown,
        unit,
        currency,
        prices,
        indicatorUnitLabel,
        code2Subsector,
        subsector2Sector
    }));

    return {treemap, selected, table};
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
    const donorLabel = escapeSQL(getNameByCode(donorMapping, donor) ?? "Unknown");
    const recipientLabel = escapeSQL(getNameByCode(recipientMapping, recipient) ?? "Unknown");

    const db = await getDB();
    const query = await db.query(
        `
            WITH filtered AS (
                SELECT
                    year,
                    donor_code AS donor,
                    recipient_code AS recipient,
                    sub_sector,
                    indicator,
                    value
                FROM sectors
                WHERE
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND indicator IN (${indicatorSelection})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
            ),
            conversion AS (
                SELECT
                    year,
                    ${prices === "constant" ? "dac_code AS donor," : ""}
                    ${currency}_${prices} AS factor
                FROM ${prices}_conversion_table
                    ${prices === "constant" ? `WHERE dac_code IN (${donor})` : ""}
            ),
            converted AS (
                SELECT
                    f.year,
                    f.sub_sector,
                    ${combineIndicators
                        ? "'Bilateral + Imputed multilateral ODA'"
                        : `CASE
                                ${indicatorCase}
                            END`
                    } AS indicator_label,
                    SUM(f.value) AS original_value,
                    SUM(f.value * c.factor) AS converted_value
                FROM filtered f
                    JOIN conversion c
                        ON f.year = c.year
                        ${prices === "constant" ? "AND f.donor = c.donor" : ""}
                GROUP BY f.year, f.sub_sector${combineIndicators ? "" : ", f.indicator"}
            ),
            indicator_totals AS (
                SELECT
                    year,
                    SUM(value) AS indicator_original_value
                FROM filtered
                GROUP BY year
            )
            SELECT
                c.year,
                '${donorLabel}' AS donor,
                '${recipientLabel}' AS recipient,
                c.sub_sector,
                c.indicator_label,
                c.converted_value,
                c.original_value,
                it.indicator_original_value
            FROM converted c
                LEFT JOIN indicator_totals it ON c.year = it.year
            ORDER BY c.year, c.sub_sector
        `
    );

    return query.toArray().map((row) => ({
        year: row.year,
        donor: row.donor,
        recipient: row.recipient,
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
        const subsectorName = code2Subsector[row.sub_sector] ?? "Other";
        const sectorName = subsector2Sector[subsectorName] ?? "Other";
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

function buildSelected(rows, {
    donorName,
    recipientName,
    selectedSector,
    breakdown,
    currency,
    prices,
    code2Subsector,
    subsector2Sector
}) {
    const relevantRows = rows.filter((row) => {
        const subsectorName = code2Subsector[row.sub_sector] ?? "Other";
        const sectorName = subsector2Sector[subsectorName] ?? "Other";
        return sectorName === selectedSector;
    });

    if (!relevantRows.length) return [];

    const unit = `${currency} ${prices} million`;

    if (breakdown) {
        const subsectorTotals = new Map();
        for (const row of relevantRows) {
            const subsectorName = code2Subsector[row.sub_sector] ?? "Other";
            subsectorTotals.set(subsectorName, (subsectorTotals.get(subsectorName) ?? 0) + (row.converted_value ?? 0));
        }

        const orderedSubsectors = [...subsectorTotals.entries()]
            .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))
            .map(([name]) => name);
        const orderIndex = new Map(orderedSubsectors.map((name, index) => [name, index]));

        return relevantRows
            .map((row) => {
                const subsectorName = code2Subsector[row.sub_sector] ?? "Other";
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

    const aggregatedByYear = new Map();
    for (const row of relevantRows) {
        const entry = aggregatedByYear.get(row.year) ?? {
            year: row.year,
            donor: donorName,
            recipient: recipientName,
            sector: selectedSector,
            indicator: row.indicator,
            value: 0
        };
        entry.value += row.converted_value ?? 0;
        aggregatedByYear.set(row.year, entry);
    }

    return [...aggregatedByYear.values()]
        .sort((a, b) => a.year - b.year)
        .map((entry) => ({
            ...entry,
            unit,
            source: "OECD CRS, MultiSystem"
        }));
}

function buildTable(rows, {
    donorName,
    recipientName,
    selectedSector,
    breakdown,
    unit,
    currency,
    prices,
    indicatorUnitLabel,
    code2Subsector,
    subsector2Sector
}) {
    const relevantRows = rows.filter((row) => {
        const subsectorName = code2Subsector[row.sub_sector] ?? "Other";
        const sectorName = subsector2Sector[subsectorName] ?? "Other";
        return sectorName === selectedSector;
    });

    if (!relevantRows.length) return [];

    const unitLabel = tableUnitLabel(unit, currency, prices, selectedSector, indicatorUnitLabel);

    if (breakdown) {
        const sectorTotalsByYear = new Map();
        for (const row of relevantRows) {
            sectorTotalsByYear.set(
                row.year,
                (sectorTotalsByYear.get(row.year) ?? 0) + (row.original_value ?? 0)
            );
        }

        const subsectorTotals = new Map();
        for (const row of relevantRows) {
            const subsectorName = code2Subsector[row.sub_sector] ?? "Other";
            subsectorTotals.set(subsectorName, (subsectorTotals.get(subsectorName) ?? 0) + (row.converted_value ?? 0));
        }
        const orderedSubsectors = [...subsectorTotals.entries()]
            .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))
            .map(([name]) => name);
        const orderIndex = new Map(orderedSubsectors.map((name, index) => [name, index]));

        return relevantRows
            .map((row) => {
                const subsectorName = code2Subsector[row.sub_sector] ?? "Other";
                return {
                    year: row.year,
                    donor: donorName,
                    recipient: recipientName,
                    sector: selectedSector,
                    sub_sector: subsectorName,
                    indicator: row.indicator,
                    value: valueForUnit({
                        unit,
                        convertedValue: row.converted_value,
                        originalValue: row.original_value,
                        sectorTotal: sectorTotalsByYear.get(row.year),
                        indicatorTotal: row.indicator_total_original
                    }),
                    unit: unitLabel,
                    source: "OECD CRS, MultiSystem",
                    __order: orderIndex.get(subsectorName) ?? orderedSubsectors.length
                };
            })
            .sort((a, b) => (a.year - b.year) || (a.__order - b.__order))
            .map(({__order, ...rest}) => rest);
    }

    const aggregatedByYear = new Map();
    for (const row of relevantRows) {
        const entry = aggregatedByYear.get(row.year) ?? {
            year: row.year,
            donor: donorName,
            recipient: recipientName,
            sector: selectedSector,
            indicator: row.indicator,
            convertedValue: 0,
            originalValue: 0,
            indicatorTotal: row.indicator_total_original
        };
        entry.convertedValue += row.converted_value ?? 0;
        entry.originalValue += row.original_value ?? 0;
        entry.indicatorTotal = row.indicator_total_original ?? entry.indicatorTotal;
        aggregatedByYear.set(row.year, entry);
    }

    return [...aggregatedByYear.values()]
        .sort((a, b) => a.year - b.year)
        .map((entry) => ({
            year: entry.year,
            donor: donorName,
            recipient: recipientName,
            sector: selectedSector,
            indicator: entry.indicator,
            value: valueForUnit({
                unit,
                convertedValue: entry.convertedValue,
                originalValue: entry.originalValue,
                sectorTotal: entry.originalValue,
                indicatorTotal: entry.indicatorTotal
            }),
            unit: unitLabel,
            source: "OECD CRS, MultiSystem"
        }));
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
