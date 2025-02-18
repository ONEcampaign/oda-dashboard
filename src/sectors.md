```js 
import {DuckDBClient} from "npm:@observablehq/duckdb";

import {setCustomColors} from "./components/setCustomColors.js";
import {formatString} from "./components/formatString.js";
import {getCurrencyLabel} from "./components/getCurrencyLabel.js";

import {uniqueValuesSectors} from "./components/uniqueValuesSectors.js";
import {rangeInput} from "./components/rangeInput.js";

import {linePlot} from "./components/linePlot.js";
import {table} from "./components/table.js";

import {downloadPNG} from './components/downloadPNG.js';
import {downloadXLSX} from "./components/downloadXLSX.js";
```

```js
setCustomColors();
```

```js
const db = DuckDBClient.of({
    sectors: FileAttachment("./data/sectors.parquet")
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
const breakdownSectorsInput = Inputs.radio(
    new Map([
        ["Total", "Sector"],
        ["Breakdown", "Subsector"]
    ]),
    {
        value: "Sector"
    }
)
const breakdownSectors = Generators.input(breakdownSectorsInput)

// Unit
const unitSectorsInput = Inputs.radio(
    ["Value", "Share of total", "Share of indicator", "GNI Share"],
    {
        label: null,
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
import {convertToArrayOfArrays, customColors} from "./components/flourishTreemap.js"

convertToArrayOfArrays(querySectors)

async function updateVisualisation() {
    
    console.log("Vis: ", window.vis)
    
    // Update the Flourish visualisation with data
    window.vis.update({
        "data": { 
            "data":  convertToArrayOfArrays(querySectors)
        },
        "bindings": {
            "data": {
                "nest_columns": [
                    0,
                    1
                ],
                "popup_metadata": [],
                "size_columns": [
                    2
                ]
            }
        },
        "state": {
            ...window.vis.state,
            "color" : {
                "categorical_custom_palette": customColors(querySectors)
            },
            "size_by_number_formatter": {
                "prefix": getCurrencyLabel(currencySectors, {preffixOnly: true}),
                "suffix": " M"
            }
            
        }
    });
}

updateVisualisation();

const selectedSector = "Health";
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
    <a class="view-button">
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
            ${
            indicatorSectors == "Total"
            ? html`<h3 class="plot-subtitle">Bilateral and imputed multilateral, ${timeRangeSectors[0] === timeRangeSectors[1] ? timeRangeSectors[0] : `${timeRangeSectors[0]}-${timeRangeSectors[1]}`}</h3>`
            : html`<h3 class="plot-subtitle">${indicatorSectors}, ${timeRangeSectors[0] === timeRangeSectors[1] ? timeRangeSectors[0] : `${timeRangeSectors[0]}-${timeRangeSectors[1]}`}</h3>`
            }
            <div id="flourish-treemap"></div>
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
            "Download plot",
            {
            reduce: () => downloadPNG(
            "treemap-sectors",
            "plot5_test"
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
            ${
            indicatorSectors == "Total"
            ? html`<h3 class="plot-subtitle">${selectedSector}, bilateral and imputed multilateral</h3>`
            : html`<h3 class="plot-subtitle">${selectedSector}, ${indicatorSectors}</h3>`
            }
            <div class="plot-settings">
                ${breakdownSectorsInput}
            </div>
            ${
            resize(
            (width) => linePlot(
            querySectors,
            "sectors",
            width,
            {
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
            "Download plot",
            {
            reduce: () => downloadPNG(
            "lines-sectors",
            "plot4_test"
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
        ${
        indicatorSectors == "Total"
        ? html`<h3 class="table-subtitle">Breakdown of ${selectedSector}, bilateral and imputed multilateral</h3>`
        : html`<h3 class="table-subtitle">Breakdown of ${selectedSector}, ${indicatorSectors}</h3>`
        }
        <div class="table-settings">
            ${unitSectorsInput}
        </div>
        ${table(querySectors, "sectors", {unit: unitSectors, sectorName: selectedSector})}
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
        "Download data",
        {
        reduce: () => downloadXLSX(
        querySectors,
        "file3_test"
        )
        }
        )
        }
    </div>
</div>
