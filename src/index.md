```js 
import {DuckDBClient} from "npm:@observablehq/duckdb";

import {setCustomColors} from "./components/colors.js"
import {formatString, convertUint32Array} from "./components/utils.js";

import {uniqueValuesFinancing} from "./components/uniqueValuesFinancing.js";
import {rangeInput} from "./components/rangeInput.js";

import {barPlot, linePlot, sparkbarTable} from "./components/visuals.js";

import {downloadPNG, downloadXLSX} from './components/downloads.js';
```

```js
setCustomColors();
```

```js
const db = DuckDBClient.of({
    financing: FileAttachment("./data/scripts/financing.parquet")
});
```

```js
// USER INPUTS
// Donor
const donorFinancingInput = Inputs.select(
    uniqueValuesFinancing.donors,
    {
        label: "Donor",
        value: "DAC Countries, Total",
        sort: true
    })
const donorFinancing = Generators.input(donorFinancingInput);

// Indicator
const indicatorFinancingInput = Inputs.select(
    uniqueValuesFinancing.indicators,
    {
        label: "Indicator",
        value: "Total ODA"
    })
const indicatorFinancing = Generators.input(indicatorFinancingInput);

// Type
const typeFinancingInput = Inputs.select(
    uniqueValuesFinancing.indicatorTypes,
    {
        label: "Type",
        value: "Official Definition",
        sort: true
    })
const typeFinancing = Generators.input(typeFinancingInput);

// Currency
const currencyFinancingInput = Inputs.select(
    uniqueValuesFinancing.currencies,
    {
        label: "Currency",
        value: "US Dollars",
        sort: true
    })
const currencyFinancing = Generators.input(currencyFinancingInput);

// Prices
const pricesFinancingInput = Inputs.radio(
    uniqueValuesFinancing.prices,
    {
        label: "Prices",
        value: "Constant"
    }
)
const pricesFinancing = Generators.input(pricesFinancingInput)

// Year
const timeRangeFinancingInput = rangeInput(
    {
        min: uniqueValuesFinancing.timeRange[0],
        max: uniqueValuesFinancing.timeRange[1],
        step: 1,
        value: [
            uniqueValuesFinancing.timeRange[0],
            uniqueValuesFinancing.timeRange[1]
        ],
        label: "Time range",
        enableTextInput: true
    })
const timeRangeFinancing = Generators.input(timeRangeFinancingInput)

// Unit
const unitFinancingInput = Inputs.select(
    new Map(
        [
            [`Million ${currencyFinancingInput.value}`, "Value"],
            ["GNI Share", "GNI Share"]
        ]
    ),
    {
        label: "Unit",
        value: "Value"
    }
)
const unitFinancing = Generators.input(unitFinancingInput)

// Intenational commitments
const commitmentFinancingInput = Inputs.toggle(
    {label: html`Int'l commitment`, value: false}
)

const commitmentFinancing = Generators.input(commitmentFinancingInput)
```

```js
// DATA QUERY
const queryFinancingString = `
SELECT 
    year AS Year,
    "Donor Name" AS Donor,
    Indicator,
    CASE 
        WHEN "Indicator Type" = 'Official Definition' AND Year < 2018 THEN 'Flow'
        WHEN "Indicator Type" = 'Official Definition' AND Year >= 2018 THEN 'Grant Equivalent'
        ELSE "Indicator Type"
    END AS Type,
    value AS Value,
    "GNI Share",
    Currency,
    Prices,
FROM financing
WHERE 
    Year >= ? AND 
    Year <= ? AND
    Donor = ? AND 
    Indicator = ? AND
    "Indicator Type" = ? AND 
    Currency = ? AND 
    Prices = ?;
`;

const queryFinancingParams = [
    timeRangeFinancing[0],
    timeRangeFinancing[1],
    donorFinancing,
    indicatorFinancing,
    typeFinancing,
    currencyFinancing,
    pricesFinancing
];

const queryFinancing = await db.query(queryFinancingString, queryFinancingParams);

