```js
import * as React from "npm:react"
import {NavMenu} from "./components/NavMenu.js"
import {DropdownMenu} from "./components/DropdownMenu.js"
import {ToggleSwitch} from "./components/ToggleSwitch.js"
import {MultiSelect} from "./components/MultiSelect.js"
import {RangeInput} from "./components/RangeInput.js"
import {ONEVisual} from "./components/ONEVisual.js"
import {setCustomColors} from "@one-data/observable-themes/use-colors"
import {
    recipientsQueries,
    transformTableData,
    donorOptions,
    recipientOptions,
    recipientsIndicators
} from "./js/recipientQueries.js"
import {name2CodeMap, getNameByCode, getCurrencyLabel, formatString} from "./js/utils.js"
import {customPalette} from "./js/colors.js"
import {downloadXLSX} from "./js/downloads.js"
import {barPlot, linePlot, sparkbarTable} from "./js/visuals.js"
import {AutoPlot} from "./components/AutoPlot.js"
import {AutoTable} from "./components/AutoTable.js"
import {CURRENCY_OPTIONS, PRICES_OPTIONS} from "./js/config.js"
import "./js/embed.js"

setCustomColors(customPalette)

const timeRangeOptions = await FileAttachment("./data/analysis_tools/base_time.json").json()

const donorMapping = name2CodeMap(donorOptions, {})
const recipientMapping = name2CodeMap(recipientOptions, {useRecipientGroups: true})
const indicatorMapping = new Map(
    Object.entries(recipientsIndicators).map(([k, v]) => [v, Number(k)])
)

const DONOR_OPTIONS = Array.from(donorMapping.entries())
    .map(([label, value]) => ({label, value}))
    .sort((a, b) => a.label.localeCompare(b.label))

const RECIPIENT_OPTIONS = Array.from(recipientMapping.entries())
    .map(([label, value]) => ({label, value}))
    .sort((a, b) => a.label.localeCompare(b.label))

const INDICATOR_OPTIONS = Array.from(indicatorMapping.entries())
    .map(([label, value]) => ({label, value}))

```

```jsx
const BILATERAL_CODE = indicatorMapping.get("Bilateral")
const MULTILATERAL_CODE = indicatorMapping.get("Imputed multilateral")

function App() {
  const [donor, setDonor] = React.useState(donorMapping.get("DAC countries"))
  const [recipient, setRecipient] = React.useState(recipientMapping.get("Developing countries"))
  const [indicator, setIndicator] = React.useState([BILATERAL_CODE, MULTILATERAL_CODE])
  const [currency, setCurrency] = React.useState("usd")
  const [prices, setPrices] = React.useState("constant")
  const [timeRange, setTimeRange] = React.useState([timeRangeOptions.end - 20, timeRangeOptions.end])
  const [unit, setUnit] = React.useState("value")

  const isMulti = indicator.length === 2

  React.useEffect(() => {
    if (isMulti && unit === "pct_total") setUnit("value")
  }, [isMulti])

  const unitOptions = React.useMemo(() => {
    const opts = [
      {label: `Million ${getCurrencyLabel(currency, {currencyOnly: true})}`, value: "value"},
    ]
    if (!isMulti) opts.push({label: "% of Bilateral + Imputed multilateral ODA", value: "pct_total"})
    return opts
  }, [currency, isMulti])

  const data = React.useMemo(
    () => indicator.length > 0
      ? recipientsQueries(donor, recipient, indicator, currency, prices, timeRange)
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

  const indicatorSubtitle = React.useMemo(() => {
    if (indicator.length > 1) {
      return `<span style="color:${customPalette.bilateral}; font-weight:600">Bilateral</span> and <span style="color:${customPalette.multilateral}; font-weight:600">imputed multilateral</span> ODA`
    }
    const name = getNameByCode(indicatorMapping, indicator) ?? ""
    return `${name} ODA`
  }, [indicator])

  const relativeIndicatorSubtitle = React.useMemo(() => {
    if (indicator.length > 1) {
      return `<span style="color:${customPalette.bilateral}; font-weight:600">Bilateral</span> and <span style="color:${customPalette.multilateral}; font-weight:600">imputed multilateral</span> as a share of the total`
    }
    const name = getNameByCode(indicatorMapping, indicator) ?? ""
    return `${name} as a share of the total`
  }, [indicator])

  const barPlotFn = React.useCallback(
    (width) => barPlot(absoluteData, currency, "recipients", width, {}),
    [absoluteData, currency]
  )

  const linePlotFn = React.useCallback(
    (width) => linePlot(relativeData, "recipients", width),
    [relativeData]
  )

  const tableFn = React.useCallback(
    () => sparkbarTable(tableData, "recipients", {}),
    [tableData]
  )

  const barFilename = formatString(`${donorName} ${recipientName}`, {fileMode: true})
  const lineFilename = formatString(`${donorName} ${recipientName} share`, {fileMode: true})
  const tableFilename = formatString(`${donorName} ${recipientName} ${unit}`, {fileMode: true})

  const tableNote = unit === "value"
    ? `ODA values in ${pricesNote} ${currencyLabel}.`
    : `ODA values as a share of total aid received by ${recipientName} from ${donorName}.`

  return (
    <div className="mx-auto w-full space-y-10 px-6 py-10">
      <NavMenu currentPage="recipients" />
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
                      label="Indicator"
                      options={INDICATOR_OPTIONS}
                      value={indicator}
                      onChange={setIndicator}
                      placeholder={null}
                      maxSelected={2}
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
              title={`ODA to ${recipientName} from ${donorName}`}
              subtitle={indicatorSubtitle}
              subtitleIsHTML={true}
              source="OECD DAC2A table."
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
              title={`ODA to ${recipientName} from ${donorName}`}
              subtitle={relativeIndicatorSubtitle}
              subtitleIsHTML={true}
              source="OECD DAC2A table."
              note={`ODA values as a share of all aid received by ${recipientName}.`}
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
          title={`ODA to ${recipientName} from ${donorName}`}
          source="OECD DAC2A table."
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
