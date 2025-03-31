import * as Plot from "npm:@observablehq/plot";
import {table} from "npm:@observablehq/inputs";
import {html} from "npm:htl"
import {utcYear} from "npm:d3-time";
import {timeFormat} from "npm:d3-time-format";
import {sum, rollups, descending, min, max} from "npm:d3-array"
import {schemeObservable10} from "npm:d3-scale-chromatic";
import {getCurrencyLabel, formatValue} from "./utils.js";
import {customPalette, paletteFinancing, paletteRecipients, paletteSectors, paletteGender} from "./colors.js";

export function linePlot(data, mode, width,
                         {
                             selectedSector = null,
                             currency = null,
                             breakdown = null,
                             showIntlCommitment = false,
                         } = {}) {

    let arrayData = data.map((row) => ({
        ...row,
        Year: new Date(row.Year, 1, 1)
    }))

    let labelSymbol,
        yValue,
        groupVar,
        stacked = false,
        customChannels,
        customFormat,
        colorScale
    if (mode === "sectors") {

        labelSymbol = getCurrencyLabel(currency, {})
        yValue = "Value"
        groupVar = breakdown ? "Sub-sector" : "Sector"
        customChannels = {}
        customFormat = {
            stroke: true,
            x: (d) => formatYear(d)
        }
        colorScale = paletteSectors

        // const uniqueSubsectors = new Set(
        //     arrayData
        //         .filter(row => row.Sector === sectorName)
        //         .map(row => row.Subsector)
        // ).size;
        //
        // if (breakdown === "Sector" || (breakdown === "Subsector" && uniqueSubsectors === 1)) {
        //     const aggregated = rollups(
        //         arrayData,
        //         (v) => sum(v, (d) => d.Value),
        //         (d) => d.Sector
        //     );
        //
        //     aggregated.sort((a, b) => descending(a[1], b[1]));
        //
        //     colorScale = {
        //         domain: aggregated.map(([sector]) => sector),
        //         range: paletteSectors
        //     }
        // }
        //
        // arrayData = Object.values(
        //     arrayData
        //         .filter((row) => row.Sector === sectorName) // Filter rows by sectorName
        //         .reduce((acc, row) => {
        //             const key = `${row.Year}-${row[breakdown]}`; // Unique key combining year and the grouping field
        //
        //             acc[key] ??= {
        //                 Year: row.Year,
        //                 [breakdown]: row[breakdown], // Set either Sector or Subsector dynamically
        //                 Value: 0
        //             }; // Initialize if absent
        //
        //             acc[key].Value += row.Value; // Sum the values
        //
        //             return acc;
        //         }, {})
        // );
        //
        // if (breakdown === "Subsector" && uniqueSubsectors > 1) {
        //     arrayData = arrayData.sort((a, b) => a.Subsector.localeCompare(b.Subsector));
        //     colorScale = paletteSectors
        // }
    } else {
        labelSymbol = "%"
        customFormat = {
            stroke: true,
            x: (d) => formatYear(d),
            custom: (d) => `${d}%`,
            y: false
        }
        if (mode === "financing") {
            yValue = "Value"
            groupVar = "Type"
            customChannels = {
                custom: {
                    value: yValue,
                    label: "GNI Share"
                }
            }
            colorScale = paletteFinancing
        } else if (mode === "recipients") {
            yValue = "Value"
            groupVar = "Indicator"
            stacked = new Set(data.map(d => d[groupVar])).size > 1;
            customChannels = {
                custom: {
                    value: yValue,
                    label: "Share of total"
                }
            }
            colorScale = paletteRecipients
        } else if (mode === "gender") {
            yValue = "Value"
            groupVar = "Indicator"
            stacked = new Set(data.map(d => d[groupVar])).size > 1;
            customChannels = {
                custom: {
                    value: yValue,
                    label: "Share of total"
                }
            }
            colorScale = paletteGender
        }
    }


    const formatYear = timeFormat("%Y");

    return Plot.plot({
        width: width,
        ...(mode !== "sectors" && {height: width * 0.5}),
        marginTop: 25,
        marginRight: 25,
        marginBottom: 25,
        marginLeft: mode === "sectors" ? 75 : 50,
        x: {
            inset: 10,
            label: null,
            tickSize: 0,
            ticks: 5,
            grid: false,
            tickFormat: "%Y",
            tickPadding: 10,
            interval: utcYear,
        },
        y: {
            inset: 5,
            label: labelSymbol,
            tickSize: 0,
            ticks: 4,
            grid: true
        },
        color: colorScale,

        marks: [

            ...(
                stacked
                    ? [
                        Plot.areaY(arrayData, {
                            x: "Year",
                            y: yValue,
                            fill: groupVar,
                            fillOpacity: 0.85
                        }),

                        Plot.tip(arrayData,
                            Plot.pointer(
                                Plot.stackY({
                                    x: "Year",
                                    y: yValue,
                                    fill: groupVar,
                                    channels: customChannels,
                                    format: customFormat,
                                    lineHeight: 1.25,
                                    fontSize: 12
                                })
                            )
                        )

                    ]
                    : [
                        Plot.line(arrayData, {
                            x: "Year",
                            y: yValue,
                            z: groupVar,
                            stroke: groupVar,
                            curve: "monotone-x",
                            strokeWidth: 2.5
                        }),

                        Plot.tip(
                            arrayData,
                            Plot.pointer({
                                x: "Year",
                                y: yValue,
                                stroke: groupVar,
                                channels: customChannels,
                                format: customFormat,
                                lineHeight: 1.25,
                                fontSize: 12
                            })
                        )
                    ]
            ),

            // Horizontal line to show international commitment
            showIntlCommitment
                ? Plot.ruleY( [0.7],
                    {
                        stroke: customPalette.intlCommitment,
                        strokeDasharray: [5, 5],
                        strokeWidth: 1,

                    }
                )
                : null,

            showIntlCommitment
                ? Plot.text(
                    arrayData.filter(d => d.Year === min(arrayData, d => d.Year)),
                    {
                        x: "Year",
                        y: 0.7,
                        text: ["International commitment"],
                        fill: customPalette.intlCommitment,
                        textAnchor: "start",
                        dy: -10
                    }
                )
                :
                null

        ]
    });
}