const dataFinancing = queryFinancing.toArray()
    .map((row) => ({
        ...row,
        ["GNI Share"]: convertUint32Array(row["GNI Share"]),
        ["Value"]: convertUint32Array(row["Value"])
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

<div class="title-container">
    <div class="title-logo">
        <a href="https://data.one.org/" target="_blank">
            <img src="./ONE-logo-black.png" alt="A black circle with ONE written in white thick letters.">
        </a>
    </div>
    <h1 class="title-text">
        ODA Dashboard
    </h1>
</div>

<div class="header card">
    <a class="view-button active" href="./">
        Financing
    </a>
    <a class="view-button" href="./recipients">
        Recipients
    </a>
    <a class="view-button" href="./sectors">
        Sectors
    </a>
    <a class="view-button" href="./gender">
        Gender
    </a>
</div>

<div class="settings card">
    <div class="settings-group">
        ${donorFinancingInput}
    </div>
    <div class="settings-group">
        ${currencyFinancingInput}
        ${indicatorFinancingInput}
    </div>
    <div class="settings-button">
        ${showMoreButton}
    </div>
    <div class="settings-group hidden">
        ${pricesFinancingInput}
        ${timeRangeFinancingInput}
    </div>
</div>
<div class="grid grid-cols-2">
    <div class="card">
        <div  class="plot-container" id="bars-financing">
            <h2 class="plot-title">
                ${formatString(`${indicatorFinancing} from ${donorFinancing}`)}
            </h2>
            <div class="plot-subtitle-panel">
                ${
                    typeFinancing == "Official Definition"
                    ? html`<h3 class="plot-subtitle"><span class="flow-label subtitle-label">Flows</span> and <span class="ge-label  subtitle-label">grant equivalents</span></h3>`
                    : html`<h3 class="plot-subtitle">${typeFinancing}</h3>`
                }
            </div>
            ${
                resize(
                    (width) => barPlot(
                        dataFinancing, 
                        currencyFinancing, 
                        "financing", 
                        width
                    )
                )
            }
            <div class="bottom-panel">
                <div class="text-section">
                    <p class="plot-source">Source: OECD DAC Table 1.</p>
                    <p class="plot-note">ODA values in million ${pricesFinancing} ${currencyFinancing}.</p>
                </div>
                <div class="logo-section">
                    <a href="https://data.one.org/" target="_blank">
                        <img src="./ONE-logo-black.png" alt="A black circle with ONE written in white thick letters.">
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
                            "bars-financing",
                            formatString(`${indicatorFinancing} from ${donorFinancing}`, {fileMode: true})
                        )
                    }   
                )
            }
        </div>
    </div>
    <div class="card">
        <div class="plot-container" id="lines-financing">
            <h2 class="plot-title">
                ${formatString(`${indicatorFinancing} from ${donorFinancing}`)}
            </h2>
            <div class="plot-subtitle-panel">
                ${
                    typeFinancing == "Official Definition"
                    ? html`<h3 class="plot-subtitle"><span class="flow-label subtitle-label">Flows</span> and <span class="ge-label  subtitle-label">grant equivalents</span> as a share of GNI</h3>`
                    : html`<h3 class="plot-subtitle">${typeFinancing}</h3>`
                }
                ${commitmentFinancingInput}
            </div>
            ${
            resize(
                (width) => linePlot(
                    dataFinancing, 
                    "financing", 
                    width,
                    {showIntlCommitment: commitmentFinancing}
                ))
            }
            <div class="bottom-panel">
                <div class="text-section">
                    <p class="plot-source">Source: OECD DAC Table 1.</p>
                    <p class="plot-note">ODA values as a share of the GNI of ${formatString(donorFinancing)}.</p>
                </div>
                <div class="logo-section">
                    <a href="https://data.one.org/" target="_blank">
                        <img src="./ONE-logo-black.png" alt="A black circle with ONE written in white thick letters.">
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
                            "lines-financing",
                            formatString(`${indicatorFinancing} from ${donorFinancing}_gni_share`, {fileMode: true})
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
            ${formatString(`${indicatorFinancing} from ${donorFinancing}`)}
        </h2>
        <div class="table-subtitle-panel">
            ${unitFinancingInput}
        </div>
        ${
            sparkbarTable(
                dataFinancing, 
                "financing", 
                {unit: unitFinancing}
            )
        }
        <div class="bottom-panel">
            <div class="text-section">
                <p class="plot-source">Source: OECD DAC Table 1.</p>
                ${
                    unitFinancing === "Value" 
                    ? html`<p class="plot-note">ODA values in million ${pricesFinancing} ${currencyFinancing}.</p>`
                    : html`<p class="plot-note">ODA values as a share of the GNI of ${formatString(donorFinancing)}.</p>`
                }
            </div>
            <div class="logo-section">
                <a href="https://data.one.org/" target="_blank">
                    <img src="./ONE-logo-black.png" alt="A black circle with ONE written in white thick letters.">
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
                        dataFinancing,
                        formatString(`${indicatorFinancing} from ${donorFinancing}`, {fileMode: true})
                    )
                }
            )
        }
    </div>
</div>