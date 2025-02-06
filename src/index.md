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
    financing: FileAttachment("./data/financing.parquet"),
    recipients: FileAttachment("./data/recipients.parquet"),
    sectors: FileAttachment("./data/sectors.parquet")
});
```

```js
// USER INPUTS

// FINANINCING VIEW
// Donor
const donorFinancingInput = Inputs.select(
    uniqueValuesFinancing.donors,
    {
        label: "Donor",
        value: "DAC Countries, Total",
        sort: true
    })
const donorFinancing = Generators.input(donorFinancingInput);

// Indicator
const indicatorFinancingInput = Inputs.select(
    uniqueValuesFinancing.indicators,
    {
        label: "Indicator",
        value: "Total ODA"
    })
const indicatorFinancing = Generators.input(indicatorFinancingInput);

// Type
const typeFinancingInput = Inputs.select(
    uniqueValuesFinancing.indicatorTypes,
    {
        label: "Type",
        value: "Official Definition",
        sort: true
    })
const typeFinancing = Generators.input(typeFinancingInput);

// Currency
const currencyFinancingInput = Inputs.select(
    uniqueValuesFinancing.currencies,
    {
        label: "Currency",
        value: "US Dollars",
        sort: true
    })
const currencyFinancing = Generators.input(currencyFinancingInput);

// Prices
const pricesFinancingInput = Inputs.radio(
    uniqueValuesFinancing.prices,
    {
        label: "Prices",
        value: "Constant"
    }
)
const pricesFinancing = Generators.input(pricesFinancingInput)

// Year
const timeRangeFinancingInput = rangeInput(
    {
        min: uniqueValuesFinancing.timeRange[0],
        max: uniqueValuesFinancing.timeRange[1],
        step: 1,
        value: [
            uniqueValuesFinancing.timeRange[0],
            uniqueValuesFinancing.timeRange[1]
        ],
        label: "Time range",
        enableTextInput: true
    })
const timeRangeFinancing = Generators.input(timeRangeFinancingInput)

// Unit
const unitFinancingInput = Inputs.radio(
    ["Value", "GNI Share"],
    {
        label: null,
        value: "Value"
    }
)
const unitFinancing = Generators.input(unitFinancingInput)

// RECIPIENT VIEW
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

// SECTORS VIEW
// Donor
const donorSectorsInput = Inputs.select(
    uniqueValuesSectors.donors,
    {
        label: "Donor",
        value: "DAC Countries, Total",
        sort: true
    })
const donorSectors = Generators.input(donorSectorsInput);

// Recipient
const recipientSectorsInput = Inputs.select(
    uniqueValuesSectors.recipients,
    {
        label: "Recipient",
        value: "Developing Countries, Total",
        sort: true
    })
const recipientSectors = Generators.input(recipientSectorsInput);

// Indicator
const indicatorSectorsInput = Inputs.select(
    uniqueValuesSectors.indicators,
    {
        label: "Indicator",
        value: "Total",
        sort: true
    })
const indicatorSectors = Generators.input(indicatorSectorsInput);

// Currency
const currencySectorsInput = Inputs.select(
    uniqueValuesSectors.currencies,
    {
        label: "Currency",
        value: "US Dollars",
        sort: true
    })
const currencySectors = Generators.input(currencySectorsInput);

// Prices
const pricesSectorsInput = Inputs.radio(
    uniqueValuesSectors.prices,
    {
        label: "Prices",
        value: "Constant"
    }
)
const pricesSectors = Generators.input(pricesSectorsInput)

// Year
const timeRangeSectorsInput = rangeInput(
    {
        min: uniqueValuesSectors.timeRange[0],
        max: uniqueValuesSectors.timeRange[1],
        step: 1,
        value: [
            uniqueValuesSectors.timeRange[0],
            uniqueValuesSectors.timeRange[1]
        ],
        label: "Time range",
        enableTextInput: true
    })
const timeRangeSectors = Generators.input(timeRangeSectorsInput)

// Breakdown
const breakdownSectorsInput = Inputs.radio(
    new Map([
        ["Total", "Sector"],
        ["Breakdown", "Subsector"]
    ]),
    {
        value: "Sector"
    }
)
const breakdownSectors = Generators.input(breakdownSectorsInput)

