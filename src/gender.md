```js
import * as React from "npm:react"
import {NavMenu} from "./components/NavMenu.js"
import {DropdownMenu} from "./components/DropdownMenu.js"
import {ToggleSwitch} from "./components/ToggleSwitch.js"
import {MultiSelect} from "./components/MultiSelect.js"
import {RangeInput} from "./components/RangeInput.js"
import {ONEVisual} from "./components/ONEVisual.js"
import {setCustomColors} from "@one-data/observable-themes/use-colors"
import {genderQueries, transformTableData, donorOptions, recipientOptions, genderIndicators} from "./js/genderQueries.js"
import {name2CodeMap, getNameByCode, getCurrencyLabel, formatString} from "./js/utils.js"
import {customPalette, paletteGender} from "./js/colors.js"
import {downloadXLSX} from "./js/downloads.js"
import {barPlot, linePlot, sparkbarTable} from "./js/visuals.js"
import {AutoPlot} from "./components/AutoPlot.js"
import {AutoTable} from "./components/AutoTable.js"
import {CURRENCY_OPTIONS, PRICES_OPTIONS} from "./js/config.js"
import "./js/embed.js"

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
    {label: `Million ${getCurrencyLabel(currency, {currencyOnly: true})}`, value: "value"},
    {label: "% of total", value: "total"}
  ], [currency])

  const data = React.useMemo(
    () => indicator.length > 0
      ? genderQueries(donor, recipient, indicator, currency, prices, timeRange)
      : {absolute: [], relative: [], rawData: []},
    [donor, recipient, indicator, currency, prices, timeRange]
  )

  const absoluteData = data?.absolute ?? []
  const relativeData = data?.relative ?? []

  const tableData = React.useMemo(
    () => transformTableData(data?.rawData ?? [], unit, currency, prices),
    [data?.rawData, unit, currency, prices]
  )

  const donorName = formatString(getNameByCode(donorMapping, donor) ?? "")
  const recipientName = getNameByCode(recipientMapping, recipient) ?? ""
  const currencyLabel = getCurrencyLabel(currency, {currencyLong: true, inSentence: true})
  const pricesNote = `${prices}${prices === "constant" ? ` ${timeRangeOptions.base}` : ""}`

  const barSubtitle = React.useMemo(
    () => buildGenderSubtitle(indicator),
    [indicator]
  )

  const lineSubtitle = React.useMemo(
    () => buildGenderSubtitle(indicator, " as a share of the total"),
    [indicator]
  )

  const barPlotFn = React.useCallback(
    (width) => barPlot(absoluteData, currency, "gender", width, {}),
    [absoluteData, currency]
  )

  const linePlotFn = React.useCallback(
    (width) => linePlot(relativeData, "gender", width),
    [relativeData]
  )

  const tableFn = React.useCallback(
    () => sparkbarTable(tableData, "gender", {}),
    [tableData]
  )

  const barFilename = formatString(`gender ODA ${donorName} ${recipientName}`, {fileMode: true})
  const lineFilename = formatString(`gender ODA ${donorName} ${recipientName} share`, {fileMode: true})
  const tableFilename = formatString(`gender ODA ${donorName} ${recipientName} ${unit}`, {fileMode: true})

  const tableNote = unit === "value"
    ? `ODA values in ${pricesNote} ${currencyLabel}.`
    : `ODA values as a share of total aid received by ${recipientName}.`

  return (
    <div className="mx-auto w-full space-y-10 px-6 py-10">
      <NavMenu currentPage="gender" />

      <section className="p-4 sm:p-6 mb-6">
        <div className="grid gap-6 md:grid-cols-3">
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
            <MultiSelect
                label="Gender is"
                options={INDICATOR_OPTIONS}
                value={indicator}
                onChange={setIndicator}
                placeholder={null}
                maxSelected={4}
            />
          </div>
        </div>
      </section>

      {indicator.length === 0 ? (
        <p className="px-4 sm:px-6 text-sm text-slate-500">Select at least one indicator.</p>
      ) : (
        <>

      <div className="grid gap-10 lg:grid-cols-2">
        <div className="border border-blackbg-white p-4 sm:p-6">
          <ONEVisual
            title={`Gender ODA to ${recipientName} from ${donorName}`}
            subtitle={barSubtitle}
            subtitleIsHTML={true}
            source="OECD Creditor Reporting System."
            note={`ODA values in ${pricesNote} ${currencyLabel}.`}
            empty={absoluteData.length === 0}
            emptyMessage="No data available"
            onDownload={() => downloadXLSX(absoluteData, barFilename)}
            plotFileName={barFilename}
          >
            <AutoPlot data={absoluteData} plotFn={barPlotFn} />
          </ONEVisual>
        </div>

        <div className="border border-blackbg-white p-4 sm:p-6">
          <ONEVisual
            title={`Gender ODA to ${recipientName} from ${donorName}`}
            subtitle={lineSubtitle}
            subtitleIsHTML={true}
            source="OECD Creditor Reporting System."
            empty={relativeData.length === 0}
            emptyMessage="No data available"
            onDownload={() => downloadXLSX(relativeData, lineFilename)}
            plotFileName={lineFilename}
          >
            <AutoPlot data={relativeData} plotFn={linePlotFn} />
          </ONEVisual>
        </div>
      </div>

      <div className="p-4 sm:p-6">
        <DropdownMenu label="Unit" options={unitOptions} value={unit} onChange={setUnit} />
      </div>

      <div className="border border-blackbg-white p-4 sm:p-6">
        <ONEVisual
          title={`Gender ODA to ${recipientName} from ${donorName}`}
          source="OECD DAC Table Creditor Reporting System."
          note={tableNote}
          empty={tableData.length === 0}
          emptyMessage="No data available"
          onDownload={() => downloadXLSX(tableData, tableFilename)}
        >
          <AutoTable data={tableData} tableFn={tableFn} />
        </ONEVisual>
      </div>
        </>
      )}
    </div>
  )
}

display(<App />)
```
