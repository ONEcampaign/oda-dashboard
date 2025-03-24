import {FileAttachment} from "observablehq:stdlib";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {name2CodeMap, getKeysByValue} from "./utils.js";


const db = await DuckDBClient.of({
    gender: FileAttachment("../data/scripts/gender.parquet"),
    current_conversion_table: FileAttachment("../data/scripts/current_conversion_table.csv"),
    constant_conversion_table: FileAttachment("../data/scripts/constant_conversion_table.csv")
});

const donorOptions = await FileAttachment("../data/settings/donors.json").json()
const recipientOptions = await FileAttachment("../data/settings/recipients.json").json()

const donorMapping = name2CodeMap(donorOptions)
const recipientMapping = name2CodeMap(recipientOptions)

export function genderQueries(
    donor,
    recipient,
    indicator,
    currency,
    prices,
    timeRange
) {

    const absolute = absoluteGenderQuery(
        donor,
        recipient,
        indicator,
        currency,
        prices,
        timeRange
    );

    const relative = relativeGenderQuery(
        donor,
        recipient,
        indicator,
        currency,
        prices,
        timeRange
    );

    return {absolute, relative};

}

async function absoluteGenderQuery(
    donor,
    recipient,
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
                    gender_code AS indicator, 
                    (value * 1.1 / 1.1) AS value
                FROM gender
                WHERE 
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND year between ${timeRange[0]} AND ${timeRange[1]}
                    AND 
                    ${
                        indicator === 3
                            ? "gender_code IN (1, 2)"
                            : `gender_code = ${indicator}`
                    }
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
                '${getKeysByValue(donorMapping, donor)}' AS donor,
                '${getKeysByValue(recipientMapping, recipient)}' AS recipient,
                CASE
                    WHEN indicator = 2 THEN 'Main focus'
                    WHEN indicator = 1 THEN 'Secondary focus'
                    WHEN indicator = 0 THEN 'Not targeted'
                END AS Indicator,
                SUM(converted_value) as Value,
                '${currency} ${prices} million' as Unit,
                'OECD Creditor Reporting System' AS Source
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
    currency,
    prices,
    timeRange
) {

    const query = await db.query(
        `
            WITH filtered AS (
                SELECT 
                    year,
                    gender_code AS indicator,
                    SUM(value * 1.1 / 1.1) AS value
                FROM gender
                WHERE 
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                    AND
                    ${
                        indicator === 3
                            ? "gender_code IN (1, 2)"
                            : `gender_code = ${indicator}`
                    }
                group by year, indicator
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
                f.year AS Year,
                '${getKeysByValue(donorMapping, donor)}' AS donor,
                '${getKeysByValue(recipientMapping, recipient)}' AS recipient,
                CASE
                    WHEN indicator = 2 THEN 'Main focus'
                    WHEN indicator = 1 THEN 'Secondary focus'
                    WHEN indicator = 0 THEN 'Not targeted'
                END AS Indicator,
                ROUND(100.0 * f.value / t.total_value, 2) AS Value,
                '% of total aid' AS Unit,
                'OECD Creditor Reporting System' AS Source
            FROM filtered f
            JOIN total t ON f.year = t.year
            ORDER BY f.year
        `
    );



    return query.toArray().map((row) => ({
        ...row
    }));

}