// Unit
const unitSectorsInput = Inputs.radio(
    ["Value", "Share of total", "Share of indicator", "GNI Share"],
    {
        label: null,
        value: "Value"
    }
)
const unitSectors = Generators.input(unitSectorsInput)
```

```js
// DATA QUERIES

// FINANINCING VIEW
const queryFinancingString = `
SELECT 
    year AS Year,
    "Donor Name" AS Donor,
    Indicator,
    CASE 
        WHEN "Indicator Type" = 'Official Definition' AND Year < 2018 THEN 'Flow'
        WHEN "Indicator Type" = 'Official Definition' AND Year >= 2018 THEN 'Grant Equivalent'
        ELSE "Indicator Type"
    END AS Type,
    value AS Value,
    "GNI Share",
    Currency,
    Prices,
FROM financing
WHERE 
    Year >= ? AND 
    Year <= ? AND
    Donor = ? AND 
    Indicator = ? AND
    "Indicator Type" = ? AND 
    Currency = ? AND 
    Prices = ?;
`;

const queryFinancingParams = [
    timeRangeFinancing[0],
    timeRangeFinancing[1],
    donorFinancing,
    indicatorFinancing,
    typeFinancing,
    currencyFinancing,
    pricesFinancing
    
];

const queryFinancing = await db.query(queryFinancingString, queryFinancingParams);

// RECIPIENTS VIEW
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

// SECTORS VIEW
const querySectorsString = `
SELECT 
    year AS Year,
    "Donor Name" AS Donor,
    "Recipient Name" AS Recipient,
    Indicator,
    Sector,
    Subsector,
    value AS Value,
    share_of_total AS "Share of total",
    share_of_indicator AS "Share of indicator",
    "GNI Share",
    Currency,
    Prices
FROM sectors
WHERE 
    Year >= ? AND 
    Year <= ? AND
    Donor = ? AND 
    Recipient = ? AND
    Currency = ? AND 
    prices = ? AND
    (
        (? = 'Total' AND Indicator != 'Total') 
        OR (? != 'Total' AND Indicator = ?)
    );
`;

const querySectorsParams = [
    timeRangeSectors[0],
    timeRangeSectors[1],
    donorSectors,
    recipientSectors,
    currencySectors,
    pricesSectors,
    indicatorSectors,
    indicatorSectors,
    indicatorSectors
];

const querySectors = await db.query(querySectorsString, querySectorsParams);
```

```js
const viewSelection = Mutable("Financing")
const selectFinancing = () => viewSelection.value = "Financing";
const selectRecipients = () => viewSelection.value = "Recipients";
const selectSectors = () => viewSelection.value = "Sectors"
const selectGender = () => viewSelection.value = "Gender"
```

```js
const moreSettingsFinancing = Mutable(false)
const showMoreSettingsFinancing = () => {
    moreSettingsFinancing.value = !moreSettingsFinancing.value;
};

const moreSettingsRecipients = Mutable(false)
const showMoreSettingsRecipients = () => {
    moreSettingsRecipients.value = !moreSettingsRecipients.value;
};

const moreSettingsSectors = Mutable(false)
const showMoreSettingsSectors = () => {
    moreSettingsSectors.value = !moreSettingsSectors.value;
};
```

```html
<div class="header card" style="display: flex; flex-flow: row nowrap">
    <div class="view-button ${viewSelection === 'Financing' ? 'active' : ''}">
        ${Inputs.button("Financing", {reduce: selectFinancing})}
    </div>
    <div class="view-button ${viewSelection === 'Recipients' ? 'active' : ''}">
        ${Inputs.button("Recipients", {reduce: selectRecipients})}
    </div>
    <div class="view-button ${viewSelection === 'Sectors' ? 'active' : ''}">
        ${Inputs.button("Sectors", {reduce: selectSectors})}
    </div>
    <div class="view-button ${viewSelection === 'Gender' ? 'active' : ''}">
        ${Inputs.button("Gender", {reduce: selectGender})}
    </div>
</div>

