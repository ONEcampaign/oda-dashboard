```js
import * as React from "npm:react"
import {
    DropdownMenu,
    DropdownMenuMini,
    RangeInput,
    ToggleSwitch,
    ToggleSwitchMini
} from "npm:@one-data/observable-themes/inputs"
import {Header} from "npm:@one-data/observable-themes/ui"
import {ONEVisual, AutoPlot, AutoTable} from "npm:@one-data/observable-themes/charts"
import {getCurrencyLabel, formatString, resolveScale, isEmbedded} from "npm:@one-data/observable-themes/utils"
import {setCustomColors} from "npm:@one-data/observable-themes/colors"
import {
    genderQueries,
    transformTableData,
    donorOptions,
    recipientOptions,
    genderIndicators
} from "./js/genderQueries.js"
import {name2CodeMap, getNameByCode} from "./js/utils.js"
import {customPalette, paletteGender} from "./js/colors.js"
import {columnChart} from "./js/columnChart.js"
import {areaChart} from "./js/areaChart.js"
import {sparkbarTable} from "./js/sparkBarTable.js"
import {APP_TITLE, APP_DESCRIPTION, NAV_ITEMS, CURRENCY_OPTIONS, PRICES_OPTIONS, SCALE} from "./js/config.js"

setCustomColors(customPalette)

const timeRangeOptions = await FileAttachment("./data/analysis_tools/base_time.json").json()

const donorMapping = name2CodeMap(donorOptions, {removeEU27EUI: true})
const recipientMapping = name2CodeMap(recipientOptions, {useRecipientGroups: true})
const indicatorMapping = new Map(
    Object.entries(genderIndicators).map(([k, v]) => [v, Number(k)])
)

const DONOR_OPTIONS = Array.from(donorMapping.entries())
    .map(([label, value]) => ({label, value}))
    .sort((a, b) => a.label.localeCompare(b.label))

const RECIPIENT_OPTIONS = Array.from(recipientMapping.entries())
    .map(([label, value]) => ({label, value}))
    .sort((a, b) => a.label.localeCompare(b.label))

const INDICATOR_OPTIONS = Array.from(indicatorMapping.entries())
    .map(([label, value]) => ({label, value}))

const GENDER_COLOR_MAP = new Map(
    paletteGender.domain.map((name, i) => [name, paletteGender.range[i]])
)
```

