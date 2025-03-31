import {FileAttachment} from "observablehq:stdlib";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {name2CodeMap, getNameByCode, generateIndicatorMap} from "./utils.js";


const db = await DuckDBClient.of({
    financing: FileAttachment("../data/scripts/financing.parquet"),
    recipients: FileAttachment("../data/scripts/recipients.parquet"),
    sectors: FileAttachment("../data/scripts/sectors.parquet"),
    gender: FileAttachment("../data/scripts/gender.parquet"),
    gni_table: FileAttachment("../data/scripts/gni_table.parquet"),
    current_conversion_table: FileAttachment("../data/scripts/current_conversion_table.csv"),
    // constant_conversion_table: FileAttachment("../data/scripts/constant_conversion_table.csv")
});

const donorOptions = await FileAttachment("../data/analysis_tools/donors.json").json()
const recipientOptions = await FileAttachment("../data/analysis_tools/recipients.json").json()

const donorMapping = name2CodeMap(donorOptions)
const recipientMapping = name2CodeMap(recipientOptions)

const financingIndicators = await FileAttachment('../data/analysis_tools/financing_indicators.json').json()
const recipientsIndicators = await FileAttachment('../data/analysis_tools/recipients_indicators.json').json()
const genderIndicators = await FileAttachment('../data/analysis_tools/gender_indicators.json').json()

const code2Subsector = await FileAttachment("../data/analysis_tools/sub_sectors.json").json()
const subsector2Sector = await FileAttachment("../data/analysis_tools/sectors.json").json()

//  FINANCING VIEW
export function financingQueries(
    donor,
    indicator,
    currency,
    prices,
    timeRange
) {


    const indicatorMapping = new Map(
        Object.entries(financingIndicators).map(([k, v]) => [v, Number(k)])
    );


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
                    WHEN year < 2018 THEN 'Flows'
                    WHEN year >= 2018 THEN 'Grant equivalents'
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
                f.year AS Year,
                '${getNameByCode(donorMapping, donor)}' AS donor,
                ${
                    indicator === indicatorMapping.get("Total ODA")
                        ? "f.value / g.gni * 100 AS Value,"
                        : "f.value / t.total_value * 100 AS Value,"
                }
                CASE 
                    WHEN f.year < 2018 THEN 'Flows'
                    WHEN f.year >= 2018 THEN 'Grant equivalents'
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


// RECIPIENTS VIEW
export function recipientsQueries(
    donor,
    recipient,
    indicator,
    currency,
    prices,
    timeRange
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

    return {absolute, relative};

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


//  SECTORS VIEW
export function sectorsQueries(
    donor,
    recipient,
    selectedSector,
    currency,
    prices,
    timeRange,
    breakdown
) {


    const treemap = treemapSectorQuery(
        donor,
        recipient,
        currency,
        prices,
        timeRange
    );

    const selected = selectedSectorQuery(
        donor,
        recipient,
        selectedSector,
        currency,
        prices,
        timeRange,
        breakdown
    )

    return {treemap, selected};

}


async function treemapSectorQuery(
    donor,
    recipient,
    currency,
    prices,
    timeRange
) {

    const code2SectorCase = Object.entries(code2Subsector)
        .map(([code, subsector]) => {
            const sector = subsector2Sector[subsector] || 'Other';
            return `WHEN ${code} THEN '${sector.replace(/'/g, "''")}'`;
        })
        .join('\n');

    const sectorCaseSQL = `CASE indicator\n${code2SectorCase}\nEND AS Sector`;

    const query = await db.query(
        `
            WITH filtered AS (
             SELECT
                year,
                donor_code AS donor,
                indicator,
                SUM(value * 1.1 / 1.1) AS value
             FROM sectors 
             WHERE
                 donor_code IN (${donor})
                 AND recipient_code IN (${recipient})
                 AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
            GROUP BY year, donor_code, indicator
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
                '${timeRange[0]}-${timeRange[1]}' AS period,
                '${getNameByCode(donorMapping, donor)}' AS donor,
                '${getNameByCode(recipientMapping, recipient)}' AS recipient,
                ${sectorCaseSQL},
                SUM(converted_value) as Value,
                '${currency} ${prices} million' as Unit,
                'OECD CRS' AS Source
            FROM joined
            GROUP BY sector
        `
    )

    return query.toArray().map((row) => ({
        ...row
    }));

}


async function selectedSectorQuery(
    donor,
    recipient,
    selectedSector,
    currency,
    prices,
    timeRange,
    breakdown
) {

    //
    const relevantSubsectors = Object.entries(subsector2Sector)
        .filter(([, sector]) => sector === selectedSector)
        .map(([subsector]) => subsector);

    const indicatorCodes = Object.entries(code2Subsector)
        .filter(([, subsector]) => relevantSubsectors.includes(subsector))
        .map(([code]) => Number(code)); // or keep as strings depending on SQL needs

    //
    const code2SubsectorCase = Object.entries(code2Subsector)
        .filter(([, subsector]) => relevantSubsectors.includes(subsector))
        .map(([code, subsector]) => `WHEN ${code} THEN '${subsector.replace(/'/g, "''")}'`)
        .join('\n');

    const subsectorCaseSQL = `CASE indicator\n${code2SubsectorCase}\nEND AS 'Sub-sector',`;

    const query = await db.query(
        `
            WITH filtered AS (
             SELECT
                year,
                donor_code AS donor,
                ${breakdown ? "indicator,": ""}
                SUM(value * 1.1 / 1.1) AS value
             FROM sectors 
             WHERE
                donor_code IN (${donor})
                AND recipient_code IN (${recipient})
                AND indicator IN (${indicatorCodes})
                AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
            GROUP BY year, ${breakdown ? "indicator,": ""} donor_code 
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
                    ${breakdown ? "f.indicator AS indicator," : ""}
                    SUM(f.value * c.factor) AS converted_value
                FROM filtered f
                    JOIN conversion c
                ON f.year = c.year
                    ${prices === "constant" ? "AND f.donor = c.donor" : ""}
                GROUP BY f.year ${breakdown ? ", f.indicator" : ""}
            )
            SELECT
                year AS Year,
                '${getNameByCode(donorMapping, donor)}' AS donor,
                '${getNameByCode(recipientMapping, recipient)}' AS recipient,
                ${
                    breakdown
                            ? subsectorCaseSQL
                            : `'${selectedSector}' AS Sector,`
                }
                converted_value as Value,
                '${currency} ${prices} million' as Unit,
                'OECD CRS' AS Source
            FROM joined
        `
    )

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

    const indicators = indicator.length > 0 ? indicator : [-1]; // use -1 or any value that won’t match real indicators

    const indicatorCase = Object.entries(genderIndicators)
        .map(([code, label]) => `WHEN indicator = ${code} THEN '${label}'`)
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

    return {absolute, relative};

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
                year AS Year,
                '${getNameByCode(donorMapping, donor)}' AS donor,
                '${getNameByCode(recipientMapping, recipient)}' AS recipient,
                CASE    
                    ${indicatorCase}
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
                    ${indicatorCase}
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


