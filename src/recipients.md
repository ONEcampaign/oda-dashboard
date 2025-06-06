```js 
import {setCustomColors} from "@one-data/observable-themes/use-colors";
import {customPalette} from "./components/colors.js";
import {logo} from "@one-data/observable-themes/use-images";
import {recipientsQueries} from './components/recipientQueries.js';
import {formatString, getCurrencyLabel, name2CodeMap, getNameByCode, generateIndicatorMap, decodeHTML} from "./components/utils.js";
import {rangeInput} from "./components/rangeInput.js";
import {barPlot, linePlot, sparkbarTable} from "./components/visuals.js";
import {downloadPNG, downloadXLSX} from './components/downloads.js';
```

```js
setCustomColors(customPalette);
```

```js
const donorOptions = await FileAttachment("./data/analysis_tools/donors.json").json()
const donorMapping = name2CodeMap(donorOptions, {})
```

```js
const recipientOptions = await FileAttachment("./data/analysis_tools/recipients.json").json()
const recipientMapping = name2CodeMap(recipientOptions)
```

```js
const indicatorOptions = await FileAttachment("./data/analysis_tools/recipients_indicators.json").json()
const indicatorMapping = new Map(
    Object.entries(indicatorOptions).map(([k, v]) => [v, Number(k)])
);
```

```js
const timeRangeOptions = await FileAttachment("./data/analysis_tools/base_time.json").json()
```

```js
// USER INPUTS
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
            ["% of Bilateral + Imputed multilateral ODA", "pct_total"],
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
        if (
            indicatorInput.value.length === 2 && decodeHTML(o.innerHTML) === "% of Bilateral + Imputed multilateral ODA" 
        ) {
            o.setAttribute("disabled", "disabled")
        } else o.removeAttribute("disabled");
    }
}

updateUnitOptions();
indicatorInput.addEventListener("input", updateUnitOptions);
donorInput.addEventListener("input", updateUnitOptions);
```

```js
// DATA QUERY
const data = recipientsQueries(
    donor, 
    recipient, 
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
    <a class="view-button" href="./">
        Financing
    </a>
    <a class="view-button active" href="./recipients">
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
                                        absoluteData.every(row => row.value === null) | absoluteData.length === 0 
                                            ? html`
                                                <div class="card">
                                                    <h2 class="plot-title">
                                                            ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                                    </h2>
                                                    <div class="warning">
                                                        No data available
                                                    </div>
                                                </div>
                                            `
                                            : html`
                                                <div class="card">
                                                    <div class="plot-container" id="bars-recipients">
                                                        <h2 class="plot-title">
                                                            ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                                        </h2>
                                                        <div class="plot-subtitle-panel">
                                                            ${
                                                                indicator.length > 1
                                                                ? html`<h3 class="plot-subtitle"><span class="bilateral-label subtitle-label">Bilateral</span> and <span class="multilateral-label subtitle-label">imputed multilateral</span> ODA</h3>`
                                                                : html`<h3 class="plot-subtitle">${getNameByCode(indicatorMapping, indicator)}  ODA</h3>`
                                                            }
                                                        </div>
                                                        ${
                                                            resize(
                                                                (width) => barPlot(
                                                                    absoluteData, 
                                                                    currency, 
                                                                    "recipients", 
                                                                    width, 
                                                                    {}
                                                                )
                                                            )
                                                        }
                                                        <div class="bottom-panel">
                                                            <div class="text-section">
                                                                <p class="plot-source">Source: OECD DAC2A table.</p>
                                                                <p class="plot-note">ODA values in ${prices} ${prices === "constant" ? timeRangeOptions.base: ""} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>
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
                                                                         "bars-recipients",
                                                                         formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)}`, {fileMode: true})                        
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
                                                                        formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)}`, {fileMode: true})
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
                                                            ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)} as a share of total ODA
                                                    </h2>
                                                    <div class="warning">
                                                        No data available
                                                    </div>
                                                </div>
                                            `
                                            : html`
                                                <div class="card">
                                                    <div class="plot-container" id="lines-recipients">
                                                        <h2 class="plot-title">
                                                            ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                                        </h2>
                                                        <div class="plot-subtitle-panel">
                                                            ${
                                                                indicator.length > 1
                                                                ? html`<h3 class="plot-subtitle"><span class="bilateral-label subtitle-label">Bilateral</span> and <span class="multilateral-label subtitle-label">imputed multilateral</span> as a share of the total</h3>`
                                                                : html`<h3 class="plot-subtitle">${getNameByCode(indicatorMapping, indicator)} as a share of the total</h3>`
                                                            }
                                                        </div>
                                                        ${
                                                            resize(
                                                                (width) => linePlot(
                                                                    relativeData,
                                                                    "recipients",
                                                                    width
                                                                )
                                                            )
                                                        }
                                                        <div class="bottom-panel">
                                                            <div class="text-section">
                                                                <p class="plot-source">Source: OECD DAC2A table.</p>
                                                                <p class="plot-note">ODA values as a share of all aid received by ${getNameByCode(recipientMapping, recipient)}.</p>
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
                                                                         "lines-recipients",
                                                                         formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)} share`, {fileMode: true})                        )
                                                                }
                                                            )
                                                        }
                                                        ${
                                                            Inputs.button(
                                                                "Download data", 
                                                                {
                                                                    reduce: () => downloadXLSX(
                                                                        relativeData,
                                                                        formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)} share`, {fileMode: true})
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
                                        ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                    </h2>
                                    <div class="table-subtitle-panel">
                                        ${unitInput}
                                    </div>
                                    ${
                                        tableData.every(row => row.value === null) | tableData.length === 0 
                                            ? html `
                                                <div class="warning">
                                                    No data available
                                                </div>
                                            `
                                            : html`
                                                ${
                                                    sparkbarTable(  
                                                        tableData, 
                                                        "recipients",
                                                        {}
                                                    )
                                                }
                                                <div class="bottom-panel">
                                                    <div class="text-section">
                                                        <p class="plot-source">Source: OECD DAC2A table.</p>
                                                        ${
                                                            unit === "value" 
                                                                ? html`<p class="plot-note">ODA values in ${prices} ${prices === "constant" ? timeRangeOptions.base: ""} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>`
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
                                                            "Download data", 
                                                            {
                                                                reduce: () => downloadXLSX(
                                                                    tableData,
                                                                    formatString(`${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)} share ${unit}`, {fileMode: true})
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
            `
    }
</div>

