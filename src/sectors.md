```js 
import {setCustomColors} from "@one-data/observable-themes/use-colors";
import {logo} from "@one-data/observable-themes/use-images";
import {formatString, getCurrencyLabel, name2CodeMap, getNameByCode, generateIndicatorMap, decodeHTML} from "./components/utils.js";
import {sectorsQueries} from "./components/sectorsQueries.js";
import {rangeInput} from "./components/rangeInput.js";
import {barPlot, sparkbarTable} from "./components/visuals.js";
import {treemapPlot, selectedSector} from "./components/Treemap.js";
import {paletteSubsectors} from './components/colors.js';
import {downloadPNG, downloadXLSX} from './components/downloads.js';
```

```js
const donorOptions = await FileAttachment("./data/analysis_tools/donors.json").json()
const donorMapping = name2CodeMap(donorOptions, {removeEU27EUI:true})

const recipientOptions = await FileAttachment("./data/analysis_tools/recipients.json").json()
const recipientMapping = name2CodeMap(recipientOptions)

const indicatorOptions = await FileAttachment("./data/analysis_tools/sectors_indicators.json").json()
const indicatorMapping = new Map(
    Object.entries(indicatorOptions).map(([k, v]) => [v, Number(k)])
);

const subsector2Sector = await FileAttachment("./data/analysis_tools/sectors.json").json()

const timeRangeOptions = await FileAttachment("./data/analysis_tools/base_time.json").json()
```

```js
// USER INPUTS
// Donor
const donorInput = Inputs.select(
    donorMapping,
    {
        label: "Donor",
        value: donorMapping.get("DAC countries"),
        sort: true
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
        ["Constant", "constant"],
        ["Current", "current"]
    ]),
    {
        label: "Prices",
        value: "constant",
    }
)
const prices = Generators.input(pricesInput)

// Year
const timeRangeInput = rangeInput(
    {
        min: 2013,
        max: timeRangeOptions.end,
        step: 1,
        value: [2013, timeRangeOptions.end],
        label: "Time range",
        enableTextInput: true
    })
const timeRange = Generators.input(timeRangeInput)

// Breakdown
const breakdownInput = Inputs.toggle(
    {
        label: "Sector breakdown",
        value: true
    }
)
const breakdown = Generators.input(breakdownInput)

// Breakdown Placeholder
const breakdownPlaceholderInput = Inputs.toggle(
    {
        label: "Sector breakdown",
        value: false,
        disabled: true
    }
)
const breakdownPlaceholder = Generators.input(breakdownPlaceholderInput)
```

```js
// Unit
const unitInput = Inputs.select(
    new Map(
        [
            [`Million ${getCurrencyLabel(currency, {currencyOnly: true,})}`, "value"],
            [`% of ${selectedSector} ODA`, "pct_sector"],
            [
                `% of ${indicator.length > 1 
                    ? "Bilateral + Imputed multilateral ODA" 
                    : getNameByCode(indicatorMapping, indicator)}`, 
                "pct_total"
            ]
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
const subsectorCount = Object.values(subsector2Sector).filter(
    (sector) => sector === selectedSector
).length;

const breakdownIsDisabled = subsectorCount === 1;

const checkbox = breakdownPlaceholderInput.querySelector("input");
const parentDiv = checkbox.closest("form");

parentDiv.classList.add("disabled");


function disableBreakdown() {
    
    for (const o of unitInput.querySelectorAll("option")) {
        if (decodeHTML(o.innerHTML) === `% of ${selectedSector} ODA` && (breakdownIsDisabled || !breakdown)) {
            o.setAttribute("disabled", "disabled");
        }
        else o.removeAttribute("disabled");
    }
}

disableBreakdown();
unitInput.addEventListener("input", disableBreakdown);
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

```js
const uniqueSubsectors =  [
    ...new Set(selectedData.map(row => row["sub_sector"])).values()
]

function generateSubtitle() {
    const limit = 3;
    const shown = uniqueSubsectors.slice(0, limit);
    const subtitleSpans = shown.map((name, i) => {
        return html`<span class="subtitle-label" style=color:${paletteSubsectors[i]}>${name}</span>${i < shown.length - 1 ? ', ' : ''}`;
    });

    if (uniqueSubsectors.length > limit) {
        subtitleSpans.push(", and other");
    }
    
    subtitleSpans.push("; ")

    return subtitleSpans;
}

