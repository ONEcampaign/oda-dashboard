import {FileAttachment} from "observablehq:stdlib";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {name2CodeMap, getNameByCode, escapeSQL} from "./utils.js";

const db = await DuckDBClient.of({
    sectors: FileAttachment("../data/scripts/sectors.parquet"),
    current_conversion_table: FileAttachment("../data/scripts/current_conversion_table.csv"),
    constant_conversion_table: FileAttachment("../data/scripts/constant_conversion_table.csv")
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
        code2SubsectorCase,
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
        code2SubsectorCase,
        currency,
        prices,
        timeRange,
        breakdown,
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
                        ? "'Bilateral + Imputed multilateral ODA'"
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
                'OECD CRS, MultiSystem'  AS source
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
    code2SubsectorCase,
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
                        ? "'Bilateral + Imputed multilateral ODA'"
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
            ${breakdown 
                 ? `,
                    totals AS (
                        SELECT 
                            sub_sector, 
                            SUM(converted_value) AS total_value
                        FROM joined
                        GROUP BY sub_sector
                    )
                    ` 
                : ""
            }
            SELECT
                j.year AS year,
                '${escapeSQL(getNameByCode(donorMapping, donor))}' AS donor,
                '${escapeSQL(getNameByCode(recipientMapping, recipient))}' AS recipient,
                ${
                    breakdown 
                        ? `
                            CASE j.sub_sector 
                                ${code2SubsectorCase}
                            END AS 'sub_sector',
                        ` 
                        : ""
                }
                '${selectedSector}' AS sector,
                j.indicator,
                j.converted_value AS value,
                '${currency} ${prices} million' AS unit,
                'OECD CRS, MultiSystem' AS source
            FROM joined j
                ${breakdown ? "LEFT JOIN totals t ON j.sub_sector = t.sub_sector" : ""}
            ORDER BY 
                j.year, 
                ${breakdown ? "t.total_value DESC," : ""} 
                ${breakdown ? "j.sub_sector," : ""}
                sector
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
    code2SubsectorCase,
    currency,
    prices,
    timeRange,
    breakdown,
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
                        ? "'Bilateral + Imputed multilateral ODA'"
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
                    ${breakdown ? "f.sub_sector AS sub_sector," : ""}
                    f.indicator AS indicator,
                    SUM(f.value * 1.1 / 1.1) AS value,
                    SUM(f.value * c.factor) AS converted_value
                FROM filtered f
                    JOIN conversion c
                ON f.year = c.year
                    ${prices === "constant" ? "AND f.donor = c.donor" : ""}
                GROUP BY f.year, ${breakdown ? "f.sub_sector," : ""} indicator
            ),
            ${
                breakdown 
                    ? `
                        totals_by_subsector AS (
                            SELECT 
                                sub_sector, 
                                SUM(converted_value) AS total_subsector_value
                            FROM converted_table
                            GROUP BY sub_sector
                        ),
                    ` 
                    : 
                        ""
            }
            total_table AS (
                SELECT
                    year,
                    SUM(value * 1.1 / 1.1) AS total_value
                FROM sectors 
                WHERE
                   donor_code IN (${donor})
                   AND recipient_code IN (${recipient})
                   AND year BETWEEN ${timeRange[0]} AND ${timeRange[1]}
                   ${
                        unit === "pct_sector" 
                            ? `AND sub_sector IN (${subsectorCodes})`
                            : `AND indicator IN (${indicator})`
                   }
                GROUP BY year  
            ),
            final_table AS (
                SELECT
                    ct.year,
                    ${breakdown ? "ct.sub_sector," : ""}
                        ct.indicator,
                    ct.value,
                    ct.converted_value,
                    tt.total_value
                    ${breakdown ? ", ts.total_subsector_value" : ""}
                FROM converted_table ct
                    LEFT JOIN total_table tt ON ct.year = tt.year
                    ${breakdown ? "LEFT JOIN totals_by_subsector ts ON ct.sub_sector = ts.sub_sector" : ""}
            )
            SELECT
                year AS year,
                '${escapeSQL(getNameByCode(donorMapping, donor))}' AS donor,
                '${escapeSQL(getNameByCode(recipientMapping, recipient))}' AS recipient,
                ${
                    breakdown
                            ? `
                        CASE sub_sector 
                            ${code2SubsectorCase}
                        END AS 'sub_sector',
                    `
                            : ""
                }
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
                'OECD CRS, MultiSystem'  AS source
            FROM final_table
            ORDER BY
                ${breakdown ? "total_subsector_value DESC," : ""}
                year,
                ${breakdown ? "sub_sector," : ""} indicator
        `
    )

    return query.toArray().map((row) => ({
        ...row
    }));

}
