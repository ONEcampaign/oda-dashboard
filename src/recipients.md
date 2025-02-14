```js 
import {DuckDBClient} from "npm:@observablehq/duckdb";

import {setCustomColors} from "./components/setCustomColors.js";

import {uniqueValuesFinancing} from "./components/uniqueValuesFinancing.js";
import {uniqueValuesRecipients} from "./components/uniqueValuesRecipients.js";
import {uniqueValuesSectors} from "./components/uniqueValuesSectors.js";

import {rangeInput} from "./components/rangeInput.js";

import {formatString} from "./components/formatString.js";

import {barPlot} from "./components/barPlot.js";
import {linePlot} from "./components/linePlot.js";
import {treemapPlot, selectedSector} from "./components/treemapPlot.js";

import {table} from "./components/table.js";

import {downloadPNG} from './components/downloadPNG.js';
import {downloadXLSX} from "./components/downloadXLSX.js";
```

```js
setCustomColors();
```

```js
const oneLogo = FileAttachment("./ONE-logo-black.png").href;
```

```js
const db = DuckDBClient.of({
    recipients: FileAttachment("./data/recipients.parquet")
});
```

```js
// USER INPUTS
// Donor
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
const unitRecipientsInput = Inputs.radio(
    ["Value", "Share of total", "GNI Share"],
    {
        label: null,
        value: "Value"
    }
)
const unitRecipients = Generators.input(unitRecipientsInput)
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
```

```js
const moreSettings = Mutable(false)
const showmoreSettings = () => {
    moreSettings.value = !moreSettings.value;
};
```

```html
<div class="title-container" xmlns="http://www.w3.org/1999/html">
    <div class="title-logo">
        <a href="https://data.one.org/" target="_blank">
            <img src=${oneLogo} alt="A black circle with ONE written in white thick letters.">
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
    <div class="settings-button ${moreSettings ? 'active' : ''}">
        ${Inputs.button( moreSettings ? "Show less" : "Show more", {reduce: showmoreSettings})}
    </div>
    <div class="settings-group ${moreSettings ? '' : 'hidden'}">
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
            ${
            indicatorRecipients == "Total"
            ? html`<h3 class="plot-subtitle"><span class="bilateral-label-subtitle">Bilateral</span> and <span class="multilateral-label-subtitle">imputed multilateral</span></h3>`
            : html`<h3 class="plot-subtitle">${indicatorRecipients}</h3>`
            }
            ${
            resize(
            (width) => barPlot(queryRecipients, currencyRecipients, "recipients", width)
            )
            }
            <div class="bottom-panel">
                <div class="text-section">
                    <p class="plot-source">Source: OECD DAC Table 2a.</p>
                    <p class="plot-note">ODA values in million ${pricesRecipients} ${currencyRecipients}.</pclass>
                </div>
                <div class="logo-section">
                    <a href="https://data.one.org/" target="_blank">
                        <img src=${oneLogo} alt="A black circle with ONE written in white thick letters.">
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
            "bars-recipients",
            "plot3_test"
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
            ${
            indicatorRecipients == "Total"
            ? html`<h3 class="plot-subtitle"><span class="bilateral-label-subtitle">Bilateral</span> and <span class="multilateral-label-subtitle">imputed multilateral</span> as a share of total ODA</h3>`
            : html`<h3 class="plot-subtitle">${indicatorRecipients} as a share of all ODA</h3>`
            }
            ${
            resize(
            (width) => linePlot(
            queryRecipients,
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
                        <img src=${oneLogo} alt="A black circle with ONE written in white thick letters.">
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
            "lines-recipients",
            "plot4_test"
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
        <div class="table-settings">
            ${unitRecipientsInput}
        </div>
        ${table(queryRecipients, "recipients", {unit: unitRecipients})}
        <div class="bottom-panel">
            <div class="text-section">
                <p class="plot-source">Source: OECD DAC Table 2a.</p>
                <p class="plot-note">ODA values in million ${pricesRecipients} ${currencyRecipients}. GNI share refers to the Gross National Income of ${formatString(recipientRecipients)}.</pclass>
            </div>
            <div class="logo-section">
                <a href="https://data.one.org/" target="_blank">
                    <img src=${oneLogo} alt="A black circle with ONE written in white thick letters.">
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
        queryRecipients,
        "file2_test"
        )
        }
        )
        }
    </div>
</div>
```