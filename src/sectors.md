```js 
import {DuckDBClient} from "npm:@observablehq/duckdb";

import {setCustomColors} from "./components/colors.js"
import {formatString, getCurrencyLabel, convertUint32Array} from "./components/utils.js";

import {uniqueValuesSectors} from "./components/uniqueValuesSectors.js";
import {rangeInput} from "./components/rangeInput.js";

import {convertToArrayOfArrays, customColors, vis} from "./components/flourish.js"
import {linePlot, sparkbarTable} from "./components/visuals.js";

import {treemapPlot, selectedSector} from "./components/Treemap.js"

import {downloadPNG, downloadXLSX} from './components/downloads.js';
```

```js
setCustomColors();
```

```js
const db = DuckDBClient.of({
    sectors: FileAttachment("./data/scripts/sectors.parquet")
});
```

```js
// USER INPUTS
// Donor
const donorSectorsInput = Inputs.select(
    uniqueValuesSectors.donors,
    {
        label: "Donor",
        value: "DAC Countries, Total",
        sort: true
    })
const donorSectors = Generators.input(donorSectorsInput);

// Recipient
const recipientSectorsInput = Inputs.select(
    uniqueValuesSectors.recipients,
    {
        label: "Recipient",
        value: "Developing Countries, Total",
        sort: true
    })
const recipientSectors = Generators.input(recipientSectorsInput);

// Indicator
const indicatorSectorsInput = Inputs.select(
    uniqueValuesSectors.indicators,
    {
        label: "Indicator",
        value: "Total",
        sort: true
    })
const indicatorSectors = Generators.input(indicatorSectorsInput);

// Currency
const currencySectorsInput = Inputs.select(
    uniqueValuesSectors.currencies,
    {
        label: "Currency",
        value: "US Dollars",
        sort: true
    })
const currencySectors = Generators.input(currencySectorsInput);

// Prices
const pricesSectorsInput = Inputs.radio(
    uniqueValuesSectors.prices,
    {
        label: "Prices",
        value: "Constant"
    }
)
const pricesSectors = Generators.input(pricesSectorsInput)

// Year
const timeRangeSectorsInput = rangeInput(
    {
        min: uniqueValuesSectors.timeRange[0],
        max: uniqueValuesSectors.timeRange[1],
        step: 1,
        value: [
            uniqueValuesSectors.timeRange[0],
            uniqueValuesSectors.timeRange[1]
        ],
        label: "Time range",
        enableTextInput: true
    })
const timeRangeSectors = Generators.input(timeRangeSectorsInput)

// Breakdown
const breakdownSectorsInput = Inputs.toggle(
    {
        label: "Sector breakdown",
        value: "Sector",
        values: ["Subsector", "Sector"]
    }
)
const breakdownSectors = Generators.input(breakdownSectorsInput)

// Unit
const unitSectorsInput = Inputs.select(
    new Map(
        [
            [`Million ${currencySectorsInput.value}`, "Value"],
            ["GNI Share", "GNI Share"],
            ["Share of total", "Share of total"],
            ["Share of indicator", "Share of indicator"]
        ]
    ),
    {
        label: "Unit",
        value: "Value"
    }
)
const unitSectors = Generators.input(unitSectorsInput)
```

```js
// DATA QUERY
const querySectorsString = `
SELECT 
    year AS Year,
    "Donor Name" AS Donor,
    "Recipient Name" AS Recipient,
    Indicator,
    Sector,
    Subsector,
    value AS Value,
    share_of_total AS "Share of total",
    share_of_indicator AS "Share of indicator",
    "GNI Share",
    Currency,
    Prices
FROM sectors
WHERE 
    Year >= ? AND 
    Year <= ? AND
    Donor = ? AND 
    Recipient = ? AND
    Currency = ? AND 
    prices = ? AND
    (
        (? = 'Total' AND Indicator != 'Total') 
        OR (? != 'Total' AND Indicator = ?)
    );
