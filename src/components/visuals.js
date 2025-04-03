import * as Plot from "npm:@observablehq/plot";
import {table} from "npm:@observablehq/inputs";
import {html} from "npm:htl"
import {utcYear} from "npm:d3-time";
import {timeFormat, utcFormat} from "npm:d3-time-format";
import {min, max} from "npm:d3-array"
import {getCurrencyLabel, formatValue} from "./utils.js";
import {customPalette, paletteFinancing, paletteRecipients, paletteSectors, paletteGender} from "./colors.js";

export function linePlot(data, mode, width,
                         {
                             selectedSector = null,
                             currency = null,
                             breakdown = null,
                             GNIShare = false,
                             showIntlCommitment = false,
                         } = {}) {

    let arrayData = data.map((row) => ({
        ...row,
        year: new Date(row.year, 1, 1)
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
        yValue = "value"
        groupVar = breakdown ? "sub_sector" : "sector"
        customChannels = {}
        customFormat = {
            stroke: true,
            x: (d) => formatYear(d)
        }

        if (breakdown) {
            const uniqueSubsectors = [
                ...new Set(data.map(row => row["sub_sector"])).values()
            ].sort((a, b) => a.localeCompare(b));

            colorScale = {
                domain: uniqueSubsectors,
                range: paletteSectors
            }
        } else {
            colorScale = {
                domain: [selectedSector],
                range: [paletteSectors[0]]
            }
        }

    } else {
        labelSymbol = "%"
        customFormat = {
            stroke: true,
            x: (d) => formatYear(d),
            custom: (d) => `${d.toFixed(2)}%`,
            y: false
        }
        if (mode === "financing") {
            yValue = "value"
            groupVar = "type"
            customChannels = {
                custom: {
                    value: yValue,
                    label: GNIShare ? "GNI Share" : "Share of total"
                }
            }
            colorScale = paletteFinancing
        } else if (mode === "recipients") {
            yValue = "value"
            groupVar = "indicator"
            stacked = new Set(data.map(d => d[groupVar])).size > 1;
            customChannels = {
                custom: {
                    value: yValue,
                    label: "Share of total"
                }
            }
            colorScale = paletteRecipients
        } else if (mode === "gender") {
            yValue = "value"
            groupVar = "indicator"
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
                stacked || breakdown
                    ? [
                        Plot.areaY(arrayData, {
                            x: "year",
                            y: yValue,
                            fill: groupVar,
                            fillOpacity: 0.85
                        }),

                        Plot.tip(arrayData,
                            Plot.pointer(
                                Plot.stackY({
                                    x: "year",
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
                            x: "year",
                            y: yValue,
                            z: groupVar,
                            stroke: groupVar,
                            curve: "monotone-x",
                            strokeWidth: 2.5
                        }),

                        Plot.tip(
                            arrayData,
                            Plot.pointer({
                                x: "year",
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
                    arrayData.filter(d => d.year === min(arrayData, d => d.year)),
                    {
                        x: "year",
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
        year: new Date(row.year, 1, 1)
    }))

    let fillVar, colorScale
    if (mode === "financing") {
        fillVar = "type"
        colorScale = paletteFinancing
    } else if (mode === "recipients") {
        fillVar = "indicator"
        colorScale = paletteRecipients
    }
    else if (mode === "gender") {
        fillVar = "indicator"
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
                    x: "year",
                    y: "value",
                    fill: fillVar,
                    opacity: .85,
                    tip: {
                        lineHeight: 1.25,
                        fontSize: 12,
                        channels: {
                            year: d => utcFormat("%Y")(d.year),
                        }
                    }
                }
            ),

            // Horizontal line at 0
            Plot.ruleY(
                [0], {
                    stroke: "black",
                    strokeWidth: .5
                }
            )
        ]
    })
}

export function sparkbarTable(data, mode) {

    let tableData,
        columnsToShow,
        valueColumns,
        colorMapping,
        colorColumn,
        maxValues
    if (mode === "sectors") {

        const uniqueSubsectors = [
            ...new Set(data.map(row => row["sub_sector"])).values()
        ].sort((a, b) => a.localeCompare(b));


        const unitKey = "value"; // make sure this matches actual key in the data

        tableData = Object.values(
            data.reduce((acc, row) => {
                const yearKey = row.year;
                const subsector = row["sub_sector"];
                const value = row[unitKey];

                if (!acc[yearKey]) {
                    acc[yearKey] = { year: yearKey };
                    uniqueSubsectors.forEach(s => {
                        acc[yearKey][s] = null;
                    });
                }

                acc[yearKey][subsector] =
                    (acc[yearKey][subsector] || 0) + (typeof value === "number" ? value : 0);

                return acc;
            }, {})
        );


        columnsToShow = Object.keys(tableData[0]);
        valueColumns = columnsToShow.filter(item => item !== "year")

        maxValues = Math.max(...valueColumns
            .flatMap(column => tableData
                .map(d => d[column]))
            .filter(v => v !== undefined)
        );

    } else {

        if (mode === "financing") {
            colorMapping = paletteFinancing
            colorColumn = "type"
        } else if (mode === "recipients") {
            colorMapping = paletteRecipients
            colorColumn = "indicator"
        } else if (mode === "gender") {
            colorMapping = paletteGender
            colorColumn = "indicator"
        }

        tableData = data
        valueColumns = ["value"];
        columnsToShow = ["year", colorColumn, valueColumns[0]]

        maxValues = max(tableData, d => d[valueColumns]);

    }

    const getColorForType = (type) => {
        const index = colorMapping.domain.indexOf(type);
        return index !== -1 ? colorMapping.range[index] : customPalette.lightGrey; // Default color if no match
    };

    return table(tableData, {
        columns: Object.keys(tableData[0])
            .filter(column => columnsToShow.includes(column)),
        sort: "year",
        reverse: true,
        format: {
            year: (x) => x,
            ...Object.fromEntries(
                valueColumns.map((column, index) => [
                    column,
                    (rowValue, row) => {
                        if (mode === "sectors") {
                            const colors = paletteSectors;
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
            year: "left",
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