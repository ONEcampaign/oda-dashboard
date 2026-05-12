import * as Plot from "npm:@observablehq/plot";
import {utcYear} from "npm:d3-time";
import {getCurrencyLabel} from "npm:@one-data/observable-themes/utils"
import {
    paletteFinancing,
    paletteRecipients,
    paletteTreemap,
    paletteSubsectors,
    paletteGender
} from "./colors.js";
import {plotHeight} from "./utils.js";

export function columnChart(data, currency, mode, width, {breakdown = false, scale = null}) {

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

    if (scale && scale.divisor !== 1) {
        arrayData = arrayData.map(row => ({
            ...row,
            Value: row.Value != null ? row.Value / scale.divisor : null
        }));
    }

    const suffixWord = scale?.suffix
        ? scale.suffix.charAt(0) + scale.suffix.slice(1)
        : null;
    const yAxisLabel = getCurrencyLabel(currency, { suffix: suffixWord });

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
            range: breakdown ? paletteSubsectors : [paletteTreemap.active]
        }
    } else {
        fillVar = "Indicator"
        if (mode === "recipients") {
            colorScale = paletteRecipients
        } else if (mode === "gender") {
            colorScale = paletteGender
            stackOrder = paletteGender.domain.slice().reverse()
        }
    }

    return Plot.plot({
        width: width,
        height: plotHeight(width),
        marginTop: 25,
        marginRight: 25,
        marginBottom: 25,
        marginLeft: 40,
        x: {
            inset: 5,
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
            label: yAxisLabel,
            labelArrow: false,
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
                        order: stackOrder,
                        format: {
                            x: d => d.getFullYear(),
                            y: d => d.toFixed(1),
                            fill: true,
                        },
                        lineHeight: 1.25,
                        fontSize: 12,
                        fontFamily: "'Italian Plate', Helvetica, sans-serif",
                    })
                )
            ),

            Plot.ruleY(
                [0], {
                    stroke: "black",
                    strokeWidth: .5
                }
            )
        ]
    })
}