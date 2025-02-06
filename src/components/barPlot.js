import * as Plot from "npm:@observablehq/plot";
import {utcYear} from "npm:d3-time";
import {timeFormat} from "npm:d3-time-format";
import {ONEPalette} from "./ONEPalette.js";
import {getCurrencyLabel} from "./getCurrencyLabel.js";
import {formatValue} from "./formatValue.js";

export function barPlot(query, currency, mode, width) {

    const arrayData = query.toArray()
        .map((row) => ({
            ...row,
            Year: new Date(row.Year, 1, 1)
        }))

    let fillVar, colorScale
    if (mode === "financing") {
        fillVar = "Type"
        colorScale = {
            domain: ["Flow", "Grant Equivalent",],
            range: [ONEPalette.blue, ONEPalette.cyan],
        }
    } else if (mode === "recipients") {
        fillVar = "Indicator"
        colorScale = {
            domain: ["Bilateral", "Imputed multilateral"],
            range: [ONEPalette.orange, ONEPalette.teal],
        }
    }

    const formatYear = timeFormat("%Y")

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

            Plot.rectY(arrayData, {
                    x: "Year",
                    y: "Value",
                    fill: fillVar,
                    opacity: .75,
                    tip: {
                        lineHeight: 1.25,
                        fontSize: 12
                    },
                    title: (d) => `${d[fillVar]}, ${formatYear(d.Year)}\n${getCurrencyLabel(currency, {long: false, value: formatValue(d.Value).label})}`
                }),

            // Horizontal line at 0
            Plot.ruleY([0], {
                stroke: "black",
                strokeWidth: .5
            }),

        ]
    })
}