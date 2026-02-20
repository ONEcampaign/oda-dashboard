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
    sectorsQueries,
    transformSelectedData,
    transformTableData,
    donorOptions,
    recipientOptions,
    sectorsIndicators,
    subsector2Sector
} from "./js/sectorsQueries.js"
import {treemapPlot} from "./js/Treemap.js"
import {name2CodeMap, getNameByCode, getCurrencyLabel, formatString} from "./js/utils.js"
import {customPalette, paletteSubsectors} from "./js/colors.js"
import {downloadXLSX} from "./js/downloads.js"
import {barPlot, sparkbarTable} from "./js/visuals.js"
import {AutoPlot} from "./components/AutoPlot.js"
import {AutoTable} from "./components/AutoTable.js"
import {CURRENCY_OPTIONS, PRICES_OPTIONS} from "./js/config.js"
import "./js/embed.js"

setCustomColors(customPalette)

const timeRangeOptions = await FileAttachment("./data/analysis_tools/base_time.json").json()

const donorMapping = name2CodeMap(donorOptions, {removeEU27EUI: true})
const recipientMapping = name2CodeMap(recipientOptions, {useRecipientGroups: true})
const indicatorMapping = new Map(
    Object.entries(sectorsIndicators).map(([k, v]) => [v, Number(k)])
)

const DONOR_OPTIONS = Array.from(donorMapping.entries())
    .map(([label, value]) => ({label, value}))
    .sort((a, b) => a.label.localeCompare(b.label))

const RECIPIENT_OPTIONS = Array.from(recipientMapping.entries())
    .map(([label, value]) => ({label, value}))
    .sort((a, b) => a.label.localeCompare(b.label))

const INDICATOR_OPTIONS = Array.from(indicatorMapping.entries())
    .map(([label, value]) => ({label, value}))

const BILATERAL_CODE = indicatorMapping.get("Bilateral")
const MULTILATERAL_CODE = indicatorMapping.get("Imputed multilateral")
const SECTORS_MIN = 2013
```

```jsx
// Treemap wrapper: passes onSectorChange directly into treemapPlot
function TreemapContainer({data, currency, onSectorChange}) {
  const ref = React.useRef(null)
  const [width, setWidth] = React.useState(0)
  const onSectorChangeRef = React.useRef(onSectorChange)
  onSectorChangeRef.current = onSectorChange

  React.useEffect(() => {
    if (!ref.current) return
    const observer = new ResizeObserver(entries => setWidth(entries[0].contentRect.width))
    observer.observe(ref.current)
    setWidth(ref.current.clientWidth)
    return () => observer.disconnect()
  }, [])

  React.useEffect(() => {
    const node = ref.current
    if (!node || !width || !data?.length) {
      if (node) node.innerHTML = ""
      return
    }
    const plotEl = treemapPlot(data, width, {
      currency,
      onSectorChange: (sector) => onSectorChangeRef.current(sector)
    })
    node.innerHTML = ""
    node.appendChild(plotEl)
    return () => { if (plotEl?.remove) plotEl.remove() }
  }, [data, width, currency])

  return <div ref={ref} className="h-full w-full" />
}

function buildSectorBarSubtitle(selectedData, effectiveBreakdown, breakdownIsDisabled, indicator) {
  const indicatorLabel = indicator.length > 1
    ? "Bilateral + Imputed multilateral"
    : (getNameByCode(indicatorMapping, indicator) ?? "")

  if (effectiveBreakdown && !breakdownIsDisabled && selectedData.length > 0) {
    const uniqueSubsectors = [...new Set(selectedData.map(row => row["sub_sector"]))]
    const limit = 3
    const shown = uniqueSubsectors.slice(0, limit)
    const parts = shown.map((name, i) => {
      const sep = i < shown.length - 1 ? ", " : ""
      return `<span style="color:${paletteSubsectors[i]}; font-weight:600">${name}</span>${sep}`
    })
    if (uniqueSubsectors.length > limit) parts.push(", and other")
    parts.push("; ")
    return parts.join("") + `${indicatorLabel} ODA`
  }
  return `${indicatorLabel} ODA`
}

