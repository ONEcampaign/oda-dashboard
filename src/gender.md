```js 
import {setCustomColors} from "./components/colors.js"
import {formatString, convertUint32Array, name2CodeMap} from "./components/utils.js";

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
        ["Gender total", 3],
        ["Principal focus", 2],
        ["Significant focus", 1],
        ["Not targeted", 0],
    ]),
    {
        label: "Indicator",
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
${Inputs.table(relativeData)}
<div class="grid grid-cols-2">
    <div class="card">
        <div class="plot-container" id="bars-gender">
            <h2 class="plot-title">
            </h2>
            <div class="plot-subtitle-panel">
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
                <div class="logo-section">
                    <a href="https://data.one.org/" target="_blank">
                        <img src="./ONE-logo-black.png" alt="A black circle with ONE written in white thick letters.">
                    </a>
                </div>
            </div>
        </div>
        <div class="download-panel">
        </div>
    </div>
    <div class="card">
        <div class="plot-container" id="bars-gender">
            <h2 class="plot-title">
            </h2>
            <div class="plot-subtitle-panel">
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
                <div class="logo-section">
                    <a href="https://data.one.org/" target="_blank">
                        <img src="./ONE-logo-black.png" alt="A black circle with ONE written in white thick letters.">
                    </a>
                </div>
            </div>
        </div>
        <div class="download-panel">
        </div>
    </div>
</div>

<div class="card">
</div>