<div class="view-box ${viewSelection === 'Financing' ? 'active' : ''}">

    <div class="settings card">
        <div class="settings-group">
            ${donorFinancingInput}
        </div>
        <div class="settings-group">
            ${currencyFinancingInput}
            ${indicatorFinancingInput}
        </div>
        <div class="settings-button ${moreSettingsFinancing ? 'active' : ''}">
            ${Inputs.button( moreSettingsFinancing ? "Show less" : "Show more", {reduce: showMoreSettingsFinancing})}
        </div>
        <div class="settings-group" style="visibility: ${moreSettingsFinancing ? 'block' : 'hidden'}">
            ${pricesFinancingInput}
            ${timeRangeFinancingInput}
        </div>
    </div>

    <div class="grid grid-cols-2">
        
        <div class="card">
            <div  class="plot-container" id="bars-financing">
                <h2 class="plot-title">
                    ${formatString(`${indicatorFinancing} from ${donorFinancing}`)}
                </h2>
                ${
                    typeFinancing == "Official Definition"
                    ? html`<h3 class="plot-subtitle"><span class="flow-label-subtitle">Flows</span> and <span class="ge-label-subtitle">grant equivalents</span></h3>`
                    : html`<h3 class="plot-subtitle">${typeFinancing}</h3>`
                }
                ${
                    resize(
                        (width) => barPlot(queryFinancing, currencyFinancing, "financing", width)
                    )
                }
                <div class="bottom-panel">
                    <div class="text-section">
                        <p class="plot-source">Source: OECD DAC Table 1.</p>
                        <p class="plot-note">ODA values in million ${pricesFinancing} ${currencyFinancing}.</pclass>
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
                                "bars-financing",
                                "plot1_test"
                            )
                        }   
                    )
                }
            </div>
            
        </div>
        
        <div class="card">
            <div class="plot-container" id="lines-financing">
                <h2 class="plot-title">
                    ${formatString(`${indicatorFinancing} from ${donorFinancing}`)}
                </h2>
                ${
                    typeFinancing == "Official Definition"
                    ? html`<h3 class="plot-subtitle"><span class="flow-label-subtitle">Flows</span> and <span class="ge-label-subtitle">grant equivalents</span> as a share of GNI</h3>`
                    : html`<h3 class="plot-subtitle">${typeFinancing}</h3>`
                }
                ${
                    resize(
                        (width) => linePlot(
                            queryFinancing, 
                            "financing", 
                            width
                        )
                    )
                }
                <div class="bottom-panel">
                    <div class="text-section">
                        <p class="plot-source">Source: OECD DAC Table 1.</p>
                        <p class="plot-note">GNI share refers to the Gross National Income of ${formatString(donorFinancing)}.</p>
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
                                "lines-financing",
                                "plot2_test"
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
                ${formatString(`${indicatorFinancing} from ${donorFinancing}`)}
            </h2>
            <div class="table-settings">
                ${unitFinancingInput}
            </div>
            ${table(queryFinancing, "financing", {unit: unitFinancing})}
            <div class="bottom-panel">
                <div class="text-section">
                    <p class="plot-source">Source: OECD DAC Table 1.</p>
                    <p class="plot-note">ODA values in million ${pricesFinancing} ${currencyFinancing}. GNI share refers to the Gross National Income of ${formatString(donorFinancing)}.</pclass>
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
                            queryFinancing,
                            "file1_test"
                         )
                     }
                )
            }
        </div>
    </div>
    
</div>

<div class="view-box ${viewSelection === 'Recipients' ? 'active' : ''}">

    <div class="settings card">
        <div class="settings-group">
            ${donorRecipientsInput}
            ${recipientRecipientsInput}
        </div>
        <div class="settings-group">
            ${currencyRecipientsInput}
            ${indicatorRecipientsInput}
        </div>
        <div class="settings-button ${moreSettingsRecipients ? 'active' : ''}">
            ${Inputs.button( moreSettingsRecipients ? "Show less" : "Show more", {reduce: showMoreSettingsRecipients})}
        </div>
        <div class="settings-group" style="visibility: ${moreSettingsRecipients ? 'block' : 'hidden'}">
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
    
</div>

