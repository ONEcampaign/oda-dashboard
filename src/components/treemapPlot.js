import { Treemap } from "./Treemap.js";
import * as d3 from "npm:d3";
import { formatValue } from "./formatValue.js";
import { getCurrencyLabel } from "./getCurrencyLabel.js";
import { Mutable } from "observablehq:stdlib";
import { schemeObservable10 } from "npm:d3-scale-chromatic";

// Declare an observable variable to hold the selected sector
export const selectedSector = Mutable("Health"); // Default selected sector

export function treemapPlot(query, width, { currency = null } = {}) {
    const arrayData = query.toArray().map((row) => ({
        ...row,
        Year: new Date(row.Year, 1, 1),
    }));

    // Aggregate data by sector and calculate total values
    const aggregated = d3.rollups(
        arrayData,
        (v) => d3.sum(v, (d) => d.Value),
        (d) => d.Sector
    );

    const formattedData = [
        { id: "root", parentId: null, Value: null },
        ...aggregated.map(([sector, value]) => ({
            id: sector,
            parentId: "root",
            Value: value,
        })),
    ];

    // Function to handle clicks and update the selectedSector observable
    const handleClick = (id) => {
        selectedSector.value = id; // Update the selected sector
    };

    // Return the Treemap visualization with the updated color scale
    return Treemap(formattedData, {
        parentId: (d) => d.parentId,
        value: (d) => d.Value,
        label: (d) =>
            d.id +
            "\n" +
            getCurrencyLabel(currency, { long: false, value: formatValue(d.Value).label }),
        group: (d) => d.id,
        width: width,
        height: 400,
        padding: 4,
        fillOpacity: (d) => selectedSector.value === d.id ? 1 : 0.25, // Highlight selected sector
        stroke: (d) => selectedSector.value === d.id ? "grey" : "white", // Add a border for selected sector
        onClick: handleClick, // Pass the click handler to the Treemap
    });
}

// This will reactively handle the selected sector value
// selectedSector; // The observable will be updated automatically when a sector is clicked
