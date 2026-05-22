import {table} from "npm:@observablehq/inputs";
import {min, max} from "npm:d3-array"
import {formatCurrencyValue} from "npm:@one-data/observable-themes/utils"
import {sparkbar} from "npm:@one-data/observable-themes/charts"
import {CURRENCY_OPTIONS} from "./config.js";
import {
    customPalette,
    paletteFinancing,
    paletteRecipients,
    paletteTreemap,
    paletteSubsectors,
    paletteGender
} from "./colors.js";


const CURRENCY_CODES = new Set(CURRENCY_OPTIONS.map(o => o.value));

export function sparkbarTable(data, mode, {breakdown, currency = null, scale = null, unit = null}) {
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
        minValues,
        maxValues,
        colorColumn = null,
        getColorForType = () => customPalette.lightGrey,
        colorPalette = [],
        sortPalette = null;

    if (mode === "financing") {

        tableData = arrayData;

        colorColumn = "Type";
        const colorMapping = paletteFinancing;

        getColorForType = (type) => {
            const index = colorMapping.domain.indexOf(type);
            return index !== -1 ? colorMapping.range[index] : customPalette.lightGrey;
        };

        valueColumns = ["Value"];
        columnsToShow = ["Year", "Donor", "Indicator", "Type", "Value"];

        minValues = min(tableData, d => d["Value"]);
        maxValues = max(tableData, d => d["Value"]);

    } else {

        let groupVar, contextColumns;

        if (mode === "recipients") {
            groupVar = "Indicator";
            colorPalette = paletteRecipients.range;
            contextColumns = ["Donor", "Recipient",];
            sortPalette = paletteRecipients;
        } else if (mode === "sectors") {
            groupVar = breakdown ? "Sub-sector" : "Sector";
            colorPalette = breakdown ? paletteSubsectors : [paletteTreemap.active];
            contextColumns = breakdown
                ? ["Donor", "Recipient", "Sector", "Indicator"]
                : ["Donor", "Recipient", "Indicator"];
        } else if (mode === "gender") {
            groupVar = "Indicator";
            colorPalette = paletteGender.range;
            contextColumns = ["Donor", "Recipient"];
            sortPalette = paletteGender;
        }

        const uniqueGroupsRaw = [...new Set(arrayData.map(row => row[groupVar])).values()];
        const uniqueGroups = sortPalette
            ? uniqueGroupsRaw.sort((a, b) => sortPalette.domain.indexOf(a) - sortPalette.domain.indexOf(b))
            : uniqueGroupsRaw;

        const unitKey = "Value";

        tableData = Object.values(
            arrayData.reduce((acc, row) => {
                const yearKey = row.Year;
                const group = row[groupVar];
                const value = row[unitKey];

                if (!acc[yearKey]) {
                    acc[yearKey] = {Year: yearKey};
                    contextColumns.forEach(col => { acc[yearKey][col] = row[col] ?? null; });
                    uniqueGroups.forEach(s => { acc[yearKey][s] = null; });
                }

                acc[yearKey][group] =
                    (acc[yearKey][group] || 0) + (typeof value === "number" ? value : 0);

                return acc;
            }, {})
        );

        columnsToShow = ["Year", ...contextColumns, ...uniqueGroups];
        valueColumns = uniqueGroups;

        minValues = Math.min(...valueColumns
            .flatMap(column => tableData.map(d => d[column]))
            .filter(v => v !== undefined));
        maxValues = Math.max(...valueColumns
            .flatMap(column => tableData.map(d => d[column]))
            .filter(v => v !== undefined));
    }

    const isCurrencyUnit = CURRENCY_CODES.has(currency) && unit === "value";
    const isPctUnit = unit != null && unit !== "value";
    const cellFmt = isCurrencyUnit
        ? (v) => formatCurrencyValue(v, "", scale)
        : isPctUnit
            ? (v) => v != null ? `${parseFloat(v).toFixed(2)}%` : "—"
            : null;

    return table(tableData, {
        columns: columnsToShow.filter(col => Object.prototype.hasOwnProperty.call(tableData[0], col)),
        sort: "Year",
        reverse: true,
        format: {
            Year: x => String(x),
            ...Object.fromEntries(
                valueColumns.map((column, index) => [
                    column,
                    (rowValue, row) => {
                        if (mode === "financing") {
                            return sparkbar(
                                getColorForType(tableData[row][colorColumn]),
                                "left",
                                minValues,
                                maxValues,
                                cellFmt
                            )(rowValue);
                        } else {
                            const paletteIndex = sortPalette
                                ? sortPalette.domain.indexOf(column)
                                : -1;
                            const effectiveIndex = paletteIndex !== -1 ? paletteIndex : index % colorPalette.length;
                            return sparkbar(
                                colorPalette[effectiveIndex],
                                "left",
                                minValues,
                                maxValues,
                                cellFmt
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

// export function sparkbar(fillColor, alignment, globalMax, formatFn = null) {
//     const safeRange = globalMax === 0 ? 1 : globalMax;
//
//     return (x) => {
//         const barWidth = (100 * Math.abs(x - 0)) / safeRange;
//
//         const barStyle =
//             alignment === "center"
//                 ? `
//                   position: absolute;
//                   height: 80%;
//                   top: 10%;
//                   background: ${hex2rgb(fillColor, 0.4)};
//                   width: ${barWidth}%;
//                   ${
//                     x >= 0
//                         ? `left: 0%;`
//                         : `left: ${(0 - barWidth / 100) * 100}%;`
//                 }
//                   box-sizing: border-box;
//                   overflow: hidden;
//                 `
//                 : `
//                   position: absolute;
//                   height: 90%;
//                   top: 5%;
//                   background: ${hex2rgb(fillColor, 0.4)};
//                   width: ${barWidth}%;
//                   ${alignment === "right" ? "right: 0;" : "left: 0;"};
//                   box-sizing: border-box;
//                   overflow: hidden;
//                 `;
//
//         const zeroLineStyle =
//             alignment === "center"
//                 ? `
//                   position: absolute;
//                   height: 100%;
//                   width: 1px;
//                   background: ${hex2rgb(customPalette.midGrey, 0.5)};
//                   left: 0%;
//                   box-sizing: border-box;
//                 `
//                 : alignment === "right"
//                     ? `
//                       position: absolute;
//                       height: 100%;
//                       width: 1px;
//                       background: ${hex2rgb(customPalette.midGrey, 0.5)};
//                       right: 0;
//                       box-sizing: border-box;
//                     `
//                     : `
//                       position: absolute;
//                       height: 100%;
//                       width: 1px;
//                       background: ${hex2rgb(customPalette.midGrey, 0.5)};
//                       left: 0;
//                       box-sizing: border-box;
//                     `;
//
//         const textAlignment =
//             alignment === "center"
//                 ? "center"
//                 : alignment === "right"
//                     ? "end"
//                     : "start";
//
//         return html`
//             <div style="
//                 position: relative;
//                 width: 100%;
//                 height: var(--size-l);
//                 background: none;
//                 display: flex;
//                 z-index: 0;
//                 align-items: center;
//                 justify-content: ${textAlignment};
//                 box-sizing: border-box;
//                 overflow: hidden;">
//                 <div style="${barStyle}"></div>
//                 <div style="${zeroLineStyle}"></div>
//                 <span style="
//                     position: relative;
//                     z-index: 1;
//                     font: calc(var(--table-base-font-size) * 1.25) 'Italian Plate', sans-serif;
//                     color: black;
//                     text-shadow: .5px .5px 0 ${customPalette.lightGrey};
//                     padding: 0 3px;">
//                     ${formatFn ? formatFn(x) : formatValue(x).label}
//                 </span>
//             </div>`;
//     };
// }
//
// function hex2rgb(hex, alpha = 1) {
//     hex = hex.replace(/^#/, "");
//     let r, g, b, a = 1;
//
//     if (hex.length === 6) {
//         r = parseInt(hex.slice(0, 2), 16);
//         g = parseInt(hex.slice(2, 4), 16);
//         b = parseInt(hex.slice(4, 6), 16);
//     } else if (hex.length === 8) {
//         r = parseInt(hex.slice(0, 2), 16);
//         g = parseInt(hex.slice(2, 4), 16);
//         b = parseInt(hex.slice(4, 6), 16);
//         a = parseInt(hex.slice(6, 8), 16) / 255;
//     } else {
//         throw new Error("Invalid hex format. Use #RRGGBB or #RRGGBBAA.");
//     }
//
//     return `rgba(${r}, ${g}, ${b}, ${a * alpha})`;
// }