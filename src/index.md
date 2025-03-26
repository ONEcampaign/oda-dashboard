```js
import {setCustomColors} from "./components/colors.js"
import {financingQueries} from "./components/dataQueries.js"
import {formatString, getCurrencyLabel, name2CodeMap, getNameByCode, generateIndicatorMap} from "./components/utils.js";
import {rangeInput} from "./components/rangeInput.js";
import {barPlot, linePlot, sparkbarTable} from "./components/visuals.js";
import {downloadPNG, downloadXLSX} from './components/downloads.js';
```

```js
setCustomColors();
```

```js
const donorOptions = await FileAttachment("./data/analysis_tools/donor_mapping.json").json()
const donorMapping = name2CodeMap(donorOptions)

const indicatorOptions = await FileAttachment("./data/analysis_tools/indicators.json").json()
const indicatorMapping = generateIndicatorMap(indicatorOptions, "financing")
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
        ["Current", "current"],
        // ["Constant", "constant"]
    ]),
    {
        label: "Prices",
        value: "current"
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

// Unit
const unitInput = Inputs.select(
    new Map(
        [
            [`Million ${currencyInput.value}`, "Value"],
            ["GNI Share", "GNI Share"]
        ]
    ),
    {
        label: "Unit",
        value: "Value"
    }
)
const unit = Generators.input(unitInput)

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
    timeRange
)

const absoluteData = data.absolute
const relativeData = data.relative
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
        ${donorInput}
    </div>
    <div class="settings-group">
        ${currencyInput}
        ${indicatorInput}
    </div>
    <div class="settings-button">
        ${showMoreButton}
    </div>
    <div class="settings-group hidden">
        ${pricesInput}
        ${timeRangeInput}
    </div>
</div>

<div class="grid grid-cols-2">
    <div class="card">
        <div  class="plot-container" id="bars-financing">
            <h2 class="plot-title">
                ${formatString(`${getNameByCode(indicatorMapping, indicator)} from ${getNameByCode(donorMapping, donor)}`)}
            </h2>
            <div class="plot-subtitle-panel">
                <h3 class="plot-subtitle">
                    <span class="flow-label subtitle-label">Flows</span> and <span class="ge-label  subtitle-label">grant equivalents</span>
                </h3>
            </div>
            ${
                resize(
                    (width) => barPlot(
                        absoluteData, 
                        currency, 
                        "financing", 
                        width
                    )
                )
            }
            <div class="bottom-panel">
                <div class="text-section">
                    <p class="plot-source">Source: OECD DAC Table 1.</p>
                    <p class="plot-note">ODA values in million ${prices} ${getCurrencyLabel(currency, {preffixOnly: true})}.</p>                </div>
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
                            formatString(`${getNameByCode(indicatorMapping, indicator)} from ${getNameByCode(donorMapping, donor)}`, {fileMode: true})
                        )
                    }   
                )
            }
        </div>
    </div>
    <div class="card">
        <div class="plot-container" id="lines-financing">
            <h2 class="plot-title">
                ${formatString(`${getNameByCode(indicatorMapping, indicator)} from ${getNameByCode(donorMapping, donor)}`)}
            </h2>
            <div class="plot-subtitle-panel">
                <h3 class="plot-subtitle">
                ${
                    indicator === indicatorMapping.get("Total ODA") 
                        ? html`<span class="flow-label subtitle-label">Flows</span> and <span class="ge-label subtitle-label">grant equivalents</span> as a share of GNI`
                        : html`<span class="flow-label subtitle-label">Flows</span> and <span class="ge-label subtitle-label">grant equivalents</span> as a share total aid`
                }
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
                    {showIntlCommitment: commitment}
                ))
            }
            <div class="bottom-panel">
                <div class="text-section">
                    <p class="plot-source">Source: OECD DAC Table 1.</p>
                    <p class="plot-note">ODA values as a share of GNI of ${formatString(getNameByCode(donorMapping, donor))}.</p>
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
                            formatString(`${getNameByCode(indicatorMapping, indicator)} from ${donor}_gni_share`, {fileMode: true})
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
            ${formatString(`${getNameByCode(indicatorMapping, indicator)} from ${getNameByCode(donorMapping, donor)}`)}
        </h2>
        <div class="table-subtitle-panel">
            ${unitInput}
        </div>
        ${
            sparkbarTable(
                data, 
                "financing", 
                {unit: unit}
            )
        }
        <div class="bottom-panel">
            <div class="text-section">
                <p class="plot-source">Source: OECD DAC Table 1.</p>
                ${
                    unit === "Value" 
                    ? html`<p class="plot-note">ODA values in million ${prices} ${getCurrencyLabel(currency, {preffixOnly: true})}.</p>`
                    : html`<p class="plot-note">ODA values as a share of the GNI of ${formatString(donor)}.</p>`
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
                        data,
                        formatString(`${getNameByCode(indicatorMapping, indicator)} from ${getNameByCode(donorMapping, donor)}`, {fileMode: true})
                    )
                }
            )
        }
    </div>
</div>