`;

const querySectorsParams = [
    timeRangeSectors[0],
    timeRangeSectors[1],
    donorSectors,
    recipientSectors,
    currencySectors,
    pricesSectors,
    indicatorSectors,
    indicatorSectors,
    indicatorSectors
];

const querySectors = await db.query(querySectorsString, querySectorsParams);

const dataSectors = querySectors.toArray()
    .map((row) => ({
        ...row,
        ["Value"]: convertUint32Array(row["Value"]),
        ["GNI Share"]: convertUint32Array(row["GNI Share"]),
        ["Share of total"]: convertUint32Array(row["Share of total"]),
        ["Share of indicator"]: convertUint32Array(row["Share of indicator"])
    }))
```

```js
const moreSettings = Mutable(false)
const showMoreSettings = () => {
    moreSettings.value = !moreSettings.value;
    if (moreSettings.value) {
        document.querySelector(".settings-button").classList.add("active")
        document.querySelector(".settings-group:last-of-type").classList.remove("hidden")
    } else {
        document.querySelector(".settings-button").classList.remove("active")
        document.querySelector(".settings-group:last-of-type").classList.add("hidden")
    }
};
```

```js
const showMoreButton = Inputs.button(moreSettings ? "Show less" : "Show more", {
    reduce: showMoreSettings 
});
showMoreButton.addEventListener("submit", event => event.preventDefault());
```

```js
// async function updateVisualisation() {
//    
//     // Update the Flourish visualisation with data
//     window.vis.update({
//         "data": {
//             "data": convertToArrayOfArrays(dataSectors)
//         },
//         "bindings": {
//             "data": {
//                 "nest_columns": [
//                     0,
//                     1
//                 ],
//                 "popup_metadata": [],
//                 "size_columns": [
//                     2
//                 ]
//             }
//         },
//         "state": {
//             ...window.vis.state,
//             "color": {
//                 "categorical_custom_palette": customColors(dataSectors)
//             },
//             "size_by_number_formatter": {
//                 "prefix": getCurrencyLabel(currencySectors, {preffixOnly: true}),
//                 "suffix": " M"
//             }
//
//         },
//         "metadata": {
//             "data": {
//                 "0": {
//                     "type_id": "string$arbitrary_string",
//                     "type": "string"
//                 },
//                 "1": {
//                     "type_id": "string$arbitrary_string",
//                     "type": "string"
//                 },
//                 "2": {
//                     "type_id": "number$none_point",
//                     "type": "number",
//                     "output_format_id": "number$comma_point"
//                 }
//             }
//         }
//     });
// }
//
// updateVisualisation();
```


<div class="title-container" xmlns="http://www.w3.org/1999/html">
    <div class="title-logo">
        <a href="https://data.one.org/" target="_blank">
            <img src="./ONE-logo-black.png" alt="A black circle with ONE written in white thick letters."/>
        </a>
    </div>
    <h1 class="title-text">
        ODA Dashboard
    </h1>
</div>

<div class="header card">
    <a class="view-button" href="./">
        Financing
    </a>
    <a class="view-button" href="./recipients">
        Recipients
    </a>
    <a class="view-button active" href="./sectors">
        Sectors
    </a>
    <a class="view-button" href="./gender">
        Gender
    </a>
</div>

<div class="settings card">
    <div class="settings-group">
        ${donorSectorsInput}
        ${recipientSectorsInput}
    </div>
    <div class="settings-group">
        ${currencySectorsInput}
        ${indicatorSectorsInput}
    </div>
    <div class="settings-button">
        ${showMoreButton}
    </div>
    <div class="settings-group hidden">
        ${pricesSectorsInput}
        ${timeRangeSectorsInput}
    </div>
