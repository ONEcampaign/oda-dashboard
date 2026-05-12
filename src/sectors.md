```js
import * as React from "npm:react"
import {
    DropdownMenu,
    DropdownMenuMini,
    RangeInput,
    RangeInputMini,
    ToggleSwitch,
    ToggleSwitchMini
} from "npm:@one-data/observable-themes/inputs"
import {Header} from "npm:@one-data/observable-themes/ui"
import {ONEVisual, AutoPlot, AutoTable} from "npm:@one-data/observable-themes/charts"
import {
    getCurrencyLabel,
    formatString,
    formatValue,
    resolveScale,
    isEmbedded
} from "npm:@one-data/observable-themes/utils"
import {setCustomColors} from "npm:@one-data/observable-themes/colors"
import {
    donorOptions,
    recipientOptions,
    sectorsIndicators,
    code2Subsector,
    subsector2Sector,
    sectorsQueries,
    transformTableData,
    transformSelectedData
} from "./js/sectorsQueries.js"
import {treemapChart, selectSector} from "./js/treemapChart.js"
import {name2CodeMap, getNameByCode} from "./js/utils.js"
import {customPalette, paletteSubsectors} from "./js/colors.js"
import {columnChart} from "./js/columnChart.js"
import {sparkbarTable} from "./js/sparkBarTable.js"
import {APP_TITLE, APP_DESCRIPTION, NAV_ITEMS, CURRENCY_OPTIONS, PRICES_OPTIONS, SCALE} from "./js/config.js"

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
const SECTORS_MIN_YEAR = 2013
```