export function barPlot(data, currency, mode, width) {

    const arrayData = data.map((row) => ({
        ...row,
        Year: new Date(row.Year, 1, 1)
    }))

    let fillVar, colorScale
    if (mode === "financing") {
        fillVar = "Type"
        colorScale = paletteFinancing
    } else if (mode === "recipients") {
        fillVar = "Indicator"
        colorScale = paletteRecipients
    }
    else if (mode === "gender") {
        fillVar = "Indicator"
        colorScale = paletteGender
    }

    return Plot.plot({
        width: width,
        height: width * .5,
        marginTop: 25,
        marginRight: 25,
        marginBottom: 25,
        marginLeft: 75,
        x: {
            inset: 10,
            label: null,
            tickSize: 0,
            ticks: 5,
            grid: false,
            tickFormat: "%Y",
            tickPadding: 10,
            interval: utcYear,
        },
        y: {
            inset: 5,
            label: getCurrencyLabel(currency, {}),
            tickSize: 0,
            ticks: 4,
            grid: true
        },
        color: colorScale,
        marks: [
            Plot.rectY(
                arrayData, {
                    x: "Year",
                    y: "Value",
                    fill: fillVar,
                    opacity: .85,
                }
            ),

            // Horizontal line at 0
            Plot.ruleY(
                [0], {
                    stroke: "black",
                    strokeWidth: .5
                }
            ),
            Plot.tip(
                arrayData,
                Plot.pointer(
                    Plot.stackY({
                        x: "Year",
                        y: "Value",
                        fill: fillVar,
                        lineHeight: 1.25,
                        fontSize: 12
                    })
                )
            )
        ]
    })
}