```

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
    <a class="view-button" href="./faqs">
        FAQs
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
                                    ${
                                        treemapData.every(row => row.value === null) | treemapData.length === 0 
                                            ? html`
                                                <div class="card"> 
                                                    <h2 class="plot-title">
                                                        ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)} by sector
                                                    </h2>
                                                    <div class="warning">
                                                        No data available
                                                    </div>
                                                </div>
                                            `
                                            : html`
                                                <div class="card">
                                                    <div class="plot-container" id="treemap-sectors">
                                                        <h2 class="plot-title">
                                                            ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)} by sector
                                                        </h2>
                                                        <div class="plot-subtitle-panel">
                                                            ${
                                                                indicator.length > 1
                                                                ? html`<h3 class="plot-subtitle">Bilateral + Imputed multilateral ODA; ${timeRange[0] === timeRange[1] ? timeRange[0] : `${timeRange[0]}-${timeRange[1]}`}</h3>`
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
                                                                <p class="plot-source">Source: OECD DAC Creditor Reporting System, Provider's total use of the multilateral system databases.</p>
                                                                <p class="plot-note">ODA values in million ${prices} ${prices === "constant" ? timeRangeOptions.base: ""} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>
                                                            </div>
                                                            <div class="logo-section">
                                                                <a href="https://data.one.org/" target="_blank">
                                                                    <img src=${logo} alt=“The ONE Campaign logo:a solid black circle with the word ‘ONE’ in bold white capital letters.”>
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
                                            `
                                    }
                                    ${
                                        selectedData.every(row => row.value === null) | selectedData.length === 0 
                                            ? html`
                                                <div class="card"> 
                                                    <h2 class="plot-title">
                                                        ${selectedSector} ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                                    </h2>
                                                    <div class="warning">
                                                        No data available
                                                    </div>
                                                </div>
                                            `
                                            : html`
                                                <div class="card">
                                                    <div class="plot-container" id="bars-sectors">
                                                        <h2 class="plot-title">
                                                            ${selectedSector} ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                                        </h2>
                                                        <div class="plot-subtitle-panel">
                                                            <h3 class="plot-subtitle">
                                                                ${breakdown && !breakdownIsDisabled ? generateSubtitle() : html` `}
                                                                ${indicator.length > 1 ? "Bilateral + Imputed multilateral" : getNameByCode(indicatorMapping, indicator)} ODA
                                                            </h3>
                                                            ${breakdownIsDisabled ? breakdownPlaceholderInput : breakdownInput}
                                                        </div>
                                                        ${
                                                            resize(
                                                                (width) => barPlot(
                                                                    selectedData,   
                                                                    currency,
                                                                    "sectors",
                                                                    width, {
                                                                        breakdown: breakdownIsDisabled ? breakdownPlaceholder : breakdown
                                                                    }
                                                                )
                                                            )
                                                        }
                                                        <div class="bottom-panel">
                                                            <div class="text-section">
                                                                <p class="plot-source">Source: OECD DAC Creditor Reporting System, Provider's total use of the multilateral system databases.</p>
                                                                <p class="plot-note">ODA values in million ${prices} ${prices === "constant" ? timeRangeOptions.base: ""} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>
                                                            </div>
                                                            <div class="logo-section">
                                                                <a href="https://data.one.org/" target="_blank">
                                                                    <img src=${logo} alt=“The ONE Campaign logo:a solid black circle with the word ‘ONE’ in bold white capital letters.”>
                                                                </a>
                                                            </div>
                                                        </div>
                                                    </div>
                                                    <div class="download-panel">
                                                        ${
                                                            Inputs.button(
                                                                "Download plot", {
                                                                    reduce: () => downloadPNG(
                                                                        "bars-sectors",
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
                                            `
                                    }
                                </div>
                                <div class="card">
                                    <h2 class="table-title">
                                        ${breakdown && !breakdownIsDisabled ? "Breakdown of" : ""} ${selectedSector} ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                    </h2>
                                    <div class="table-subtitle-panel">
                                        ${
                                            indicator.length > 1
                                            ? html`<h3 class="plot-subtitle">Bilateral + Imputed multilateral ODA</h3>`
                                            : html`<h3 class="plot-subtitle">${getNameByCode(indicatorMapping, indicator)} ODA</h3>`
                                        }
                                        ${unitInput}
                                    </div>
                                        ${
                                            tableData.every(row => row.value === null) | tableData.length === 0 
                                                ? html`
                                                    <div class="warning">
                                                        No data available
                                                    </div>
                                                `
                                                : html`
                                                    ${
                                                        sparkbarTable(
                                                            tableData, 
                                                            "sectors",
                                                            {breakdown: breakdownIsDisabled ? breakdownPlaceholder : breakdown}
                                                        )
                                                    }
                                                    <div class="bottom-panel">
                                                        <div class="text-section">
                                                                <p class="plot-source">Source: OECD DAC Creditor Reporting System, Provider's total use of the multilateral system databases.</p>
                                                            ${
                                                                unit === "value" 
                                                                    ? html`<p class="plot-note">ODA values in ${timeRangeOptions.base} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>`
                                                                    : unit === "indicator"
                                                                        ? html`<p class="plot-note">ODA values as a share of ${selectedSector} ODA received by ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}.</p>`
                                                                        : html`<p class="plot-note">ODA values as a share of total aid received by ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}.</p>`
                                                            }                
                                                        </div>
                                                        <div class="logo-section">
                                                            <a href="https://data.one.org/" target="_blank">
                                                                <img src=${logo} alt=“The ONE Campaign logo:a solid black circle with the word ‘ONE’ in bold white capital letters.”>
                                                            </a>
                                                        </div>
                                                    </div>
                                                    <div class="download-panel table">
                                                        ${
                                                            Inputs.button(
                                                                "Download data", {
                                                                    reduce: () => downloadXLSX(
                                                                        tableData,
                                                                        formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)} ${selectedSector} ${breakdown ? "breakdown" : ""} ${unit}`, {fileMode: true})                    )
                                                                }
                                                            )
                                                        }
                                                    </div>
                                                `
                                        }
                                </div>
                            `
                    }
                </div>
            `
    }
</div>