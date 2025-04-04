```js 
import {setCustomColors} from "./components/colors.js"
import {formatString, getCurrencyLabel, name2CodeMap, getNameByCode, generateIndicatorMap} from "./components/utils.js";
import {genderQueries} from "./components/genderQueries.js"
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

const recipientOptions = await FileAttachment("./data/analysis_tools/recipients.json").json()
const recipientMapping = name2CodeMap(recipientOptions)

const indicatorOptions = await FileAttachment("./data/analysis_tools/gender_indicators.json").json()
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
```
    
```js
// Unit
const unitInput = Inputs.select(
    new Map(
        [
            [`Million ${getCurrencyLabel(currency, {currencyOnly: true,})}`, "value"],
            ["% of total ODA", "total"]
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
// DATA QUERY
const data = genderQueries(
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
                                        <div class="plot-container" id="bars-gender">
                                            <h2 class="plot-title">
                                                ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                            </h2>
                                            <div class="plot-subtitle-panel">
                                                <div class="plot-subtitle">
                                                    Gender is
                                                    ${generateSubtitle(indicator, indicatorMapping)}
                                                </div>
                                            </div>
                                            ${
                                                resize(
                                                    (width) => barPlot(
                                                        absoluteData, 
                                                        currency, 
                                                        "gender", 
                                                        width
                                                    )
                                                )
                                            }
                                            <div class="bottom-panel">
                                                <div class="text-section">
                                                    <p class="plot-source">Source: OECD Creditor Reporting System.</p>
                                                    <p class="plot-note">ODA values in ${prices} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>
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
                                    <div class="card">
                                        <div class="plot-container" id="lines-gender">
                                            <h2 class="plot-title">
                                                ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                            </h2>
                                            <div class="plot-subtitle-panel">
                                                <div class="plot-subtitle">
                                                    Gender is
                                                    ${generateSubtitle(indicator, indicatorMapping)}
                                                    as a share of total ODA
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
                                                            "lines-gender",
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
                                </div>
                                <div class="card">
                                    <div class="plot-container">
                                        <h2 class="table-title">
                                            Gender ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
                                        </h2>
                                        <div class="table-subtitle-panel">
                                            ${unitInput}
                                        </div>
                                        ${
                                            sparkbarTable(
                                                tableData, 
                                                "gender"
                                            )
                                        }
                                        <div class="bottom-panel">
                                            <div class="text-section">
                                                <p class="plot-source">Source: OECD DAC Table Creditor Reporting System.</p>
                                                ${
                                                    unit === "value" 
                                                        ? html`<p class="plot-note">ODA values in ${prices} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>`
                                                        : unit === "total"
                                                            ? html`<p class="plot-note">ODA values as a share of total aid received by ${getNameByCode(recipientMapping, recipient)}.</p>`
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
                                                             formatString(`gender ODA ${getNameByCode(donorMapping, donor)} ${getNameByCode(recipientMapping, recipient)} ${unit}`, {fileMode: true})                    )
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