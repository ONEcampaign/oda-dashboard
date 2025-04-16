```js
import {setCustomColors} from "./components/colors.js"
import {financingQueries} from "./components/financingQueries.js"
import {formatString, getCurrencyLabel, name2CodeMap, getNameByCode, generateIndicatorMap, decodeHTML} from "./components/utils.js";
import {rangeInput} from "./components/rangeInput.js";
import {barPlot, linePlot, sparkbarTable} from "./components/visuals.js";
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

const indicatorOptions = await FileAttachment('./data/analysis_tools/financing_indicators.json').json()
const indicatorMapping = new Map(
    Object.entries(indicatorOptions).map(([k, v]) => [v, Number(k)])
);

const timeRangeOptions = await FileAttachment("./data/analysis_tools/financing_time.json").json()
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

// Indicator
const indicatorInput = Inputs.select(
    indicatorMapping,
    {
        label: "Indicator",
        value: indicatorMapping.get("Total ODA")
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
        min: timeRangeOptions.start,
        max: timeRangeOptions.end,
        step: 1,
        value: [timeRangeOptions.end - 20, timeRangeOptions.end],
        label: "Time range",
        enableTextInput: true
    })
const timeRange = Generators.input(timeRangeInput)
```

```js
// Unit
const unitInput = Inputs.select(
    new Map(
        [
            [`Million ${getCurrencyLabel(currency, {currencyOnly: true,})}`, "value"],
            ["% of GNI", "gni_pct"],
            ["% of total ODA", "total_pct"]
        ]
    ),
    {
        label: "Unit",
        value: "value"
    }
)
const unit = Generators.input(unitInput)

function updateUnitOptions() {
    for (const o of unitInput.querySelectorAll("option")) {
        if (decodeHTML(o.innerHTML) === "% of total ODA" & indicatorInput.value === indicatorMapping.get("Total ODA")) {
            o.setAttribute("disabled", "disabled");
        }
        else o.removeAttribute("disabled");
    }
}

updateUnitOptions();
indicatorInput.addEventListener("input", updateUnitOptions);

// Intenational commitments
const commitmentInput = Inputs.toggle(
    {label: html`Int'l commitment`, value: false}
)

const commitment = Generators.input(commitmentInput)
```

```js
// DATA QUERY
const data = financingQueries(
    donor, 
    indicator,
    currency,
    prices,
    timeRange, 
    unit
)