function App() {
  // All state at the top
  const [donor, setDonor] = React.useState(donorMapping.get("DAC countries"))
  const [recipient, setRecipient] = React.useState(recipientMapping.get("Developing countries"))
  const [indicator, setIndicator] = React.useState([BILATERAL_CODE, MULTILATERAL_CODE])
  const [currency, setCurrency] = React.useState("usd")
  const [prices, setPrices] = React.useState("constant")
  const [breakdown, setBreakdown] = React.useState(true)
  const [currentSector, setCurrentSector] = React.useState("Health")
  const [timeRange, setTimeRange] = React.useState([timeRangeOptions.end - 10, timeRangeOptions.end])
  const [unit, setUnit] = React.useState("value")

  const [treemapData, setTreemapData] = React.useState([])
  const [selectedBaseData, setSelectedBaseData] = React.useState([])
  const [tableBaseData, setTableBaseData] = React.useState([])
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState(null)

  const breakdownIsDisabled = React.useMemo(
    () => Object.values(subsector2Sector).filter(s => s === currentSector).length === 1,
    [currentSector]
  )

  const effectiveBreakdown = breakdownIsDisabled ? false : breakdown

  // Reset unit when pct_sector becomes unavailable
  React.useEffect(() => {
    if (unit === "pct_sector" && (breakdownIsDisabled || !effectiveBreakdown)) {
      setUnit("value")
    }
  }, [breakdownIsDisabled, effectiveBreakdown, unit])

  // Track base params separately from sector to avoid loading/treemap redraw on sector-only changes
  const prevBaseKeyRef = React.useRef(null)

  React.useEffect(() => {
    if (indicator.length === 0) return
    let cancelled = false

    const donor_ = Array.isArray(donor) ? donor.join(",") : String(donor)
    const recipient_ = Array.isArray(recipient) ? recipient.join(",") : String(recipient)
    const baseKey = `${donor_}|${recipient_}|${[...indicator].sort().join(",")}|${currency}|${prices}|${timeRange[0]}-${timeRange[1]}`
    const baseChanged = prevBaseKeyRef.current !== baseKey
    prevBaseKeyRef.current = baseKey

    if (baseChanged) {
      setLoading(true)
      setError(null)
    }

    const result = sectorsQueries(donor, recipient, indicator, currentSector, currency, prices, timeRange)

    Promise.all([result.treemap, result.selectedBase, result.tableBase])
      .then(([treemap, selectedBase, tableBase]) => {
        if (cancelled) return
        if (baseChanged) setTreemapData(treemap ?? [])
        setSelectedBaseData(selectedBase ?? [])
        setTableBaseData(tableBase ?? [])
        if (baseChanged) setLoading(false)
      })
      .catch(err => {
        if (cancelled) return
        console.error("Sectors query failed:", err)
        if (baseChanged) { setError(err); setLoading(false) }
      })

    return () => { cancelled = true }
  }, [donor, recipient, indicator, currentSector, currency, prices, timeRange])

  const selectedData = React.useMemo(
    () => transformSelectedData(selectedBaseData, effectiveBreakdown),
    [selectedBaseData, effectiveBreakdown]
  )

  const tableData = React.useMemo(
    () => transformTableData(tableBaseData, unit, effectiveBreakdown),
    [tableBaseData, unit, effectiveBreakdown]
  )

  const unitOptions = React.useMemo(() => {
    const indicatorLabel = indicator.length > 1
      ? "Bilateral + Imputed multilateral ODA"
      : (getNameByCode(indicatorMapping, indicator) ?? "")
    const opts = [
      {label: `Million ${getCurrencyLabel(currency, {currencyOnly: true})}`, value: "value"},
      {label: `% of ${indicatorLabel}`, value: "pct_total"},
    ]
    if (!breakdownIsDisabled && effectiveBreakdown) {
      opts.splice(1, 0, {label: `% of ${currentSector} ODA`, value: "pct_sector"})
    }
    return opts
  }, [currency, indicator, currentSector, breakdownIsDisabled, effectiveBreakdown])

  const donorName = formatString(getNameByCode(donorMapping, donor) ?? "")
  const recipientName = getNameByCode(recipientMapping, recipient) ?? ""
  const currencyLabel = getCurrencyLabel(currency, {currencyLong: true, inSentence: true})
  const indicatorLabel = indicator.length > 1
    ? "Bilateral + Imputed multilateral"
    : (getNameByCode(indicatorMapping, indicator) ?? "")

  const sectorsPeriod = timeRange[0] === timeRange[1] ? `${timeRange[0]}` : `${timeRange[0]}–${timeRange[1]}`
  const treemapSubtitle = `${indicatorLabel} ODA; ${sectorsPeriod}`

  const sectorBarSubtitle = React.useMemo(
    () => buildSectorBarSubtitle(selectedData, effectiveBreakdown, breakdownIsDisabled, indicator),
    [selectedData, effectiveBreakdown, breakdownIsDisabled, indicator]
  )

  const barPlotFn = React.useCallback(
    (width) => barPlot(selectedData, currency, "sectors", width, {breakdown: effectiveBreakdown}),
    [selectedData, currency, effectiveBreakdown]
  )

  const tableFn = React.useCallback(
    () => sparkbarTable(tableData, "sectors", {breakdown: effectiveBreakdown}),
    [tableData, effectiveBreakdown]
  )

  const pricesNote = `${prices}${prices === "constant" ? ` ${timeRangeOptions.base}` : ""}`
  const sourceText = "OECD DAC Creditor Reporting System, Provider's total use of the multilateral system databases."
  const plotNote = `ODA values in million ${pricesNote} ${currencyLabel}.`

  const treemapFilename = formatString(`${donorName} ${recipientName} by sector`, {fileMode: true})
  const barFilename = formatString(`${donorName} ${recipientName} ${currentSector} ${effectiveBreakdown ? "breakdown" : "total"}`, {fileMode: true})
  const tableFilename = formatString(`${donorName} ${recipientName} ${currentSector} ${effectiveBreakdown ? "breakdown" : ""} ${unit}`, {fileMode: true})

  const tableNote = React.useMemo(() => {
    if (unit === "value") return `ODA values in ${pricesNote} ${currencyLabel}.`
    if (unit === "pct_sector") return `ODA values as a share of ${currentSector} ODA received by ${recipientName} from ${donorName}.`
    return `ODA values as a share of total aid received by ${recipientName} from ${donorName}.`
  }, [unit, currencyLabel, currentSector, recipientName, donorName])

  return (
    <div className="mx-auto w-full max-w-6xl space-y-10 px-0 py-14 sm:px-6 sm:py-10">
      <NavMenu currentPage="sectors" />

      <section className="p-4 sm:p-6 mb-6">
        <div className="grid gap-6 md:grid-cols-2">
          <div className="flex flex-col items-stretch gap-6">
            <DropdownMenu label="Donor" options={DONOR_OPTIONS} value={donor} onChange={setDonor} />
            <DropdownMenu label="Recipient" options={RECIPIENT_OPTIONS} value={recipient} onChange={setRecipient} />
            <MultiSelect
              label="Indicator"
              options={INDICATOR_OPTIONS}
              value={indicator}
              onChange={setIndicator}
              placeholder={null}
              maxSelected={2}
            />
          </div>
          <div className="flex flex-col items-stretch gap-6">
            <DropdownMenu label="Currency" options={CURRENCY_OPTIONS} value={currency} onChange={setCurrency} />
            <ToggleSwitch label="Prices" value={prices} options={PRICES_OPTIONS} onChange={setPrices} />
            <RangeInput
                min={SECTORS_MIN}
                max={timeRangeOptions.end}
                step={1}
                label="Time range"
                value={timeRange}
                onChange={setTimeRange}
            />
          </div>
        </div>
      </section>

      {indicator.length === 0 ? (
        <p className="px-4 sm:px-6 text-sm text-slate-500">Select at least one indicator.</p>
      ) : (
        <>

      <div className="grid gap-10 lg:grid-cols-2">
        <div className="border-2 border-black bg-white p-4 sm:p-6">
          <ONEVisual
            title={`ODA to ${recipientName} from ${donorName} by sector`}
            subtitle={treemapSubtitle}
            source={sourceText}
            note={plotNote}
            loading={loading}
            error={error}
            empty={!loading && !error && treemapData.length === 0}
            emptyMessage="No data available"
            onDownload={() => downloadXLSX(treemapData, treemapFilename)}
            plotFileName={treemapFilename}
          >
            <TreemapContainer
              data={treemapData}
              currency={currency}
              onSectorChange={setCurrentSector}
            />
          </ONEVisual>
        </div>

        <div className="border-2 border-black bg-white p-4 sm:p-6">
          <ONEVisual
            title={`${currentSector} ODA to ${recipientName} from ${donorName}`}
            subtitle={sectorBarSubtitle}
            subtitleIsHTML={true}
            source={sourceText}
            note={plotNote}
            loading={loading}
            error={error}
            empty={!loading && !error && selectedData.length === 0}
            emptyMessage="No data available"
            onDownload={() => downloadXLSX(selectedData, barFilename)}
            plotFileName={barFilename}
          >
            <AutoPlot data={selectedData} plotFn={barPlotFn} />
          </ONEVisual>
          {!breakdownIsDisabled && (
              <div className="mb-3">
                  <ToggleSwitch
                      label="Sector breakdown"
                      value={breakdown}
                      options={[{label: "Off", value: false}, {label: "On", value: true}]}
                      onChange={setBreakdown}
                  />
              </div>
          )}
        </div>
      </div>

      <div className="p-4 sm:p-6">
        <DropdownMenu label="Unit" options={unitOptions} value={unit} onChange={setUnit} />
      </div>

      <div className="border-2 border-black bg-white p-4 sm:p-6">
        <ONEVisual
          title={`${effectiveBreakdown && !breakdownIsDisabled ? "Breakdown of " : ""}${currentSector} ODA to ${recipientName} from ${donorName}`}
          subtitle={`${indicatorLabel} ODA`}
          source={sourceText}
          note={tableNote}
          loading={loading}
          error={error}
          empty={!loading && !error && tableData.length === 0}
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
