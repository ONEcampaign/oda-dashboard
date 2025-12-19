```js
import {setCustomColors} from "@one-data/observable-themes/use-colors";
import {customPalette} from "./components/colors.js";
import {logo} from "@one-data/observable-themes/use-images";
import {formatString, getCurrencyLabel, name2CodeMap, getNameByCode, generateIndicatorMap} from "./components/utils.js";
import {genderQueries, transformTableData, donorOptions, recipientOptions, genderIndicators} from "./components/genderQueries.js";
import {rangeInput} from "./components/rangeInput.js";
import {barPlot, linePlot, sparkbarTable} from "./components/visuals.js";
import {downloadPNG, downloadXLSX} from './components/downloads.js';
```

```js
setCustomColors(customPalette);
```

```js
// Use metadata exported from genderQueries.js to avoid duplicate loading
const donorMapping = name2CodeMap(donorOptions, {removeEU27EUI:true})
```

```js
const recipientMapping = name2CodeMap(recipientOptions, { useRecipientGroups: true })
```

```js
const indicatorMapping = new Map(
    Object.entries(genderIndicators).map(([k, v]) => [v, Number(k)])
);
```

```js
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
        label: "Gender is",
        value: [
            indicatorMapping.get("Main target"), 
            indicatorMapping.get("Secondary target")
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
            ["% of total", "total"]
        ]
    ),
    {
        label: "Unit",
        value: "value"
    }
)
const unit = Generators.input(unitInput)
```

```js
// DATA QUERY (optimized: unit changes don't trigger re-query)
const data = genderQueries(
    donor,
    recipient,
    indicator,
    currency,
    prices,
    timeRange
)

const absoluteData = data.absolute
const relativeData = data.relative
```

```js
// Table data calculated separately so unit changes are instant
const tableData = transformTableData(data.rawData, unit, currency, prices)
```

```js
const indicatorClassMap = {
    "Main target": "gender-main",
    "Secondary target": "gender-secondary",
    "Not targeted": "gender-not-targeted",
    "Not screened": "gender-not-screened"
};

function generateSubtitle(codes, indicatorMapping) {
    return codes.map((code, i) => {
        const name = getNameByCode(indicatorMapping, code);
        const className = indicatorClassMap[name] || 'unknown';
        return html`<span class="subtitle-label ${className}">${name}</span>${i < codes.length - 1 ? ', ' : ''}`;
    });
}
```

```js
const includes_germany = [
    5,     // Germany
    918,   // EU institutions
    20000, // All bilateral donors
    20001, // DAC countries
    20002, // EU 27 countries
    20003, // EU27 + EU Institutions
    20004, // G7 countries, 
]

const germany_is_donor = includes_germany.includes(donor);
```

<div class="header card">
    <a class="view-button" href="./">
        Financing
    </a>
    <a class="view-button" href="./recipients">
        Recipients
    </a>
    <a class="view-button" href="./sectors">
        Sectors
    </a>
    <a class="view-button active" href="./gender">
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
                                ${
                                  germany_is_donor
                                    ? html`
                                        <div class="grid grid-cols-2">
                                          <div class="card" style="margin: 0 auto;">
                                            <div class="note">
                                                Germany has reported only semi-aggregated data for part of the Federal Ministry for Economic Cooperation and Development (BMZ) data (approx. EUR 4 billion) for 2024, due to an internal transition of their IT systems. Granular data on recipients, sectors, and policy markers (for example) were not available for submission to the OECD at time of publication. The OECD will re-publish an update in early 2026 once these data have been obtained and processed. <a href="https://www.oecd.org/en/data/insights/data-explainers/2025/12/final-oecd-statistics-on-oda-and-other-development-finance-flows-in-2024-key-figures-and-trends.html">More information.</a>
                                            </div>
                                          </div>
                                        </div>
                                      `
                                    : null
                                }
                                <div class="grid grid-cols-2">
                                    ${
                                        absoluteData.every(row => row.value === null) | absoluteData.length === 0 
                                            ? html`
                                                <div class="card">
                                                    <h2 class="plot-title">
                                                        Gender ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                                    </h2>
                                                    <div class="warning">
                                                        No data available
                                                    </div>
                                                </div>
                                            `
                                            : html`
                                                <div class="card">
                                                    <div class="plot-container" id="bars-gender">
                                                        <h2 class="plot-title">
                                                            Gender ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                                        </h2>
                                                        <div class="plot-subtitle-panel">
                                                            <div class="plot-subtitle">
                                                                Gender is ${generateSubtitle(indicator, indicatorMapping)}
                                                            </div>
                                                        </div>
                                                        ${
                                                            resize(
                                                                (width) => barPlot(
                                                                    absoluteData, 
                                                                    currency, 
                                                                    "gender", 
                                                                    width,
                                                                    {}
                                                                )
                                                            )
                                                        }
                                                        <div class="bottom-panel">
                                                            <div class="text-section">
                                                                <p class="plot-source">Source: OECD Creditor Reporting System.</p>
                                                                <p class="plot-note">ODA values in ${prices}  ${prices === "constant" ? timeRangeOptions.base: ""} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>
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
                                                                        "bars-gender",
                                                                         formatString(`gender ODA ${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)}`, {fileMode: true})
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
                                                                         formatString(`gender ODA ${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)}`, {fileMode: true})
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
                                                        Gender ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)} as a share of the total
                                                    </h2>
                                                    <div class="warning">
                                                        No data available
                                                    </div>
                                                </div>
                                            `
                                            : html`
                                                <div class="card">
                                                    <div class="plot-container" id="area-gender">
                                                        <h2 class="plot-title">
                                                            Gender ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                                        </h2>
                                                        <div class="plot-subtitle-panel">
                                                            <div class="plot-subtitle">
                                                                Gender is ${generateSubtitle(indicator, indicatorMapping)} as a share of the total
                                                            </div>
                                                        </div>
                                                        ${
                                                            resize(
                                                                (width) => linePlot(
                                                                    relativeData, 
                                                                    "gender", 
                                                                    width
                                                                )
                                                            )
                                                        }
                                                        <div class="bottom-panel">
                                                            <div class="text-section">
                                                                <p class="plot-source">Source: OECD Creditor Reporting System.</p>
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
                                                                        "area-gender",
                                                                         formatString(`gender ODA ${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)} share`, {fileMode: true})                        )
                                                                }
                                                            )
                                                        }
                                                        ${
                                                            Inputs.button(
                                                                "Download data", 
                                                                {
                                                                    reduce: () => downloadXLSX(
                                                                        relativeData,
                                                                        formatString(`gender ODA ${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)} share`, {fileMode: true})                        )
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
                                        Gender ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
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
                                                            "gender",
                                                            {}
                                                        )
                                                    }
                                                    <div class="bottom-panel">
                                                        <div class="text-section">
                                                            <p class="plot-source">Source: OECD DAC Table Creditor Reporting System.</p>
                                                            ${
                                                                unit === "value" 
                                                                    ? html`<p class="plot-note">ODA values in ${prices}  ${prices === "constant" ? timeRangeOptions.base: ""} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>`
                                                                    : unit === "total"
                                                                        ? html`<p class="plot-note">ODA values as a share of total aid received by ${getNameByCode(recipientMapping, recipient)}.</p>`
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
                                                                             formatString(`gender ODA ${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)} ${unit}`, {fileMode: true})                    )
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