import * as Plot from "npm:@observablehq/plot";
import {utcYear} from "npm:d3-time";
import {getCurrencyLabel} from "./getCurrencyLabel.js";

export function barPlot(data, currency, mode, width) {

    const arrayData = data.map((row) => ({
            ...row,
            Year: new Date(row.Year, 1, 1)
        }))

    let fillVar, colorScale
    if (mode === "financing") {
        fillVar = "Type"
        colorScale = {
            domain: ["Flow", "Grant Equivalent"],
            range: ["#9ACACD", "#17858C"]
        }
    } else if (mode === "recipients") {
        fillVar = "Indicator"
        colorScale = {
            domain: ["Bilateral", "Imputed multilateral"],
            range: ["#1A9BA3", "#FF7F4C"],
        }
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
                    opacity: .75,
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
                Plot.pointer({
                    x: "Year",
                    y: "Value",
                    fill: fillVar,
                    lineHeight: 1.25,
                    fontSize: 12
                })
            )

        ]
    })
}