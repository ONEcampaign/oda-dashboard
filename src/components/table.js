import * as Inputs from "npm:@observablehq/inputs";
import {schemeObservable10} from "npm:d3-scale-chromatic";
import {max} from "npm:d3-array";
import {sparkbar} from "./sparkbar.js";
import {ONEPalette} from "./ONEPalette.js";

export function table(query, mode, {
                        unit= null,
                        sectorName = null,
                    } = {}) {

    let arrayData = query.toArray()
        .map((row) => row.toJSON());

    let columnsToShow, valueColumns, colorMapping, colorColumn, maxValues
    if (mode === "sectors") {
        const allSubsectors = [
            ...new Set(arrayData
                .filter((row) => row.Sector === sectorName)
                .map(row => row.Subsector)
                .sort((a, b) => a.localeCompare(b)))
        ];

        arrayData = Object.values(
            arrayData
                .filter((row) => row.Sector === sectorName) // Filter rows by sectorName
                .reduce((acc, row) => {
                    const yearKey = row.Year; // Group by Year

                    // Initialize the year if not present in the accumulator
                    if (!acc[yearKey]) {
                        acc[yearKey] = { Year: row.Year };

                        // Initialize all subsectors for this year with null
                        allSubsectors.forEach(subsector => {
                            acc[yearKey][subsector] = null;
                        });
                    }

                    // Add the Subsector value (if exists) for this year
                    acc[yearKey][row.Subsector] = (acc[yearKey][row.Subsector] || 0) + row[unit];

                    return acc;
                }, {})
        );

        columnsToShow = Object.keys(arrayData[0]);
        valueColumns = columnsToShow.filter(item => item !== 'Year')

        maxValues = Math.max(...valueColumns
            .flatMap(column => arrayData
                .map(d => d[column]))
            .filter(v => v !== undefined)
        );

    } else {
        if (mode === "financing") {
            columnsToShow = ["Year", "Type", unit]
            valueColumns = [unit];
            colorMapping = {
                domain: ["Flow", "Grant Equivalent"],
                range: [ONEPalette.blue, ONEPalette.cyan]
            }
            colorColumn = "Type"
        } else if (mode === "recipients") {
            columnsToShow = ["Year", "Indicator", unit]
            valueColumns = [unit];
            colorMapping = {
                domain: ["Bilateral", "Imputed multilateral", "Total"],
                range: [ONEPalette.orange, ONEPalette.teal, ONEPalette.blue]
            }
            colorColumn = "Indicator"

            // Get unique values of the Indicator column
            const uniqueIndicators = [...new Set(arrayData.map(d => d.Indicator))];

            // If there's only one unique Indicator, keep the original data
            if (uniqueIndicators.length > 1) {
                // Group by Year and sum the 'Value' column
                const groupedData = arrayData.reduce((acc, d) => {
                    const key = d.Year;
                    if (!acc[key]) {
                        acc[key] = { ...d, [unit]: d[unit], Indicator: "Total" };
                    } else {
                        acc[key][unit] += d[unit]; // Sum up the Value column
                    }
                    return acc;
                }, {});

                // Convert the object back to an array
                arrayData = Object.values(groupedData);
            }
        }

        maxValues = max(arrayData, d => d[valueColumns]);

    }

    const getColorForType = (type) => {
        const index = colorMapping.domain.indexOf(type);
        return index !== -1 ? colorMapping.range[index] : ONEPalette.lightGrey; // Default color if no match
    };

    return Inputs.table(arrayData, {
        columns: Object.keys(arrayData[0])
            .filter(column => columnsToShow.includes(column)),
        sort: "Year",
        reverse: true,
        format: {
            Year: (x) => x,
            ...Object.fromEntries(
                valueColumns.map((column, index) => [
                    column,
                    (rowValue, row) => {
                        if (mode === "sectors") {
                            const colors = schemeObservable10;
                            return sparkbar(
                                colors[index % colors.length],
                                "left",
                                maxValues
                            )(rowValue);
                        } else {
                            const fillColor = getColorForType(arrayData[row][colorColumn]);
                            return sparkbar(
                                fillColor,
                                "left",
                                maxValues
                            )(rowValue);
                        }
                    }
                ])
            )
        },
        align: {
            Year: "left",
            ...Object.fromEntries(
                columnsToShow.map(column => [column, "left"])
            )
        }
    });
}

