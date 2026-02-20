```js
import * as React from "npm:react"
import {NavMenu} from "./components/NavMenu.js"
import {DropdownMenu} from "./components/DropdownMenu.js"
import {ToggleSwitch} from "./components/ToggleSwitch.js"
import {RangeInput} from "./components/RangeInput.js"
import {ONEVisual} from "./components/ONEVisual.js"
import {setCustomColors} from "@one-data/observable-themes/use-colors"
import {financingQueries, transformTableData, donorOptions, financingIndicators} from "./js/financingQueries.js"
import {name2CodeMap, getNameByCode, getCurrencyLabel, formatString} from "./js/utils.js"
import {customPalette} from "./js/colors.js"
import {downloadXLSX} from "./js/downloads.js"
import {barPlot, linePlot, sparkbarTable} from "./js/visuals.js"
import {AutoPlot} from "./components/AutoPlot.js"
import {AutoTable} from "./components/AutoTable.js"
import {CURRENCY_OPTIONS, PRICES_OPTIONS} from "./js/config.js"
import "./js/embed.js"

setCustomColors(customPalette)

const timeRangeOptions = await FileAttachment("./data/analysis_tools/financing_time.json").json()

const donorMapping = name2CodeMap(donorOptions, {})
const indicatorMapping = new Map(
    Object.entries(financingIndicators).map(([k, v]) => [v, Number(k)])
)

const DONOR_OPTIONS = Array.from(donorMapping.entries())
    .map(([label, value]) => ({label, value}))
    .sort((a, b) => a.label.localeCompare(b.label))

const INDICATOR_OPTIONS = Array.from(indicatorMapping.entries())
    .map(([label, value]) => ({label, value}))

const TOTAL_ODA_CODE = indicatorMapping.get("Total ODA")
const CORE_ODA_CODE = indicatorMapping.get("Core ODA (ONE Definition)")
const EU27_EUI_CODE = donorMapping.get("EU27 + EU Institutions")
```

