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
import {financingQueries, transformTableData, donorNames, indicatorNames, yearOptions, eu27EuiLastYear, psiTransitionYears, donorsWithGni, defaults, names} from "./js/financingQueries.js"
import {customPalette} from "./js/colors.js"
import {columnChart} from "./js/columnChart.js"
import {areaChart} from "./js/areaChart.js"
import {sparkbarTable} from "./js/sparkBarTable.js"
import {APP_TITLE, APP_DESCRIPTION, NAV_ITEMS, CURRENCY_OPTIONS, PRICES_OPTIONS, SCALE} from "./js/config.js"

setCustomColors(customPalette)

const DONOR_OPTIONS = donorNames.map(n => ({label: n, value: n}))

const INDICATOR_OPTIONS = indicatorNames.map(n => ({label: n, value: n}))
```

```jsx
function App() {
    const [donor, setDonor] = React.useState(defaults.donor_name)
    const [indicator, setIndicator] = React.useState(defaults.indicator_name)
    const [currency, setCurrency] = React.useState("usd")
    const [prices, setPrices] = React.useState("constant")
    const [timeRange, setTimeRange] = React.useState([yearOptions.end - 20, yearOptions.end])
    const [unit, setUnit] = React.useState("value")
    const [commitment, setCommitment] = React.useState(false)

    const isTotalODA = indicator === names.total_oda
    const hasGni = donorsWithGni.has(donor)

    React.useEffect(() => {
        if (isTotalODA && unit === "total_pct") setUnit("value")
    }, [isTotalODA])

    React.useEffect(() => {
        if (!hasGni && unit === "gni_pct") setUnit("value")
    }, [hasGni])

    React.useEffect(() => {
        setCommitment(false)
    }, [indicator])

    const unitOptions = React.useMemo(() => [
        {label: getCurrencyLabel(currency, {currencyLong: true, currencyOnly: true}), value: "value"},
        {label: "% of GNI", value: "gni_pct", disabled: !hasGni},
        {label: "% of total ODA", value: "total_pct", disabled: isTotalODA},
    ], [currency, isTotalODA, hasGni])

    const data = React.useMemo(
        () => financingQueries(donor, indicator, currency, prices, timeRange),
        [donor, indicator, currency, prices, timeRange]
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

    const donorName = formatString(donor ?? "")
    const indicatorName = indicator ?? ""
    const currencyLabel = getCurrencyLabel(currency, {currencyOnly: true, currencyLong: true})
    const pricesNote = `${prices}${prices === "constant" ? ` ${yearOptions.base}` : ""}`
    const coreOdaNote = indicator === names.core_oda
        ? "Core ODA (ONE definition): Total ODA excluding in-donor spending."
        : ""
    const eu27Note = donor === names.eu27_eui && timeRange[1] > eu27EuiLastYear
        ? `Shown up to ${eu27EuiLastYear}. Later data do not yet include EU members' contributions to the EU Institutions, which are needed to avoid counting them twice.`
        : ""
    const psiNote = indicator === names.psi
        && psiTransitionYears.some(year => year >= timeRange[0] && year <= timeRange[1])
        ? `In ${psiTransitionYears.join(" and ")}, the OECD's transition to new methods for private sector instruments, the total adds instruments still reported as net flows to those reported as grant equivalents.`
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

    const columnChartFn = React.useCallback(
        (width) => columnChart(absoluteData, currency, "financing", width, {scale: absoluteScale}),
        [absoluteData, currency, absoluteScale]
    )

    const areaChartFn = React.useCallback(
        (width) => areaChart(relativeData, "financing", width, {showIntlCommitment: commitment, GNIShare: isTotalODA}),
        [relativeData, commitment, isTotalODA]
    )

    const tableFn = React.useCallback(
        () => sparkbarTable(tableData, "financing", {currency, scale: absoluteScale, unit}),
        [tableData, currency, absoluteScale, unit]
    )

    const columnFilename = formatString(`${donorName} ${indicatorName}`, {fileMode: true})
    const areaFilename = formatString(`${donorName} ${indicatorName} share`, {fileMode: true})
    const tableFilename = formatString(`${donorName} ${indicatorName} ${unit}`, {fileMode: true})

    const chartNote = [
        `ODA values in ${pricesNote} ${currencyLabel}.`,
        coreOdaNote,
        psiNote,
        eu27Note
    ].filter(Boolean).join(" ")

    const relativeNote = [
        isTotalODA
            ? `ODA values as a share of the GNI of ${donorName}.`
            : `ODA values as a share of total contributions from ${donorName}.`,
        coreOdaNote,
        psiNote,
        eu27Note
    ].filter(Boolean).join(" ")

    const tableNote = React.useMemo(() => {
        const base = unit === "value"
            ? `ODA values in ${pricesNote} ${currencyLabel}.`
            : unit === "gni_pct"
                ? `ODA values as a share of the GNI of ${donorName}.`
                : `ODA values as a share of total contributions from ${donorName}.`
        return [base, coreOdaNote, psiNote, unit !== "total_pct" ? eu27Note : ""].filter(Boolean).join(" ")
    }, [unit, pricesNote, currencyLabel, donorName, coreOdaNote, psiNote, eu27Note])

    return (
        <div className="mx-auto space-y-12 px-4 py-10 sm:px-8 sm:py-16 lg:px-12 lg:py-20">

            <Header 
                appTitle={APP_TITLE}
                appDescription={APP_DESCRIPTION}
                navItems={NAV_ITEMS}
                currentPage="financing"
                descriptionMaxWidth={550}
            />

            <div className="flex flex-col gap-4">
                <h3
                    className="section-header"
                >
                    REFINE YOUR VIEW
                </h3>
                <div className="grid gap-6 md:grid-cols-3 pl-6">
                    <div className="flex flex-col items-stretch gap-6">
                        <DropdownMenu label="Donor" options={DONOR_OPTIONS} value={donor} onChange={setDonor}
                                      search={true}/>
                        <DropdownMenu label="Indicator" options={INDICATOR_OPTIONS} value={indicator}
                                      onChange={setIndicator} search={true}/>
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
                        <RangeInput
                            min={yearOptions.start}
                            max={yearOptions.end}
                            step={1}
                            label="Time range"
                            value={timeRange}
                            onChange={setTimeRange}
                        />
                    </div>
                </div>
            </div>

            <div className="grid gap-10 lg:grid-cols-2">
                <ONEVisual
                    title={`${indicatorName} from ${donorName}`}
                    subtitle={absoluteSubtitle}
                    subtitleIsHTML={Boolean(absoluteSubtitle)}
                    source="OECD DAC1 table."
                    note={chartNote}
                    empty={absoluteData.length === 0}
                    emptyMessage="No data available"
                    fileName={columnFilename}
                    data={absoluteData}
                    imageDownload={true}
                    dataDownload={true}
                >
                    <AutoPlot data={absoluteData} plotFn={columnChartFn}/>
                </ONEVisual>
                <ONEVisual
                    title={`${indicatorName} from ${donorName}`}
                    subtitle={relativeSubtitle}
                    subtitleIsHTML={Boolean(relativeSubtitle)}
                    controls={
                        isTotalODA && (
                            <ToggleSwitchMini
                                label="Show 0.7% target"
                                value={commitment}
                                options={[{label: "On", value: true}, {label: "Off", value: false}]}
                                onChange={setCommitment}
                                hint={"In 1970, the UN set a target for donor countries to give 0.7% of their GNI in ODA. It remains a key benchmark for comparing contributions."}
                            />
                        )
                    }
                    source="OECD DAC1 table."
                    note={relativeNote}
                    empty={relativeData.every(d => d.value == null)}
                    emptyMessage="No data available"
                    fileName={areaFilename}
                    data={relativeData}
                    imageDownload={true}
                    dataDownload={true}
                >
                    <AutoPlot data={relativeData} plotFn={areaChartFn}/>
                </ONEVisual>
            </div>

            <ONEVisual
                title={`${indicatorName} from ${donorName}`}
                subtitle={absoluteSubtitle}
                subtitleIsHTML={Boolean(absoluteSubtitle)}
                controls={
                    <DropdownMenuMini label="Unit" options={unitOptions} value={unit} onChange={setUnit}/>
                }
                source="OECD DAC1 table."
                note={tableNote}
                empty={tableData.length === 0}
                emptyMessage="No data available"
                fileName={tableFilename}
                data={tableData}
                dataDownload={true}
            >
                <AutoTable data={tableData} tableFn={tableFn}/>
            </ONEVisual>
        </div>
    )
}

display(<App/>)
```
