import Flourish from "npm:@flourish/live-api"
import {sum, rollups} from "npm:d3-array"

export function convertToArrayOfArrays(data) {

    const array = data.map(row => [
            row.Sector,
            row.Sector === row.Subsector ? null : row.Subsector, // Empty subsector if it matches sector
            row.Value
        ]);

    const keys = Object.keys(array[0]);
    const arrayOfArrays = array.map(row =>
        Object.values(row).map(value => value === null ? "" : String(value))
    );
    arrayOfArrays.unshift(keys);

    return arrayOfArrays;
}

export function customColors(data) {

    const sectorTotals = rollups(
        data,
        v => sum(v, d => d.Value),
        d => d.Sector
    );
    sectorTotals.sort((a, b) => b[1] - a[1]);

    const colors = ["#1A9BA3", "#FF7F4C", "#102493", "#A3DAF5"]
    const sectorColors = sectorTotals.map((d, i) => `${d[0]}: ${colors[i % colors.length]}`);

    return sectorColors.join("\n");
}


async function loadVisualisation(baseID, containerName){

    const response = await fetch(`https://public.flourish.studio/visualisation/${baseID}/visualisation.json`);
    const visJson = await response.json();

    // Contains the bindings, the data, the state, etc.
    const options = {
        ...visJson,
        container: `#${containerName}`,
        api_key: "sxBX4HlbTrC0rYuta53XMdJ_bxwibQPFspw0BAslXDNi_CanQkN4yp_-vWpGpY89",
    }

    window.vis = new Flourish.Live(options);
}

export const vis = loadVisualisation(21615459, "flourish-treemap")

