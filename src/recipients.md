```js 
import {DuckDBClient} from "npm:@observablehq/duckdb";

import {setCustomColors} from "./components/colors.js"
import {formatString, convertUint32Array} from "./components/utils.js";

import {uniqueValuesRecipients} from "./components/uniqueValuesRecipients.js";
import {rangeInput} from "./components/rangeInput.js";

import {barPlot, linePlot, sparkbarTable} from "./components/visuals.js";

import {downloadPNG, downloadXLSX} from './components/downloads.js';
```

```js
setCustomColors();
```

```js
const db = DuckDBClient.of({
    recipients: FileAttachment("./data/recipients.parquet")
});
```

```js
// USER INPUTS
const donorRecipientsInput = Inputs.select(
    uniqueValuesRecipients.donors,
    {
        label: "Donor",
        value: "DAC Countries, Total",
        sort: true
    })
const donorRecipients = Generators.input(donorRecipientsInput);

// Recipient
const recipientRecipientsInput = Inputs.select(
    uniqueValuesRecipients.recipients,
    {
        label: "Recipient",
        value: "Developing countries, Total",
        sort: true
    })
const recipientRecipients = Generators.input(recipientRecipientsInput);

// Indicator
const indicatorRecipientsInput = Inputs.select(
    uniqueValuesRecipients.indicators,
    {
        label: "Indicator",
        value: "Total",
        sort: true
    })
const indicatorRecipients = Generators.input(indicatorRecipientsInput);

// Currency
const currencyRecipientsInput = Inputs.select(
    uniqueValuesRecipients.currencies,
    {
        label: "Currency",
        value: "US Dollars",
        sort: true
    })
const currencyRecipients = Generators.input(currencyRecipientsInput);

// Prices
const pricesRecipientsInput = Inputs.radio(
    uniqueValuesRecipients.prices,
    {
        label: "Prices",
        value: "Constant"
    }
)
const pricesRecipients = Generators.input(pricesRecipientsInput)

// Year
const timeRangeRecipientsInput = rangeInput(
    {
        min: uniqueValuesRecipients.timeRange[0],
        max: uniqueValuesRecipients.timeRange[1],
        step: 1,
        value: [
            uniqueValuesRecipients.timeRange[0],
            uniqueValuesRecipients.timeRange[1]
        ],
        label: "Time range",
        enableTextInput: true
    })
const timeRangeRecipients = Generators.input(timeRangeRecipientsInput)

// Unit
const unitRecipientsInput = Inputs.select(
    new Map(
        [
            [`Million ${currencyRecipientsInput.value}`, "Value"],
            ["GNI Share", "GNI Share"],
            ["Share of total", "Share of total"]
        ]
    ),
    {
        label: "Unit",
        value: "Value",
    }
)

const unitRecipients = Generators.input(unitRecipientsInput)

function updateUnitOptions() {
    for (const o of unitRecipientsInput.querySelectorAll("option")) {
        if (o.innerHTML === "Share of total" & indicatorRecipientsInput.value === "Total") {
            o.setAttribute("disabled", "disabled");
        }
        else o.removeAttribute("disabled");
    }
}

updateUnitOptions();
indicatorRecipientsInput.addEventListener("input", updateUnitOptions);
```

```js
// DATA QUERY
const queryRecipientsString = `
SELECT 
    year AS Year,
    "Donor Name" AS Donor,
    "Recipient Name" AS Recipient,
    Indicator,
    value AS Value,
    share AS "Share of total",
    "GNI Share",
    Currency,
    Prices
FROM recipients
WHERE 
    Year >= ? AND 
    Year <= ? AND
    Donor = ? AND 
    Recipient = ? AND
    Currency = ? AND 
    Prices = ? AND
    (
        (? = 'Total' AND Indicator != 'Total') 
        OR (? != 'Total' AND Indicator = ?)
    );