```jsx
const MAIN_CODE = indicatorMapping.get("Main target")
const SECONDARY_CODE = indicatorMapping.get("Secondary target")

function buildGenderSubtitle(indicatorCodes, suffix = "") {
  const parts = indicatorCodes.map((code, i) => {
    const name = getNameByCode(indicatorMapping, code) ?? ""
    const color = GENDER_COLOR_MAP.get(name) ?? "inherit"
    const sep = i < indicatorCodes.length - 1 ? ", " : ""
    return `<span style="color:${color}; font-weight:600">${name}</span>${sep}`
  })
  return `Gender is ${parts.join("")}${suffix}`
}

function App() {
  const [donor, setDonor] = React.useState(donorMapping.get("DAC countries"))
  const [recipient, setRecipient] = React.useState(recipientMapping.get("Developing countries"))
  const [indicator, setIndicator] = React.useState([MAIN_CODE, SECONDARY_CODE])
  const [currency, setCurrency] = React.useState("usd")
  const [prices, setPrices] = React.useState("constant")
  const [timeRange, setTimeRange] = React.useState([timeRangeOptions.end - 10, timeRangeOptions.end])
  const [unit, setUnit] = React.useState("value")

  const unitOptions = React.useMemo(() => [
    {label: getCurrencyLabel(currency, {currencyLong: true, currencyOnly: true}), value: "value"},
    {label: "% of all bilateral ODA", value: "total"}
  ], [currency])

  const data = React.useMemo(
    () => indicator.length > 0
      ? genderQueries(donor, recipient, indicator, currency, prices, timeRange)
      : {absolute: [], relative: [], rawData: []},
    [donor, recipient, indicator, currency, prices, timeRange]
  )

  const absoluteData = data?.absolute ?? []
  const relativeData = data?.relative ?? []

  const absoluteScale = React.useMemo(
    () => resolveScale(absoluteData.map(d => d.value), SCALE),
    [absoluteData]
  )
    
    

  const tableData = React.useMemo(
    () => transformTableData(data?.rawData ?? [], unit, currency, prices),
    [data?.rawData, unit, currency, prices]
  )

  const donorName = formatString(getNameByCode(donorMapping, donor) ?? "")
  const recipientName = getNameByCode(recipientMapping, recipient) ?? ""
  const currencyLabel = getCurrencyLabel(currency, {currencyOnly: true, currencyLong: true})
  const pricesNote = `${prices}${prices === "constant" ? ` ${timeRangeOptions.base}` : ""}`

  const columnSubtitle = React.useMemo(
    () => buildGenderSubtitle(indicator),
    [indicator]
  )

  const lineSubtitle = React.useMemo(
    () => buildGenderSubtitle(indicator, " as a share of all bilateral ODA"),
    [indicator]
  )

  const columnPlotFn = React.useCallback(
    (width) => columnChart(absoluteData, currency, "gender", width, { scale: absoluteScale }),
    [absoluteData, currency, absoluteScale]
  )

  const linePlotFn = React.useCallback(
    (width) => areaChart(relativeData, "gender", width),
    [relativeData]
  )

  const tableFn = React.useCallback(
    () => sparkbarTable(tableData, "gender", { currency, scale: absoluteScale, unit }),
    [tableData, currency, absoluteScale, unit]
  )

  const columnFilename = formatString(`gender ODA ${donorName} ${recipientName}`, {fileMode: true})
  const lineFilename = formatString(`gender ODA ${donorName} ${recipientName} share`, {fileMode: true})
  const tableFilename = formatString(`gender ODA ${donorName} ${recipientName} ${unit}`, {fileMode: true})

  const tableNote = unit === "value"
    ? `ODA values in ${pricesNote} ${currencyLabel}.`
    : `ODA values as a share of all bilateral ODA received by ${recipientName}.`

  return (
      <div className="mx-auto space-y-12 px-4 py-10 sm:px-8 sm:py-16 lg:px-12 lg:py-20">

          <Header 
              appTitle={APP_TITLE}
              appDescription={APP_DESCRIPTION}
              navItems={NAV_ITEMS}
              currentPage="gender"
              descriptionMaxWidth={550}
          />

        <div className="flex flex-col gap-4">
            <h3 className="section-header">
                REFINE YOUR VIEW
            </h3>
            <div className="grid gap-6 md:grid-cols-3 pl-6">
                    <div className="flex flex-col items-stretch gap-6">
                  <DropdownMenu label="Donor" options={DONOR_OPTIONS} value={donor} onChange={setDonor} />
                  <DropdownMenu label="Recipient" options={RECIPIENT_OPTIONS} value={recipient} onChange={setRecipient} />
                </div>
                <div className="flex flex-col items-stretch gap-6">
                  <DropdownMenu label="Currency" options={CURRENCY_OPTIONS} value={currency} onChange={setCurrency} />
                  <ToggleSwitch label="Prices" value={prices} options={PRICES_OPTIONS} onChange={setPrices} />
                </div>
                <div className="flex flex-col items-stretch gap-6">
                  <RangeInput
                      min={timeRangeOptions.start}
                      max={timeRangeOptions.end}
                      step={1}
                      label="Time range"
                      value={timeRange}
                      onChange={setTimeRange}
                  />
                  <DropdownMenu multi
                      label="Gender is"
                      options={INDICATOR_OPTIONS}
                      value={indicator}
                      onChange={setIndicator}
                      placeholder={"Select indicators..."}
                  />
                </div>
            </div>
        </div>

      {indicator.length === 0 ? (
          <p className="plain-text flex px-6 py-10 items-center justify-center text-center text-lg text-slate-500">
              Select at least one indicator.
          </p>    
      ) : (
        <>

      <div className="grid gap-10 lg:grid-cols-2">
          <ONEVisual
            title={`Gender ODA to ${recipientName} from ${donorName}`}
            subtitle={columnSubtitle}
            subtitleIsHTML={true}
            source="OECD Creditor Reporting System."
            note={`ODA values in ${pricesNote} ${currencyLabel}.`}
            empty={absoluteData.length === 0}
            emptyMessage="No data available"
            fileName={columnFilename}
            data={absoluteData}
            imageDownload={true}
            dataDownload={true}
          >
            <AutoPlot data={absoluteData} plotFn={columnPlotFn} />
          </ONEVisual>

          <ONEVisual
            title={`Gender ODA to ${recipientName} from ${donorName}`}
            subtitle={lineSubtitle}
            subtitleIsHTML={true}
            source="OECD Creditor Reporting System."
            empty={relativeData.length === 0}
            emptyMessage="No data available"
            fileName={lineFilename}
            data={relativeData}
            imageDownload={true}
            dataDownload={true}
          >
            <AutoPlot data={relativeData} plotFn={linePlotFn} />
          </ONEVisual>
      </div>
      
        <ONEVisual
          title={`Gender ODA to ${recipientName} from ${donorName}`}
          subtitle={columnSubtitle}
          subtitleIsHTML={true}
          controls={
              <DropdownMenuMini 
                  label="Unit" 
                  options={unitOptions} 
                  value={unit} 
                  onChange={setUnit} 
              />
          }
          source="OECD DAC Table Creditor Reporting System."
          note={tableNote}
          empty={tableData.length === 0}
          emptyMessage="No data available"
          fileName={tableFilename}
          data={tableData}
          dataDownload={true}
        >
          <AutoTable data={tableData} tableFn={tableFn} />
        </ONEVisual>
            
        </>
      )}
    </div>
  )
}

display(<App />)
```
