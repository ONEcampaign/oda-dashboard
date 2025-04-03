import {FileAttachment} from "observablehq:stdlib";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {name2CodeMap, getNameByCode, escapeSQL} from "./utils.js";

const db = await DuckDBClient.of({
    sectors: FileAttachment("../data/scripts/sectors.parquet"),
    current_conversion_table: FileAttachment("../data/scripts/current_conversion_table.csv"),
    // constant_conversion_table: FileAttachment("../data/scripts/constant_conversion_table.csv")
});

const donorOptions = await FileAttachment("../data/analysis_tools/donors.json").json()
const donorMapping = name2CodeMap(donorOptions)

const recipientOptions = await FileAttachment("../data/analysis_tools/recipients.json").json()
const recipientMapping = name2CodeMap(recipientOptions)

const sectorsIndicators = await FileAttachment('../data/analysis_tools/sectors_indicators.json').json()

const code2Subsector = await FileAttachment("../data/analysis_tools/sub_sectors.json").json()
const subsector2Sector = await FileAttachment("../data/analysis_tools/sectors.json").json()


//  SECTORS VIEW
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


    const indicators = indicator.length > 0 ? indicator : [-1]; // use -1 or any value that won’t match real indicators

    const indicatorCase = Object.entries(sectorsIndicators)
        .map(([code, label]) => `WHEN indicator = ${code} THEN '${escapeSQL(label)}'`)
        .join("\n");

    const code2SectorCase = Object.entries(code2Subsector)
        .map(([code, subsector]) => {
            const sector = subsector2Sector[subsector] || 'Other';
            return `WHEN ${code} THEN '${escapeSQL(sector)}'`;
        })
        .join('\n');

    const sectorCaseSQL = `CASE sub_sector\n${code2SectorCase}\nEND AS sector`;

    //
    const relevantSubsectors = Object.entries(subsector2Sector)
        .filter(([, sector]) => sector === selectedSector)
        .map(([subsector]) => subsector);

    const subsectorCodes = Object.entries(code2Subsector)
        .filter(([, subsector]) => relevantSubsectors.includes(subsector))
        .map(([code]) => Number(code)); // or keep as strings depending on SQL needs

    //
    const code2SubsectorCase = Object.entries(code2Subsector)
        .filter(([, subsector]) => relevantSubsectors.includes(subsector))
        .map(([code, subsector]) => `WHEN ${code} THEN '${escapeSQL(subsector)}'`)
        .join('\n');

    const subsectorCaseSQL = `CASE sub_sector\n${code2SubsectorCase}\nEND AS 'sub_sector',`;


    const treemap = treemapSectorsQuery(
        donor,
        recipient,
        indicators,
        indicatorCase,
        sectorCaseSQL,
        currency,
        prices,
        timeRange
    );

    const selected = selectedSectorsQuery(
        donor,
        recipient,
        indicators,
        indicatorCase,
        selectedSector,
        subsectorCodes,
        subsectorCaseSQL,
        currency,
        prices,
        timeRange,
        breakdown
    )
    
    const table = tableSectorsQuery(
        donor,
        recipient,
        indicators,
        indicatorCase,
        selectedSector,
        subsectorCodes,
        subsectorCaseSQL,
        currency,
        prices,
        timeRange,
        unit
    )

    return {treemap, selected, table};

}