`;

const queryRecipientsParams = [
    timeRangeRecipients[0],
    timeRangeRecipients[1],
    donorRecipients,
    recipientRecipients,
    currencyRecipients,
    pricesRecipients,
    indicatorRecipients,
    indicatorRecipients,
    indicatorRecipients,
];

const queryRecipients = await db.query(queryRecipientsString, queryRecipientsParams);

const dataRecipients = queryRecipients.toArray()
    .map((row) => ({
        ...row,
        ["Value"]: convertUint32Array(row["Value"]),
        ["GNI Share"]: convertUint32Array(row["GNI Share"]),
        ["Share of total"]: convertUint32Array(row["Share of total"])
    }))
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
    <a class="view-button">
        Gender
    </a>
</div>

<div class="settings card">
    <div class="settings-group">
        ${donorRecipientsInput}
        ${recipientRecipientsInput}
    </div>
    <div class="settings-group">
        ${currencyRecipientsInput}
        ${indicatorRecipientsInput}
    </div>
    <div class="settings-button">
        ${showMoreButton}
    </div>
    <div class="settings-group hidden">
        ${pricesRecipientsInput}
        ${timeRangeRecipientsInput}
    </div>
</div>
<div class="grid grid-cols-2">
    <div class="card">
        <div class="plot-container" id="bars-recipients">
            <h2 class="plot-title">
                ${formatString(`ODA to ${recipientRecipients} from ${donorRecipients}`)}
            </h2>
            <div class="plot-subtitle-panel">
                ${
                    indicatorRecipients == "Total"
                    ? html`<h3 class="plot-subtitle"><span class="bilateral-label subtitle-label">Bilateral</span> and <span class="multilateral-label subtitle-label">imputed multilateral</span></h3>`
                    : html`<h3 class="plot-subtitle">${indicatorRecipients}</h3>`
                }
            </div>
            ${
                resize(
                    (width) => barPlot(
                        dataRecipients, 
                        currencyRecipients, 
                        "recipients", 
                        width
                    )
                )
            }
            <div class="bottom-panel">
                <div class="text-section">
                    <p class="plot-source">Source: OECD DAC Table 2a.</p>
                    <p class="plot-note">ODA values in million ${pricesRecipients} ${currencyRecipients}.</p>
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
                             formatString(`ODA to ${recipientRecipients} from ${donorRecipients}`, {fileMode: true})
                        )
                    }
                )
            }
        </div>
    </div>
    <div class="card">
        <div class="plot-container" id="lines-recipients">
            <h2 class="plot-title">
                ${formatString(`ODA to ${recipientRecipients} from ${donorRecipients}`)}
            </h2>
            <div class="plot-subtitle-panel">
                ${
                    indicatorRecipients == "Total"
                    ? html`<h3 class="plot-subtitle"><span class="bilateral-label-subtitle">Bilateral</span> and <span class="multilateral-label-subtitle">imputed multilateral</span> as a share of total ODA</h3>`
                    : html`<h3 class="plot-subtitle">${indicatorRecipients} as a share of all ODA</h3>`
                }
            </div>
            ${
                resize(
                    (width) => linePlot(
                        dataRecipients,
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
                             formatString(`ODA to ${recipientRecipients} from ${donorRecipients}_share`, {fileMode: true})
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
            ${formatString(`ODA to ${recipientRecipients} from ${donorRecipients}`)}
        </h2>
        <div class="table-subtitle-panel">
            ${unitRecipientsInput}
        </div>
        ${sparkbarTable(dataRecipients, "recipients", {unit: unitRecipients})}
        <div class="bottom-panel">
            <div class="text-section">
                <p class="plot-source">Source: OECD DAC Table 2a.</p>
                ${
                    unitRecipients === "Value" 
                    ? html`<p class="plot-note">ODA values in million ${pricesRecipients} ${currencyRecipients}.</p>`
                    : unitRecipients === "GNI Share" 
                        ? html`<p class="plot-note">ODA values as a share of the GNI of ${formatString(recipientRecipients)}.</p>`
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
                        dataRecipients,
                        formatString(`ODA to ${recipientRecipients} from ${donorRecipients}`, {fileMode: true})
                    )
                }
            )
        }
    </div>
</div>