</div>
<div class="grid grid-cols-2">
    <div class="card">
        <div class="plot-container" id="treemap-sectors">
            <h2 class="plot-title">
                ${formatString(`ODA to ${recipientSectors} from ${donorSectors} by sector`)}
            </h2>
            <div class="plot-subtitle-panel">
                ${
                    indicatorSectors == "Total"
                    ? html`<h3 class="plot-subtitle">Bilateral and imputed multilateral, ${timeRangeSectors[0] === timeRangeSectors[1] ? timeRangeSectors[0] : `${timeRangeSectors[0]}-${timeRangeSectors[1]}`}</h3>`
                    : html`<h3 class="plot-subtitle">${indicatorSectors}, ${timeRangeSectors[0] === timeRangeSectors[1] ? timeRangeSectors[0] : `${timeRangeSectors[0]}-${timeRangeSectors[1]}`}</h3>`
                }
            </div>
            ${
                resize(
                    (width) => treemapPlot(dataSectors, width, {currency: currencySectors})
                )
            }
            <div class="bottom-panel">
                <div class="text-section">
                    <p class="plot-source">Source: OECD DAC Creditor Reporting System database.</p>
                    <p class="plot-note">ODA values in million ${pricesSectors} ${currencySectors}.</p>
                </div>
                <div class="logo-section">
                    <a href="https://data.one.org/" target="_blank">
                        <img src="./ONE-logo-black.png" alt="A black circle with ONE written in white thick letters."/>
                    </a>
                </div>
            </div>
        </div>
        <div class="download-panel">
            ${
                Inputs.button(
                    "Download plot", {
                        reduce: () => downloadPNG(
                            "treemap-sectors",
                            formatString(`ODA to ${recipientSectors} from ${donorSectors} by sector`, {fileMode: true})
                        )
                    }
                )
            }
        </div>
    </div>
    <div class="card">
        <div class="plot-container" id="lines-sectors">
            <h2 class="plot-title">
                ${formatString(`ODA to ${recipientSectors} from ${donorSectors}`)}
            </h2>
            <div class="plot-subtitle-panel">
                ${
                    indicatorSectors == "Total"
                    ? html`<h3 class="plot-subtitle">${selectedSector}, bilateral and imputed multilateral</h3>`
                    : html`<h3 class="plot-subtitle">${selectedSector}, ${indicatorSectors}</h3>`
                }
                ${breakdownSectorsInput}
            </div>
            ${
                resize(
                    (width) => linePlot(
                        dataSectors,
                        "sectors",
                        width, {
                            sectorName: selectedSector,
                            currency: currencySectors,
                            breakdown: breakdownSectors
                        }
                    )
                )
            }
            <div class="bottom-panel">
                <div class="text-section">
                    <p class="plot-source">Source: OECD DAC Creditor Reporting System database.</p>
                    <p class="plot-note">ODA values in million ${pricesSectors} ${currencySectors}.</p>
                </div>
                <div class="logo-section">
                    <a href="https://data.one.org/" target="_blank">
                        <img src="./ONE-logo-black.png" alt="A black circle with ONE written in white thick letters."/>
                    </a>
                </div>
            </div>
        </div>
        <div class="download-panel">
            ${
                Inputs.button(
                    "Download plot", {
                        reduce: () => downloadPNG(
                            "lines-sectors",
                            formatString(`ODA to ${recipientSectors} from ${donorSectors} ${selectedSector} ${breakdownSectors === "Sector" ? "total" : "breakdown"}`, {fileMode: true})
                        )
                    }
                )
            }
        </div>
    </div>
</div>
<div class="card">
    <div class="plot-container">
        <h2 class="table-title">
            ${formatString(`ODA to ${recipientSectors} from ${donorSectors}, ${indicatorSectors}`)}
        </h2>
        <div class="table-subtitle-panel">
            ${
                indicatorSectors == "Total"
                ? html`<h3 class="table-subtitle">Breakdown of ${selectedSector}, bilateral and imputed multilateral</h3>`
                : html`<h3 class="table-subtitle">Breakdown of ${selectedSector}, ${indicatorSectors}</h3>`
            }
            ${unitSectorsInput}
        </div>
        ${sparkbarTable(dataSectors, "sectors", {unit: unitSectors, sectorName: selectedSector})}
        <div class="bottom-panel">
            <div class="text-section">
                <p class="plot-source">Source: OECD DAC Creditor Reporting System database.</p>
                <p class="plot-note">ODA values in million ${pricesSectors} ${currencySectors}. GNI share refers to the Gross National Income of ${formatString(recipientSectors)}.</p>
            </div>
            <div class="logo-section">
                <a href="https://data.one.org/" target="_blank">
                    <img src="./ONE-logo-black.png" alt="A black circle with ONE written in white thick letters."/>
                </a>
            </div>
        </div>
    </div>
    <div class="download-panel">
        ${
            Inputs.button(
                "Download data", {
                    reduce: () => downloadXLSX(
                        dataSectors,
                        formatString(`ODA to ${recipientSectors} from ${donorSectors} by sector`, {fileMode: true})
                    )
                }
            )
        }
    </div>
</div>