export function sparkbarTable(data, mode, {
    unit= null,
    sectorName = null,
} = {}) {

    let tableData, columnsToShow, valueColumns, colorMapping, colorColumn, maxValues
    if (mode === "sectors") {
        const allSubsectors = [
            ...new Set(data
                .filter((row) => row.Sector === sectorName)
                .map(row => row.Subsector)
                .sort((a, b) => a.localeCompare(b)))
        ];

        tableData = Object.values(
            data
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

        columnsToShow = Object.keys(tableData[0]);
        valueColumns = columnsToShow.filter(item => item !== 'Year')

        maxValues = Math.max(...valueColumns
            .flatMap(column => tableData
                .map(d => d[column]))
            .filter(v => v !== undefined)
        );

    } else {

        if (mode === "financing") {
            tableData = data
            columnsToShow = ["Year", "Type", unit]
            valueColumns = [unit];
            colorMapping = paletteFinancing
            colorColumn = "Type"
        } else if (mode === "recipients") {
            columnsToShow = ["Year", "Indicator", unit]
            valueColumns = [unit];
            colorMapping = paletteRecipients
            colorColumn = "Indicator"

            // Get unique values of the Indicator column
            const uniqueIndicators = [...new Set(data.map(d => d.Indicator))];

            // If there's only one unique Indicator, keep the original data
            if (uniqueIndicators.length > 1) {
                // Group by Year and sum the 'Value' column
                const groupedData = data.reduce((acc, d) => {
                    const key = d.Year;
                    if (!acc[key]) {
                        acc[key] = { ...d, [unit]: d[unit], Indicator: "Total" };
                    } else {
                        acc[key][unit] += d[unit]; // Sum up the Value column
                    }
                    return acc;
                }, {});

                // Convert the object back to an array
                tableData = Object.values(groupedData);
            } else {
                tableData = data
            }
        }

        maxValues = max(tableData, d => d[valueColumns]);

    }

    const getColorForType = (type) => {
        const index = colorMapping.domain.indexOf(type);
        return index !== -1 ? colorMapping.range[index] : customPalette.lightGrey; // Default color if no match
    };

    return table(tableData, {
        columns: Object.keys(tableData[0])
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
                            const fillColor = getColorForType(tableData[row][colorColumn]);
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

function sparkbar(fillColor, alignment, globalMax) {
    const range = globalMax ;

    // Ensure the range is not zero to avoid division by zero
    const safeRange = range === 0 ? 1 : range;

    return (x) => {
        // Calculate bar width as a percentage of the total range
        const barWidth = (100 * Math.abs(x - 0)) / safeRange;

        const barStyle =
            alignment === "center"
                ? `
                  position: absolute;
                  height: 80%;
                  top: 10%;
                  background: ${hex2rgb(fillColor, 0.4)};
                  width: ${barWidth}%;
                  ${
                    x >= 0
                        ? `left: 0%;`
                        : `left: ${(0 - barWidth / 100) * 100}%;`
                }
                  box-sizing: border-box;
                  overflow: hidden;
                `
                : `
                  position: absolute;
                  height: 80%;
                  top: 10%;
                  background: ${hex2rgb(fillColor, 0.4)};
                  width: ${barWidth}%;
                  ${alignment === "right" ? "right: 0;" : "left: 0;"};
                  box-sizing: border-box;
                  overflow: hidden;
                `;

        // Zero line style with full height
        const zeroLineStyle =
            alignment === "center"
                ? `
                  position: absolute;
                  height: 100%;
                  width: 1px;
                  background: ${hex2rgb(customPalette.midGrey, 0.5)};
                  left: 0%;
                  box-sizing: border-box;
                `
                : alignment === "right"
                    ? `
                      position: absolute;
                      height: 100%;
                      width: 1px;
                      background: ${hex2rgb(customPalette.midGrey, 0.5)};
                      right: 0;
                      box-sizing: border-box;
                    `
                    : `
                      position: absolute;
                      height: 100%;
                      width: 1px;
                      background: ${hex2rgb(customPalette.midGrey, 0.5)};
                      left: 0;
                      box-sizing: border-box;
                    `;

        // Text alignment based on alignment type
        const textAlignment =
            alignment === "center"
                ? "center"
                : alignment === "right"
                    ? "end" // Right-align text
                    : "start"; // Left-align text

        return html`
            <div style="
                position: relative;
                width: 100%; /* Constrain to table cell width */
                height: var(--size-l);
                background: none;
                display: flex;
                z-index: 0;
                align-items: center;
                justify-content: ${textAlignment};
                box-sizing: border-box;
                overflow: hidden;"> <!-- Prevent overflow -->
                <div style="${barStyle}"></div>
                <div style="${zeroLineStyle}"></div> <!-- Zero line -->
                <span style="
                    position: relative;
                    z-index: 1;
                    font-size: var(--size-m);
                    color: black;
                    text-shadow: .5px .5px 0 ${customPalette.lightGrey};
                    padding: 0 3px;">
                    ${formatValue(x).label}
                </span>
            </div>`;
    };
}

function hex2rgb(hex, alpha = 1) {
    // Remove the hash if present
    hex = hex.replace(/^#/, "");

    // Parse the hex into RGB components
    let r,
        g,
        b,
        a = 1; // Default alpha is 1

    if (hex.length === 6) {
        // If hex is #RRGGBB
        r = parseInt(hex.slice(0, 2), 16);
        g = parseInt(hex.slice(2, 4), 16);
        b = parseInt(hex.slice(4, 6), 16);
    } else if (hex.length === 8) {
        // If hex is #RRGGBBAA
        r = parseInt(hex.slice(0, 2), 16);
        g = parseInt(hex.slice(2, 4), 16);
        b = parseInt(hex.slice(4, 6), 16);
        a = parseInt(hex.slice(6, 8), 16) / 255; // Alpha is in [0, 255]
    } else {
        throw new Error("Invalid hex format. Use #RRGGBB or #RRGGBBAA.");
    }

    // Combine the RGBA components into a CSS string
    return `rgba(${r}, ${g}, ${b}, ${a * alpha})`;
}