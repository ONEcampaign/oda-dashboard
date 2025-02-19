import * as Plot from "npm:@observablehq/plot";
import {utcYear} from "npm:d3-time";
import {timeFormat} from "npm:d3-time-format";
import {convertUint32Array} from "./convertUintArray.js";
import {ONEPalette} from "./ONEPalette.js";
import {getCurrencyLabel} from "./getCurrencyLabel.js";
import * as d3 from "npm:d3";
import {formatValue} from "./formatValue.js";

export function linePlot(query, mode, width,
                         {
                             sectorName = null,
                             currency = null,
                             breakdown = null,
                             showIntlCommitment = false,
                         } = {}) {

    let arrayData, labelSymbol, yValue, groupVar, customChannels, customFormat, colorScale
    if (mode === "sectors") {

        arrayData = query.toArray()
            .map((row) => ({
                ...row,
                Year: new Date(row.Year, 1, 1),
                Value: convertUint32Array(row.Value, 2)
            }))

        labelSymbol = getCurrencyLabel(currency, {})
        yValue = "Value"
        groupVar = breakdown
        customChannels = {}
        customFormat = {
            stroke: true,
            x: (d) => formatYear(d)
        }
        const uniqueSubsectors = new Set(
            arrayData
                .filter(row => row.Sector === sectorName)
                .map(row => row.Subsector)
        ).size;

        if (breakdown === "Sector" || (breakdown === "Subsector" && uniqueSubsectors === 1)) {
            const aggregated = d3.rollups(
                arrayData,
                (v) => d3.sum(v, (d) => d.Value),
                (d) => d.Sector
            );

            aggregated.sort((a, b) => d3.descending(a[1], b[1]));

            colorScale = {
                domain: aggregated.map(([sector]) => sector),
                range: ["#1A9BA3", "#FF7F4C", "#081248", "#A3DAF5"]
            }
        }

        arrayData = Object.values(
            arrayData
                .filter((row) => row.Sector === sectorName) // Filter rows by sectorName
                .reduce((acc, row) => {
                    const key = `${row.Year}-${row[breakdown]}`; // Unique key combining year and the grouping field

                    acc[key] ??= {
                        Year: row.Year,
                        [breakdown]: row[breakdown], // Set either Sector or Subsector dynamically
                        Value: 0
                    }; // Initialize if absent

                    acc[key].Value += row.Value; // Sum the values

                    return acc;
                }, {})
        );

        if (breakdown === "Subsector" && uniqueSubsectors > 1) {
            arrayData = arrayData.sort((a, b) => a.Subsector.localeCompare(b.Subsector));
            colorScale = ["#1A9BA3", "#FF7F4C", "#081248", "#A3DAF5"]
        }
    } else {
        labelSymbol = "%"
        customFormat = {
            stroke: true,
            x: (d) => formatYear(d),
            custom: (d) => `${d}%`,
            y: false
        }
        if (mode === "financing") {
            yValue = "GNI Share"
            groupVar = "Type"
            customChannels = {
                custom: {
                    value: yValue,
                    label: "GNI Share"
                }
            }
            colorScale = {
                domain: ["Flow", "Grant Equivalent"],
                range: ["#9ACACD", "#17858C"]
            }
        } else if (mode === "recipients") {
            yValue = "Share of total"
            groupVar = "Indicator"
            customChannels = {
                custom: {
                    value: yValue,
                    label: "Share of total"
                }
            }
            colorScale = {
                domain: ["Bilateral", "Imputed multilateral"],
                range: ["#1A9BA3", "#FF7F4C"],
            }
        }

        arrayData = query.toArray().map((row) => ({
            ...row,
            Year: new Date(row.Year, 1, 1),
            [yValue]: convertUint32Array(row[yValue], 2)
        }));
    }


    const formatYear = timeFormat("%Y");

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
            label: labelSymbol,
            tickSize: 0,
            ticks: 4,
            grid: true
        },
        color: colorScale,

        marks: [
            Plot.line(arrayData, {
                x: "Year",
                y: yValue,
                z: groupVar,
                stroke: groupVar,
                curve: "monotone-x",
                strokeWidth: 2.5
            }),

            // Horizontal line to show international commitment
            showIntlCommitment
                ? Plot.ruleY( [0.7],
                    {
                        stroke: "#A20021",
                        strokeDasharray: [5, 5],
                        strokeWidth: 1,

                    }
                )
                : null,

            showIntlCommitment
            ? Plot.text(
                    arrayData.filter(d => d.Year === d3.min(arrayData, d => d.Year)),
                    {
                        x: "Year",
                        y: 0.7,
                        text: ["International commitment"],
                        fill: "#A20021",
                        textAnchor: "start",
                        dy: -10
                    }
                )
                :
                null,

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
    });
}

