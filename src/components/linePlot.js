import * as Plot from "npm:@observablehq/plot";
import {utcYear} from "npm:d3-time";
import {timeFormat} from "npm:d3-time-format";
import {ONEPalette} from "./ONEPalette.js";
import {getCurrencyLabel} from "./getCurrencyLabel.js";
import * as d3 from "npm:d3";
import {formatValue} from "./formatValue.js";

export function linePlot(query, mode, width,
                         {
                             sectorName = null,
                             currency = null,
                             breakdown = null,
                         } = {}) {

    let arrayData = query.toArray().map((row) => ({
        ...row,
        Year: new Date(row.Year, 1, 1), // Ensure the year is a Date object
    }));

    let labelSymbol, yValue, groupVar, colorScale
    if (mode === "financing") {
        labelSymbol = "%"
        yValue = "GNI Share"
        groupVar = "Type"
        colorScale = {
            domain: ["Flow", "Grant Equivalent",],
            range: [ONEPalette.blue, ONEPalette.cyan]
        }
    } else if (mode === "recipients") {
        labelSymbol = "%"
        yValue = "Share of total"
        groupVar = "Indicator"
        colorScale = {
            domain: ["Bilateral", "Imputed multilateral"],
            range: [ONEPalette.orange, ONEPalette.teal]
        }
    } else if (mode === "sectors") {

        labelSymbol = getCurrencyLabel(currency, {})
        yValue = "Value"
        groupVar = breakdown

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
                range: d3.schemeObservable10,
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
            colorScale = d3.schemeObservable10
        }
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
            tickFormat: formatYear,
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
                curve: "catmull-rom",
                strokeWidth: 2.5,
                tip: {
                    lineHeight: 1.25,
                    fontSize: 12
                },
                title: mode === "sectors"
                    ? (d) => `${d[groupVar]}, ${formatYear(d.Year)}\n${getCurrencyLabel(currency, {long: false, value: formatValue(d[yValue]).label})}`
                    : (d) => `${d[groupVar]}, ${formatYear(d.Year)}\n${yValue}: ${formatValue(d[yValue]).label}%`
            })
        ]
    });
}

