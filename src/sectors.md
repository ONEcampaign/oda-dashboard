```js 
import {setCustomColors} from "./components/colors.js"
import {formatString, getCurrencyLabel, name2CodeMap, getNameByCode, generateIndicatorMap} from "./components/utils.js";
import {sectorsQueries} from "./components/sectorsQueries.js"
import {rangeInput} from "./components/rangeInput.js";
import {linePlot, sparkbarTable} from "./components/visuals.js";
import {treemapPlot, selectedSector} from "./components/Treemap.js"
import {downloadPNG, downloadXLSX} from './components/downloads.js';
```


```js
setCustomColors();
```

```js
const ONELogo = await FileAttachment("./ONE-logo-black.png").image()
```

```js
const donorOptions = await FileAttachment("./data/analysis_tools/donors.json").json()
const donorMapping = name2CodeMap(donorOptions)

const recipientOptions = await FileAttachment("./data/analysis_tools/recipients.json").json()
const recipientMapping = name2CodeMap(recipientOptions)

const indicatorOptions = await FileAttachment("./data/analysis_tools/sectors_indicators.json").json()
const indicatorMapping = new Map(
    Object.entries(indicatorOptions).map(([k, v]) => [v, Number(k)])
);
```


```js
// USER INPUTS
// Donor
const donorInput = Inputs.select(
    donorMapping,
    {
        label: "Donor",
        value: donorMapping.get("DAC countries")
    })
const donor = Generators.input(donorInput);

// Recipient
const recipientInput = Inputs.select(
    recipientMapping,
    {
        label: "Recipient",
        value: recipientMapping.get("Developing countries"),
        sort: true
    })
const recipient = Generators.input(recipientInput);

// Indicator
const indicatorInput = Inputs.checkbox(
    indicatorMapping,
    {
        label: "Indicator",
        value: [
            indicatorMapping.get("Bilateral"), 
            indicatorMapping.get("Imputed multilateral")
        ],
    })
const indicator = Generators.input(indicatorInput);

// Currency
const currencyInput = Inputs.select(
    new Map([
        ["US Dollars", "usd"],
        ["Canada Dollars", "cad"],
        ["Euros", "eur"],
        ["British pounds", "gbp"]
    ]),
    {
        label: "Currency",
        value: "usd",
        sort: true
    })
const currency = Generators.input(currencyInput);

// Prices
const pricesInput = Inputs.radio(
    new Map([
        ["Current", "current"],
        ["Constant", "constant"]
    ]),
    {
        label: "Prices",
        value: "current",
        disabled: ["constant"]
    }
)
const prices = Generators.input(pricesInput)

// Year
const timeRangeInput = rangeInput(
    {
        min: 2000,
        max: 2023,
        step: 1,
        value: [2013, 2023],
        label: "Time range",
        enableTextInput: true
    })
const timeRange = Generators.input(timeRangeInput)

// Breakdown
const breakdownInput = Inputs.toggle(
    {
        label: "Sector breakdown",
        value: false
    }
)
const breakdown = Generators.input(breakdownInput)

// Unit
const unitInput = Inputs.select(
    new Map(
        [
            [`Million ${currencyInput.value}`, "value"],
            [`% of ${selectedSector} ODA`, "indicator"]
        ]
    ),
    {
        label: "Unit",
        value: "Value"
    }
)
const unit = Generators.input(unitInput)
```

