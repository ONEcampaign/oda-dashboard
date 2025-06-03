import {FileAttachment} from "observablehq:stdlib";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {name2CodeMap, getNameByCode, escapeSQL} from "./utils.js";

const [
    donorOptions,
    recipientOptions,
    genderIndicators
] = await Promise.all([
    FileAttachment("../data/analysis_tools/donors.json").json(),
    FileAttachment("../data/analysis_tools/recipients.json").json(),
    FileAttachment('../data/analysis_tools/gender_indicators.json').json()
])


const db = await DuckDBClient.of({
    gender: FileAttachment("../data/scripts/gender.parquet"),
    current_conversion_table: FileAttachment("../data/scripts/current_conversion_table.csv"),
    constant_conversion_table: FileAttachment("../data/scripts/constant_conversion_table_2023.csv")
});

const donorMapping = name2CodeMap(donorOptions, {})

const recipientMapping = name2CodeMap(recipientOptions)


// GENDER VIEW
export function genderQueries(
    donor,
    recipient,
    indicator,
    currency,
    prices,
    timeRange,
    unit
) {

    const indicators = indicator.length > 0 ? indicator : [-1]; // use -1 or any value that won’t match real indicators

    const indicatorCase = Object.entries(genderIndicators)
        .map(([code, label]) => `WHEN indicator = ${code} THEN '${escapeSQL(label)}'`)
        .join("\n");

    const absolute = absoluteGenderQuery(
        donor,
        recipient,
        indicators,
        indicatorCase,
        currency,
        prices,
        timeRange
    );

    const relative = relativeGenderQuery(
        donor,
        recipient,
        indicators,
        indicatorCase,
        currency,
        prices,
        timeRange
    );

    const table = tableGenderQuery(
        donor,
        recipient,
        indicators,
        indicatorCase,
        currency,
        prices,
        timeRange,
        unit
    )

    return {absolute, relative, table};

}

async function absoluteGenderQuery(
    donor,
    recipient,
    indicator,
    indicatorCase,
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
                FROM gender
                WHERE 
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND year between ${timeRange[0]} AND ${timeRange[1]}
                    AND indicator IN (${indicator})
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
            joined AS (
                SELECT
                    f.year,
                    f.indicator,
                    f.value * c.factor AS converted_value
                FROM filtered f
                    JOIN conversion c
                ON f.year = c.year
                    ${prices === "constant" ? "AND f.donor = c.donor" : ""}
            )
            SELECT
                year AS year,
                '${escapeSQL(getNameByCode(donorMapping, donor))}' AS donor,
                '${escapeSQL(getNameByCode(recipientMapping, recipient))}' AS recipient,
                CASE    
                    ${indicatorCase}
                END AS indicator,
                SUM(converted_value) AS value,
                '${currency} ${prices} million' AS unit,
                'OECD CRS' AS source
            FROM joined
            GROUP BY year, indicator
            ORDER BY year
        `
    )

    return query.toArray().map((row) => ({
        ...row
    }));

}

async function relativeGenderQuery(
    donor,
    recipient,
    indicator,
    indicatorCase,
    currency,
    prices,
    timeRange
) {

    const query = await db.query(
        `
            WITH filtered AS (
                SELECT 
                    year,
                    indicator,
                    SUM(value * 1.1 / 1.1) AS value
                FROM gender
                WHERE 
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                    AND indicator IN (${indicator})
                GROUP BY year, indicator
            ),
            total AS (
                SELECT 
                    year,
                    SUM(value * 1.1 / 1.1) AS total_value
                FROM gender
                WHERE
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                GROUP BY year
            )
            SELECT
                f.year AS year,
                '${escapeSQL(getNameByCode(donorMapping, donor))}' AS donor,
                '${escapeSQL(getNameByCode(recipientMapping, recipient))}' AS recipient,
                CASE
                    ${indicatorCase}
                END AS indicator,
                f.value / t.total_value * 100 AS value,
                '% of total ODA' AS unit,
                'OECD CRS' AS source
            FROM filtered f
            JOIN total t ON f.year = t.year
            ORDER BY f.year
        `
    );


    return query.toArray().map((row) => ({
        ...row
    }));

}

async function tableGenderQuery(
    donor,
    recipient,
    indicator,
    indicatorCase,
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
                    (value * 1.1 / 1.1) AS value
                FROM gender
                WHERE 
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND year between ${timeRange[0]} AND ${timeRange[1]}
                    AND indicator IN (${indicator})
            ),
            total_table AS (
                SELECT
                    year,
                    SUM(value * 1.1 / 1.1) AS total_value
                FROM gender
                WHERE
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND year between ${timeRange[0]} AND ${timeRange[1]}  
                GROUP BY year
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
            converted_table AS (
                SELECT
                    f.year,
                    f.indicator,
                    SUM(f.value * 1.1 / 1.1) AS value,
                    SUM(f.value * c.factor) AS converted_value
                FROM filtered f
                    JOIN conversion c
                ON f.year = c.year
                    ${prices === "constant" ? "AND f.donor = c.donor" : ""}
                GROUP BY f.year, f.indicator
            ),
            final_table AS (
                SELECT 
                    ct.year, 
                    ct.indicator, 
                    ct.value,
                    ct.converted_value,
                    tt.total_value
                FROM converted_table ct
                LEFT JOIN total_table tt 
                    ON ct.year = tt.year
            )
            SELECT
                year AS year,
                '${escapeSQL(getNameByCode(donorMapping, donor))}' AS donor,
                '${escapeSQL(getNameByCode(recipientMapping, recipient))}' AS recipient,
                CASE    
                    ${indicatorCase}
                END AS indicator,
                ${
                    unit === "value"
                        ? "converted_value"
                        : "value / total_value * 100"
                } AS value,
                ${
                        unit === "value"
                                ? `'${currency} ${prices} million'`
                                : "'% of total ODA'"
                } AS unit,
                'OECD CRS' AS source
            FROM final_table
            ORDER BY year
        `
    )

    return query.toArray().map((row) => ({
        ...row
    }));

}


