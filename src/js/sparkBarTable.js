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

                // Sum only real numbers; a cell with no numeric value stays null (shown as "—")
                if (typeof value === "number" && !Number.isNaN(value)) {
                    acc[yearKey][group] = (acc[yearKey][group] ?? 0) + value;
                }

                return acc;
            }, {})
        );

        columnsToShow = ["Year", ...contextColumns, ...uniqueGroups];
        valueColumns = uniqueGroups;

        const numericValues = valueColumns
            .flatMap(column => tableData.map(d => d[column]))
            .filter(v => v != null);
        minValues = Math.min(...numericValues);
        maxValues = Math.max(...numericValues);
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
