import {FileAttachment} from "observablehq:stdlib";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {name2CodeMap, getNameByCode} from "./utils.js";

const db = await DuckDBClient.of({
    recipients: FileAttachment("../data/scripts/recipients.parquet"),
    current_conversion_table: FileAttachment("../data/scripts/current_conversion_table.csv"),
    // constant_conversion_table: FileAttachment("../data/scripts/constant_conversion_table.csv")
});

const donorOptions = await FileAttachment("../data/analysis_tools/donors.json").json()
const donorMapping = name2CodeMap(donorOptions)

const recipientOptions = await FileAttachment("../data/analysis_tools/recipients.json").json()
const recipientMapping = name2CodeMap(recipientOptions)

const recipientsIndicators = await FileAttachment('../data/analysis_tools/recipients_indicators.json').json()


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

    const indicators = indicator.length > 0 ? indicator : [-1]; // use -1 or any value that won’t match real indicators

    const indicatorCase = Object.entries(recipientsIndicators)
        .map(([code, label]) => `WHEN indicator = ${code} THEN '${label}'`)
        .join("\n");


    const absolute = absoluteRecipientsQuery(
        donor,
        recipient,
        indicators,
        indicatorCase,
        currency,
        prices,
        timeRange
    );

    const relative = relativeRecipientsQuery(
        donor,
        recipient,
        indicators,
        indicatorCase,
        currency,
        prices,
        timeRange
    );

    const table = tableRecipientsQuery(
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

async function absoluteRecipientsQuery(
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
                FROM recipients
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
                year AS Year,
                '${getNameByCode(donorMapping, donor)}' AS donor,
                '${getNameByCode(recipientMapping, recipient)}' AS recipient,
                CASE
                    ${indicatorCase}
                END AS Indicator,
                SUM(converted_value) as Value,
                '${currency} ${prices} million' as Unit,
                'OECD DAC2A' AS Source
            FROM joined
            GROUP BY year, indicator
            ORDER BY year
        `
    )

    return query.toArray().map((row) => ({
        ...row
    }));

}


async function relativeRecipientsQuery(
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
                FROM recipients
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
                FROM recipients
                WHERE
                    recipient_code IN (${recipient})
                    AND donor_code IN (${donor})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                GROUP BY year
            )
            SELECT
                f.year AS Year,
                '${getNameByCode(donorMapping, donor)}' AS donor,
                '${getNameByCode(recipientMapping, recipient)}' AS recipient,
                CASE
                    ${indicatorCase}
                END AS Indicator,
                f.value / t.total_value * 100 AS Value,
                '% of total ODA' AS Unit,
                'OECD DAC2A' AS Source
            FROM filtered f
            JOIN total t ON f.year = t.year
            ORDER BY f.year
        `
    );

    return query.toArray().map((row) => ({
        ...row
    }));

}


async function tableRecipientsQuery(
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
                FROM recipients
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
            converted_table AS (
                SELECT
                    f.year,
                    ${
                        indicator.length === 2 
                            ? "'Total ODA'"
                            : `CASE
                                    ${indicatorCase} 
                                END`
                    } AS indicator,
                    SUM(f.value) AS value,
                    SUM(f.value * c.factor) AS converted_value
                FROM filtered f
                JOIN conversion c
                    ON f.year = c.year
                        ${prices === "constant" ? "AND f.donor = c.donor" : ""}
                GROUP BY f.year ${indicator.length === 1 ? ", f.indicator" : ""}
            ),
            total_table AS (
                SELECT
                    year,
                    SUM(value * 1.1 / 1.1) AS total_value
                FROM recipients
                WHERE
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                GROUP BY year
            ),
            final_table AS (
                SELECT
                    ct.year,
                    ct.indicator,
                    ct.value,
                    ct.converted_value,
                    tt.total_value,
                FROM converted_table ct
                    LEFT JOIN total_table tt ON ct.year = tt.year
            )
            SELECT
                year AS Year,
                '${getNameByCode(donorMapping, donor)}' AS donor,
                '${getNameByCode(recipientMapping, recipient)}' AS recipient,
                indicator AS Indicator,
                ${
                    unit === "value" 
                            ? "converted_value" 
                            : "value / total_value * 100"
                } AS Value,
                ${
                    unit === "value"
                        ? `'${currency} ${prices} million'`
                        : "'% of total ODA'"
                } AS unit,
                'OECD DAC2A' AS Source
            FROM final_table
            ORDER BY year
        `
    )

    return query.toArray().map((row) => ({
        ...row
    }));

}
