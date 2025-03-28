```js 
import {setCustomColors} from "./components/colors.js"
import {recipientsQueries} from './components/dataQueries.js'
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

const recipientOptions = await FileAttachment("./data/analysis_tools/recipient_mapping.json").json()
const recipientMapping = name2CodeMap(recipientOptions)

const indicatorOptions = await FileAttachment("./data/analysis_tools/indicators.json").json()
const indicatorMapping = generateIndicatorMap(indicatorOptions, "recipients")
```

```js
// USER INPUTS
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
        value: recipientMapping.get("Developing countries")
    })
const recipient = Generators.input(recipientInput);

// Indicator
const indicatorInput = Inputs.checkbox(
    indicatorMapping,
    {
        label: "Indicator",
        value: [indicatorMapping.get("Bilateral"), indicatorMapping.get("Imputed multilateral")],
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
            ["GNI Share", "GNI Share"],
            ["Share of total", "Share of total"]
        ]
    ),
    {
        label: "Unit",
        value: "Value",
    }
)

const unit = Generators.input(unitInput)

function updateUnitOptions() {
    for (const o of unitInput.querySelectorAll("option")) {
        if (o.innerHTML === "Share of total" & indicatorInput.value === "Total") {
            o.setAttribute("disabled", "disabled");
        }
        else o.removeAttribute("disabled");
    }
}

updateUnitOptions();
indicatorInput.addEventListener("input", updateUnitOptions);
```

```js
// DATA QUERY
const data = recipientsQueries(
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

console.log(donorMapping.get("Austria"))
```

<div class="title-container" xmlns="http://www.w3.org/1999/html">
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
</div>

<div class="settings card">
    <div class="settings-group">
        ${donorInput}
        ${recipientInput}
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
        <div class="plot-container" id="bars-recipients">
            <h2 class="plot-title">
                ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
            </h2>
            <div class="plot-subtitle-panel">
                ${
                    indicator.length > 1
                    ? html`<h3 class="plot-subtitle"><span class="bilateral-label subtitle-label">Bilateral</span> and <span class="multilateral-label subtitle-label">imputed multilateral</span> aid</h3>`
                    : html`<h3 class="plot-subtitle">${getNameByCode(indicatorMapping, indicator)} aid</h3>`
                }
            </div>
            ${
                resize(
                    (width) => barPlot(
                        absoluteData, 
                        currency, 
                        "recipients", 
                        width
                    )
                )
            }
            <div class="bottom-panel">
                <div class="text-section">
                    <p class="plot-source">Source: OECD DAC Table 2a.</p>
                    <p class="plot-note">ODA values in ${prices} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>
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
                    "Download plot", {
                         reduce: () => downloadPNG(
                             "bars-recipients",
                             formatString(`ODA to ${recipient} from ${donor}`, {fileMode: true})
                        )
                    }
                )
            }
        </div>
    </div>
    <div class="card">
        <div class="plot-container" id="lines-recipients">
            <h2 class="plot-title">
                ODA to ${getNameByCode(recipientMapping, recipient)} from ${getNameByCode(donorMapping, donor)}
            </h2>
            <div class="plot-subtitle-panel">
                ${
                    indicator.length > 1
                    ? html`<h3 class="plot-subtitle"><span class="bilateral-label subtitle-label">Bilateral</span> and <span class="multilateral-label subtitle-label">imputed multilateral</span> as a share of total aid</h3>`
                    : html`<h3 class="plot-subtitle">${getNameByCode(indicatorMapping, indicator)} as a share of total aid</h3>`
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
                    <p class="plot-source">Source: OECD DAC Table 2a.</p>
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
                    "Download plot", {
                        reduce: () => downloadPNG(
                            "lines-recipients",
                             formatString(`ODA to ${recipient} from ${donor}_share`, {fileMode: true})
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
            ${unitInput}
        </div>
        ${sparkbarTable(data, "recipients", {unit: unit})}
        <div class="bottom-panel">
            <div class="text-section">
                <p class="plot-source">Source: OECD DAC Table 2a.</p>
                ${
                    unit === "Value" 
                    ? html`<p class="plot-note">ODA values in ${prices} ${getCurrencyLabel(currency, {currencyLong: true, inSentence: true})}.</p>`
                    : unit === "GNI Share" 
                        ? html`<p class="plot-note">ODA values as a share of the GNI of ${formatString(recipient)}.</p>`
                        : html` `
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
                "Download data", {
                    reduce: () => downloadXLSX(
                        data,
                        formatString(`ODA to ${recipient} from ${donor}`, {fileMode: true})
                    )
                }
            )
        }
    </div>
</div>