```js
// DATA QUERY
const data = sectorsQueries(
    donor,
    recipient,
    indicator,
    selectedSector,
    currency,
    prices,
    timeRange,
    breakdown,
    unit
)

const treemapData = data.treemap
const selectedData = data.selected
const tableData = data.table
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

<div>
    ${
        !data 
            ? html` `
            : html`
                <div class="settings card">
                    <div class="settings-group">
                        ${donorInput}
                        ${recipientInput}
                    </div>
                    <div class="settings-group">
                        ${currencyInput}
                        ${indicatorInput}
                    </div>
                    <div class="settings-group hidden">
                        ${pricesInput}
                        ${timeRangeInput}
                    </div>
                </div>
                <div>
                    ${
                        indicator.length === 0 
                            ? html ` 
                                <div class="grid grid-cols-2">
                                    <div class="card"> 
                                        <div class="warning">
                                            Select at least one indicator
                                        </div>
                                    </div>
                                </div>
                            `
                            : html`
                                <div class="grid grid-cols-2">
                                    <div class="card">
                                        <div class="plot-container" id="treemap-sectors">
                                            <h2 class="plot-title">
                                                ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)} by sector
                                            </h2>
                                            <div class="plot-subtitle-panel">
                                                ${
                                                    indicator.length > 1
                                                    ? html`<h3 class="plot-subtitle">Total ODA; ${timeRange[0] === timeRange[1] ? timeRange[0] : `${timeRange[0]}-${timeRange[1]}`}</h3>`
                                                    : html`<h3 class="plot-subtitle">${getNameByCode(indicatorMapping, indicator)} ODA; ${timeRange[0] === timeRange[1] ? timeRange[0] : `${timeRange[0]}-${timeRange[1]}`}</h3>`
                                                }
                                            </div>
                                            ${
                                                resize(
                                                    (width) => treemapPlot(treemapData, width, {currency: currency})
                                                )
                                            }
                                            <div class="bottom-panel">
                                                <div class="text-section">
                                                    <p class="plot-source">Source: OECD DAC Creditor Reporting System database.</p>
                                                    <p class="plot-note">ODA values in million ${prices} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>
                                                </div>
                                                <div class="logo-section">
                                                    <a href="https://data.one.org/" target="_blank">
                                                        ${ONELogo}
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
                                                            formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)} by sector`, {fileMode: true})
                                                        )
                                                    }
                                                )
                                            }
                                            ${
                                                Inputs.button(
                                                    "Download data", 
                                                    {
                                                        reduce: () => downloadXLSX(
                                                            treemapData,
                                                            formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)} by sector`, {fileMode: true})
                                                        )
                                                    }
                                                )
                                            }
                                        </div>
                                    </div>
                                    <div class="card">
                                        <div class="plot-container" id="lines-sectors">
                                            <h2 class="plot-title">
                                                ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                            </h2>
                                            <div class="plot-subtitle-panel">
                                                ${
                                                    indicator.length > 1
                                                    ? html`<h3 class="plot-subtitle">${selectedSector}; Total ODA</h3>`
                                                    : html`<h3 class="plot-subtitle">${selectedSector}; ${getNameByCode(indicatorMapping, indicator)} ODA</h3>`
                                                }
                                                ${breakdownInput}
                                            </div>
                                            ${
                                                resize(
                                                    (width) => linePlot(
                                                        selectedData,
                                                        "sectors",
                                                        width, {
                                                            selectedSector: selectedSector,
                                                            currency: currency,
                                                            breakdown: breakdown
                                                        }
                                                    )
                                                )
                                            }
                                            <div class="bottom-panel">
                                                <div class="text-section">
                                                    <p class="plot-source">Source: OECD DAC Creditor Reporting System database.</p>
                                                    <p class="plot-note">ODA values in million ${prices} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>
                                                </div>
                                                <div class="logo-section">
                                                    <a href="https://data.one.org/" target="_blank">
                                                        ${ONELogo}
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
                                                            formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)} ${selectedSector} ${breakdown ? "breakdown" : "total"}`, {fileMode: true})
                                                        )
                                                    }
                                                )
                                            }
                                            ${
                                                Inputs.button(
                                                    "Download data", 
                                                    {
                                                        reduce: () => downloadXLSX(
                                                            selectedData,
                                                            formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)} ${selectedSector} ${breakdown ? "breakdown" : "total"}`, {fileMode: true})
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
                                            ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                        </h2>
                                        <div class="table-subtitle-panel">
                                            ${
                                                indicator.length > 1
                                                ? html`<h3 class="plot-subtitle">Breakdown of ${selectedSector}; Total ODA</h3>`
                                                : html`<h3 class="plot-subtitle">Breakdown of ${selectedSector}; ${getNameByCode(indicatorMapping, indicator)} ODA</h3>`
                                            }
                                            ${unitInput}
                                        </div>
                                        ${
                                            sparkbarTable(
                                                tableData, 
                                                "sectors"
                                            )
                                        }
                                        <div class="bottom-panel">
                                            <div class="text-section">
                                                <p class="plot-source">Source: OECD DAC Creditor Reporting System database.</p>
                                                ${
                                                    unit === "value" 
                                                        ? html`<p class="plot-note">ODA values in ${prices} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>`
                                                        : unit === "indicator"
                                                            ? html`<p class="plot-note">ODA values as a share of ${selectedSector} ODA received by ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}.</p>`
                                                            : html`<p class="plot-note">ODA values as a share of total aid received by ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}.</p>`
                                                }                
                                            </div>
                                            <div class="logo-section">
                                                <a href="https://data.one.org/" target="_blank">
                                                    ${ONELogo}
                                                </a>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="download-panel">
                                        ${
                                            Inputs.button(
                                                "Download data", {
                                                    reduce: () => downloadXLSX(
                                                        tableData,
                                                        formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)} ${selectedSector} breakdown ${unit}`, {fileMode: true})                    )
                                                }
                                            )
                                        }
                                    </div>
                                </div>
                            `
                    }
                </div>
            `
    }
</div>