import * as Plot from "npm:@observablehq/plot";
import {table} from "npm:@observablehq/inputs";
import {html} from "npm:htl"
import {utcYear} from "npm:d3-time";
import {timeFormat} from "npm:d3-time-format";
import {min, max} from "npm:d3-array"
import {getCurrencyLabel, formatValue} from "./utils.js";
import {customPalette, paletteFinancing, paletteRecipients, colorSector, paletteSubsectors, paletteGender} from "./colors.js";

export function linePlot(data, mode, width,
                         {
                             selectedSector = null,
                             currency = null,
                             breakdown = null,
                             GNIShare = false,
                             showIntlCommitment = false,
                         } = {}) {

    let arrayData = data.map((row) => {
        const formattedRow = {};
        for (const [key, value] of Object.entries({
            ...row,
            year: new Date(row.year, 1, 1)
        })) {
            const formattedKey = key
                .replace(/_/g, "-")
                .replace(/^./, char => char.toUpperCase());
            formattedRow[formattedKey] = value;
        }
        return formattedRow;
    });

    let labelSymbol,
        yValue,
        groupVar,
        stacked = false,
        customChannels,
        customFormat,
        colorScale,
        stackOrder

    yValue = "Value"
    labelSymbol = "%"
    customFormat = {
        stroke: true,
        x: (d) => formatYear(d),
        custom: (d) => `${d.toFixed(2)}%`,
        y: false
    }
    if (mode === "financing") {

        groupVar = "Type"
        customChannels = {
            custom: {
                value: yValue,
                label: GNIShare ? "GNI Share" : "Share of total"
            }
        }
        colorScale = paletteFinancing
        stacked = false
    } else {
        groupVar = "Indicator"
        customChannels = {
            custom: {
                value: yValue,
                label: "Share of total"
            }
        }
        if (mode === "recipients") {
            colorScale = paletteRecipients
            stacked = new Set(arrayData.map(d => d[groupVar])).size > 1;
        } else if (mode === "gender") {
            colorScale = paletteGender
            stacked = true
            stackOrder = [ ...new Set(arrayData.map(d => d[groupVar]))].slice().reverse()
        }
    }


    const formatYear = timeFormat("%Y");

    return Plot.plot({
        width: width,
        height: width * 0.5,
        marginTop: 25,
        marginRight: 25,
        marginBottom: 25,
        marginLeft: 50,
        x: {
            inset: 10,
            label: null,
            tickSize: 0,
            ticks: 5,
            grid: false,
            tickFormat: "%Y",
            tickPadding: 10,
            interval: utcYear
        },
        y: {
            inset: 5,
            label: labelSymbol,
            tickSize: 0,
            ticks: 4,
            grid: true,
            ...(showIntlCommitment && {
                domain: [0, Math.max(0.75, max(arrayData, d => d[yValue]) * 1.1)]
            })
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
                            fillOpacity: 0.85,
                            order: stackOrder
                        }),

                        Plot.tip(arrayData,
                            Plot.pointerX(
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
                ? Plot.ruleY([0.7],
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

export function barPlot(data, currency, mode, width, {breakdown = false}) {

    let arrayData = data.map((row) => {
        const formattedRow = {};
        for (const [key, value] of Object.entries({
            ...row,
            year: new Date(row.year, 1, 1)
        })) {
            const formattedKey = key
                .replace(/_/g, "-")
                .replace(/^./, char => char.toUpperCase());
            formattedRow[formattedKey] = value;
        }
        return formattedRow;
    });

    let fillVar, colorScale, stackOrder
    if (mode === "financing") {
        fillVar = "Type"
        colorScale = paletteFinancing
    } else if (mode === "sectors") {

        fillVar = breakdown ? "Sub-sector" : "Sector"
        const uniqueGroups = [
            ...new Set(arrayData.map(row => row[fillVar])).values()
        ]
        colorScale = {
            domain: uniqueGroups,
            range: breakdown ? paletteSubsectors : [colorSector]
        }
    } else {
        fillVar = "Indicator"
        if (mode === "recipients") {
            colorScale = paletteRecipients
        } else if (mode === "gender") {
            colorScale = paletteGender
            stackOrder = [ ...new Set(arrayData.map(d => d[fillVar]))].slice().reverse()
        }
    }

    return Plot.plot({
        width: width,
        ...(mode !== "sectors" && {height: width * 0.5}),
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
                    order: stackOrder,
                    opacity: .85
                }
            ),

            Plot.tip(arrayData,
                Plot.pointerX(
                    Plot.stackY({
                        x: "Year",
                        y: "Value",
                        fill: fillVar,
                        lineHeight: 1.25,
                        fontSize: 12
                    })
                )
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

export function sparkbarTable(data, mode, {breakdown}) {
    if (!data || data.length === 0) {
        return table([], {columns: []});
    }

    let arrayData = data.map((row) => {
        const formattedRow = {};
        for (const [key, value] of Object.entries(row)) {
            const formattedKey = key
                .replace(/_/g, "-")
                .replace(/^./, char => char.toUpperCase());
            formattedRow[formattedKey] = value;
        }
        return formattedRow;
    });

    let tableData,
        columnsToShow,
        valueColumns,
        maxValues,
        getColorForType = () => customPalette.lightGrey, // default fallback
        colorPalette = []; // default fallback


    if (mode === "financing" || mode === "recipients") {

        tableData = arrayData;

        let colorColumn,
            colorMapping;

        if (mode === "financing") {
            colorColumn = "Type";
            colorMapping = paletteFinancing;
        } else {
            colorColumn = "Indicator";
            colorMapping = paletteRecipients;
        }

        getColorForType = (type) => {
            const index = colorMapping.domain.indexOf(type);
            return index !== -1 ? colorMapping.range[index] : customPalette.lightGrey;
        };

        valueColumns = ["Value"];
        columnsToShow = ["Year", colorColumn, valueColumns[0]];

        maxValues = max(tableData, d => d[valueColumns]);

    } else {

        let groupVar

        if (mode === "sectors") {
            groupVar = breakdown ? "Sub-sector" : "Sector";
            colorPalette = breakdown ? paletteSubsectors : [colorSector];
        } else if (mode === "gender") {
            groupVar = "Indicator";
            colorPalette = paletteGender.range;
        }

        const uniqueGroups = [...new Set(arrayData.map(row => row[groupVar])).values()];

        const unitKey = "Value";

        tableData = Object.values(
            arrayData.reduce((acc, row) => {
                const yearKey = row.Year;
                const group = row[groupVar];
                const value = row[unitKey];

                if (!acc[yearKey]) {
                    acc[yearKey] = {Year: yearKey};
                    uniqueGroups.forEach(s => {
                        acc[yearKey][s] = null;
                    });
                }

                acc[yearKey][group] =
                    (acc[yearKey][group] || 0) + (typeof value === "number" ? value : 0);

                return acc;
            }, {})
        );

        columnsToShow = Object.keys(tableData[0]);
        valueColumns = columnsToShow.filter(item => item !== "Year");

        maxValues = Math.max(...valueColumns
            .flatMap(column => tableData.map(d => d[column]))
            .filter(v => v !== undefined));
    }

    return table(tableData, {
        columns: Object.keys(tableData[0]).filter(column => columnsToShow.includes(column)),
        sort: "Year",
        reverse: true,
        format: {
            Year: x => String(x),
            ...Object.fromEntries(
                valueColumns.map((column, index) => [
                    column,
                    (rowValue, row) => {
                        if (mode === "financing" || mode === "recipients") {
                            return sparkbar(
                                getColorForType(tableData[row][columnsToShow[1]]),
                                "left",
                                maxValues
                            )(rowValue);
                        } else {
                            return sparkbar(
                                colorPalette[index % colorPalette.length],
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
            ...Object.fromEntries(columnsToShow.map(column => [column, "left"]))
        }
    });
}


function sparkbar(fillColor, alignment, globalMax) {
    const range = globalMax;

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