<div class="view-box ${viewSelection === 'Sectors' ? 'active' : ''}">

    <div class="settings card">
        <div class="settings-group">
            ${donorSectorsInput}
            ${recipientSectorsInput}
        </div>
        <div class="settings-group">
            ${currencySectorsInput}
            ${indicatorSectorsInput}
        </div>
        <div class="settings-button ${moreSettingsSectors ? 'active' : ''}">
            ${Inputs.button( moreSettingsSectors ? "Show less" : "Show more", {reduce: showMoreSettingsSectors})}
        </div>
        <div class="settings-group" style="visibility: ${moreSettingsSectors ? 'block' : 'hidden'}">
            ${pricesSectorsInput}
            ${timeRangeSectorsInput}
        </div>
    </div>
    
    <div class="grid grid-cols-2">
        
        <div class="card">
            <div class="plot-container" id="treemap-sectors">
                <h2 class="plot-title">
                    ${formatString(`ODA to ${recipientSectors} from ${donorSectors} by sector`)}
                </h2>
                ${
                    indicatorSectors == "Total"
                    ? html`<h3 class="plot-subtitle">Bilateral and imputed multilateral, ${timeRangeSectors[0] === timeRangeSectors[1] ? timeRangeSectors[0] : `${timeRangeSectors[0]}-${timeRangeSectors[1]}`}</h3>`
                    : html`<h3 class="plot-subtitle">${indicatorSectors}, ${timeRangeSectors[0] === timeRangeSectors[1] ? timeRangeSectors[0] : `${timeRangeSectors[0]}-${timeRangeSectors[1]}`}</h3>`
                }
                ${
                    resize(
                        (width) =>
                        treemapPlot(querySectors, width, {currency: currencySectors})
                    )
                }
                <div class="bottom-panel">
                    <div class="text-section">
                        <p class="plot-source">Source: OECD DAC Creditor Reporting System database.</p>
                        <p class="plot-note">ODA values in million ${pricesSectors} ${currencySectors}.</p>
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
                                "treemap-sectors",
                                "plot5_test"
                            )
                        }
                    )
                }
            </div>
        </div>
        
        <div class="card">
            <div class="plot-container" id="lines-sectors">
                <h2 class="plot-title">
                    ${formatString(`ODA to ${recipientSectors} from ${donorSectors}`)}
                </h2>
                ${
                    indicatorSectors == "Total"
                    ? html`<h3 class="plot-subtitle">${selectedSector}, bilateral and imputed multilateral</h3>`
                    : html`<h3 class="plot-subtitle">${selectedSector}, ${indicatorSectors}</h3>`
                }
                <div class="plot-settings">
                    ${breakdownSectorsInput}
                </div>
                ${
                    resize(
                        (width) => linePlot(
                            querySectors, 
                            "sectors", 
                            width,
                            {   
                                sectorName: selectedSector,
                                currency: currencySectors,
                                breakdown: breakdownSectors
                
                            }
                        )
                    )
                }
                <div class="bottom-panel">
                    <div class="text-section">
                        <p class="plot-source">Source: OECD DAC Creditor Reporting System database.</p>
                        <p class="plot-note">ODA values in million ${pricesSectors} ${currencySectors}.</pclass>
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
                                "lines-sectors",
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
                ${formatString(`ODA to ${recipientSectors} from ${donorSectors}, ${indicatorSectors}`)}
            </h2>
            ${
                indicatorSectors == "Total"
                ? html`<h3 class="table-subtitle">Breakdown of ${selectedSector}, bilateral and imputed multilateral</h3>`
                : html`<h3 class="table-subtitle">Breakdown of ${selectedSector}, ${indicatorSectors}</h3>`
            }
            <div class="table-settings">
                ${unitSectorsInput}
            </div>
            ${table(querySectors, "sectors", {unit: unitSectors, sectorName: selectedSector})}
            <div class="bottom-panel">
                <div class="text-section">
                    <p class="plot-source">Source: OECD DAC Creditor Reporting System database.</p>
                    <p class="plot-note">ODA values in million ${pricesSectors} ${currencySectors}. GNI share refers to the Gross National Income of ${formatString(recipientSectors)}.</pclass>
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
                            querySectors,
                            "file3_test"
                        )
                    }
                )
            }
        </div>
    </div>

</div>

```