async function treemapSectorsQuery(
    donor,
    recipient,
    indicator,
    indicatorCase,
    sectorCaseSQL,
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
                sub_sector,
                ${
                        indicator.length === 2
                                ? "'Total ODA'"
                                : `CASE
                            ${indicatorCase} 
                        END`
                } AS indicator,
                SUM(value * 1.1 / 1.1) AS value
             FROM sectors 
             WHERE
                 donor_code IN (${donor})
                 AND recipient_code IN (${recipient})
                 AND indicator IN (${indicator})
                 AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
            GROUP BY year, donor_code, sub_sector, indicator
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
                    f.sub_sector,
                    indicator,
                    f.value * c.factor AS converted_value
                FROM filtered f
                    JOIN conversion c
                ON f.year = c.year
                    ${prices === "constant" ? "AND f.donor = c.donor" : ""}
            )
            SELECT
                '${timeRange[0]}-${timeRange[1]}' AS period,
                '${escapeSQL(getNameByCode(donorMapping, donor))}' AS donor,
                '${escapeSQL(getNameByCode(recipientMapping, recipient))}' AS recipient,
                ${sectorCaseSQL},
                indicator,
                SUM(converted_value)  AS value,
                '${currency} ${prices} million' AS unit,
                'OECD CRS, Multisystem'  AS source
            FROM joined
            GROUP BY sector, indicator
        `
    )

    return query.toArray().map((row) => ({
        ...row
    }));

}


async function selectedSectorsQuery(
    donor,
    recipient,
    indicator,
    indicatorCase,
    selectedSector,
    subsectorCodes,
    subsectorCaseSQL,
    currency,
    prices,
    timeRange,
    breakdown
) {


    const query = await db.query(
        `
            WITH filtered AS (
             SELECT
                year,
                donor_code AS donor,
                ${breakdown ? "sub_sector,": ""}
                ${
                    indicator.length === 2
                        ? "'Total ODA'"
                        : `CASE
                            ${indicatorCase} 
                        END`
                } AS indicator,
                SUM(value * 1.1 / 1.1) AS value
             FROM sectors 
             WHERE
                donor_code IN (${donor})
                AND recipient_code IN (${recipient})
                AND sub_sector IN (${subsectorCodes})
                AND indicator IN (${indicator})
                AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
            GROUP BY year, donor_code, ${breakdown ? "sub_sector,": ""} indicator
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
                    ${breakdown ? "f.sub_sector AS sub_sector," : ""}
                    indicator,
                    SUM(f.value * c.factor) AS converted_value
                FROM filtered f
                    JOIN conversion c
                ON f.year = c.year
                    ${prices === "constant" ? "AND f.donor = c.donor" : ""}
                GROUP BY f.year, ${breakdown ? "f.sub_sector," : ""} indicator
            )
            SELECT
                year AS year,
                '${escapeSQL(getNameByCode(donorMapping, donor))}' AS donor,
                '${escapeSQL(getNameByCode(recipientMapping, recipient))}' AS recipient,
                ${breakdown ? subsectorCaseSQL : ""}
                '${selectedSector}' AS sector,
                indicator,
                converted_value  AS value,
                '${currency} ${prices} million' AS unit,
                'OECD CRS, Multisystem'  AS source
            FROM joined
            ORDER BY year, ${breakdown ? "sub_sector,": ""} Sector
        `
    )

    return query.toArray().map((row) => ({
        ...row
    }));

}


async function tableSectorsQuery(
    donor,
    recipient,
    indicator,
    indicatorCase,
    selectedSector,
    subsectorCodes,
    subsectorCaseSQL,
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
                sub_sector,
                ${
                    indicator.length === 2
                        ? "'Total ODA'"
                        : `CASE
                            ${indicatorCase} 
                        END`
                } AS indicator,
                SUM(value * 1.1 / 1.1) AS value
             FROM sectors 
             WHERE
                donor_code IN (${donor})
                AND recipient_code IN (${recipient})
                AND indicator IN (${indicator})
                AND sub_sector IN (${subsectorCodes})
                AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
            GROUP BY year, sub_sector, indicator, donor_code 
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
                    f.sub_sector AS sub_sector,
                    f.indicator AS indicator,
                    SUM(f.value * 1.1 / 1.1) AS value,
                    SUM(f.value * c.factor) AS converted_value
                FROM filtered f
                    JOIN conversion c
                ON f.year = c.year
                    ${prices === "constant" ? "AND f.donor = c.donor" : ""}
                GROUP BY f.year, f.sub_sector, indicator
            ),
            total_table AS (
                SELECT
                    year,
                    SUM(value * 1.1 / 1.1) AS total_value
                 FROM sectors 
                 WHERE
                    donor_code IN (${donor})
                    AND recipient_code IN (${recipient})
                    AND sub_sector IN (${subsectorCodes})
                    AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                GROUP BY year  
            ),
            final_table AS (
                SELECT
                    ct.year,
                    ct.sub_sector,
                    ct.indicator,
                    ct.value,
                    ct.converted_value,
                    tt.total_value,
                FROM converted_table ct
                    LEFT JOIN total_table tt ON ct.year = tt.year
            )
            SELECT
                year AS year,
                '${escapeSQL(getNameByCode(donorMapping, donor))}' AS donor,
                '${escapeSQL(getNameByCode(recipientMapping, recipient))}' AS recipient, 
                ${subsectorCaseSQL}
                '${selectedSector}' AS sector,
                indicator AS indicator,
                ${
                    unit === "value"
                        ? "converted_value"
                            : "value / total_value * 100"
                }  AS value,
                ${
                    unit === "value"
                        ? `'${currency} ${prices} million'`
                        : `'% of ${selectedSector}'`
                } AS unit,
                'OECD CRS, Multisystem'  AS source
            FROM final_table
        `
    )

    return query.toArray().map((row) => ({
        ...row
    }));

}
