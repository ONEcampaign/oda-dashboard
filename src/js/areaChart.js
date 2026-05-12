import * as Plot from "npm:@observablehq/plot";
import {utcYear} from "npm:d3-time";
import {timeFormat} from "npm:d3-time-format";
import {min, max} from "npm:d3-array"
import {
    customPalette,
    paletteFinancing,
    paletteRecipients,
    paletteGender
} from "./colors.js";
import {plotHeight} from "./utils.js";

export function areaChart(data, mode, width,
                          {
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

    const yValue = "Value"
    const formatYear = timeFormat("%Y");

    let groupVar, customChannels, colorScale, stackOrder

    const customFormat = {
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
        marginLeft: 50,
        x: {
            inset: 5,
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
            label: null,
            labelArrow: false,
            tickFormat: d => `${d}%`,
            tickSize: 0,
            ticks: 4,
            grid: true,
            ...(showIntlCommitment && {
                domain: [0, Math.max(0.75, max(arrayData, d => d[yValue]) * 1.1)]
            })
        },
        color: colorScale,

        marks: [
            showIntlCommitment
                ? Plot.ruleY([0.7], {
                    stroke: customPalette.intlCommitment,
                    strokeDasharray: [5, 5],
                    strokeWidth: 1,
                })
                : null,

            showIntlCommitment
                ? Plot.text(
                    arrayData.filter(d => d.Year === min(arrayData, d => d.Year)),
                    {
                        x: "Year",
                        y: 0.7,
                        text: ["International aid target (0.7%)"],
                        fill: customPalette.intlCommitment,
                        textAnchor: "start",
                        dy: -10,
                        fontSize: 12,
                        fontFamily: "'Italian Plate', Helvetica, sans-serif",
                    }
                )
                : null,

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
                        order: stackOrder,
                        lineHeight: 1.25,
                        fontSize: 12,
                        fontFamily: "'Italian Plate', Helvetica, sans-serif",
                    })
                )
            )
        ]
    });
}