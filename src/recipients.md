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
    recipientsIndicators,
    donorOptions,
    recipientOptions,
    recipientsQueries,
    transformTableData
} from "./js/recipientQueries.js"
import {name2CodeMap, getNameByCode} from "./js/utils.js"
import {customPalette} from "./js/colors.js"
import {columnChart} from "./js/columnChart.js"
import {areaChart} from "./js/areaChart.js"
import {sparkbarTable} from "./js/sparkBarTable.js"
import {APP_TITLE, APP_DESCRIPTION, NAV_ITEMS, CURRENCY_OPTIONS, PRICES_OPTIONS, SCALE} from "./js/config.js"

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
  const [tableView, setTableView] = React.useState("disaggregated")

  const unitOptions = React.useMemo(() => [
    {label: getCurrencyLabel(currency, {currencyLong: true, currencyOnly: true}), value: "value"},
    {label: "% of Bilateral + Imputed multilateral ODA", value: "pct_total"},
  ], [currency])

  const data = React.useMemo(
    () => indicator.length > 0
      ? recipientsQueries(donor, recipient, indicator, currency, prices, timeRange)
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

  const displayTableData = React.useMemo(() => {
    if (tableView === "total" && indicator.length > 1) {
      const byYear = new Map()
      for (const row of tableData) {
        if (!byYear.has(row.year)) {
          byYear.set(row.year, { ...row, indicator: "Bilateral + imputed multilateral ODA", value: 0 })
        }
        byYear.get(row.year).value += row.value ?? 0
      }
      return [...byYear.values()]
    }
    return tableData
  }, [tableData, tableView, indicator])

  const donorName = formatString(getNameByCode(donorMapping, donor) ?? "")
  const recipientName = getNameByCode(recipientMapping, recipient) ?? ""
    const currencyLabel = getCurrencyLabel(currency, {currencyOnly: true, currencyLong: true})
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
      return `<span style="color:${customPalette.bilateral}; font-weight:600">Bilateral</span> and <span style="color:${customPalette.multilateral}; font-weight:600">imputed multilateral</span> as a share of aid received by ${recipientName}`
    }
    const name = getNameByCode(indicatorMapping, indicator) ?? ""
    return `${name} as a share of the total`
  }, [indicator])

  const columnChartFn = React.useCallback(
    (width) => columnChart(absoluteData, currency, "recipients", width, { scale: absoluteScale }),
    [absoluteData, currency, absoluteScale]
  )

  const areaChartFn = React.useCallback(
    (width) => areaChart(relativeData, "recipients", width),
    [relativeData]
  )

  const tableSubtitle = React.useMemo(() => {
    if (tableView === "total" && indicator.length > 1) {
      return unit === "value"
        ? `<span style="color:${customPalette.total}; font-weight:600">Bilateral + imputed multilateral</span> ODA`
        : `<span style="color:${customPalette.total}; font-weight:600">Bilateral + imputed multilateral</span> as a share of aid received by ${recipientName}`
    }
    return unit === "value" ? indicatorSubtitle : relativeIndicatorSubtitle
  }, [tableView, indicator, unit, indicatorSubtitle, relativeIndicatorSubtitle, recipientName])

  const tableFn = React.useCallback(
    () => sparkbarTable(displayTableData, "recipients", { currency, scale: absoluteScale, unit }),
    [displayTableData, currency, absoluteScale, unit]
  )

  const columnFilename = formatString(`${donorName} ${recipientName}`, {fileMode: true})
  const areaFilename = formatString(`${donorName} ${recipientName} share`, {fileMode: true})
  const tableFilename = formatString(`${donorName} ${recipientName} ${unit}`, {fileMode: true})

  const tableNote = unit === "value"
    ? `ODA values in ${pricesNote} ${currencyLabel}.`
    : `ODA values as a share of all aid from bilateral donors to ${recipientName}.`

  return (
      <div className="mx-auto space-y-12 px-4 py-10 sm:px-8 sm:py-16 lg:px-12 lg:py-20">

          <Header 
              appTitle={APP_TITLE}
              appDescription={APP_DESCRIPTION}
              navItems={NAV_ITEMS}
              currentPage="recipients"
              descriptionMaxWidth={550}
          />

          <div className="flex flex-col gap-4">
              <h3 className="section-header">
                  REFINE YOUR VIEW
              </h3>
              <div className="grid gap-6 md:grid-cols-3 pl-6">
                <div className="flex flex-col items-stretch gap-6">
                    <DropdownMenu label="Donor" options={DONOR_OPTIONS} value={donor} onChange={setDonor} search={true}/>
                    <DropdownMenu label="Recipient" options={RECIPIENT_OPTIONS} value={recipient} onChange={setRecipient} search={true}/>
                </div>
                <div className="flex flex-col items-stretch gap-6">
                    <DropdownMenu label="Currency" options={CURRENCY_OPTIONS} value={currency} onChange={setCurrency} />
                    <ToggleSwitch
                        label="Prices"
                        value={prices}
                        options={PRICES_OPTIONS}
                        onChange={setPrices}
                        hint="Constant prices adjust for inflation, allowing you to compare values over time. Current prices reflect values at the time."
                    />              
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
                        label="Indicator"
                        placeholder="Select indicators..."
                        options={INDICATOR_OPTIONS}
                        value={indicator}
                        onChange={setIndicator}
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
                title={`ODA to ${recipientName} from ${donorName}`}
                subtitle={indicatorSubtitle}
                subtitleIsHTML={true}
                source="OECD DAC2A table."
                note={`ODA values in ${pricesNote} ${currencyLabel}.`}
                empty={absoluteData.length === 0}
                emptyMessage="No data available"
                fileName={columnFilename}
                data={absoluteData}
                imageDownload={true}
                dataDownload={true}
                
              >
                  <AutoPlot data={absoluteData} plotFn={columnChartFn} />
              </ONEVisual>
        
              <ONEVisual
                title={`ODA to ${recipientName} from ${donorName}`}
                subtitle={relativeIndicatorSubtitle}
                subtitleIsHTML={true}
                source="OECD DAC2A table."
                note={`ODA values as a share of all aid from bilateral donors to ${recipientName}.`}
                empty={relativeData.length === 0}
                emptyMessage="No data available"
                fileName={areaFilename}
                data={relativeData}
                imageDownload={true}
                dataDownload={true}
              >
                <AutoPlot data={relativeData} plotFn={areaChartFn} />
              </ONEVisual>
            </div>
            
            <ONEVisual
              title={`ODA to ${recipientName} from ${donorName}`}
              subtitle={tableSubtitle}
              subtitleIsHTML={true}
              source="OECD DAC2A table."
              controls={
                <>
                  <DropdownMenuMini label="Unit" options={unitOptions} value={unit} onChange={setUnit} search={false} />
                  {indicator.length > 1 && (
                    <ToggleSwitchMini
                      label="View"
                      value={tableView}
                      options={[
                        {label: "Disaggregated", value: "disaggregated"},
                        {label: "Total", value: "total"}
                      ]}
                      onChange={setTableView}
                    />
                  )}
                </>
              }
              note={tableNote}
              empty={displayTableData.length === 0}
              emptyMessage="No data available"
              fileName={tableFilename}
              data={displayTableData}
              dataDownload={true}
            >
              <AutoTable data={displayTableData} tableFn={tableFn} />
            </ONEVisual>
        </>
      )}
    </div>
  )
}

display(<App />)
```
