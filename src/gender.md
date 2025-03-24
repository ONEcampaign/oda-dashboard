```js 
import {setCustomColors} from "./components/colors.js"
import {formatString, getCurrencyLabel, name2CodeMap, getKeysByValue} from "./components/utils.js";

import {genderQueries} from "./components/dataQueries.js"

import {uniqueValuesGender} from "./components/uniqueValuesGender.js";
import {rangeInput} from "./components/rangeInput.js";

import {barPlot, linePlot, sparkbarTable} from "./components/visuals.js";

import {downloadPNG, downloadXLSX} from './components/downloads.js';
```

```js
setCustomColors();
```

```js
const donorOptions = await FileAttachment("./data/settings/donors.json").json()
const recipientOptions = await FileAttachment("./data/settings/recipients.json").json()

const donorMapping = name2CodeMap(donorOptions)
const recipientMapping = name2CodeMap(recipientOptions)
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
const indicatorInput = Inputs.select(
    new Map([
        ["Main + secondary focus", 3],
        ["Main focus", 2],
        ["Secondary focus", 1],
        ["Not targeted", 0],
    ]),
    {
        label: "Gender is",
        value: 3
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
        value: "constant"
    }
)
const prices = Generators.input(pricesInput)

// Year
const timeRangeInput = rangeInput(
    {
        min: uniqueValuesGender.timeRange[0],
        max: uniqueValuesGender.timeRange[1],
        step: 1,
        value: [
            uniqueValuesGender.timeRange[1] - 10,
            uniqueValuesGender.timeRange[1]
        ],
        label: "Time range",
        enableTextInput: true
    })
const timeRange = Generators.input(timeRangeInput)

```


```js
// DATA QUERY
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
        <div class="plot-container" id="bars-gender">
            <h2 class="plot-title">
                ODA to ${getKeysByValue(recipientMapping, recipient)} from ${getKeysByValue(donorMapping, donor)}
            </h2>
            <div class="plot-subtitle-panel">
                ${
                    indicator === 3 
                        ? html`<h3 class="plot-subtitle"> Gender as <span class="gender-main subtitle-label">main</span> and <span class="gender-secondary subtitle-label">secondary</span> focus</h3>`
                        : indicator === 2
                            ? html`<h3 class="plot-subtitle"> Gender as main focus</h3>`
                            : indicator === 1
                                ? html`<h3 class="plot-subtitle"> Gender as secondary focus</h3>`
                                : html`<h3 class="plot-subtitle"> Aid that does not target gender</h3>`
                }
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
                    <p class="plot-note">ODA values in million ${prices} ${getCurrencyLabel(currency, {preffixOnly: true})}.</p>
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
                            "bars-gender",
                             formatString(`gender ODA to ${getKeysByValue(donorMapping, donor)} from ${getKeysByValue(recipientMapping, recipient)}`, {fileMode: true})
                        )
                    }
                )
            }
        </div>
    </div>
    <div class="card">
        <div class="plot-container" id="lines-gender">
            <h2 class="plot-title">
                ODA to ${getKeysByValue(recipientMapping, recipient)} from ${getKeysByValue(donorMapping, donor)}
            </h2>
            <div class="plot-subtitle-panel">
                ${
                    indicator === 3 
                        ? html`<h3 class="plot-subtitle"> Gender as <span class="gender-main subtitle-label">main</span> and <span class="gender-secondary subtitle-label">secondary</span> focus as a share of total aid</h3>`
                        : indicator === 2
                            ? html`<h3 class="plot-subtitle"> Gender as main focus as a share of total aid</h3>`
                            : indicator === 1
                                ? html`<h3 class="plot-subtitle"> Gender as secondary focus as a share of total aid</h3>`
                                : html`<h3 class="plot-subtitle"> Aid that does not target gender as a share of total aid</h3>`
                }
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
                            "lines-gender",
                             formatString(`gender ODA to ${getKeysByValue(donorMapping, donor)} from ${getKeysByValue(recipientMapping, recipient)} share`, {fileMode: true})
                        )
                    }
                )
            }
        </div>
    </div>
</div>

<div class="card">
</div>