```jsx
function App() {
  const [donor, setDonor] = React.useState(donorMapping.get("DAC countries"))
  const [indicator, setIndicator] = React.useState(TOTAL_ODA_CODE)
  const [currency, setCurrency] = React.useState("usd")
  const [prices, setPrices] = React.useState("constant")
  const [timeRange, setTimeRange] = React.useState([timeRangeOptions.end - 20, timeRangeOptions.end])
  const [unit, setUnit] = React.useState("value")
  const [commitment, setCommitment] = React.useState(false)

  const isTotalODA = indicator === TOTAL_ODA_CODE

  React.useEffect(() => {
    if (isTotalODA && unit === "total_pct") setUnit("value")
  }, [isTotalODA])

  const unitOptions = React.useMemo(() => {
    const opts = [
      {label: `Million ${getCurrencyLabel(currency, {currencyOnly: true})}`, value: "value"},
      {label: "% of GNI", value: "gni_pct"},
    ]
    if (!isTotalODA) opts.push({label: "% of total ODA", value: "total_pct"})
    return opts
  }, [currency, isTotalODA])

  const data = React.useMemo(
    () => financingQueries(donor, indicator, currency, prices, timeRange),
    [donor, indicator, currency, prices, timeRange]
  )

  const absoluteData = data?.absolute ?? []
  const relativeData = data?.relative ?? []

  const tableData = React.useMemo(
    () => transformTableData(data?.rawData ?? [], unit, indicator, currency, prices),
    [data?.rawData, unit, indicator, currency, prices]
  )

  const donorName = formatString(getNameByCode(donorMapping, donor) ?? "")
  const indicatorName = getNameByCode(indicatorMapping, indicator) ?? ""
  const currencyLabel = getCurrencyLabel(currency, {currencyLong: true, inSentence: true})
  const pricesNote = `${prices}${prices === "constant" ? ` ${timeRangeOptions.base}` : ""}`
  const coreOdaNote = indicator === CORE_ODA_CODE
    ? "Core ODA (ONE definition): Total ODA excluding in-donor spending."
    : ""
  const eu27Note = donor === EU27_EUI_CODE && timeRange[1] === 2024
    ? "2024 values do not include contributions by EU Institutions."
    : ""

  const absoluteSubtitle = React.useMemo(() => {
    const types = [...new Set(absoluteData.map(d => d.type))]
    if (types.length > 1) {
      return `in <span style="color:${customPalette.flow}; font-weight:600">Flows</span> and <span style="color:${customPalette.ge}; font-weight:600">grant equivalents</span>`
    }
    return types.length ? `in ${types[0]}` : ""
  }, [absoluteData])

  const relativeSubtitle = React.useMemo(() => {
    const types = [...new Set(relativeData.map(d => d.type))]
    const sharePart = isTotalODA ? " as a share of GNI" : " as a share of total ODA"
    if (types.length > 1) {
      return `in <span style="color:${customPalette.flow}; font-weight:600">Flows</span> and <span style="color:${customPalette.ge}; font-weight:600">grant equivalents</span>${sharePart}`
    }
    return types.length ? `in ${types[0]}${sharePart}` : sharePart
  }, [relativeData, isTotalODA])

  const barPlotFn = React.useCallback(
    (width) => barPlot(absoluteData, currency, "financing", width, {}),
    [absoluteData, currency]
  )

  const linePlotFn = React.useCallback(
    (width) => linePlot(relativeData, "financing", width, {showIntlCommitment: commitment, GNIShare: isTotalODA}),
    [relativeData, commitment, isTotalODA]
  )

  const tableFn = React.useCallback(
    () => sparkbarTable(tableData, "financing", {}),
    [tableData]
  )

  const barFilename = formatString(`${donorName} ${indicatorName}`, {fileMode: true})
  const lineFilename = formatString(`${donorName} ${indicatorName} share`, {fileMode: true})
  const tableFilename = formatString(`${donorName} ${indicatorName} ${unit}`, {fileMode: true})

  const plotNote = [
    `ODA values in ${pricesNote} ${currencyLabel}.`,
    coreOdaNote,
    eu27Note
  ].filter(Boolean).join(" ")

  const tableNote = React.useMemo(() => {
    const base = unit === "value"
      ? `ODA values in ${pricesNote} ${currencyLabel}.`
      : unit === "gni_pct"
        ? `ODA values as a share of the GNI of ${donorName}.`
        : `ODA values as a share of total contributions from ${donorName}.`
    return [base, coreOdaNote, unit !== "total_pct" ? eu27Note : ""].filter(Boolean).join(" ")
  }, [unit, pricesNote, currencyLabel, donorName, coreOdaNote, eu27Note])

  return (
    <div className="mx-auto w-full space-y-10 px-6 py-10">
      <NavMenu currentPage="financing" />

      <section className="p-4 sm:p-6 mb-6">
        <div className="grid gap-6 md:grid-cols-3">
          <div className="flex flex-col items-stretch gap-6">
            <DropdownMenu label="Donor" options={DONOR_OPTIONS} value={donor} onChange={setDonor} />
            <DropdownMenu label="Indicator" options={INDICATOR_OPTIONS} value={indicator} onChange={setIndicator} />
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
              {isTotalODA && (
                <ToggleSwitch
                    label="Show international commitment"
                    value={commitment}
                    options={[{label: "Off", value: false}, {label: "On", value: true}]}
                    onChange={setCommitment}
                />
              )}
          </div>
        </div>
      </section>

      <div className="grid gap-10 lg:grid-cols-2">
        <div className="border border-blackbg-white p-4 sm:p-6">
          <ONEVisual
            title={`${indicatorName} from ${donorName}`}
            subtitle={absoluteSubtitle}
            subtitleIsHTML={Boolean(absoluteSubtitle)}
            source="OECD DAC1 table."
            note={plotNote}
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
            title={`${indicatorName} from ${donorName}`}
            subtitle={relativeSubtitle}
            subtitleIsHTML={Boolean(relativeSubtitle)}
            source="OECD DAC1 table."
            note={[`ODA values as a share of GNI of ${donorName}.`, coreOdaNote, eu27Note].filter(Boolean).join(" ")}
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
          title={`${indicatorName} from ${donorName}`}
          source="OECD DAC1 table."
          note={tableNote}
          empty={tableData.length === 0}
          emptyMessage="No data available"
          onDownload={() => downloadXLSX(tableData, tableFilename)}
        >
          <AutoTable data={tableData} tableFn={tableFn} />
        </ONEVisual>
      </div>
    </div>
  )
}

display(<App />)
```