```jsx
// Treemap wrapper: passes onSectorChange directly into treemapChart
function TreemapContainer({data, currency, sector, onSectorChange}) {
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
        const chartEl = treemapChart(data, width, {
            currency,
            onSectorChange: (s) => onSectorChangeRef.current(s)
        })
        node.innerHTML = ""
        node.appendChild(chartEl)
        return () => {
            if (chartEl?.remove) chartEl.remove()
        }
    }, [data, width, currency])

    // Sync external sector changes (e.g. from dropdown) into the treemap visuals
    React.useEffect(() => {
        if (!ref.current || !width) return
        selectSector(ref.current, sector)
    }, [sector])

    return <div ref={ref} className="h-full w-full"/>
}

function buildSectorColumnSubtitle(selectedData, effectiveBreakdown, breakdownIsDisabled, indicator) {
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
    const [sector, setSector] = React.useState("All sectors")
    const [year, setYear] =
        React.useState(timeRangeOptions.end)
    const [yearRange, setYearRange] = React.useState([timeRangeOptions.end - 10, timeRangeOptions.end])
    const [unit, setUnit] = React.useState("value")

    const [treemapData, setTreemapData] = React.useState([])
    const [selectedBaseData, setSelectedBaseData] = React.useState([])
    const [tableBaseData, setTableBaseData] = React.useState([])
    const [loading, setLoading] = React.useState(false)
    const [error, setError] = React.useState(null)

    const breakdownIsDisabled = React.useMemo(
        () => Object.values(subsector2Sector).filter(s => s === sector).length === 1,
        [sector]
    )

    const effectiveBreakdown = breakdownIsDisabled ? false : breakdown

    // Reset unit when pct_sector becomes unavailable
    React.useEffect(() => {
        if (unit === "pct_sector" && (breakdownIsDisabled || !effectiveBreakdown)) {
            setUnit("value")
        }
    }, [breakdownIsDisabled, effectiveBreakdown, unit])

    // Effect 1: treemap data — uses selected year only
    React.useEffect(() => {
        if (indicator.length === 0) return
        let cancelled = false
        setLoading(true)
        setError(null)

        const result = sectorsQueries(donor, recipient, indicator, null, currency, prices, [year, year])
        result.treemap
            .then(treemap => {
                if (!cancelled) {
                    setTreemapData(treemap ?? []);
                    setLoading(false)
                }
            })
            .catch(err => {
                if (!cancelled) {
                    console.error("Treemap query failed:", err);
                    setError(err);
                    setLoading(false)
                }
            })

        return () => {
            cancelled = true
        }
    }, [donor, recipient, indicator, currency, prices, year])

    // Effect 2: column/table data
    React.useEffect(() => {
        if (indicator.length === 0 || sector === "All sectors") {
            setSelectedBaseData([])
            setTableBaseData([])
            return
        }
        let cancelled = false

        const result = sectorsQueries(donor, recipient, indicator, sector, currency, prices, yearRange)
        Promise.all([result.selectedBase, result.tableBase])
            .then(([selectedBase, tableBase]) => {
                if (!cancelled) {
                    setSelectedBaseData(selectedBase ?? []);
                    setTableBaseData(tableBase ?? [])
                }
            })
            .catch(err => {
                if (!cancelled) console.error("column/table query failed:", err)
            })

        return () => {
            cancelled = true
        }
    }, [donor, recipient, indicator, sector, currency, prices, yearRange])

    const selectedData = React.useMemo(
        () => transformSelectedData(selectedBaseData, effectiveBreakdown),
        [selectedBaseData, effectiveBreakdown]
    )

    const selectedScale = React.useMemo(
        () => resolveScale(selectedData.map(d => d.value), SCALE),
        [selectedData]
    )

    const tableData = React.useMemo(
        () => transformTableData(tableBaseData, unit, effectiveBreakdown),
        [tableBaseData, unit, effectiveBreakdown]
    )

    const sectorOptions = React.useMemo(() => {
        const unique = [...new Set(treemapData.map(d => d.sector))]
            .filter(Boolean)
            .sort()
            .map(s => ({label: s, value: s}))
        return [{label: "All sectors", value: "All sectors"}, ...unique]
    }, [treemapData])

    const unitOptions = React.useMemo(() => {
        const indicatorLabel = indicator.length > 1
            ? "Bilateral + Imputed multilateral"
            : (getNameByCode(indicatorMapping, indicator) ?? "")
        return [
            {label: getCurrencyLabel(currency, {currencyLong: true, currencyOnly: true}), value: "value"},
            {label: `% of ${sector} ODA`, value: "pct_sector", disabled: breakdownIsDisabled || !effectiveBreakdown},
            {label: `% of ${indicatorLabel} ODA`, value: "pct_total"},
        ]
    }, [currency, indicator, sector, breakdownIsDisabled, effectiveBreakdown])

    const donorName = formatString(getNameByCode(donorMapping, donor) ?? "")
    const recipientName = getNameByCode(recipientMapping, recipient) ?? ""
    const currencyLabel = getCurrencyLabel(currency, {currencyOnly: true, currencyLong: true})
    const indicatorLabel = indicator.length > 1
        ? "Bilateral + Imputed multilateral"
        : (getNameByCode(indicatorMapping, indicator) ?? "")

    const treemapSubtitle = `${indicatorLabel} ODA; ${year}`

    const sectorColumnSubtitle = React.useMemo(
        () => buildSectorColumnSubtitle(selectedData, effectiveBreakdown, breakdownIsDisabled, indicator),
        [selectedData, effectiveBreakdown, breakdownIsDisabled, indicator]
    )

    const columnChartFn = React.useCallback(
        (width) => columnChart(selectedData, currency, "sectors", width, {
            breakdown: effectiveBreakdown,
            scale: selectedScale
        }),
        [selectedData, currency, effectiveBreakdown, selectedScale]
    )

    const tableFn = React.useCallback(
        () => sparkbarTable(tableData, "sectors", {
            breakdown: effectiveBreakdown,
            currency,
            scale: selectedScale,
            unit
        }),
        [tableData, effectiveBreakdown, currency, selectedScale, unit]
    )

    const pricesNote = `${prices}${prices === "constant" ? ` ${timeRangeOptions.base}` : ""}`
    const sourceText = "OECD DAC Creditor Reporting System, Provider's total use of the multilateral system databases."
    const chartNote = `ODA values in ${pricesNote} ${currencyLabel}.`

    const treemapFilename = formatString(`${donorName} ${recipientName} by sector`, {fileMode: true})
    const columnFilename = formatString(`${donorName} ${recipientName} ${sector} ${effectiveBreakdown ? "breakdown" : "total"}`, {fileMode: true})
    const tableFilename = formatString(`${donorName} ${recipientName} ${sector} ${effectiveBreakdown ? "breakdown" : ""} ${unit}`, {fileMode: true})

    const tableNote = React.useMemo(() => {
        if (unit === "value") return `ODA values in ${pricesNote} ${currencyLabel}.`
        if (unit === "pct_sector") return `ODA values as a share of ${sector} ODA received by ${recipientName} from ${donorName}.`
        return `ODA values as a share of total aid received by ${recipientName} from ${donorName}.`
    }, [unit, currencyLabel, sector, recipientName, donorName])

    return (
        <div className="mx-auto space-y-12 px-4 py-10 sm:px-8 sm:py-16 lg:px-12 lg:py-20">

            <Header appTitle={APP_TITLE} appDescription={APP_DESCRIPTION} navItems={NAV_ITEMS} currentPage="sectors"/>

            <div className="flex flex-col gap-4">
                <h3 className="section-header">
                    REFINE YOUR VIEW
                </h3>
                <div className="grid gap-6 md:grid-cols-3 pl-6">
                    <div className="flex flex-col items-stretch gap-6">
                        <DropdownMenu label="Donor" options={DONOR_OPTIONS} value={donor} onChange={setDonor}
                                      search={true}/>
                        <DropdownMenu label="Recipient" options={RECIPIENT_OPTIONS} value={recipient}
                                      onChange={setRecipient} search={true}/>
                    </div>
                    <div className="flex flex-col items-stretch gap-6">
                        <DropdownMenu label="Currency" options={CURRENCY_OPTIONS} value={currency}
                                      onChange={setCurrency}/>
                        <ToggleSwitch
                            label="Prices"
                            value={prices}
                            options={PRICES_OPTIONS}
                            onChange={setPrices}
                            hint="Constant prices adjust for inflation, allowing you to compare values over time. Current prices reflect values at the time."
                        />
                    </div>
                    <div className="flex flex-col items-stretch gap-6">
                        <DropdownMenu
                            label="Sector"
                            options={sectorOptions}
                            value={sector}
                            onChange={setSector}
                            search={true}
                        />
                        <DropdownMenu multi
                                      label="Indicator"
                                      options={INDICATOR_OPTIONS}
                                      value={indicator}
                                      onChange={setIndicator}
                                      placeholder="Select indicators..."
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
                            title={`ODA to ${recipientName} from ${donorName} by sector`}
                            subtitle={treemapSubtitle}
                            controls={
                                <RangeInputMini
                                    min={SECTORS_MIN_YEAR}
                                    max={timeRangeOptions.end}
                                    step={1}
                                    label="Year"
                                    value={year}
                                    onChange={setYear}
                                    single={true}
                                />
                            }
                            source={sourceText}
                            note={chartNote}
                            loading={loading}
                            error={error}
                            empty={!loading && !error && treemapData.length === 0}
                            emptyMessage="No data available"
                            fileName={treemapFilename}
                            data={treemapData}
                            imageDownload={true}
                            dataDownload={true}
                        >
                            <TreemapContainer
                                data={treemapData}
                                currency={currency}
                                sector={sector}
                                onSectorChange={setSector}
                            />
                        </ONEVisual>

                        {sector === "All sectors" ? (
                            <div
                                className="plain-text flex px-20 py-10 items-start justify-center text-center text-lg text-slate-500">
                                Select a sector from the dropdown or treemap to explore trends over time.
                            </div>
                        ) : (
                            <>
                                <ONEVisual
                                    title={`${sector} ODA to ${recipientName} from ${donorName}`}
                                    subtitle={sectorColumnSubtitle}
                                    subtitleIsHTML={true}
                                    controls={
                                        !breakdownIsDisabled && (
                                            <div>
                                                <RangeInputMini
                                                    min={SECTORS_MIN_YEAR}
                                                    max={timeRangeOptions.end}
                                                    step={1}
                                                    label="Time range"
                                                    value={yearRange}
                                                    onChange={setYearRange}
                                                />
                                                <ToggleSwitchMini
                                                    label="Sector breakdown"
                                                    value={breakdown}
                                                    options={[{label: "Off", value: false}, {label: "On", value: true}]}
                                                    onChange={setBreakdown}
                                                />
                                            </div>
                                        )}
                                    source={sourceText}
                                    note={chartNote}
                                    loading={loading}
                                    error={error}
                                    empty={!loading && !error && selectedData.length === 0}
                                    emptyMessage="No data available"
                                    fileName={columnFilename}
                                    data={selectedData}
                                    imageDownload={true}
                                    dataDownload={true}
                                >
                                    <AutoPlot data={selectedData} plotFn={columnChartFn}/>
                                </ONEVisual>
                            </>
                        )}
                    </div>

                    {sector === "All sectors" ? (
                        <>
                            <div
                                className="plain-text flex px-6 py-10 items-center justify-center text-center text-lg text-slate-500">
                                Select a sector from the dropdown or treemap to explore trends over time.
                            </div>
                        </>
                    ) : (
                        <>
                            <ONEVisual
                                title={`${effectiveBreakdown && !breakdownIsDisabled ? "Breakdown of " : ""}${sector} ODA to ${recipientName} from ${donorName}`}
                                subtitle={`${indicatorLabel} ODA`}
                                controls={
                                    <DropdownMenuMini label="Unit" options={unitOptions} value={unit}
                                                      onChange={setUnit}/>
                                }
                                source={sourceText}
                                note={tableNote}
                                loading={loading}
                                error={error}
                                empty={!loading && !error && tableData.length === 0}
                                emptyMessage="No data available"
                                fileName={tableFilename}
                                data={tableData}
                                dataDownload={true}
                            >
                                <AutoTable data={tableData} tableFn={tableFn}/>
                            </ONEVisual>
                        </>
                    )}
                </>
            )}
        </div>
    )
}

display(<App/>)
```
