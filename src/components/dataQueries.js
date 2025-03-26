import {FileAttachment} from "observablehq:stdlib";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {name2CodeMap, getNameByCode, generateIndicatorMap} from "./utils.js";


const db = await DuckDBClient.of({
    financing: FileAttachment("../data/scripts/financing.parquet"),
    recipients: FileAttachment("../data/scripts/recipients.parquet"),
    gender: FileAttachment("../data/scripts/gender.parquet"),
    gni_table: FileAttachment("../data/scripts/gni_table.parquet"),
    current_conversion_table: FileAttachment("../data/scripts/current_conversion_table.csv"),
    constant_conversion_table: FileAttachment("../data/scripts/constant_conversion_table.csv")
});

const donorOptions = await FileAttachment("../data/analysis_tools/donor_mapping.json").json()
const recipientOptions = await FileAttachment("../data/analysis_tools/recipient_mapping.json").json()
const indicatorOptions = await FileAttachment("../data/analysis_tools/indicators.json").json()

const donorMapping = name2CodeMap(donorOptions)
const recipientMapping = name2CodeMap(recipientOptions)



//  FINANCING VIEW
export function financingQueries(
    donor,
    indicator,
    currency,
    prices,
    timeRange
) {

    const indicatorMapping = generateIndicatorMap(indicatorOptions, "financing")

    const absolute = absoluteFinancingQuery(
        donor,
        indicator,
        indicatorMapping,
        currency,
        prices,
        timeRange
    );

    const relative = relativeFinancingQuery(
        donor,
        indicator,
        indicatorMapping,
        currency,
        prices,
        timeRange
    );

    return {absolute, relative};

}

async function absoluteFinancingQuery(
    donor,
    indicator,
    indicatorMapping,
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
                '${getNameByCode(indicatorMapping, indicator)}' AS indicator,
                CASE
                    WHEN year < 2018 THEN 'Flow'
                    WHEN year >= 2018 THEN 'Grant equivalent'
                END AS Type,
                SUM(converted_value) as Value,
                '${currency} ${prices} million' as Unit,
                'OECD DAC1' AS Source
            FROM joined
            GROUP BY year, indicator
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
    indicatorMapping,
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
                    AND indicator = (${indicator})
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
                f.year AS Year,
                '${getNameByCode(donorMapping, donor)}' AS donor,
                ${
                    indicator === indicatorMapping.get("Total ODA")
                        ? "f.value / g.gni * 100 AS Value,"
                        : "f.value / t.total_value * 100 AS Value,"
                }
                CASE 
                    WHEN f.year < 2018 THEN 'Flow'
                    WHEN f.year >= 2018 THEN 'Grant equivalent'
                END AS Type,
                ${
                    indicator === indicatorMapping.get("Total ODA")
                        ? "'% of GNI' AS Unit,"
                        : "'% of total aid' AS Unit,"
                }
                'OECD DAC1' AS Source
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



//  RECIPIENTS VIEW
export function recipientsQueries(
    donor,
    recipient,
    indicator,
    currency,
    prices,
    timeRange
) {

    const indicatorMapping = generateIndicatorMap(indicatorOptions, "recipients")

    const absolute = absoluteRecipientsQuery(
        donor,
        recipient,
        indicator,
        indicatorMapping,
        currency,
        prices,
        timeRange
    );

    const relative = relativeRecipientsQuery(
        donor,
        recipient,
        indicator,
        indicatorMapping,
        currency,
        prices,
        timeRange
    );

    return {absolute, relative};

}

async function absoluteRecipientsQuery(
    donor,
    recipient,
    indicator,
    indicatorMapping,
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
                    ${
                        indicator === indicatorMapping.get("Total ODA")
                            ? ""
                            : `AND indicator = ${indicator}`
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
                '${getNameByCode(donorMapping, donor)}' AS donor,
                '${getNameByCode(recipientMapping, recipient)}' AS recipient,
                CASE
                    WHEN indicator = 1 THEN 'Imputed multilateral'
                    WHEN indicator = 0 THEN 'Bilateral'
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
    indicatorMapping,
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
                    ${
                        indicator === indicatorMapping.get("Total ODA")
                                ? ""
                                : `AND indicator = ${indicator}`
                    }
                GROUP BY year, indicator
            ),
            total AS (
                SELECT 
                    year,
                    SUM(value * 1.1 / 1.1) AS total_value
                FROM recipients
                WHERE
                    recipient_code IN (${recipient})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                GROUP BY year
            )
            SELECT
                f.year AS Year,
                '${getNameByCode(donorMapping, donor)}' AS donor,
                '${getNameByCode(recipientMapping, recipient)}' AS recipient,
                CASE
                    WHEN indicator = 1 THEN 'Imputed multilateral'
                    WHEN indicator = 0 THEN 'Bilateral'
                END AS Indicator,
                f.value / t.total_value * 100 AS Value,
                '% of total aid' AS Unit,
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


// GENDER VIEW
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
                    indicator, 
                    (value * 1.1 / 1.1) AS value
                FROM gender
                WHERE 
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND year between ${timeRange[0]} AND ${timeRange[1]}
                    AND 
                    ${
                        indicator === 3
                            ? "indicator IN (1, 2)"
                            : `indicator = ${indicator}`
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
                '${getNameByCode(donorMapping, donor)}' AS donor,
                '${getNameByCode(recipientMapping, recipient)}' AS recipient,
                CASE
                    WHEN indicator = 2 THEN 'Main focus'
                    WHEN indicator = 1 THEN 'Secondary focus'
                    WHEN indicator = 0 THEN 'Not targeted'
                    WHEN indicator = 9 THEN 'Not screened'
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
                    indicator,
                    SUM(value * 1.1 / 1.1) AS value
                FROM gender
                WHERE 
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                    AND
                    ${
                        indicator === 3
                            ? "indicator IN (1, 2)"
                            : `indicator = ${indicator}`
                    }
                GROUP BY year, indicator
            ),
            total AS (
                SELECT 
                    year,
                    SUM(value * 1.1 / 1.1) AS total_value
                FROM gender
                WHERE
                    donor_code IN (${donorMapping.get("DAC members")}, ${donorMapping.get("non-DAC countries")})
                    AND recipient_code IN (${recipientMapping.get("Developing countries")})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                GROUP BY year
            )
            SELECT
                f.year AS Year,
                '${getNameByCode(donorMapping, donor)}' AS donor,
                '${getNameByCode(recipientMapping, recipient)}' AS recipient,
                CASE
                    WHEN indicator = 2 THEN 'Main focus'
                    WHEN indicator = 1 THEN 'Secondary focus'
                    WHEN indicator = 0 THEN 'Not targeted'
                    WHEN indicator = 9 THEN 'Not screened'
                END AS Indicator,
                f.value / t.total_value * 100 AS Value,
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