const absoluteData = data.absolute
const relativeData = data.relative
const tableData = data.table
```

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
                    </div>
                    <div class="settings-group">
                        ${currencyInput}
                        ${indicatorInput}
                    </div>
                    <div class="settings-group">
                        ${pricesInput}
                        ${timeRangeInput}
                    </div>
                </div>
                <div class="grid grid-cols-2">
                    ${
                        absoluteData.every(row => row.value === null) | absoluteData.length === 0
                            ? html`
                                <div class="card">
                                    <h2 class="plot-title">
                                        ${formatString(`${getNameByCode(indicatorMapping, indicator)} from ${getNameByCode(donorMapping, donor)}`)}
                                    </h2>
                                    <div class="warning">
                                        No data available
                                    </div>
                                </div>
                            `
                            : html`
                                <div class="card">
                                    <div  class="plot-container" id="bars-financing">
                                        <h2 class="plot-title">
                                            ${formatString(`${getNameByCode(indicatorMapping, indicator)} from ${getNameByCode(donorMapping, donor)}`)}
                                        </h2>
                                        <div class="plot-subtitle-panel">
                                            <h3 class="plot-subtitle">
                                                ${
                                                    new Set(absoluteData.map(d => d.type)).size > 1 
                                                        ? html`in <span class="flow-label subtitle-label">Flows</span> and <span class="ge-label  subtitle-label">grant equivalents</span>`
                                                        : html`in ${[...new Set(absoluteData.map(d => d.type))][0]}`
                                                }
                                            </h3>
                                        </div>
                                        ${
                                            resize(
                                                (width) => barPlot(
                                                    absoluteData, 
                                                    currency, 
                                                    "financing", 
                                                    width, 
                                                    {}
                                                )
                                            )
                                        }
                                        <div class="bottom-panel">
                                            <div class="text-section">
                                                <p class="plot-source">Source: OECD DAC1 table.</p>
                                                <p class="plot-note">ODA values in ${prices} ${prices === "constant" ? timeRangeOptions.base: ""} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>                
                                            </div>
                                            <div class="logo-section">
                                                <a href="https://data.one.org/" target="_blank">
                                                    ${ONELogo.cloneNode(true)}
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
                                                        formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(indicatorMapping, indicator)}`, {fileMode: true})
                                                    )
                                                }   
                                            )
                                        }
                                        ${
                                            Inputs.button(
                                                "Download data", 
                                                {
                                                    reduce: () => downloadXLSX(
                                                        absoluteData,
                                                        formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(indicatorMapping, indicator)}`, {fileMode: true})
                                                    )
                                                }
                                            )
                                        }
                                    </div>
                                </div>
                            `
                    }
                    ${
                        relativeData.every(row => row.value === null) | relativeData.length === 0
                            ? html`
                                <div class="card">
                                    <h2 class="plot-title">
                                        ${formatString(`${getNameByCode(indicatorMapping, indicator)} from ${getNameByCode(donorMapping, donor)}`)} ${indicator === indicatorMapping.get("Total ODA") ? "as a share of GNI" : "as a share of total ODA"}
                                    </h2>
                                    <div class="warning">
                                        No data available
                                    </div>
                                </div>
                            `
                            : html`
                                <div class="card">
                                    <div class="plot-container" id="lines-financing">
                                        <h2 class="plot-title">
                                            ${formatString(`${getNameByCode(indicatorMapping, indicator)} from ${getNameByCode(donorMapping, donor)}`)}
                                        </h2>
                                        <div class="plot-subtitle-panel">
                                            <h3 class="plot-subtitle">
                                                ${
                                                    new Set(relativeData.map(d => d.type)).size > 1 
                                                        ? html`in <span class="flow-label subtitle-label">Flows</span> and <span class="ge-label  subtitle-label">grant equivalents</span>`
                                                        : html`in ${[...new Set(relativeData.map(d => d.type))][0]}`
                                                }
                                                ${indicator === indicatorMapping.get("Total ODA") ? html`as a share of GNI` : html`as a share of total ODA`}
                                            </h3>
                                            ${
                                                indicator === indicatorMapping.get("Total ODA") 
                                                    ? commitmentInput
                                                    : html` `
                                            }
                                        </div>
                                        ${
                                        resize(
                                            (width) => linePlot(
                                                relativeData, 
                                                "financing", 
                                                width,
                                                {
                                                    showIntlCommitment: commitment,
                                                    GNIShare: indicator === indicatorMapping.get("Total ODA")
                                                }
                                            ))
                                        }
                                        <div class="bottom-panel">
                                            <div class="text-section">
                                                <p class="plot-source">Source: OECD DAC1 table.</p>
                                                <p class="plot-note">ODA values as a share of GNI of ${formatString(getNameByCode(donorMapping, donor))}.</p>
                                            </div>
                                            <div class="logo-section">
                                                <a href="https://data.one.org/" target="_blank">
                                                    ${ONELogo.cloneNode(true)}
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
                                                        formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(indicatorMapping, indicator)} share`, {fileMode: true})
                                                    )
                                                }
                                            )
                                        }
                                        ${
                                            Inputs.button(
                                                "Download data", 
                                                {
                                                    reduce: () => downloadXLSX(
                                                        relativeData,
                                                        formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(indicatorMapping, indicator)} share`, {fileMode: true})
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
                        ${formatString(`${getNameByCode(indicatorMapping, indicator)} from ${getNameByCode(donorMapping, donor)}`)}
                    </h2>
                    <div class="table-subtitle-panel">
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
                                        "financing", 
                                        {}
                                    )
                                }
                                <div class="bottom-panel">
                                    <div class="text-section">
                                        <p class="plot-source">Source: OECD DAC1 table.</p>
                                        ${
                                            unit === "value" 
                                                ? html`<p class="plot-note">ODA values in ${prices} ${prices === "constant" ? timeRangeOptions.base: ""} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>`
                                                : unit === "gni_pct"
                                                    ? html`<p class="plot-note">ODA values as a share of the GNI of ${formatString(getNameByCode(donorMapping, donor))}.</p>`
                                                    : html`<p class="plot-note">ODA values as a share of total contributions from ${formatString(getNameByCode(donorMapping, donor))}.</p>`
                                        }
                                    </div>
                                    <div class="logo-section">
                                        <a href="https://data.one.org/" target="_blank">
                                            ${ONELogo.cloneNode(true)}
                                        </a>
                                    </div>
                                </div>
                                <div class="download-panel table">
                                    ${
                                        Inputs.button(
                                            "Download data", 
                                            {
                                                reduce: () => downloadXLSX(
                                                    tableData,
                                                    formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(indicatorMapping, indicator)} ${unit}`, {fileMode: true})
                                                )
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
