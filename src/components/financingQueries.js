import {FileAttachment} from "observablehq:stdlib";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {name2CodeMap, getNameByCode, escapeSQL} from "./utils.js";

const db = await DuckDBClient.of({
    financing: FileAttachment("../data/scripts/financing.parquet").href + (navigator.userAgent.includes("Windows") ? `?t=${Date.now()}` : ""),
    gni_table: FileAttachment("../data/scripts/gni_table.parquet").href + (navigator.userAgent.includes("Windows") ? `?t=${Date.now()}` : ""),
    current_conversion_table: FileAttachment("../data/scripts/current_conversion_table.csv").href + (navigator.userAgent.includes("Windows") ? `?t=${Date.now()}` : ""),
    constant_conversion_table: FileAttachment("../data/scripts/constant_conversion_table_2024.csv").href + (navigator.userAgent.includes("Windows") ? `?t=${Date.now()}` : "")
});

const donorOptions = await FileAttachment("../data/analysis_tools/donors.json").json()
const donorMapping = name2CodeMap(donorOptions)

const financingIndicators = await FileAttachment('../data/analysis_tools/financing_indicators.json').json()
const indicatorMapping = new Map(
    Object.entries(financingIndicators).map(([k, v]) => [v, Number(k)])
);

//  FINANCING VIEW
export function financingQueries(
    donor,
    indicator,
    currency,
    prices,
    timeRange,
    unit
) {
    

    const absolute = absoluteFinancingQuery(
        donor,
        indicator,
        currency,
        prices,
        timeRange
    );

    const relative = relativeFinancingQuery(
        donor,
        indicator,
        currency,
        prices,
        timeRange
    );

    const table = tableFinancingQuery(
        donor,
        indicator,
        currency,
        prices,
        timeRange,
        unit
    );


    return {absolute, relative, table};

}

async function absoluteFinancingQuery(
    donor,
    indicator,
    currency,
    prices,
    timeRange
) {

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
                    AND indicator = ${indicator}
                    AND year between ${timeRange[0]} AND ${timeRange[1]}
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
                    SUM(f.value * c.factor) AS converted_value
                FROM filtered f
                    JOIN conversion c
                ON f.year = c.year
                    ${prices === "constant" ? "AND f.donor = c.donor" : ""}
                GROUP BY f.year
            )
            SELECT
                year AS year,
                '${escapeSQL(getNameByCode(donorMapping, donor))}' AS donor,
                '${escapeSQL(getNameByCode(indicatorMapping, indicator))}' AS indicator,
                CASE
                    WHEN year < 2018 THEN 'Flows'
                    WHEN year >= 2018 THEN 'Grant equivalents'
                END AS type,
                converted_value AS value,
                '${currency} ${prices} million' AS unit,
                'OECD DAC1' AS source
            FROM converted
            ORDER BY year
        `
    )

    return query.toArray().map((row) => ({
        ...row
    }));

}


async function relativeFinancingQuery(
    donor,
    indicator,
    currency,
    prices,
    timeRange
) {

    const query = await db.query(
        `
            WITH filtered AS (
                SELECT 
                    year,
                    SUM(value * 1.1 / 1.1) AS value
                FROM financing
                WHERE 
                    donor_code IN (${donor})
                    AND indicator IN (${indicator})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                GROUP BY year
            ),
            gni AS (
                SELECT 
                    year,
                    SUM(value * 1.1 / 1.1) AS gni
                FROM gni_table
                WHERE
                    donor_code IN (${donor})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                GROUP BY year
            ), 
            total AS (
                SELECT
                    year,
                    SUM(value * 1.1 / 1.1) AS total_value
                FROM financing
                WHERE
                    donor_code IN (${donor})
                    AND indicator = ${indicatorMapping.get("Total ODA")}
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                GROUP BY year
            )
            SELECT
                f.year AS year,
                '${escapeSQL(getNameByCode(donorMapping, donor))}' AS donor,
                ${
                    indicator === indicatorMapping.get("Total ODA")
                        ? "f.value / g.gni * 100"
                        : "f.value / t.total_value * 100"
                } AS value,
                CASE 
                    WHEN f.year < 2018 THEN 'Flows'
                    WHEN f.year >= 2018 THEN 'Grant equivalents'
                END AS type,
                ${
                    indicator === indicatorMapping.get("Total ODA")
                        ? "'% of GNI'"
                        : "'% of total ODA'"
                } AS unit,
                'OECD DAC1' AS source
            FROM filtered f
            ${
                indicator === indicatorMapping.get("Total ODA")
                    ? "JOIN gni g ON f.year = g.year"
                    : "JOIN total t ON f.year = t.year"
            }
            ORDER BY f.year
        `
    );

    return query.toArray().map((row) => ({
        ...row
    }));

}


async function tableFinancingQuery(
    donor,
    indicator,
    currency,
    prices,
    timeRange,
    unit
) {

    const query = await db.query(
        `
            WITH filtered AS (
                SELECT
                    year,
                    donor_code AS donor,
                    indicator,
                    value
                FROM financing
                WHERE
                    donor_code IN (${donor})
                    AND indicator = ${indicator}
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
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
            ),
            total_table AS (
                SELECT
                    year,
                    SUM(value * 1.1 / 1.1) AS total_value
                FROM financing
                WHERE
                    donor_code IN (${donor})
                  AND indicator = ${indicatorMapping.get("Total ODA")}
                  AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                GROUP BY year
            ),
            conversion AS (
                SELECT
                    year,
                    ${prices === "constant" ? "dac_code AS donor," : ""}
                        ${currency}_${prices} AS factor
                FROM ${prices}_conversion_table
                    ${prices === "constant" ? `WHERE dac_code IN (${donor})` : ""}
                    ),
                    converted_table AS (
                SELECT
                    f.year,
                    SUM(f.value * 1.1 / 1.1) AS value,
                    SUM(f.value * c.factor * 1.1 / 1.1) AS converted_value
                FROM filtered f
                    JOIN conversion c
                ON f.year = c.year
                    ${prices === "constant" ? "AND f.donor = c.donor" : ""}
                GROUP BY f.year
            ),
            final_table AS (
                SELECT
                    ct.year,
                    ct.value,
                    ct.converted_value,
                    gt.gni_value,
                    tt.total_value
                FROM converted_table ct
                    LEFT JOIN gni gt ON ct.year = gt.year
                    LEFT JOIN total_table tt ON ct.year = tt.year
            )
            SELECT
                year AS year,
                    '${escapeSQL(getNameByCode(donorMapping, donor))}' AS donor,
                    '${escapeSQL(getNameByCode(indicatorMapping, indicator))}' AS indicator,
                CASE
                    WHEN year < 2018 THEN 'Flows'
                    WHEN year >= 2018 THEN 'Grant equivalents'
                END AS type,
                ${
                    unit === "value" 
                        ? "converted_value" 
                        : unit === "gni_pct" 
                            ? "value / gni_value * 100" 
                            : "value / total_value * 100"
                } AS value,
                ${
                    unit === "value"
                        ? `'${currency} ${prices} million'`
                        : unit === "gni_pct"
                            ? "'% of GNI'"
                            : "'% of total ODA'"
                } AS unit,
                'OECD DAC1' AS source
            FROM final_table
            ORDER BY year
        `
    )

    return query.toArray().map((row) => ({
        ...row
    }));

}

